"""HTTP smoke client for encrypted transport; never print keys or learner data."""

import base64
import json
import os
import time

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

INFO = b"pacewise-private-api-v1"


def decoded(value):
    return base64.b64decode(value, validate=True)


def encoded(value):
    return base64.b64encode(value).decode()


class PrivateClient(httpx.Client):
    _server_public = None

    def request(self, method, url, **kwargs):
        if not str(url).startswith("/api/v1/") or str(url).startswith("/api/v1/private/"):
            return super().request(method, url, **kwargs)
        if self._server_public is None:
            config = super().request("GET", "/api/v1/private/config")
            config.raise_for_status()
            self._server_public = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256R1(), decoded(config.json()["publicKey"])
            )
        private = ec.generate_private_key(ec.SECP256R1())
        salt, nonce = os.urandom(32), os.urandom(12)
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=INFO).derive(
            private.exchange(ec.ECDH(), self._server_public)
        )
        body = kwargs.pop("json", None)
        target = str(url)
        params = kwargs.pop("params", None)
        if params:
            target += "?" + str(httpx.QueryParams(params))
        plain = json.dumps(
            {
                "method": method.upper(),
                "path": target,
                "body": json.dumps(body) if body is not None else None,
                "sentAt": time.time() * 1000,
            }
        ).encode()
        public = private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        envelope = {
            "publicKey": encoded(public),
            "salt": encoded(salt),
            "nonce": encoded(nonce),
            "ciphertext": encoded(AESGCM(key).encrypt(nonce, plain, INFO + b":request")),
        }
        response = super().request("POST", "/api/v1/private/dispatch", json=envelope, **kwargs)
        data = response.json()
        if "ciphertext" not in data:
            response.raise_for_status()
            raise RuntimeError("Unencrypted response")
        plain = AESGCM(key).decrypt(
            decoded(data["nonce"]),
            decoded(data["ciphertext"]),
            INFO + b":response:" + nonce + str(response.status_code).encode(),
        )
        result = json.loads(plain)
        headers = result.get("headers", {})
        if result["type"] == "json":
            return httpx.Response(response.status_code, json=result["body"], headers=headers, request=response.request)
        return httpx.Response(
            response.status_code, content=decoded(result["body"]), headers=headers, request=response.request
        )
