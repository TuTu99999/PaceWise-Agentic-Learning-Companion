"""
API quản lý tài liệu học tập của môn học (Tải lên, Lưu trữ CSDL, Index Qdrant, Tải về).
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db import get_db
from src.persistence_models import CourseMaterial
from src.security import (
    SessionContext,
    get_current_session,
    require_csrf,
    require_instructor,
)
from src.services.material_service import (
    _clean_text,
    delete_material_from_qdrant,
    index_material_in_qdrant,
    parse_material_content,
)

logger = logging.getLogger("pacewise.api.materials")
router = APIRouter(tags=["materials"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md"}
MAX_FILE_BYTES = 200 * 1024 * 1024  # 200 MB
UPLOAD_CHUNK_BYTES = 1024 * 1024


async def _read_upload_limited(file: UploadFile) -> bytes:
    """Read an upload without ever accepting more than the configured limit."""
    content = bytearray()
    while chunk := await file.read(UPLOAD_CHUNK_BYTES):
        if len(content) + len(chunk) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="Dung lượng file vượt quá giới hạn 200 MB")
        content.extend(chunk)
    if not content:
        raise HTTPException(status_code=422, detail="File tải lên không có nội dung (0 bytes)")
    return bytes(content)


def _safe_file_name(raw_name: str) -> str:
    """Keep download headers and stored metadata free from path/header control chars."""
    normalized = Path(raw_name.replace("\\", "/")).name
    sanitized = re.sub(r'[\r\n"]', "_", normalized).strip()
    return (sanitized or "tailieu")[:255]


def _validate_file_signature(file_bytes: bytes, suffix: str) -> None:
    if suffix == ".pdf" and not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="Nội dung file không phải PDF hợp lệ")
    if suffix in {".docx", ".pptx"} and not file_bytes.startswith(b"PK"):
        raise HTTPException(status_code=422, detail="Nội dung file không đúng định dạng OpenXML")


def _to_material_summary(m: CourseMaterial) -> dict:
    return {
        "id": m.id,
        "title": m.title,
        "moduleName": m.module_name,
        "fileName": m.file_name,
        "fileType": m.file_type,
        "fileSize": m.file_size,
        "chunkCount": m.chunk_count,
        "uploadedBy": m.uploaded_by,
        "createdAt": m.created_at.isoformat() if m.created_at else None,
        "updatedAt": m.updated_at.isoformat() if m.updated_at else None,
    }


@router.post("/instructor/materials/upload")
async def upload_material(
    file: UploadFile = File(...),
    course_id: int = Form(...),
    title: str = Form(default=""),
    module_name: str = Form(default="Tài liệu chung"),
    session: SessionContext = Depends(require_instructor),
    _: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    """Legacy development-only upload; production uses presigned S3 document tickets."""
    if course_id not in session.course_ids:
        raise HTTPException(status_code=403, detail="Bạn không có quyền giảng dạy môn học này")
    if not settings.allow_legacy_material_writes:
        raise HTTPException(status_code=410, detail="Quản lý học liệu đã chuyển sang LMS; hãy upload trên LMS")

    file_name = _safe_file_name(file.filename or "tailieu")
    suffix = Path(file_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Định dạng '{suffix}' không được hỗ trợ. Các định dạng cho phép: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    file_bytes = await _read_upload_limited(file)
    file_size = len(file_bytes)
    _validate_file_signature(file_bytes, suffix)

    clean_title = _clean_text(title.strip() or Path(file_name).stem.replace("_", " ").replace("-", " ").title())
    clean_module = _clean_text(module_name.strip() or "Tài liệu chung")

    # 1. Trích xuất text và tạo chunks
    try:
        extracted_text, chunks = parse_material_content(file_bytes, file_name, clean_title)
        extracted_text = _clean_text(extracted_text)
        for c in chunks:
            c["section_title"] = _clean_text(c.get("section_title", ""))
            c["location_detail"] = _clean_text(c.get("location_detail", ""))
            c["citation"] = _clean_text(c.get("citation", ""))
            c["content"] = _clean_text(c.get("content", ""))
    except Exception as exc:
        logger.warning("material_parse_failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=500, detail=f"Không thể xử lý nội dung file: {exc}") from exc

    # 2. Lưu trữ toàn bộ dữ liệu vào cơ sở dữ liệu PostgreSQL
    material_id = f"mat_{uuid.uuid4().hex[:16]}"
    material = CourseMaterial(
        id=material_id,
        institution_id=settings.institution_id,
        course_id=course_id,
        title=clean_title,
        module_name=clean_module,
        file_name=file_name,
        file_type=suffix.lstrip("."),
        file_size=file_size,
        file_bytes=file_bytes,
        extracted_text=extracted_text,
        chunk_count=len(chunks),
        uploaded_by=session.user_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(material)
    db.commit()
    db.refresh(material)

    # 3. Lập chỉ mục Vector tức thời vào Qdrant
    indexed_chunks = 0
    try:
        indexed_chunks = index_material_in_qdrant(material, chunks)
        if indexed_chunks != material.chunk_count:
            material.chunk_count = indexed_chunks
            db.commit()
    except Exception as exc:
        logger.warning("material_qdrant_index_warning error_type=%s", type(exc).__name__)

    return {
        "status": "success",
        "message": f"Đã lưu trữ và lập chỉ mục {indexed_chunks} đoạn kiến thức vào cơ sở dữ liệu.",
        "material": _to_material_summary(material),
    }


@router.get("/instructor/materials")
async def list_instructor_materials(
    course_id: int,
    session: SessionContext = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Danh sách tài liệu giảng viên đã tải lên trong môn học."""
    if course_id not in session.course_ids:
        raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập môn học này")

    stmt = (
        select(CourseMaterial)
        .where(CourseMaterial.course_id == course_id)
        .order_by(CourseMaterial.created_at.desc())
    )
    materials = db.scalars(stmt).all()
    return [_to_material_summary(m) for m in materials]


@router.delete("/instructor/materials/{material_id}")
async def delete_material(
    material_id: str,
    session: SessionContext = Depends(require_instructor),
    _: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    """Xóa tài liệu khỏi cơ sở dữ liệu và thu hồi toàn bộ vector trong Qdrant."""
    material = db.get(CourseMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    if material.course_id not in session.course_ids:
        raise HTTPException(status_code=403, detail="Bạn không có quyền xóa tài liệu của môn này")
    if not settings.allow_legacy_material_writes:
        raise HTTPException(status_code=410, detail="Quản lý học liệu đã chuyển sang LMS; tài liệu cũ được giữ để đọc")

    # Xóa vector points khỏi Qdrant
    try:
        delete_material_from_qdrant(material.id, settings.institution_id, material.course_id)
    except Exception as exc:
        logger.warning("delete_from_qdrant_failed error_type=%s", type(exc).__name__)

    # Remove the private object first. If object deletion is unavailable, keep
    # metadata so an operator can retry without leaving an untracked binary.
    if material.object_key and settings.course_storage_backend == "s3":
        try:
            from src.services.course_object_store import delete_object

            delete_object(settings, material.object_key)
        except Exception as exc:
            logger.warning("material_object_delete_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Chưa thể xóa file gốc an toàn.") from exc

    # Xóa khỏi PostgreSQL
    db.delete(material)
    db.commit()

    return {"status": "success", "message": "Đã xóa tài liệu khỏi cơ sở dữ liệu và vector store."}


@router.get("/materials/course/{course_id}")
async def list_course_materials_for_students(
    course_id: int,
    session: SessionContext = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Danh sách tài liệu học tập của môn học (dành cho cả học sinh và giảng viên)."""
    if course_id not in session.course_ids:
        raise HTTPException(status_code=403, detail="Bạn chưa đăng ký môn học này")

    stmt = (
        select(CourseMaterial)
        .where(CourseMaterial.course_id == course_id)
        .order_by(CourseMaterial.module_name, CourseMaterial.created_at.desc())
    )
    materials = db.scalars(stmt).all()
    return [_to_material_summary(m) for m in materials]


@router.get("/materials/{material_id}/preview")
async def preview_material(
    material_id: str,
    session: SessionContext = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> dict:
    """Xem nhanh nội dung trích xuất của tài liệu."""
    material = db.get(CourseMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    if material.course_id not in session.course_ids:
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem tài liệu này")

    preview_text = (material.extracted_text or "")[:2000]
    return {
        "id": material.id,
        "title": material.title,
        "fileName": material.file_name,
        "fileType": material.file_type,
        "chunkCount": material.chunk_count,
        "preview": preview_text,
    }


@router.get("/materials/{material_id}/download")
async def download_material(
    material_id: str,
    session: SessionContext = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> Response:
    """Download migrated S3 objects, with DB bytes only as a legacy fallback."""
    material = db.get(CourseMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    if material.course_id not in session.course_ids:
        raise HTTPException(status_code=403, detail="Bạn không có quyền tải tài liệu này")

    mime_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "ppt": "application/vnd.ms-powerpoint",
        "txt": "text/plain; charset=utf-8",
        "md": "text/markdown; charset=utf-8",
    }
    media_type = mime_types.get(material.file_type.lower(), "application/octet-stream")

    disposition = "inline" if material.file_type.lower() == "pdf" else "attachment"
    if material.object_key:
        from src.services.course_object_store import presigned_get, source_url

        return RedirectResponse(
            presigned_get(
                settings,
                source_url(material.object_key),
                material.file_name,
                inline=disposition == "inline",
            ),
            status_code=307,
            headers={"Cache-Control": "private, no-store"},
        )
    if material.file_bytes is None:
        raise HTTPException(status_code=503, detail="File gốc chưa sẵn sàng trong kho học liệu.")
    return Response(
        content=material.file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{material.file_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
