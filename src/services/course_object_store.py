"""Bounded access to the production course-material object store."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path, PurePosixPath

from src.config import Settings

OBJECT_SCHEME = "pacewise-object://"


def _client(settings: Settings):
    import boto3
    from botocore.config import Config

    timeout = settings.readiness_timeout_seconds
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        config=Config(
            connect_timeout=timeout,
            read_timeout=max(timeout, 10),
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


def object_key(source_url: str) -> str:
    if not source_url.startswith(OBJECT_SCHEME):
        raise ValueError("not a PaceWise object URL")
    key = source_url.removeprefix(OBJECT_SCHEME)
    path = PurePosixPath(key)
    if not key or path.is_absolute() or ".." in path.parts or "\\" in key:
        raise ValueError("invalid object key")
    return key


def source_url(key: str) -> str:
    # Validate before persisting the opaque internal reference.
    object_key(OBJECT_SCHEME + key)
    return OBJECT_SCHEME + key


def _path_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode()


def upload_path(
    settings: Settings,
    path: Path,
    key: str,
    content_type: str,
    checksum_sha256_base64: str | None = None,
) -> None:
    _client(settings).upload_file(
        str(path),
        settings.s3_course_materials_bucket,
        key,
        ExtraArgs={
            "ContentType": content_type,
            "ChecksumSHA256": checksum_sha256_base64 or _path_checksum(path),
            "ServerSideEncryption": "aws:kms",
            "SSEKMSKeyId": settings.s3_kms_key_id,
        },
    )


def upload_bytes(
    settings: Settings,
    data: bytes,
    key: str,
    content_type: str,
    checksum_sha256_base64: str | None = None,
) -> None:
    checksum = checksum_sha256_base64 or base64.b64encode(hashlib.sha256(data).digest()).decode()
    _client(settings).put_object(
        Bucket=settings.s3_course_materials_bucket,
        Key=key,
        Body=data,
        ContentLength=len(data),
        ContentType=content_type,
        ChecksumSHA256=checksum,
        ServerSideEncryption="aws:kms",
        SSEKMSKeyId=settings.s3_kms_key_id,
    )


def presigned_put(
    settings: Settings,
    key: str,
    content_type: str,
    checksum_sha256_base64: str,
    *,
    expires_seconds: int = 900,
) -> dict:
    params = {
        "Bucket": settings.s3_course_materials_bucket,
        "Key": key,
        "ContentType": content_type,
        "ChecksumSHA256": checksum_sha256_base64,
        "ServerSideEncryption": "aws:kms",
        "SSEKMSKeyId": settings.s3_kms_key_id,
    }
    return {
        "url": _client(settings).generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=max(60, min(900, expires_seconds)),
            HttpMethod="PUT",
        ),
        "headers": {
            "Content-Type": content_type,
            "x-amz-checksum-sha256": checksum_sha256_base64,
            "x-amz-server-side-encryption": "aws:kms",
            "x-amz-server-side-encryption-aws-kms-key-id": settings.s3_kms_key_id,
        },
    }


def presigned_get(settings: Settings, source: str, filename: str, *, inline: bool = False) -> str:
    disposition = "inline" if inline else "attachment"
    safe_name = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")[:255]
    return _client(settings).generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.s3_course_materials_bucket,
            "Key": object_key(source),
            "ResponseContentDisposition": f'{disposition}; filename="{safe_name}"',
        },
        ExpiresIn=300,
        HttpMethod="GET",
    )


def verify_object(
    settings: Settings,
    key: str,
    *,
    expected_size: int,
    expected_checksum_sha256_base64: str,
) -> None:
    result = _client(settings).head_object(
        Bucket=settings.s3_course_materials_bucket,
        Key=key,
        ChecksumMode="ENABLED",
    )
    if int(result.get("ContentLength") or -1) != expected_size:
        raise ValueError("uploaded object size mismatch")
    checksum = str(result.get("ChecksumSHA256") or "")
    if expected_checksum_sha256_base64 and checksum != expected_checksum_sha256_base64:
        raise ValueError("uploaded object checksum mismatch")
    if result.get("ServerSideEncryption") != "aws:kms":
        raise ValueError("uploaded object is not protected by KMS")


def download_to_path(settings: Settings, key: str, path: Path) -> None:
    _client(settings).download_file(settings.s3_course_materials_bucket, key, str(path))


def delete_object(settings: Settings, key: str) -> None:
    _client(settings).delete_object(Bucket=settings.s3_course_materials_bucket, Key=key)


def download_bytes(settings: Settings, source: str, max_bytes: int) -> bytes:
    response = _client(settings).get_object(
        Bucket=settings.s3_course_materials_bucket,
        Key=object_key(source),
    )
    declared = int(response.get("ContentLength") or 0)
    if declared > max_bytes:
        response["Body"].close()
        raise ValueError("object exceeds configured size limit")
    chunks: list[bytes] = []
    size = 0
    try:
        for chunk in response["Body"].iter_chunks(chunk_size=1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("object exceeds configured size limit")
            chunks.append(chunk)
    finally:
        response["Body"].close()
    return b"".join(chunks)
