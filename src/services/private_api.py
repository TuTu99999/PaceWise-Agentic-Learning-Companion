"""P-256 ECDH + HKDF-SHA256 + AES-256-GCM envelopes, not a replacement for TLS.

The browser must decrypt its own data. This removes plain payloads/internal IDs
from Network, not from a browser owner's memory/debugger. No symmetric key is
embedded in frontend source, URLs, cookies or localStorage.
"""

import base64
import hashlib
import json
import os
import time
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from src.db import SessionLocal
from src.persistence_models import PrivateRequestNonce

INFO = b"pacewise-private-api-v1"


def encoded(value):
    return base64.b64encode(value).decode()


def decoded(value, size=None):
    raw = base64.b64decode(value, validate=True)
    if size is not None and len(raw) != size:
        raise ValueError("invalid size")
    return raw


@lru_cache(maxsize=4)
def server_key(file):
    path = Path(file)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(pem)
        except FileExistsError:
            pass
    for _ in range(20):
        try:
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
            if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
                raise ValueError("P-256 key required")
            return key
        except ValueError:
            time.sleep(0.05)  # Another replica may still be creating the shared file.
    raise RuntimeError("Private API key unavailable")


def public_config(settings):
    public = (
        server_key(settings.private_api_key_file)
        .public_key()
        .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    return {"version": 1, "publicKey": encoded(public), "required": settings.private_api_required}


def open_envelope(envelope, settings):
    try:
        public = decoded(envelope["publicKey"], 65)
        salt = decoded(envelope["salt"], 32)
        nonce = decoded(envelope["nonce"], 12)
        remote = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
        shared = server_key(settings.private_api_key_file).exchange(ec.ECDH(), remote)
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=INFO).derive(shared)
        plain = AESGCM(key).decrypt(nonce, decoded(envelope["ciphertext"]), INFO + b":request")
        payload = json.loads(plain)
        if abs(time.time() - float(payload["sentAt"]) / 1000) > 300:
            raise ValueError("expired")
    except Exception as exc:
        raise HTTPException(400, "Invalid encrypted request") from exc
    identifier = hashlib.sha256(public + salt + nonce).hexdigest()
    try:
        with SessionLocal() as db:
            db.execute(delete(PrivateRequestNonce).where(PrivateRequestNonce.expires_at < datetime.now(UTC)))
            db.add(PrivateRequestNonce(id=identifier, expires_at=datetime.now(UTC) + timedelta(minutes=11)))
            db.commit()
    except IntegrityError as exc:
        raise HTTPException(409, "Encrypted request already used") from exc
    return payload, key, nonce


def seal_response(payload, key, request_nonce, status):
    nonce = os.urandom(12)
    aad = INFO + b":response:" + request_nonce + str(status).encode()
    ciphertext = AESGCM(key).encrypt(nonce, json.dumps(payload, ensure_ascii=False).encode(), aad)
    return {"version": 1, "nonce": encoded(nonce), "ciphertext": encoded(ciphertext)}
