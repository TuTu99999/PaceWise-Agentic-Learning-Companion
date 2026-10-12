"""Owned binary storage with streaming, path validation and bounded uploads."""

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from src.config import get_settings

UPLOAD_DIR = Path(get_settings().course_upload_dir)
MAX_UPLOAD_BYTES = get_settings().course_pdf_max_mb * 1024 * 1024


def save_upload(upload: UploadFile, prefix: str) -> tuple[str, str]:
    if not prefix.startswith("course-") or not prefix.removeprefix("course-").isdigit():
        raise ValueError("Invalid upload namespace")
    if Path(upload.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(422, "Chỉ nhận file PDF.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}-{uuid4().hex}.pdf"
    target = UPLOAD_DIR / name
    try:
        size = 0
        with target.open("xb") as output:
            while chunk := upload.file.read(64 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "PDF vượt giới hạn dung lượng.")
                output.write(chunk)
        if not size:
            raise HTTPException(422, "File PDF không có nội dung.")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return Path(upload.filename or name).name, f"/api/files/{name}"
