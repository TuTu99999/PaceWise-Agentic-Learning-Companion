"""Encrypted JSON RPC to existing authorized routes, plus opaque file URLs."""

import asyncio
import base64
import json
import os
import re
import time
from urllib.parse import unquote, urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from src.config import Settings, get_settings
from src.security import SessionContext, get_current_session
from src.services.private_api import INFO, encoded, open_envelope, public_config, seal_response, server_key

router = APIRouter(prefix="/private", tags=["Private API"])
DOWNLOAD = re.compile(r"^/api/v1/(?:lms-files/[^/]+/[^/]+/download|materials/[^/]+/download)$")


class EncryptedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    public_key: str = Field(alias="publicKey", max_length=100)
    salt: str = Field(max_length=50)
    nonce: str = Field(max_length=30)
    ciphertext: str = Field(max_length=12_000_000)


def _path(value):
    if not isinstance(value, str) or len(value) > 8192:
        raise HTTPException(400, "Invalid private API target")
    parts = urlsplit(value)
    plain = unquote(parts.path)
    if (
        parts.scheme
        or parts.netloc
        or parts.fragment
        or not plain.startswith("/api/v1/")
        or plain.startswith("/api/v1/private")
        or ".." in plain
        or "\\" in plain
        or plain.endswith("/stream")
        or plain.endswith("/callback")
    ):
        raise HTTPException(400, "Invalid private API target")
    return value


def _link_cipher(settings):
    raw = server_key(settings.private_api_key_file).private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return AESGCM(HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=INFO + b":file-link").derive(raw))


def opaque_links(value, session, settings):
    if isinstance(value, dict):
        return {key: opaque_links(item, session, settings) for key, item in value.items()}
    if isinstance(value, list):
        return [opaque_links(item, session, settings) for item in value]
    if session and isinstance(value, str) and DOWNLOAD.fullmatch(value):
        nonce = os.urandom(12)
        body = json.dumps({"path": value, "sid": session.sid, "exp": session.exp}).encode()
        token = base64.urlsafe_b64encode(nonce + _link_cipher(settings).encrypt(nonce, body, INFO)).decode().rstrip("=")
        return f"/api/v1/private/files/{token}"
    return value


async def _internal(request, method, path, body=None):
    async def trusted_app(scope, receive, send):
        scope["pacewise.private_dispatch"] = True
        scope["client"] = request.scope.get("client")
        await request.app(scope, receive, send)

    headers = {key: request.headers[key] for key in ("cookie", "x-csrf-token") if key in request.headers}
    headers["x-forwarded-proto"] = request.headers.get("x-forwarded-proto", request.url.scheme)
    # Do not forward user-supplied identity/role headers or arbitrary external hosts.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=trusted_app), base_url="http://private-api"
    ) as client:
        return await client.request(method, path, content=body, headers={**headers, "content-type": "application/json"})


@router.get("/config")
async def configuration(settings: Settings = Depends(get_settings)):
    return await asyncio.to_thread(public_config, settings)


@router.post("/dispatch")
async def dispatch(envelope: EncryptedRequest, request: Request, settings: Settings = Depends(get_settings)):
    payload, key, nonce = await asyncio.to_thread(open_envelope, envelope.model_dump(by_alias=True), settings)
    try:
        path = _path(payload.get("path"))
        method = payload.get("method")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise HTTPException(400, "Invalid private API method")
        body = payload.get("body")
        if body is not None and not isinstance(body, str):
            raise HTTPException(400, "Invalid private API body")
        result = await _internal(request, method, path, body)
        status = result.status_code
        content_type = result.headers.get("content-type", "")
        if "application/json" in content_type:
            session = None
            # Explicit DB scope; decode only to scope opaque links. Routes still authorize independently.
            if request.cookies.get(settings.pacewise_session_cookie):
                from src.db import SessionLocal
                from src.security import decode_session

                with SessionLocal() as db:
                    try:
                        session = decode_session(request.cookies[settings.pacewise_session_cookie], settings, db)
                    except HTTPException:
                        session = None
            output = {"type": "json", "body": opaque_links(result.json(), session, settings)}
        else:
            output = {"type": "binary", "body": encoded(result.content), "contentType": content_type}
        output["headers"] = {
            k: result.headers[k]
            for k in ("content-disposition", "retry-after", "x-request-id", "x-pacewise-partial-created")
            if k in result.headers
        }
    except HTTPException as exc:
        status = exc.status_code
        output = {"type": "json", "body": {"detail": exc.detail}, "headers": exc.headers or {}}
        result = None
    response = Response(
        json.dumps(seal_response(output, key, nonce, status)), status_code=status, media_type="application/json"
    )
    if result is not None:
        for name, value in result.headers.multi_items():
            if name.lower() in {"set-cookie", "retry-after"}:
                response.headers.append(name, value)
    return response


@router.get("/files/{token}", include_in_schema=False)
async def file_proxy(
    token: str,
    request: Request,
    session: SessionContext = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
):
    try:
        if len(token) > 2048:
            raise ValueError("size")
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        data = json.loads(_link_cipher(settings).decrypt(raw[:12], raw[12:], INFO))
        if data["sid"] != session.sid or data["exp"] <= time.time() or not DOWNLOAD.fullmatch(data["path"]):
            raise ValueError("scope")
    except Exception as exc:
        raise HTTPException(403, "Invalid or expired file reference") from exc
    result = await _internal(request, "GET", data["path"])
    headers = {key: result.headers[key] for key in ("content-type", "content-disposition") if key in result.headers}
    return Response(result.content, status_code=result.status_code, headers=headers)
