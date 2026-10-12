import base64
import hashlib
from io import BytesIO
from types import SimpleNamespace

import pytest

from src.config import Settings
from src.services import course_object_store


class Body:
    def __init__(self, data: bytes):
        self._data = data
        self.closed = False

    def iter_chunks(self, chunk_size: int):
        stream = BytesIO(self._data)
        while chunk := stream.read(chunk_size):
            yield chunk

    def close(self):
        self.closed = True


def test_object_reference_rejects_path_escape():
    with pytest.raises(ValueError):
        course_object_store.object_key("pacewise-object://course/../secret.pdf")


def test_download_is_bounded_and_closes_body(monkeypatch):
    body = Body(b"abcdef")
    client = SimpleNamespace(
        get_object=lambda **_: {"ContentLength": 6, "Body": body},
    )
    monkeypatch.setattr(course_object_store, "_client", lambda _: client)
    settings = Settings(_env_file=None, app_env="test", s3_course_materials_bucket="materials")

    assert course_object_store.download_bytes(settings, "pacewise-object://course/file.pdf", 6) == b"abcdef"
    assert body.closed


def test_declared_oversize_is_rejected_before_streaming(monkeypatch):
    body = Body(b"abcdef")
    client = SimpleNamespace(
        get_object=lambda **_: {"ContentLength": 6, "Body": body},
    )
    monkeypatch.setattr(course_object_store, "_client", lambda _: client)
    settings = Settings(_env_file=None, app_env="test", s3_course_materials_bucket="materials")

    with pytest.raises(ValueError, match="size limit"):
        course_object_store.download_bytes(settings, "pacewise-object://course/file.pdf", 5)

    assert body.closed


def test_programmatic_upload_records_sha256_and_kms(monkeypatch):
    captured = {}
    client = SimpleNamespace(put_object=lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(course_object_store, "_client", lambda _: client)
    settings = Settings(
        _env_file=None,
        app_env="test",
        s3_course_materials_bucket="materials",
        s3_kms_key_id="alias/materials",
    )
    data = b"course material"

    course_object_store.upload_bytes(settings, data, "course/file.pdf", "application/pdf")

    assert captured["ChecksumSHA256"] == base64.b64encode(hashlib.sha256(data).digest()).decode()
    assert captured["ServerSideEncryption"] == "aws:kms"
    assert captured["SSEKMSKeyId"] == "alias/materials"


def test_verification_requires_expected_sha256_to_be_present(monkeypatch):
    client = SimpleNamespace(
        head_object=lambda **_: {
            "ContentLength": 10,
            "ServerSideEncryption": "aws:kms",
        }
    )
    monkeypatch.setattr(course_object_store, "_client", lambda _: client)
    settings = Settings(_env_file=None, app_env="test", s3_course_materials_bucket="materials")

    with pytest.raises(ValueError, match="checksum"):
        course_object_store.verify_object(
            settings,
            "course/file.pdf",
            expected_size=10,
            expected_checksum_sha256_base64="ZmFrZQ==",
        )
