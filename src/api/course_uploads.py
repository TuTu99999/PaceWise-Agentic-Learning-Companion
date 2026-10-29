"""Native PDF upload: encrypted authorization ticket, then streamed binary.

No database connection is held while the browser uploads. The one-time opaque
ticket is bound to the logged-in instructor, course, filename, chapter and size.
The binary endpoint returns no identifiers or personal information.
"""

import asyncio
import base64
import hashlib
import secrets
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, delete, func, select, text, update
from sqlalchemy.orm import Mapped, mapped_column

from src.config import Settings, get_settings
from src.db import Base, SessionLocal
from src.security import SessionContext, require_csrf

router = APIRouter(tags=["Course uploads"])
_upload_slots = asyncio.Semaphore(4)


class CourseUploadTicket(Base):
    __tablename__ = "course_upload_tickets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    course_id: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    chapter: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String(1000), default="")
    checksum_sha256: Mapped[str] = mapped_column(String(64), default="")
    checksum_sha256_base64: Mapped[str] = mapped_column(String(64), default="")
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    filename: str = Field(min_length=1, max_length=255)
    chapter: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0, strict=True)
    checksum_sha256: str = Field(default="", alias="checksumSha256", pattern=r"^$|^[a-fA-F0-9]{64}$")
    content_role: Literal[
        "learning_material",
        "student_assignment_brief",
        "student_rubric",
        "mixed_assignment_package",
        "teacher_solution",
    ] = "learning_material"


class CourseUploadReceipt(Base):
    __tablename__ = "course_upload_receipts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    file_id: Mapped[int] = mapped_column(Integer)
    duplicate: Mapped[bool] = mapped_column(Boolean)


class CourseUploadPolicy(Base):
    __tablename__ = "course_upload_policies"
    ticket_id: Mapped[str] = mapped_column(
        ForeignKey("course_upload_tickets.id", ondelete="CASCADE"), primary_key=True
    )
    content_role: Mapped[str] = mapped_column(String(40))


class ReceiptInput(BaseModel):
    token: str = Field(min_length=40, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


def native_instructor(session, settings):
    if settings.course_source_mode != "standalone":
        raise HTTPException(409, "Binary upload requires the standalone course source.")
    if session.role != "instructor":
        raise HTTPException(403, "Instructor role required")


def check_owner(course_id, user_id):
    from src.course_source.db import SessionLocal as CourseSession
    from src.course_source.teacher_management import teacher

    with CourseSession() as db:
        teacher(db, course_id, user_id)


@router.post("/instructor/manage/courses/{course_id}/pdf-ticket")
@router.post("/instructor/manage/courses/{course_id}/document-ticket")
async def upload_ticket(course_id: int, payload: UploadInput,
                        session: SessionContext = Depends(require_csrf), settings: Settings = Depends(get_settings)):
    native_instructor(session, settings)
    if course_id not in session.course_ids:
        raise HTTPException(403, "Course enrollment required")
    suffix = Path(payload.filename).suffix.lower()
    if (suffix not in {".pdf", ".docx"} or Path(payload.filename).name != payload.filename
            or "\\" in payload.filename or any(c in payload.filename for c in "\r\n\0")):
        raise HTTPException(422, "Tên file phải là PDF hoặc DOCX hợp lệ.")
    if payload.size > settings.course_pdf_max_mb * 1024 * 1024:
        raise HTTPException(413, f"Mỗi file tối đa {settings.course_pdf_max_mb} MB.")
    await asyncio.to_thread(check_owner, course_id, session.user_id)
    token = secrets.token_urlsafe(32)
    ticket_id = hashlib.sha256(token.encode()).hexdigest()
    content_type = (
        "application/pdf"
        if suffix == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    if settings.course_storage_backend == "s3" and not payload.checksum_sha256:
        raise HTTPException(422, "Checksum SHA-256 là bắt buộc khi tải trực tiếp lên S3.")
    checksum_base64 = (
        base64.b64encode(bytes.fromhex(payload.checksum_sha256)).decode()
        if payload.checksum_sha256
        else ""
    )
    object_key = f"{settings.institution_id}/courses/{course_id}/uploads/{ticket_id}{suffix}"
    with SessionLocal() as db:
        from src.persistence_models import LmsFileIndex

        if db.bind.dialect.name == "postgresql":
            lock = int.from_bytes(hashlib.sha256(f"pdf-queue:{settings.institution_id}:{course_id}".encode()).digest()[:8], signed=True)
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        now = datetime.now(UTC)
        db.execute(delete(CourseUploadTicket).where(CourseUploadTicket.expires_at < now))
        db.execute(delete(CourseUploadReceipt).where(CourseUploadReceipt.id.not_in(select(CourseUploadTicket.id))))
        # Tickets have a fixed 15-minute lifetime. Counting expiry timestamps
        # inside this suffix of that lifetime gives a durable, replica-safe
        # per-user creation window without another mutable in-memory limiter.
        recent_after = now + timedelta(minutes=15, seconds=-settings.upload_ticket_rate_window_seconds)
        recent = db.scalar(
            select(func.count())
            .select_from(CourseUploadTicket)
            .where(
                CourseUploadTicket.user_id == session.user_id,
                CourseUploadTicket.expires_at >= recent_after,
            )
        )
        if int(recent or 0) >= settings.upload_ticket_rate_limit:
            raise HTTPException(
                429,
                "Bạn đã tạo quá nhiều lượt tải lên. Hãy thử lại sau.",
                headers={"Retry-After": str(settings.upload_ticket_rate_window_seconds)},
            )
        queued = db.scalar(select(func.count()).select_from(LmsFileIndex).where(
            LmsFileIndex.institution_id == settings.institution_id, LmsFileIndex.course_id == course_id,
            LmsFileIndex.status.in_(("queued", "extracting", "extraction_retry", "pending", "indexing", "retry")),
        ))
        uploading = db.scalar(select(func.count()).select_from(CourseUploadTicket).where(
            CourseUploadTicket.course_id == course_id,
            CourseUploadTicket.id.not_in(select(CourseUploadReceipt.id)),
        ))
        if queued + uploading >= settings.course_file_queue_limit:
            raise HTTPException(429, "Hàng chờ xử lý môn này đã đầy. Hãy chờ các file trước xử lý xong.", headers={"Retry-After": "30"})
        pending = db.scalar(select(func.count()).select_from(CourseUploadTicket).where(
            CourseUploadTicket.user_id == session.user_id, CourseUploadTicket.consumed_at.is_(None)))
        if pending >= 20:
            raise HTTPException(429, "Có quá nhiều lượt tải đang chờ. Hãy thử lại sau.", headers={"Retry-After": "60"})
        db.add(CourseUploadTicket(id=ticket_id, user_id=session.user_id,
                                 course_id=course_id, filename=payload.filename, chapter=payload.chapter,
                                 size=payload.size, object_key=object_key,
                                 checksum_sha256=payload.checksum_sha256.lower(),
                                 checksum_sha256_base64=checksum_base64, content_type=content_type,
                                 expires_at=datetime.now(UTC) + timedelta(minutes=15)))
        # The policy mapper has no ORM relationship to the ticket mapper. On
        # PostgreSQL SQLAlchemy may therefore flush the child first even though
        # its Table contains a foreign key. Persist the parent explicitly so a
        # document role can never fail ticket creation with an FK violation.
        db.flush()
        db.add(CourseUploadPolicy(ticket_id=ticket_id, content_role=payload.content_role))
        db.commit()
    if settings.course_storage_backend == "s3":
        from src.services.course_object_store import presigned_put

        signed = await asyncio.to_thread(
            presigned_put, settings, object_key, content_type, checksum_base64
        )
        return {
            "uploadMode": "s3",
            "uploadUrl": signed["url"],
            "uploadHeaders": signed["headers"],
            "receiptToken": token,
            "maxMb": settings.course_pdf_max_mb,
        }
    return {"uploadMode": "proxy", "uploadPath": "/api/v1/private/uploads/" + token,
            "receiptToken": token, "maxMb": settings.course_pdf_max_mb}


def claim_ticket(token, user_id):
    with SessionLocal() as db:
        identifier = hashlib.sha256(token.encode()).hexdigest()
        policy = db.get(CourseUploadPolicy, identifier)
        result = db.execute(update(CourseUploadTicket).where(
            CourseUploadTicket.id == identifier,
            CourseUploadTicket.user_id == user_id, CourseUploadTicket.consumed_at.is_(None),
            CourseUploadTicket.expires_at > datetime.now(UTC),
        ).values(consumed_at=datetime.now(UTC)).returning(CourseUploadTicket))
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(409, "Lượt tải đã dùng hoặc hết hạn. Hãy chọn lại file.")
        fields = {key: getattr(row, key) for key in (
            "course_id", "filename", "chapter", "size", "object_key", "checksum_sha256",
            "checksum_sha256_base64", "content_type",
        )}
        fields["content_role"] = policy.content_role if policy else "learning_material"
        db.commit()
        return fields


def release_ticket(token: str, user_id: int) -> None:
    """Allow a safe receipt retry after transient S3/validation failures."""
    identifier = hashlib.sha256(token.encode()).hexdigest()
    with SessionLocal() as db:
        if db.get(CourseUploadReceipt, identifier) is None:
            db.execute(
                update(CourseUploadTicket)
                .where(CourseUploadTicket.id == identifier, CourseUploadTicket.user_id == user_id)
                .values(consumed_at=None)
            )
            db.commit()


def register_document(spec, actor_id, source_url, checksum, source_path):
    from src.course_source.db import SessionLocal as CourseSession
    from src.course_source.learning_api import record_resource_version, resource_extension_payload
    from src.course_source.models import CourseModule, ModuleItem, Resource, ResourceAccess, ResourceVersion
    from src.course_source.teacher_management import map_chapter, teacher
    from src.course_source.telemetry import record_change
    from src.services.document_roles import filter_student_chunks, public_markdown
    from src.services.material_service import parse_material_content

    role = spec.get("content_role", "learning_material")
    content_type = (
        "application/pdf"
        if Path(spec["filename"]).suffix.lower() == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    kind_by_role = {
        "learning_material": "file",
        "student_assignment_brief": "assignment_guide",
        "student_rubric": "student_rubric",
        "mixed_assignment_package": "teacher_assignment_package",
        "teacher_solution": "teacher_solution",
    }

    derivative = None
    if role == "mixed_assignment_package":
        data = Path(source_path).read_bytes()
        _, chunks = parse_material_content(data, spec["filename"], spec["filename"])
        visible, excluded = filter_student_chunks(chunks, role)
        if not visible or not excluded:
            raise HTTPException(
                422,
                "Word hỗn hợp phải có heading đề/rubric và heading đáp án rõ ràng để tách an toàn.",
            )
        public_data = public_markdown(visible, f"{spec['filename']} · Bản sinh viên")
        public_checksum = hashlib.sha256(public_data).hexdigest()
        public_name = f"course-{spec['course_id']}-{public_checksum}-student.md"
        storage_settings = spec.get("_settings")
        if storage_settings and storage_settings.course_storage_backend == "s3":
            from src.services.course_object_store import source_url as object_source_url
            from src.services.course_object_store import upload_bytes

            public_key = f"{storage_settings.institution_id}/courses/{spec['course_id']}/{public_name}"
            upload_bytes(storage_settings, public_data, public_key, "text/markdown")
            public_source_url = object_source_url(public_key)
        else:
            public_path = Path(source_path).parent / public_name
            if not public_path.exists():
                temporary = public_path.with_name(f".{public_name}.{secrets.token_hex(8)}.tmp")
                try:
                    temporary.write_bytes(public_data)
                    temporary.replace(public_path)
                finally:
                    temporary.unlink(missing_ok=True)
            public_source_url = f"/api/files/{public_name}"
        derivative = {
            "title": f"{Path(spec['filename']).stem} · Bản sinh viên.md",
            "source_url": public_source_url,
            "checksum": public_checksum,
            "size": len(public_data),
            "content_type": "text/markdown",
            "kind": "assignment_guide",
            "content_role": "student_assignment_brief",
        }

    with CourseSession() as db:
        # Live ownership rechecked after upload, not just when ticket was issued.
        teacher(db, spec["course_id"], actor_id)
        if db.bind.dialect.name == "postgresql":
            lock = int.from_bytes(hashlib.sha256(f"{spec['course_id']}:{spec['chapter']}:{checksum}".encode()).digest()[:8], signed=True)
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        def ensure_resource(details, *, instructor_only=False):
            candidate = db.scalar(
                select(Resource)
                .join(ResourceVersion)
                .join(ModuleItem, (ModuleItem.content_id == Resource.id) & (ModuleItem.item_type == "resource"))
                .join(CourseModule)
                .where(
                    Resource.course_id == spec["course_id"],
                    Resource.kind == details["kind"],
                    CourseModule.course_id == spec["course_id"],
                    CourseModule.name == spec["chapter"],
                    ResourceVersion.checksum_sha256 == details["checksum"],
                )
                .limit(1)
            )
            if candidate:
                return candidate, True
            resource = Resource(
                course_id=spec["course_id"],
                title=details["title"],
                kind=details["kind"],
                source_url=details["source_url"],
            )
            db.add(resource)
            db.flush()
            map_chapter(db, spec["course_id"], spec["chapter"], "resource", resource.id, resource.title)
            record_resource_version(
                db,
                resource,
                checksum=details["checksum"],
                size_bytes=details["size"],
                content_type=details["content_type"],
                ensure_course_access=not instructor_only,
            )
            if instructor_only:
                db.add(
                    ResourceAccess(
                        resource_id=resource.id,
                        scope_type="instructor",
                        scope_id=spec["course_id"],
                    )
                )
            record_change(
                db,
                actor_user_id=actor_id,
                action="resource.created",
                entity_type="resource",
                entity_id=resource.id,
                course_id=spec["course_id"],
                metadata={"content_role": details["content_role"]},
            )
            return resource, False

        original = {
            "title": spec["filename"],
            "source_url": source_url,
            "checksum": checksum,
            "size": spec["size"],
            "content_type": content_type,
            "kind": kind_by_role[role],
            "content_role": role,
        }
        private_original = role in {"mixed_assignment_package", "teacher_solution"}
        resource, original_duplicate = ensure_resource(original, instructor_only=private_original)
        if derivative:
            resource, derivative_duplicate = ensure_resource(derivative)
            duplicate = original_duplicate and derivative_duplicate
            result_role = derivative["content_role"]
        else:
            duplicate = original_duplicate
            result_role = role
        extension = resource_extension_payload(db, resource)
        item = {
            "id": resource.id,
            "title": resource.title,
            "kind": resource.kind,
            "source_url": resource.source_url,
            "content_role": result_role,
            **extension,
        }
        db.commit()
        return {"item": item, "duplicate": duplicate}


# Kept as a narrow compatibility seam for callers/tests that wrapped the
# original PDF registration transaction. It now supports both PDF and DOCX.
register_pdf = register_document


def record_receipt(token, spec, result, settings):
    import json

    from src.persistence_models import LmsFileIndex
    from src.services.lms_files import file_version

    item = result["item"]
    identifier = f"{settings.institution_id}:{spec['course_id']}:{item['id']}"
    with SessionLocal() as db:
        db.merge(CourseUploadReceipt(id=hashlib.sha256(token.encode()).hexdigest(), file_id=item["id"], duplicate=result["duplicate"]))
        # Seed a durable job immediately. The source event reconciler can recover
        # a crash between the course commit and this receipt transaction.
        if spec.get("content_role", "learning_material") != "teacher_solution" and db.get(LmsFileIndex, identifier) is None:
            db.add(LmsFileIndex(id=identifier, idempotency_key=f"file:{identifier}:{file_version(item)}",
                                institution_id=settings.institution_id, course_id=spec["course_id"],
                                file_id=item["id"], resource_version=file_version(item),
                                metadata_json=json.dumps(item, ensure_ascii=False), status="queued"))
        db.commit()


def finalize_s3_upload(token: str, actor_id: int, settings: Settings) -> dict:
    """Verify the browser upload, then register metadata without persisting bytes in PostgreSQL."""
    from src.services.course_object_store import download_to_path, source_url, verify_object
    from src.services.lms_files import validate_document

    try:
        spec = claim_ticket(token, actor_id)
        key = spec["object_key"]
        try:
            verify_object(
                settings,
                key,
                expected_size=spec["size"],
                expected_checksum_sha256_base64=spec["checksum_sha256_base64"],
            )
        except Exception as exc:
            raise HTTPException(422, "File trên S3 chưa hoàn tất hoặc không khớp checksum.") from exc

        suffix = Path(spec["filename"]).suffix.lower()
        handle, temporary_name = tempfile.mkstemp(prefix="pacewise-finalize-", suffix=suffix)
        import os

        os.close(handle)
        path = Path(temporary_name)
        try:
            download_to_path(settings, key, path)
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != spec["checksum_sha256"]:
                raise HTTPException(422, "Checksum file sau tải lên không hợp lệ.")
            validate_document(data, spec["filename"], settings.course_pdf_max_pages)
            spec["_settings"] = settings
            result = register_pdf(spec, actor_id, source_url(key), spec["checksum_sha256"], path)
            # Persist the idempotent receipt before cleaning up a redundant
            # object. If the database commit fails, the browser can safely
            # retry while the uploaded object still exists.
            record_receipt(token, spec, result, settings)
            # Do not delete a duplicate direct-upload object synchronously.
            # A receipt retry can make this exact key the canonical resource;
            # an S3 lifecycle/orphan sweep is the safe cleanup boundary.
            return result
        finally:
            path.unlink(missing_ok=True)
    except Exception:
        release_ticket(token, actor_id)
        raise


@router.post("/instructor/manage/courses/{course_id}/pdf-receipt")
@router.post("/instructor/manage/courses/{course_id}/document-receipt")
async def upload_receipt(course_id: int, payload: ReceiptInput,
                         session: SessionContext = Depends(require_csrf), settings: Settings = Depends(get_settings)):
    native_instructor(session, settings)
    if course_id not in session.course_ids:
        raise HTTPException(403, "Course enrollment required")
    await asyncio.to_thread(check_owner, course_id, session.user_id)
    identifier = hashlib.sha256(payload.token.encode()).hexdigest()
    with SessionLocal() as db:
        ticket, receipt = db.get(CourseUploadTicket, identifier), db.get(CourseUploadReceipt, identifier)
        if not ticket or ticket.user_id != session.user_id or ticket.course_id != course_id:
            raise HTTPException(404, "Chưa ghi nhận lượt tải này.")
    if receipt is None and settings.course_storage_backend == "s3":
        await asyncio.to_thread(finalize_s3_upload, payload.token, session.user_id, settings)
    with SessionLocal() as db:
        ticket, receipt = db.get(CourseUploadTicket, identifier), db.get(CourseUploadReceipt, identifier)
        if not ticket or ticket.user_id != session.user_id or ticket.course_id != course_id or not receipt:
            raise HTTPException(404, "Chưa ghi nhận lượt tải này.")
        return {"fileId": receipt.file_id, "duplicate": receipt.duplicate}


async def receive_binary(token: str, request: Request, session: SessionContext, settings: Settings):
    native_instructor(session, settings)
    incoming_type = request.headers.get("content-type", "").split(";")[0]
    if len(token) > 100 or incoming_type not in {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        raise HTTPException(422, "Chỉ nhận nội dung PDF hoặc DOCX.")
    spec = await asyncio.to_thread(claim_ticket, token, session.user_id)
    suffix = Path(spec["filename"]).suffix.lower()
    expected_type = (
        "application/pdf"
        if suffix == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    if incoming_type != expected_type:
        raise HTTPException(422, "Định dạng tải lên không khớp tên file.")
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) != spec["size"]):
        raise HTTPException(413, "Dung lượng tải không khớp file đã chọn.")
    if spec["size"] > settings.course_pdf_max_mb * 1024 * 1024:
        raise HTTPException(413, "File vượt giới hạn hiện tại.")
    name = f"course-{spec['course_id']}-{secrets.token_hex(16)}{suffix}"
    if settings.course_storage_backend == "local":
        directory = Path(settings.course_upload_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        ephemeral = False
    else:
        handle, temporary_name = tempfile.mkstemp(prefix="pacewise-upload-", suffix=suffix)
        import os

        os.close(handle)
        path = Path(temporary_name)
        path.unlink(missing_ok=True)
        ephemeral = True
    total, prefix, digest = 0, bytearray(), hashlib.sha256()
    registered = False
    receipt_recorded = False
    stored_key: str | None = None
    try:
        with path.open("xb") as output:
            async for chunk in request.stream():
                total += len(chunk)
                if total > spec["size"]:
                    raise HTTPException(413, "PDF vượt dung lượng khai báo.")
                signature_length = 5 if suffix == ".pdf" else 4
                prefix.extend(chunk[:max(0, signature_length - len(prefix))])
                expected_signature = b"%PDF-" if suffix == ".pdf" else b"PK\x03\x04"
                if len(prefix) == signature_length and bytes(prefix) != expected_signature:
                    raise HTTPException(422, "Nội dung không đúng định dạng đã chọn.")
                digest.update(chunk)
                await asyncio.to_thread(output.write, chunk)
        expected_signature = b"%PDF-" if suffix == ".pdf" else b"PK\x03\x04"
        if total != spec["size"] or bytes(prefix) != expected_signature:
            raise HTTPException(422, "File thiếu hoặc không hợp lệ.")
        # A DOCX is a ZIP container, so validate its structure and expansion
        # limits before registration. PDF extraction remains asynchronous; the
        # upload path already checks its signature and the worker reports a
        # corrupt/encrypted PDF without holding this request open.
        if suffix == ".docx":
            from src.services.lms_files import validate_document

            await asyncio.to_thread(validate_document, path.read_bytes(), spec["filename"])
        async def finalize():
            nonlocal receipt_recorded, registered, stored_key
            spec["_settings"] = settings
            if settings.course_storage_backend == "s3":
                from src.services.course_object_store import source_url as object_source_url
                from src.services.course_object_store import upload_path

                stored_key = f"{settings.institution_id}/courses/{spec['course_id']}/{name}"
                checksum_b64 = base64.b64encode(digest.digest()).decode()
                await asyncio.to_thread(upload_path, settings, path, stored_key, expected_type, checksum_b64)
                stored_source_url = object_source_url(stored_key)
            else:
                stored_source_url = "/api/files/" + name
            result = await asyncio.to_thread(
                register_pdf,
                spec,
                session.user_id,
                stored_source_url,
                digest.hexdigest(),
                path,
            )
            registered = True
            # Commit the durable result before deleting a redundant binary.
            # A cleanup failure must never make a successfully registered
            # resource look failed to the browser.
            await asyncio.to_thread(record_receipt, token, spec, result, settings)
            receipt_recorded = True
            if result["duplicate"]:
                if stored_key:
                    from src.services.course_object_store import delete_object

                    try:
                        await asyncio.to_thread(delete_object, settings, stored_key)
                    except Exception:
                        pass
                elif not ephemeral:
                    path.unlink(missing_ok=True)  # Only this request's redundant new file.

        finalization = asyncio.create_task(finalize())
        try:
            await asyncio.shield(finalization)
        except asyncio.CancelledError:
            # to_thread cannot cancel a running commit. Observe its completion
            # before cleanup so a committed resource never loses its binary.
            try:
                await finalization
            finally:
                raise
    except BaseException:
        if not receipt_recorded:
            await asyncio.to_thread(release_ticket, token, session.user_id)
        if not registered:
            if stored_key:
                from src.services.course_object_store import delete_object

                await asyncio.to_thread(delete_object, settings, stored_key)
            path.unlink(missing_ok=True)
        raise
    finally:
        if ephemeral:
            path.unlink(missing_ok=True)
    return Response(status_code=204)


@router.put("/private/uploads/{token}", status_code=204, include_in_schema=False)
async def upload_binary(token: str, request: Request, session: SessionContext = Depends(require_csrf),
                        settings: Settings = Depends(get_settings)):
    native_instructor(session, settings)
    try:
        await asyncio.wait_for(_upload_slots.acquire(), timeout=0.25)
    except TimeoutError as exc:
        raise HTTPException(429, "Hàng chờ upload đang đầy. Hãy thử lại sau.", headers={"Retry-After": "5"}) from exc
    try:
        return await receive_binary(token, request, session, settings)
    finally:
        _upload_slots.release()
