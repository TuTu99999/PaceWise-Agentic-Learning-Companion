import base64
import json
from types import SimpleNamespace

import http_ece
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from src.config import Settings
from src.services.web_push import send_push


def test_real_library_encrypts_and_signs_push_without_contacting_provider(monkeypatch, tmp_path):
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    auth = b"0123456789abcdef"

    def encode(value):
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    subscription = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test",
        "keys": {"p256dh": encode(public), "auth": encode(auth)},
    }
    captured = {}

    def transport(_url, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(status_code=201, text="", headers={})

    monkeypatch.setattr("requests.post", transport)
    settings = Settings(_env_file=None, webpush_private_key_file=str(tmp_path / "private.pem"))
    payload = {"title": "PaceWise", "href": "/reflect?activity=session:s1"}
    send_push(subscription, payload, settings, 120)
    assert b"PaceWise" not in captured["data"]
    decoded = http_ece.decrypt(captured["data"], private_key=private, auth_secret=auth, version="aes128gcm")
    assert json.loads(decoded) == payload
    assert captured["headers"]["authorization"].startswith("vapid ")
