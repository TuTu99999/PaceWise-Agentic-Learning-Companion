"""Safely adopt a pre-Alembic PaceWise PostgreSQL database.

This is a one-time maintenance command for databases that were created by the
old runtime ``create_all`` path.  It refuses to stamp a revision until the
encrypted backup and the legacy schema have both been verified.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic.config import Config
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import inspect, text

from alembic import command
from src import persistence_models  # noqa: F401
from src.api import course_uploads, google_signup  # noqa: F401
from src.config import get_settings
from src.course_source import models as course_models  # noqa: F401
from src.course_source.db import Base as CourseBase
from src.db import Base, engine
from src.schema import SCHEMA_REVISION
from src.services.customer_crypto import data_key

BASELINE_REVISION = "20261012_01"
BACKUP_HEADER = b"pacewise-db-backup:v1\n"

# These columns belong to the expand-only revision after the baseline and may
# therefore be absent from a legitimate legacy database.
EXPAND_COLUMNS: dict[str, set[str]] = {
    "course_upload_tickets": {
        "object_key",
        "checksum_sha256",
        "checksum_sha256_base64",
        "content_type",
    },
    "pacewise_course_materials": {"object_key", "checksum_sha256", "version", "mime_type"},
    "pacewise_rag_ingestion_jobs": {
        "idempotency_key",
        "lease_owner",
        "lease_expires_at",
        "heartbeat_at",
        "queued_at",
        "queue_message_id",
        "failure_reason",
        "completed_at",
    },
    "lms_file_indexes": {
        "idempotency_key",
        "lease_owner",
        "lease_expires_at",
        "heartbeat_at",
        "failure_reason",
    },
    "pacewise_notification_jobs": {
        "idempotency_key",
        "lease_owner",
        "lease_expires_at",
        "heartbeat_at",
        "failure_reason",
        "queued_at",
        "queue_message_id",
    },
}


def _verify_backup(path: Path) -> int:
    payload = path.read_bytes()
    if not payload.startswith(BACKUP_HEADER) or len(payload) <= len(BACKUP_HEADER) + 12:
        raise SystemExit("Backup is not a PaceWise encrypted database backup")
    settings = get_settings()
    key = data_key(settings.customer_data_key_file, settings.app_env == "production")[:32]
    nonce_start = len(BACKUP_HEADER)
    nonce = payload[nonce_start : nonce_start + 12]
    encrypted = payload[nonce_start + 12 :]
    try:
        dump = AESGCM(key).decrypt(nonce, encrypted, BACKUP_HEADER)
    except Exception as exc:
        raise SystemExit("Encrypted backup could not be authenticated") from exc
    if len(dump) < 1000 or b"PostgreSQL database dump" not in dump[:1000]:
        raise SystemExit("Decrypted backup is not a valid PostgreSQL SQL dump")
    return len(dump)


def _validate_metadata(metadata, schema: str) -> tuple[int, int]:
    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names(schema=schema))
    expected_tables = {table.name for table in metadata.sorted_tables}
    missing_tables = sorted(expected_tables - actual_tables)
    if missing_tables:
        raise SystemExit(f"Legacy database is missing {schema} tables: {', '.join(missing_tables)}")

    checked_columns = 0
    for table in metadata.sorted_tables:
        actual_columns = {column["name"] for column in inspector.get_columns(table.name, schema=schema)}
        expected_columns = {column.name for column in table.columns}
        allowed_missing = EXPAND_COLUMNS.get(table.name, set()) if schema == "public" else set()
        missing_columns = sorted((expected_columns - actual_columns) - allowed_missing)
        if missing_columns:
            raise SystemExit(
                f"Legacy table {schema}.{table.name} is missing columns: {', '.join(missing_columns)}"
            )

        actual_pk = set(inspector.get_pk_constraint(table.name, schema=schema).get("constrained_columns") or [])
        expected_pk = {column.name for column in table.primary_key.columns}
        if actual_pk != expected_pk:
            raise SystemExit(
                f"Primary key mismatch for {schema}.{table.name}: "
                f"found {sorted(actual_pk)}, expected {sorted(expected_pk)}"
            )
        checked_columns += len(expected_columns - allowed_missing)
    return len(expected_tables), checked_columns


def _assert_unversioned() -> None:
    inspector = inspect(engine)
    if inspector.has_table("alembic_version", schema="public"):
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        raise SystemExit(f"Database is already versioned at {revision!r}; adoption is not applicable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--maintenance-confirmed", action="store_true")
    args = parser.parse_args()

    if engine.dialect.name != "postgresql":
        raise SystemExit("Legacy adoption only supports PostgreSQL")
    if args.apply and not args.maintenance_confirmed:
        raise SystemExit("--apply requires --maintenance-confirmed")

    dump_bytes = _verify_backup(args.backup.resolve())
    _assert_unversioned()
    public_tables, public_columns = _validate_metadata(Base.metadata, "public")
    source_tables, source_columns = _validate_metadata(CourseBase.metadata, "course_source")
    print(
        "Legacy schema verified: "
        f"{public_tables} public tables/{public_columns} columns, "
        f"{source_tables} course_source tables/{source_columns} columns, "
        f"backup={dump_bytes} bytes."
    )

    if not args.apply:
        print("Dry run only. Re-run with --apply --maintenance-confirmed to adopt and migrate.")
        return 0

    command.stamp(Config("alembic.ini"), BASELINE_REVISION)
    command.upgrade(Config("alembic.ini"), "head")
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != SCHEMA_REVISION:
        raise SystemExit(f"Migration ended at {revision!r}, expected {SCHEMA_REVISION!r}")
    print(f"Legacy database adopted and migrated to {revision}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
