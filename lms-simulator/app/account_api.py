import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuthSession, NotificationPreference, PersonalFile, User, UserProfile
from app.security import hash_password, verify_password
from app.telemetry import record_change

router = APIRouter(prefix="/api/account", tags=["account"])

ACCOUNT_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads" / "personal"
ACCOUNT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_ACCOUNT_FILE_BYTES = 20 * 1024 * 1024
ALLOWED_ACCOUNT_FILE_SUFFIXES = {
    ".csv",
    ".doc",
    ".docx",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".txt",
    ".xlsx",
    ".zip",
}
NOTIFICATION_CATEGORIES = (
    "course_activities",
    "discussions",
    "conversations",
    "scheduling",
)
NOTIFICATION_FREQUENCIES = {"immediately", "daily", "weekly", "off"}


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    display_name: str = Field(min_length=2, max_length=255)
    pronouns: str = Field(default="", max_length=64)
    bio: str = Field(default="", max_length=2000)
    timezone: str = Field(default="Asia/Ho_Chi_Minh", max_length=64)
    language: str = Field(default="en", max_length=32)


class NotificationUpdate(BaseModel):
    preferences: dict[str, str]


class PasswordUpdate(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


def _current_user(request: Request, db: Session) -> User:
    user = db.get(User, request.state.current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _profile(db: Session, user: User) -> UserProfile:
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile:
        return profile
    profile = UserProfile(user_id=user.id, display_name=user.full_name)
    db.add(profile)
    db.flush()
    return profile


def _preferences(db: Session, user_id: int) -> list[NotificationPreference]:
    existing = {
        item.category: item
        for item in db.scalars(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        ).all()
    }
    for category in NOTIFICATION_CATEGORIES:
        if category not in existing:
            preference = NotificationPreference(
                user_id=user_id,
                category=category,
                frequency="daily",
            )
            db.add(preference)
            existing[category] = preference
    db.flush()
    return [existing[category] for category in NOTIFICATION_CATEGORIES]


def _file_payload(item: PersonalFile) -> dict:
    return {
        "id": item.id,
        "name": item.display_name,
        "content_type": item.content_type,
        "size_bytes": item.size_bytes,
        "created_at": item.created_at.isoformat(),
        "download_url": f"/api/account/files/{item.id}/download",
    }


def _account_payload(db: Session, user: User) -> dict:
    profile = _profile(db, user)
    preferences = _preferences(db, user.id)
    files = db.scalars(
        select(PersonalFile).where(PersonalFile.user_id == user.id).order_by(PersonalFile.created_at.desc())
    ).all()
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.full_name,
            "role": user.role,
            "avatar_color": user.avatar_color,
        },
        "profile": {
            "display_name": profile.display_name or user.full_name,
            "pronouns": profile.pronouns,
            "bio": profile.bio,
            "timezone": profile.timezone,
            "language": profile.language,
        },
        "notifications": {item.category: item.frequency for item in preferences},
        "files": [_file_payload(item) for item in files],
        "storage": {
            "used_bytes": sum(item.size_bytes for item in files),
            "quota_bytes": 100 * 1024 * 1024,
        },
    }


@router.get("")
def read_account(request: Request, db: Session = Depends(get_db)) -> dict:
    user = _current_user(request, db)
    payload = _account_payload(db, user)
    db.commit()
    return payload


@router.put("/profile")
def update_profile(payload: ProfileUpdate, request: Request, db: Session = Depends(get_db)) -> dict:
    user = _current_user(request, db)
    profile = _profile(db, user)
    full_name = payload.full_name.strip()
    display_name = payload.display_name.strip()
    if len(full_name) < 2 or len(display_name) < 2:
        raise HTTPException(status_code=422, detail="Names must contain at least two visible characters")
    user.full_name = full_name
    profile.display_name = display_name
    profile.pronouns = payload.pronouns.strip()
    profile.bio = payload.bio.strip()
    profile.timezone = payload.timezone.strip()
    profile.language = payload.language.strip()
    profile.updated_at = datetime.now(UTC)
    record_change(
        db,
        actor_user_id=user.id,
        action="account.profile.updated",
        entity_type="user",
        entity_id=user.id,
        metadata={"timezone": profile.timezone, "language": profile.language},
        emit_event=False,
    )
    result = _account_payload(db, user)
    db.commit()
    return result


@router.put("/notifications")
def update_notifications(
    payload: NotificationUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    user = _current_user(request, db)
    if set(payload.preferences) != set(NOTIFICATION_CATEGORIES):
        raise HTTPException(status_code=422, detail="Every notification category is required")
    invalid = set(payload.preferences.values()) - NOTIFICATION_FREQUENCIES
    if invalid:
        raise HTTPException(status_code=422, detail="Unsupported notification frequency")
    settings = {item.category: item for item in _preferences(db, user.id)}
    for category, frequency in payload.preferences.items():
        settings[category].frequency = frequency
    record_change(
        db,
        actor_user_id=user.id,
        action="account.notifications.updated",
        entity_type="user",
        entity_id=user.id,
        metadata={"preferences": payload.preferences},
        emit_event=False,
    )
    db.commit()
    return {"notifications": payload.preferences}


@router.post("/files", status_code=201)
def upload_personal_file(
    request: Request,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    user = _current_user(request, db)
    original_name = Path(upload.filename or "file").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_ACCOUNT_FILE_SUFFIXES:
        raise HTTPException(status_code=422, detail="Unsupported file type")
    stored_name = f"user-{user.id}-{uuid4().hex}{suffix}"
    target = ACCOUNT_UPLOAD_DIR / stored_name
    try:
        with target.open("wb") as output:
            shutil.copyfileobj(upload.file, output)
        size = target.stat().st_size
        if size > MAX_ACCOUNT_FILE_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds 20 MB")
        current_total = sum(
            db.scalars(select(PersonalFile.size_bytes).where(PersonalFile.user_id == user.id)).all()
        )
        if current_total + size > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Personal files quota exceeded")
        item = PersonalFile(
            user_id=user.id,
            display_name=original_name,
            stored_name=stored_name,
            content_type=upload.content_type or "application/octet-stream",
            size_bytes=size,
        )
        db.add(item)
        db.flush()
        record_change(
            db,
            actor_user_id=user.id,
            action="account.file.uploaded",
            entity_type="personal_file",
            entity_id=item.id,
            metadata={"name": original_name, "size_bytes": size},
            emit_event=False,
        )
        db.commit()
        return _file_payload(item)
    except Exception:
        if target.exists() and not db.scalar(select(PersonalFile).where(PersonalFile.stored_name == stored_name)):
            target.unlink(missing_ok=True)
        raise


@router.get("/files/{file_id}/download")
def download_personal_file(file_id: int, request: Request, db: Session = Depends(get_db)) -> FileResponse:
    user = _current_user(request, db)
    item = db.scalar(
        select(PersonalFile).where(PersonalFile.id == file_id, PersonalFile.user_id == user.id)
    )
    if not item:
        raise HTTPException(status_code=404, detail="File not found")
    target = ACCOUNT_UPLOAD_DIR / item.stored_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Stored file not found")
    return FileResponse(target, filename=item.display_name, media_type=item.content_type)


@router.delete("/files/{file_id}")
def delete_personal_file(file_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    user = _current_user(request, db)
    item = db.scalar(
        select(PersonalFile).where(PersonalFile.id == file_id, PersonalFile.user_id == user.id)
    )
    if not item:
        raise HTTPException(status_code=404, detail="File not found")
    target = ACCOUNT_UPLOAD_DIR / item.stored_name
    record_change(
        db,
        actor_user_id=user.id,
        action="account.file.deleted",
        entity_type="personal_file",
        entity_id=item.id,
        metadata={"name": item.display_name},
        emit_event=False,
    )
    db.delete(item)
    db.commit()
    target.unlink(missing_ok=True)
    return {"ok": True}


@router.put("/password")
def change_password(payload: PasswordUpdate, request: Request, db: Session = Depends(get_db)) -> dict:
    user = _current_user(request, db)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=422, detail="New password must be different")
    user.password_hash = hash_password(payload.new_password)
    sessions = db.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user.id,
            AuthSession.id != request.state.auth_session_id,
            AuthSession.revoked_at.is_(None),
        )
    ).all()
    now = datetime.now(UTC)
    for session in sessions:
        session.revoked_at = now
    record_change(
        db,
        actor_user_id=user.id,
        action="account.password.updated",
        entity_type="user",
        entity_id=user.id,
        metadata={"revoked_sessions": len(sessions)},
        emit_event=False,
    )
    db.commit()
    return {"ok": True, "revoked_sessions": len(sessions)}
