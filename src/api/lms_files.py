"""Course file processing status, authorized retry and authenticated viewing."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db import get_db
from src.persistence_models import LmsFileIndex
from src.security import SessionContext, get_current_session, require_csrf, require_instructor
from src.services.lms_client import LMSClient
from src.services.lms_files import authorized_files, file_name, file_version

router = APIRouter(tags=["lms-files"])


@router.get("/instructor/lms-files/status")
async def index_status(
    course_id: int,
    session: SessionContext = Depends(require_instructor),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    if course_id not in session.course_ids:
        raise HTTPException(403, "Course enrollment required")
    db.commit()
    allowed = {int(item["id"]) for item in await authorized_files(LMSClient(settings), course_id, session.user_id)}
    rows = db.scalars(
        select(LmsFileIndex)
        .where(LmsFileIndex.institution_id == settings.institution_id, LmsFileIndex.course_id == course_id)
        .order_by(LmsFileIndex.file_id)
    ).all()
    return {
        "files": [
            {
                "id": row.file_id,
                "title": json.loads(row.metadata_json).get("title", "Học liệu"),
                "status": row.status,
                "chunk_count": len(json.loads(row.chunks_json)),
                "error": row.last_error,
                "updated_at": row.updated_at.isoformat(),
                "version": row.resource_version,
                "view_url": f"/api/v1/lms-files/{course_id}/{row.file_id}/download",
            }
            for row in rows if row.file_id in allowed
        ]
    }


class RetryInput(BaseModel):
    expected_version: str = Field(alias="expectedVersion", min_length=64, max_length=64)


@router.post("/instructor/lms-files/{course_id}/{file_id}/retry")
async def retry_file(course_id: int, file_id: int, payload: RetryInput,
                     session: SessionContext = Depends(require_csrf), settings: Settings = Depends(get_settings),
                     db: Session = Depends(get_db)):
    if session.role != "instructor" or course_id not in session.course_ids:
        raise HTTPException(403, "Instructor course enrollment required")
    db.commit()
    manifest = await authorized_files(LMSClient(settings), course_id, session.user_id)
    item = next((item for item in manifest if int(item["id"]) == file_id), None)
    if item is None or ((item.get("access_scope") or []) and not any(scope.get("permission", "read") == "read" for scope in item["access_scope"])):
        raise HTTPException(403, "Tài liệu không còn được phép xử lý.")
    row = db.scalar(select(LmsFileIndex).where(
        LmsFileIndex.institution_id == settings.institution_id, LmsFileIndex.course_id == course_id,
        LmsFileIndex.file_id == file_id,
    ).with_for_update())
    if not row or row.status != "failed" or row.resource_version != payload.expected_version or file_version(item) != row.resource_version:
        raise HTTPException(409, "Trạng thái hoặc phiên bản file đã thay đổi. Hãy cập nhật lại.")
    updated = row.updated_at.replace(tzinfo=UTC) if row.updated_at.tzinfo is None else row.updated_at
    cooldown = 30 - int((datetime.now(UTC) - updated).total_seconds())
    if cooldown > 0:
        raise HTTPException(429, "Chờ một chút trước khi xử lý lại.", headers={"Retry-After": str(cooldown)})
    row.status = "pending" if json.loads(row.chunks_json) else "queued"
    row.attempts, row.last_error = 0, ""
    db.commit()
    return {"status": row.status}


@router.get("/lms-files/{course_id}/{file_id}/download")
async def download_file(
    course_id: int,
    file_id: int,
    session: SessionContext = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    if course_id not in session.course_ids:
        raise HTTPException(403, "Course enrollment required")
    client = LMSClient(settings)
    manifest = await authorized_files(client, course_id, session.user_id)
    item = next((item for item in manifest if int(item["id"]) == file_id), None)
    if item is None:
        raise HTTPException(403, "Tài liệu đã bị xóa hoặc bạn không còn quyền truy cập")
    version = file_version(item)
    data = await client.download_course_file(course_id, file_id, user_id=session.user_id)
    expected_hash = (item.get("latest_version") or {}).get("checksum_sha256")
    if expected_hash and hashlib.sha256(data).hexdigest() != expected_hash:
        raise HTTPException(409, "Nội dung tài liệu vừa thay đổi; hãy tải lại")
    # Check revocation/update during the download as well.
    current = await authorized_files(client, course_id, session.user_id)
    if not any(int(item["id"]) == file_id and file_version(item) == version for item in current):
        raise HTTPException(409, "Tài liệu hoặc quyền truy cập vừa thay đổi; hãy tải lại")
    media_type = "application/pdf" if Path(file_name(item)).suffix.lower() == ".pdf" else "application/octet-stream"
    return Response(
        data,
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )
