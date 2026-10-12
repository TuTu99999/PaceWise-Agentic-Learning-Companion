"""LMS-owned file lifecycle: durable derived text, no duplicate binary storage."""

from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import threading
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from src.config import Settings
from src.db import SessionLocal
from src.persistence_models import LmsFileIndex
from src.services.document_extraction import DocumentLimitError, bounded_extract
from src.services.document_roles import filter_student_chunks
from src.services.file_indexing import bounded_index
from src.services.lms_client import LMSClient

SUPPORTED = {".pdf", ".docx", ".pptx", ".txt", ".md"}


def validate_document(data: bytes, name: str, max_pages: int = 500) -> None:
    """Do not turn corrupt office binaries or oversized archives into RAG text."""
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        if not data.lstrip().startswith(b"%PDF-"):
            raise ValueError("Invalid PDF signature")
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted or len(reader.pages) > max_pages:
            raise ValueError("Encrypted PDF or page limit exceeded")
    elif suffix in {".docx", ".pptx"}:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(entry.file_size for entry in entries) > 40 * 1024 * 1024:
                raise ValueError("Office archive expansion limit exceeded")
            required = "word/document.xml" if suffix == ".docx" else "ppt/presentation.xml"
            if required not in archive.namelist():
                raise ValueError("Invalid Office document structure")


def file_version(item: dict[str, Any]) -> str:
    """Content + version + citation identity. ACL is checked live, never trusted from this hash."""
    latest = item.get("latest_version") or {}
    return hashlib.sha256(
        json.dumps(
            [latest.get("checksum_sha256"), latest.get("version"), item.get("title"), item.get("source_url")],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def file_name(item: dict[str, Any]) -> str:
    # Keep a readable title, but infer the actual format from the LMS-owned object.
    title = Path(str(item.get("title") or "material")).name
    suffix = Path(str(item.get("source_url") or "")).suffix.lower()
    return title if Path(title).suffix.lower() == suffix else f"{title}{suffix}"


def file_url(course_id: int, file_id: int) -> str:
    return f"/api/v1/lms-files/{course_id}/{file_id}/download"


async def sync_course_files(client: LMSClient, settings: Settings, course_id: int, course_code: str) -> None:
    manifest = await client.service_get(f"/api/pacewise/v1/courses/{course_id}/files")
    live_ids = {int(item["id"]) for item in manifest}
    # A successfully fetched empty manifest is authoritative. A failed fetch never deletes data.
    with SessionLocal() as db:
        for row in db.scalars(
            select(LmsFileIndex).where(
                LmsFileIndex.institution_id == settings.institution_id, LmsFileIndex.course_id == course_id
            )
        ).all():
            if row.file_id not in live_ids:
                row.status, row.chunks_json = "delete_pending", "[]"
        db.commit()

    for item in manifest:
        item = dict(item, course_code=course_code)
        identifier = f"{settings.institution_id}:{course_id}:{int(item['id'])}"
        version = file_version(item)
        scopes = item.get("access_scope") or []
        revoked = bool(scopes) and not any(scope.get("permission", "read") == "read" for scope in scopes)
        supported = (
            str(item.get("source_url") or "").startswith(("/api/files/", "/static/mock-files/", "pacewise-object://"))
            and Path(file_name(item)).suffix.lower() in SUPPORTED
            and str(item.get("kind") or "") not in {"teacher_solution", "teacher_assignment_package"}
        )
        with SessionLocal() as db:
            row = db.get(LmsFileIndex, identifier)
            # A failed unchanged file stays failed until an explicit retry. Sync
            # must not reset the attempt budget or repeatedly embed old bytes.
            if row and row.resource_version == version and not revoked and row.status not in {"delete_pending", "unavailable"}:
                continue
            row = row or LmsFileIndex(
                id=identifier, institution_id=settings.institution_id, course_id=course_id, file_id=int(item["id"])
            )
            row.idempotency_key = f"file:{identifier}:{version}"
            row.resource_version, row.metadata_json = version, json.dumps(item, ensure_ascii=False)
            row.chunks_json, row.attempts, row.last_error = "[]", 0, ""
            row.failure_reason = ""
            row.lease_owner = None
            row.lease_expires_at = None
            row.heartbeat_at = None
            row.status = "delete_pending" if revoked or not supported else "queued"
            db.add(row)
            db.commit()


def claim_file(
    settings: Settings,
    statuses: tuple[str, ...],
    working_status: str,
    *,
    excluded_ids: set[str] | None = None,
):
    """Lease one durable job; release the connection before any file/model I/O."""
    owner = f"file:{socket.gethostname()}:{os.getpid()}"[:255]
    now = datetime.now(UTC)
    with SessionLocal() as db:
        query = select(LmsFileIndex).where(
            LmsFileIndex.status.in_(statuses), LmsFileIndex.institution_id == settings.institution_id,
            (LmsFileIndex.lease_expires_at.is_(None)) | (LmsFileIndex.lease_expires_at <= now),
        )
        if excluded_ids:
            query = query.where(LmsFileIndex.id.not_in(excluded_ids))
        row = db.scalar(query.order_by(LmsFileIndex.updated_at).with_for_update(skip_locked=True).limit(1))
        if row is None:
            return None
        previous = row.status
        row.status = working_status
        row.attempts += 1
        row.updated_at = now
        row.lease_owner = owner
        row.heartbeat_at = now
        row.lease_expires_at = now + timedelta(seconds=settings.worker_lease_seconds)
        row.failure_reason = ""
        db.commit()
        return {"id": row.id, "course_id": row.course_id, "file_id": row.file_id,
                "version": row.resource_version, "item": json.loads(row.metadata_json),
                "chunks": row.chunks_json, "attempts": row.attempts, "previous": previous,
                "lease_owner": owner}


def update_claim(job, **values):
    with SessionLocal() as db:
        row = db.scalar(select(LmsFileIndex).where(
            LmsFileIndex.id == job["id"], LmsFileIndex.resource_version == job["version"],
            LmsFileIndex.lease_owner == job["lease_owner"],
        ).with_for_update())
        if row:
            for key, value in values.items():
                setattr(row, key, value)
            row.lease_owner = None
            row.lease_expires_at = None
            row.heartbeat_at = None
            db.commit()


def heartbeat_file_claim(settings: Settings, job: dict) -> bool:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        row = db.scalar(select(LmsFileIndex).where(
            LmsFileIndex.id == job["id"], LmsFileIndex.resource_version == job["version"],
            LmsFileIndex.lease_owner == job["lease_owner"],
        ).with_for_update())
        if row is None:
            return False
        row.heartbeat_at = now
        row.lease_expires_at = now + timedelta(seconds=settings.worker_lease_seconds)
        db.commit()
        return True


@contextmanager
def file_claim_heartbeat(settings: Settings, job: dict):
    stop = threading.Event()

    def pulse() -> None:
        while not stop.wait(max(5, settings.worker_lease_seconds // 3)):
            try:
                if not heartbeat_file_claim(settings, job):
                    return
            except Exception:
                return

    thread = threading.Thread(target=pulse, daemon=True, name=f"file-lease-{job['id'][-8:]}")
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)


def recover_file_leases(settings: Settings):
    now = datetime.now(UTC)
    with SessionLocal() as db:
        rows = db.scalars(select(LmsFileIndex).where(
            LmsFileIndex.institution_id == settings.institution_id,
            LmsFileIndex.status.in_(("extracting", "indexing")),
            LmsFileIndex.lease_expires_at.is_not(None), LmsFileIndex.lease_expires_at <= now,
        ).with_for_update(skip_locked=True)).all()
        for row in rows:
            retry = "extraction_retry" if row.status == "extracting" else "retry" if json.loads(row.chunks_json) else "delete_pending"
            row.status = retry if row.attempts < settings.worker_max_attempts else "failed"
            row.last_error = "Phiên xử lý bị gián đoạn."
            row.failure_reason = "lease_expired"
            row.lease_owner = None
            row.lease_expires_at = None
            row.heartbeat_at = None
        db.commit()


async def process_file_extractions(client: LMSClient, settings: Settings) -> int:
    processed = 0
    attempted: set[str] = set()
    for _ in range(settings.course_file_batch_size):
        job = claim_file(settings, ("queued", "extraction_retry"), "extracting", excluded_ids=attempted)
        if job is None:
            break
        attempted.add(job["id"])
        processed += 1
        item, version, course_id = job["item"], job["version"], job["course_id"]
        try:
            with file_claim_heartbeat(settings, job):
                data = await client.download_course_file(course_id, int(item["id"]))
                expected = (item.get("latest_version") or {}).get("checksum_sha256")
                if expected and hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError("File checksum changed during download; waiting for next sync")
                chunks = await bounded_extract(data, file_name(item), str(item["title"]), settings)
            role_by_kind = {
                "assignment_guide": "student_assignment_brief",
                "student_rubric": "student_rubric",
                "assignment_package": "mixed_assignment_package",
                "teacher_solution": "teacher_solution",
                "teacher_assignment_package": "teacher_solution",
            }
            declared_role = str(item.get("content_role") or role_by_kind.get(str(item.get("kind") or ""), "learning_material"))
            chunks, excluded = filter_student_chunks(chunks, declared_role)
            if not chunks:
                raise ValueError("no_student_visible_content")
            resources = []
            for index, chunk in enumerate(chunks):
                # Never claim synthetic DOCX/TXT pagination as a real page number.
                if Path(file_name(item)).suffix.lower() not in {".pdf", ".pptx"}:
                    section = str(chunk.get("section_title") or "").strip()
                    chunk = dict(
                        chunk,
                        page=None,
                        location_detail=f"{f'Mục: {section} · ' if section else ''}Đoạn {index + 1}",
                        citation=f"[{item['title']}{f', {section}' if section else ''}, Đoạn {index + 1}]",
                    )
                text = str(chunk.get("content") or "")
                for offset in range(0, len(text), 1800):
                    resources.append(
                        dict(
                            chunk,
                            content=text[offset : offset + 1800],
                            institution_id=settings.institution_id,
                            course_id=str(course_id),
                            course_code=str(item.get("course_code") or course_id),
                            source_type="lms_file",
                            access_scope="course",
                            resource_id=f"file:{item['id']}",
                            resource_version=version,
                            chunk_id=f"file:{item['id']}:{index}:{offset}",
                            document_title=item["title"],
                            file_name=file_name(item),
                            file_type=Path(file_name(item)).suffix.lower().lstrip("."),
                            download_url=file_url(course_id, int(item["id"])),
                            source_url=item.get("source_url"),
                            content_role=chunk.get("content_role", declared_role),
                        )
                    )
            if len(resources) > settings.course_file_max_chunks:
                raise DocumentLimitError("chunk_limit")
            metadata = dict(item, content_role=declared_role, excluded_private_chunks=excluded)
            update_claim(job, metadata_json=json.dumps(metadata, ensure_ascii=False), chunks_json=json.dumps(resources, ensure_ascii=False), status="pending", attempts=0, last_error="", failure_reason="")
        except Exception as exc:
            terminal = isinstance(exc, (ValueError, DocumentLimitError)) or job["attempts"] >= settings.worker_max_attempts
            message = "Không đọc được nội dung; kiểm tra file có hợp lệ, không khóa và không vượt giới hạn xử lý."
            if isinstance(exc, DocumentLimitError):
                message = "Tài liệu vượt giới hạn text/đoạn xử lý. Hãy tách nhỏ file."
            elif isinstance(exc, TimeoutError):
                message = "Trích xuất quá thời gian cho phép. Hãy thử lại hoặc tách nhỏ file."
            elif not terminal:
                message = "Tạm thời không lấy được file; hệ thống sẽ thử lại có giới hạn."
            update_claim(job, status="failed" if terminal else "extraction_retry", last_error=message,
                         failure_reason=type(exc).__name__[:255], chunks_json="[]")
    return processed


def process_file_indexes(settings: Settings) -> int:
    processed = 0
    attempted: set[str] = set()
    for _ in range(settings.course_file_batch_size):
        job = claim_file(
            settings,
            ("pending", "retry", "delete_pending"),
            "indexing",
            excluded_ids=attempted,
        )
        if job is None:
            break
        attempted.add(job["id"])
        deleting = job["previous"] == "delete_pending"
        try:
            with file_claim_heartbeat(settings, job):
                bounded_index(job, settings)
            update_claim(job, status="unavailable" if deleting else "indexed", last_error="", failure_reason="")
        except Exception as exc:
            update_claim(job, status=("delete_pending" if deleting else "retry")
                         if job["attempts"] < settings.worker_max_attempts else "failed",
                         last_error="Chưa tạo được nguồn AI. Có thể thử xử lý lại.",
                         failure_reason=type(exc).__name__[:255])
        processed += 1
    return processed


async def authorized_files(client: LMSClient, course_id: int, user_id: int) -> list[dict[str, Any]]:
    # Deliberately not cached: revocation must affect the next request, even before worker cleanup.
    return await client.service_get(f"/api/pacewise/v1/courses/{course_id}/files", {"user_id": user_id})
