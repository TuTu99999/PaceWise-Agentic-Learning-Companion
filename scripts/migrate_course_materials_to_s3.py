"""Idempotently copy legacy DB/local course files into private KMS-encrypted S3.

The default is a dry run. Binary deletion is a separate explicit phase and is
performed only after the object has been checked again. This makes the script
safe to resume after interruption.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import mimetypes
from pathlib import Path

from sqlalchemy import select

from src.config import get_settings
from src.course_source.db import SessionLocal as CourseSession
from src.course_source.models import Resource, ResourceVersion
from src.db import SessionLocal
from src.persistence_models import CourseMaterial
from src.services.course_object_store import source_url, upload_bytes, upload_path, verify_object


def checksum(path: Path) -> tuple[str, str]:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    raw = digest.digest()
    return digest.hexdigest(), base64.b64encode(raw).decode()


def migrate_database_materials(*, apply: bool, purge_bytes: bool) -> tuple[int, int]:
    settings = get_settings()
    copied = purged = 0
    with SessionLocal() as db:
        ids = list(db.scalars(select(CourseMaterial.id).order_by(CourseMaterial.id)))
    for material_id in ids:
        with SessionLocal() as db:
            material = db.get(CourseMaterial, material_id)
            if not material:
                continue
            data = material.file_bytes
            if not material.object_key:
                if data is None:
                    raise RuntimeError(f"{material.id}: missing both DB bytes and object key")
                raw_digest = hashlib.sha256(data).digest()
                digest = raw_digest.hex()
                digest_b64 = base64.b64encode(raw_digest).decode()
                safe_name = Path(material.file_name).name
                key = f"{settings.institution_id}/courses/{material.course_id}/legacy/{digest}-{safe_name}"
                if apply:
                    upload_bytes(
                        settings,
                        data,
                        key,
                        material.mime_type or "application/octet-stream",
                        digest_b64,
                    )
                    verify_object(
                        settings,
                        key,
                        expected_size=len(data),
                        expected_checksum_sha256_base64=digest_b64,
                    )
                    material.object_key = key
                    material.checksum_sha256 = digest
                    material.mime_type = material.mime_type or mimetypes.guess_type(material.file_name)[0] or "application/octet-stream"
                    db.commit()
                copied += 1
            if purge_bytes and material.file_bytes is not None:
                if not material.object_key:
                    raise RuntimeError(f"{material.id}: refusing to purge before object migration")
                data = material.file_bytes
                digest = hashlib.sha256(data).hexdigest()
                if material.checksum_sha256 and material.checksum_sha256 != digest:
                    raise RuntimeError(f"{material.id}: legacy bytes no longer match stored checksum")
                checksum_b64 = base64.b64encode(bytes.fromhex(digest)).decode()
                verify_object(
                    settings,
                    material.object_key,
                    expected_size=len(data),
                    expected_checksum_sha256_base64=checksum_b64,
                )
                material.checksum_sha256 = digest
                material.file_size = len(data)
                material.file_bytes = None
                db.commit()
                purged += 1
    return copied, purged


def _legacy_path(source: str, upload_root: Path, mock_root: Path) -> Path | None:
    if source.startswith("/api/files/"):
        root, name = upload_root, source.removeprefix("/api/files/")
    elif source.startswith("/static/mock-files/"):
        root, name = mock_root, source.removeprefix("/static/mock-files/")
    else:
        return None
    root = root.resolve()
    path = (root / name).resolve()
    if Path(name).name != name or path.parent != root:
        raise RuntimeError(f"unsafe legacy resource path: {source}")
    return path


def migrate_course_resources(*, apply: bool, delete_local: bool) -> tuple[int, int]:
    settings = get_settings()
    upload_root = Path(settings.course_upload_dir)
    mock_root = Path(settings.course_mock_file_dir)
    copied = deleted = 0
    with CourseSession() as db:
        resource_ids = list(db.scalars(select(Resource.id).order_by(Resource.id)))
    for resource_id in resource_ids:
        with CourseSession() as db:
            resource = db.get(Resource, resource_id)
            if not resource:
                continue
            path = _legacy_path(resource.source_url, upload_root, mock_root)
            if path is None:
                continue
            if not path.is_file():
                raise RuntimeError(f"{resource.id}: local source does not exist: {path}")
            digest, digest_b64 = checksum(path)
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            key = f"{settings.institution_id}/courses/{resource.course_id}/migrated/{digest}{path.suffix.lower()}"
            if apply:
                upload_path(settings, path, key, content_type, digest_b64)
                verify_object(settings, key, expected_size=path.stat().st_size, expected_checksum_sha256_base64=digest_b64)
                old_source = resource.source_url
                new_source = source_url(key)
                resource.source_url = new_source
                for version in db.scalars(
                    select(ResourceVersion).where(ResourceVersion.resource_id == resource.id)
                ):
                    if version.source_url == old_source:
                        version.source_url = new_source
                db.commit()
            copied += 1
            if delete_local:
                if not apply:
                    raise RuntimeError("--delete-local requires --apply")
                with CourseSession() as verify_db:
                    stored = verify_db.get(Resource, resource_id)
                    if not stored or stored.source_url != source_url(key):
                        raise RuntimeError(f"{resource_id}: metadata verification failed")
                verify_object(settings, key, expected_size=path.stat().st_size, expected_checksum_sha256_base64=digest_b64)
                path.unlink()
                deleted += 1
    return copied, deleted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="copy and update metadata; default is dry-run")
    parser.add_argument("--purge-db-bytes", action="store_true", help="remove verified legacy blobs from PostgreSQL")
    parser.add_argument("--delete-local", action="store_true", help="delete verified local files after metadata commit")
    args = parser.parse_args()
    settings = get_settings()
    if settings.course_storage_backend != "s3":
        raise SystemExit("COURSE_STORAGE_BACKEND=s3 is required")
    db_copied, db_purged = migrate_database_materials(apply=args.apply, purge_bytes=args.purge_db_bytes)
    file_copied, file_deleted = migrate_course_resources(apply=args.apply, delete_local=args.delete_local)
    mode = "applied" if args.apply else "dry-run"
    print(
        f"S3 migration {mode}: db={db_copied}, db_bytes_purged={db_purged}, "
        f"local={file_copied}, local_deleted={file_deleted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
