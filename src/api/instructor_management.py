"""Authenticated authoring facade. Writes go to the authoritative course source."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db import Base, SessionLocal, get_db
from src.persistence_models import PaceWiseSession, UserWorkspace
from src.security import SessionContext, get_current_session, require_csrf
from src.services.lms_client import LMSClient

router = APIRouter(prefix="/instructor/manage", tags=["Instructor authoring"])
_workbook_slots = asyncio.Semaphore(4)
logger = logging.getLogger(__name__)


def scope(session, course_id=None):
    if session.role != "instructor" or (course_id is not None and course_id not in session.course_ids):
        raise HTTPException(403, "Instructor course enrollment required")


async def forward(method, path, session, settings, payload=None):
    # No actor, arbitrary target URL, credentials or role may come from the body.
    if payload and any(key in payload for key in ("user_id", "role", "course_id", "headers")):
        raise HTTPException(422, "Acting identity is determined by the authenticated session")
    return await LMSClient(settings).teacher_request(
        method, "/api/pacewise/v1/teacher" + path, user_id=session.user_id, payload=payload
    )


@router.get("/profile")
async def profile(session: SessionContext = Depends(get_current_session), settings: Settings = Depends(get_settings)):
    scope(session)
    return await forward("GET", "/profile", session, settings)


@router.put("/profile")
async def update_profile(
    payload: dict, session: SessionContext = Depends(require_csrf), settings: Settings = Depends(get_settings)
):
    scope(session)
    return await forward("PUT", "/profile", session, settings, payload)


async def refresh_courses(session, settings, db):
    courses = await forward("GET", "/courses", session, settings)
    persist_course_scope(session, courses, db)
    return courses


def persist_course_scope(session, courses, db):
    active = [int(item["id"]) for item in courses if not item["archived"]]
    row = db.get(PaceWiseSession, session.sid)
    if row:
        row.course_ids_json = json.dumps(active)
        if row.active_course_id not in active and active:
            row.active_course_id = active[0]
        db.commit()


@router.get("/courses")
async def courses(
    session: SessionContext = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    scope(session)
    return await refresh_courses(session, settings, db)


@router.get("/roster")
async def roster(session: SessionContext = Depends(get_current_session), settings: Settings = Depends(get_settings)):
    scope(session)
    return await forward("GET", "/roster", session, settings)


@router.post("/courses", status_code=201)
async def new_course(
    payload: dict,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    scope(session)
    result = await forward("POST", "/courses", session, settings, payload)
    await refresh_courses(session, settings, db)
    return result


def assert_no_learning_history(db, course_id):
    # Domain history is protected even if simulator tasks have been removed outside PaceWise.
    excluded = {
        "pacewise_sessions",
        "pacewise_instructor_actions",
        "lms_file_indexes",
        "pacewise_course_projections",
        "pacewise_lms_course_contexts",
        "pacewise_lms_event_projections",
    }
    for table in Base.metadata.sorted_tables:
        if "course_id" in table.c and table.name not in excluded:
            if db.execute(select(table.c.course_id).where(table.c.course_id == course_id).limit(1)).first():
                raise HTTPException(409, "Môn đã có lịch sử học. Hãy lưu trữ thay vì xóa.")

    def refers(value):
        if isinstance(value, dict):
            if any(str(value.get(key, "")) == str(course_id) for key in ("courseId", "course_id")):
                return True
            return any(refers(item) for item in value.values())
        return isinstance(value, list) and any(refers(item) for item in value)

    for workspace in db.scalars(select(UserWorkspace)).all():
        if refers(json.loads(workspace.state_json)):
            raise HTTPException(409, "Môn đã được dùng trong kế hoạch. Hãy lưu trữ để giữ lịch sử.")
    db.commit()  # Release pool before waiting for the internal LMS.


@router.put("/courses/{course_id}/info")
async def course_info(
    course_id: int,
    payload: dict,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    scope(session)
    return await forward("PUT", f"/courses/{course_id}/info", session, settings, payload)


@router.post("/courses/{course_id}/lifecycle/{action}")
async def course_action(
    course_id: int,
    action: Literal["archive", "restore", "delete-empty"],
    payload: dict,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    scope(session)
    if action == "delete-empty":
        owned_courses = await forward("GET", "/courses", session, settings)
        if course_id not in {int(item["id"]) for item in owned_courses}:
            raise HTTPException(403, "Instructor course enrollment required")
        assert_no_learning_history(db, course_id)
    result = await forward("POST", f"/courses/{course_id}/{action}", session, settings, payload)
    await refresh_courses(session, settings, db)
    return result


class WorkbookInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_base64: str = Field(max_length=7_000_000)
    mode: Literal["append", "replace_future"] = "append"


@router.post("/schedule/import-preview")
async def import_preview(
    payload: WorkbookInput, session: SessionContext = Depends(require_csrf), settings: Settings = Depends(get_settings)
):
    from src.services.teacher_workbook import parse_workbook

    scope(session)
    courses = await forward("GET", "/courses", session, settings)
    async with _workbook_slots:
        rows, errors, new_courses = await asyncio.to_thread(
            parse_workbook, payload.data_base64, courses, include_course_definitions=True
        )
    if errors:
        return {"ticket": None, "errors": errors, "counts": {}, "applied": False, "items": [], "cancellations": []}
    return await forward(
        "POST",
        "/schedule/preview",
        session,
        settings,
        {
            "mode": payload.mode,
            "rows": rows,
            "course_ids": sorted({row["course_id"] for row in rows if row["course_id"] > 0}),
            "new_courses": new_courses,
        },
    )


@router.get("/schedule/history")
async def schedule_history(
    session: SessionContext = Depends(get_current_session), settings: Settings = Depends(get_settings)
):
    scope(session)
    return await forward("GET", "/schedule/history", session, settings)


@router.post("/schedule/{action}")
async def schedule_action(
    action: Literal["preview", "confirm", "restore", "demo-preview", "series-preview"],
    payload: dict,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    scope(session)
    # The source validates live ownership too (including all members' calendar copies).
    if action in {"preview", "demo-preview", "series-preview"}:
        identifiers = payload.get("course_ids")
        if not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 100 or any(
            type(identifier) is not int or identifier <= 0 for identifier in identifiers
        ):
            raise HTTPException(422, "Chọn từ 1 đến 100 môn hợp lệ.")
        for identifier in identifiers:
            scope(session, identifier)
    result = await forward("POST", f"/schedule/{action}", session, settings, payload)
    if action == "confirm" and int(result.get("counts", {}).get("courses", 0) or 0) > 0:
        # Fetch the remote state first, then acquire a local DB session briefly. Import waits never hold our pool.
        latest = await forward("GET", "/courses", session, settings)
        with SessionLocal() as db:
            persist_course_scope(session, latest, db)
    return result


@router.get("/courses/{course_id}")
async def snapshot(
    course_id: int, session: SessionContext = Depends(get_current_session), settings: Settings = Depends(get_settings)
):
    scope(session, course_id)
    return await forward("GET", f"/courses/{course_id}", session, settings)


@router.post("/courses/{course_id}/{resource}", status_code=201)
async def create(
    course_id: int,
    resource: Literal["tasks", "lessons", "pdf", "materials"],
    payload: dict,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    scope(session, course_id)
    return await forward("POST", f"/courses/{course_id}/{resource}", session, settings, payload)


def cleanup_owned_resource(source_url: str, settings: Settings) -> None:
    """Best-effort cleanup after the source transaction makes a file inaccessible."""
    if settings.course_source_mode != "standalone":
        return
    if source_url.startswith("pacewise-object://"):
        from src.services.course_object_store import delete_object, object_key

        delete_object(settings, object_key(source_url))
        return
    if not source_url.startswith("/api/files/"):
        return
    filename = source_url.removeprefix("/api/files/")
    directory = Path(settings.course_upload_dir).resolve()
    target = (directory / filename).resolve()
    if Path(filename).name != filename or target.parent != directory:
        logger.warning("Skipped invalid course resource path during cleanup")
        return
    target.unlink(missing_ok=True)


@router.delete("/courses/{course_id}/resources/{resource_id}")
async def delete_resource(
    course_id: int,
    resource_id: int,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    scope(session, course_id)
    result = await forward("DELETE", f"/courses/{course_id}/resources/{resource_id}", session, settings)
    source_url = str(result.pop("source_url", ""))
    should_delete = bool(result.pop("delete_stored_object", False))
    if should_delete and source_url:
        try:
            await asyncio.to_thread(cleanup_owned_resource, source_url, settings)
        except Exception:
            # Access has already been revoked and the deletion event will remove
            # the AI index. A storage lifecycle sweep can collect a rare orphan.
            logger.exception("Course resource metadata was deleted but object cleanup failed")
    return result


@router.put("/courses/{course_id}/weights")
async def weights(
    course_id: int,
    payload: dict,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    scope(session, course_id)
    return await forward("PUT", f"/courses/{course_id}/weights", session, settings, payload)


@router.put("/courses/{course_id}/{resource}/{item_id}")
async def update(
    course_id: int,
    resource: Literal["tasks", "lessons"],
    item_id: int,
    payload: dict,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    scope(session, course_id)
    return await forward("PUT", f"/courses/{course_id}/{resource}/{item_id}", session, settings, payload)


@router.post("/courses/{course_id}/{resource}/{item_id}/{action}")
async def archive(
    course_id: int,
    resource: Literal["tasks", "lessons"],
    item_id: int,
    action: Literal["archive", "cancel"],
    payload: dict,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    scope(session, course_id)
    if (resource, action) not in {("tasks", "archive"), ("lessons", "cancel")}:
        raise HTTPException(422, "Unsupported action")
    return await forward("POST", f"/courses/{course_id}/{resource}/{item_id}/{action}", session, settings, payload)
