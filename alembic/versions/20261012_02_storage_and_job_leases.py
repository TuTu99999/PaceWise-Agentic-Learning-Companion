"""S3 metadata and renewable worker leases."""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "20261012_02"
down_revision = "20261012_01"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {item["name"] for item in inspect(op.get_bind()).get_columns(table)}


def _add(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    if name not in {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    for column in (
        sa.Column("object_key", sa.String(1000), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("checksum_sha256_base64", sa.String(64), nullable=True),
        sa.Column("content_type", sa.String(128), nullable=True),
    ):
        _add("course_upload_tickets", column)
    op.execute("UPDATE course_upload_tickets SET object_key = '' WHERE object_key IS NULL")
    op.execute("UPDATE course_upload_tickets SET checksum_sha256 = '' WHERE checksum_sha256 IS NULL")
    op.execute("UPDATE course_upload_tickets SET checksum_sha256_base64 = '' WHERE checksum_sha256_base64 IS NULL")
    op.execute("UPDATE course_upload_tickets SET content_type = 'application/octet-stream' WHERE content_type IS NULL")

    for column in (
        sa.Column("object_key", sa.String(1000), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
    ):
        _add("pacewise_course_materials", column)
    op.execute("UPDATE pacewise_course_materials SET version = 1 WHERE version IS NULL")
    op.execute("UPDATE pacewise_course_materials SET checksum_sha256 = '' WHERE checksum_sha256 IS NULL")
    op.execute("UPDATE pacewise_course_materials SET mime_type = 'application/octet-stream' WHERE mime_type IS NULL")
    op.alter_column("pacewise_course_materials", "file_bytes", existing_type=sa.LargeBinary(), nullable=True)
    _index("ix_pacewise_course_materials_checksum_sha256", "pacewise_course_materials", ["checksum_sha256"])
    _index("uq_pacewise_course_materials_object_key", "pacewise_course_materials", ["object_key"], unique=True)

    _add("pacewise_rag_ingestion_jobs", sa.Column("idempotency_key", sa.String(255), nullable=True))
    for column in (
        sa.Column("lease_owner", sa.String(255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queue_message_id", sa.String(255), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    ):
        _add("pacewise_rag_ingestion_jobs", column)
    op.execute("UPDATE pacewise_rag_ingestion_jobs SET idempotency_key = 'rag:legacy:' || id WHERE idempotency_key IS NULL")
    op.execute("UPDATE pacewise_rag_ingestion_jobs SET failure_reason = '' WHERE failure_reason IS NULL")
    # There is no live lease in the legacy schema. Requeue its in-flight rows
    # once during migration instead of letting every new worker reclaim them.
    op.execute(
        "UPDATE pacewise_rag_ingestion_jobs SET status = 'retry', failure_reason = 'migration_requeue' "
        "WHERE status = 'processing'"
    )
    op.alter_column("pacewise_rag_ingestion_jobs", "idempotency_key", existing_type=sa.String(255), nullable=False)
    _index("uq_pacewise_rag_ingestion_jobs_idempotency_key", "pacewise_rag_ingestion_jobs", ["idempotency_key"], unique=True)
    _index("ix_pacewise_rag_ingestion_jobs_lease_expires_at", "pacewise_rag_ingestion_jobs", ["lease_expires_at"])
    _index("ix_pacewise_rag_ingestion_jobs_queued_at", "pacewise_rag_ingestion_jobs", ["queued_at"])

    for table in ("lms_file_indexes", "pacewise_notification_jobs"):
        for column in (
            sa.Column("idempotency_key", sa.String(255), nullable=True),
            sa.Column("lease_owner", sa.String(255), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failure_reason", sa.String(255), nullable=True),
        ):
            _add(table, column)
        op.execute(f"UPDATE {table} SET idempotency_key = 'legacy:' || id WHERE idempotency_key IS NULL")
        op.execute(f"UPDATE {table} SET failure_reason = '' WHERE failure_reason IS NULL")
        op.alter_column(table, "idempotency_key", existing_type=sa.String(255), nullable=False)
        _index(f"ix_{table}_lease_expires_at", table, ["lease_expires_at"])
        _index(f"ix_{table}_idempotency_key", table, ["idempotency_key"])
    op.execute(
        "UPDATE lms_file_indexes SET status = CASE WHEN chunks_json = '[]' THEN 'extraction_retry' ELSE 'retry' END, "
        "failure_reason = 'migration_requeue' WHERE status IN ('extracting', 'indexing')"
    )
    for column in (
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queue_message_id", sa.String(255), nullable=True),
    ):
        _add("pacewise_notification_jobs", column)
    _index("ix_pacewise_notification_jobs_queued_at", "pacewise_notification_jobs", ["queued_at"])


def downgrade() -> None:
    raise RuntimeError("Lease/storage migration is expand-only; deploy a forward contract migration")
