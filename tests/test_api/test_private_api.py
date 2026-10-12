import json
import os
import time
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.services.private_api import INFO, decoded, encoded


def packet(public, path, *, method="GET", body=None, sent_at=None):
    private = ec.generate_private_key(ec.SECP256R1())
    remote = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decoded(public))
    salt, nonce = os.urandom(32), os.urandom(12)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=INFO).derive(private.exchange(ec.ECDH(), remote))
    plain = json.dumps(
        {
            "path": path,
            "method": method,
            "body": json.dumps(body) if body is not None else None,
            "sentAt": sent_at if sent_at is not None else time.time() * 1000,
        }
    ).encode()
    public = private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return (
        {
            "publicKey": encoded(public),
            "salt": encoded(salt),
            "nonce": encoded(nonce),
            "ciphertext": encoded(AESGCM(key).encrypt(nonce, plain, INFO + b":request")),
        },
        key,
        nonce,
    )


def response_body(result, key, nonce):
    output = result.json()
    plain = AESGCM(key).decrypt(
        decoded(output["nonce"]),
        decoded(output["ciphertext"]),
        INFO + b":response:" + nonce + str(result.status_code).encode(),
    )
    return json.loads(plain)["body"]


@pytest.mark.asyncio
async def test_opaque_pdf_link_is_bound_to_current_session(client, private_settings, monkeypatch):
    import httpx

    from src.api.private_api import opaque_links
    from src.db import SessionLocal
    from src.security import decode_session, issue_session

    claims = {"sub": "42", "course_id": 7, "role": "student"}
    with SessionLocal() as db:
        cookie, _ = issue_session(db, claims, private_settings, [7])
        session = decode_session(cookie, private_settings, db)
    link = opaque_links("/api/v1/lms-files/7/123/download", session, private_settings)
    assert "/7/123/" not in link and link.startswith("/api/v1/private/files/")
    monkeypatch.setattr(
        "src.api.private_api._internal",
        AsyncMock(return_value=httpx.Response(200, content=b"%PDF-test", headers={"Content-Type": "application/pdf"})),
    )
    client.cookies.set("pacewise_session", cookie)
    assert (await client.get(link)).content == b"%PDF-test"
    with SessionLocal() as db:
        other, _ = issue_session(db, {**claims, "sub": "99"}, private_settings, [7])
    client.cookies.set("pacewise_session", other)
    assert (await client.get(link)).status_code == 403


@pytest.fixture
def private_settings(auth_settings, monkeypatch, tmp_path):
    auth_settings.private_api_key_file = str(tmp_path / "p256.pem")
    auth_settings.private_api_required = True
    monkeypatch.setattr("src.middleware.get_settings", lambda: auth_settings)
    return auth_settings


@pytest.mark.asyncio
async def test_encrypted_login_me_csrf_logout_and_no_plain_identity(client, monkeypatch, private_settings):
    claims = {
        "iss": "canvas-lms-simulator",
        "aud": "pacewise",
        "sub": "42",
        "course_id": 7,
        "role": "student",
        "name": "PRIVATE_NAME",
        "email": "private@example.edu",
    }
    monkeypatch.setattr("src.services.lms_client.LMSClient.login_and_create_launch", AsyncMock(return_value=claims))
    monkeypatch.setattr("src.services.lms_client.LMSClient.service_get", AsyncMock(return_value=[{"id": 7}]))
    monkeypatch.setattr("src.services.lms_client.LMSClient.service_post", AsyncMock(return_value={}))
    public = (await client.get("/api/v1/private/config")).json()["publicKey"]
    assert (await client.get("/api/v1/auth/me")).status_code == 426
    request, key, nonce = packet(
        public,
        "/api/v1/auth/lms-login",
        method="POST",
        body={"email": "private@example.edu", "password": "PRIVATE_PASSWORD"},
    )
    assert "PRIVATE_PASSWORD" not in json.dumps(request)
    result = await client.post("/api/v1/private/dispatch", json=request)
    assert result.status_code == 200
    assert (
        "PRIVATE_NAME" not in result.text
        and "private@example.edu" not in result.text
        and "courseIds" not in result.text
    )
    assert response_body(result, key, nonce)["user"]["id"] == "42"
    denied_packet, denied_key, denied_nonce = packet(
        public, "/api/v1/auth/course", method="POST", body={"courseId": 999}
    )
    denied = await client.post(
        "/api/v1/private/dispatch", json=denied_packet, headers={"X-CSRF-Token": client.cookies["pacewise_csrf"]}
    )
    assert denied.status_code == 403 and "outside" in response_body(denied, denied_key, denied_nonce)["detail"].lower()
    request, key, nonce = packet(public, "/api/v1/auth/logout", method="POST")
    failed = await client.post("/api/v1/private/dispatch", json=request)
    assert failed.status_code == 403 and "CSRF" in response_body(failed, key, nonce)["detail"]
    request, key, nonce = packet(public, "/api/v1/auth/logout", method="POST")
    result = await client.post(
        "/api/v1/private/dispatch", json=request, headers={"X-CSRF-Token": client.cookies["pacewise_csrf"]}
    )
    assert result.status_code == 200 and response_body(result, key, nonce)["ok"]
    request, key, nonce = packet(public, "/api/v1/auth/me")
    result = await client.post("/api/v1/private/dispatch", json=request)
    assert result.status_code == 401 and "user" not in response_body(result, key, nonce)


@pytest.mark.asyncio
async def test_private_api_rejects_replay_tampering_expiry_and_external_target(client, private_settings):
    public = (await client.get("/api/v1/private/config")).json()["publicKey"]
    message, key, nonce = packet(public, "/api/v1/auth/me")
    assert (await client.post("/api/v1/private/dispatch", json=message)).status_code == 401
    assert (await client.post("/api/v1/private/dispatch", json=message)).status_code == 409
    message["ciphertext"] = encoded(b"invalid-tag")
    assert (await client.post("/api/v1/private/dispatch", json=message)).status_code == 400
    message, _, _ = packet(public, "/api/v1/auth/me", sent_at=0)
    assert (await client.post("/api/v1/private/dispatch", json=message)).status_code == 400
    for path in ["https://evil.test/steal", "/api/v1/private/dispatch", "/api/v1/../health"]:
        message, key, nonce = packet(public, path)
        result = await client.post("/api/v1/private/dispatch", json=message)
        assert result.status_code == 400 and "Invalid" in response_body(result, key, nonce)["detail"]


@pytest.mark.asyncio
async def test_tls_chat_stream_bypasses_whole_response_envelope_but_still_requires_auth(client, private_settings):
    response = await client.post("/api/v1/chat/stream", json={"workflow": "qa", "message": "xin chào"})
    assert response.status_code in {401, 403}
    assert response.status_code != 426
