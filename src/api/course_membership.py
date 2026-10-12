"""Authenticated public membership facade for the PaceWise-owned source."""

import json
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from src.config import Settings, get_settings
from src.course_source import membership
from src.course_source.db import SessionLocal
from src.security import SessionContext, get_current_session, require_csrf

router = APIRouter(tags=["Course membership"])


class InvitationsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    emails: list[str] = Field(min_length=1, max_length=50)


class KnownMembersInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_ids: list[int] = Field(min_length=1, max_length=1000)


def standalone(settings):
    if settings.course_source_mode != "standalone":
        raise HTTPException(503, "Membership is managed by the external course source")


def teacher(session, settings):
    standalone(settings)
    if session.role != "instructor":
        raise HTTPException(403, "Instructor required")


def notify(request, user_id):
    broker = getattr(request.app.state, "lms_event_broker", None)
    if broker:
        # Immediate local invalidation; durable source event covers other replicas.
        broker._publish(
            SimpleNamespace(
                event_type="enrollment.changed",
                course_id=None,
                source_event_id=0,
                payload_json=json.dumps({"target_user_id": user_id}),
            )
        )


@router.get("/instructor/manage/courses/{course_id}/members")
def course_members(
    course_id: int, session: SessionContext = Depends(get_current_session), settings: Settings = Depends(get_settings)
):
    teacher(session, settings)
    with SessionLocal() as db:
        return membership.members(db, course_id, session.user_id)


@router.post("/instructor/manage/courses/{course_id}/invitations", status_code=201)
def create_invitations(
    course_id: int,
    payload: InvitationsInput,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    teacher(session, settings)
    addresses = membership.emails(payload.emails)
    with SessionLocal() as db:
        membership.throttle(db, session.user_id)
        result = membership.invite_many(db, course_id, session.user_id, addresses)
        db.commit()
        return {"invitations": result, "emailSent": False}


@router.post("/instructor/manage/courses/{course_id}/invitations/{invite_id}/revoke")
def revoke_invitation(
    course_id: int,
    invite_id: str,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    teacher(session, settings)
    with SessionLocal() as db:
        membership.throttle(db, session.user_id)
        membership.revoke(db, course_id, session.user_id, invite_id)
        db.commit()
        return {"revoked": True}


@router.post("/instructor/manage/courses/{course_id}/members/{student_id}/remove")
def remove_student(
    course_id: int,
    student_id: int,
    request: Request,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    teacher(session, settings)
    with SessionLocal() as db:
        membership.throttle(db, session.user_id)
        membership.remove_member(db, course_id, session.user_id, student_id)
        db.commit()
    notify(request, student_id)
    return {"removed": True}


@router.post("/instructor/manage/courses/{course_id}/members/add")
def add_known_students(
    course_id: int,
    payload: KnownMembersInput,
    request: Request,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    teacher(session, settings)
    with SessionLocal() as db:
        membership.throttle(db, session.user_id)
        added = membership.add_members(db, course_id, session.user_id, payload.student_ids)
        db.commit()
    for user_id in added:
        notify(request, user_id)
    return {"added": len(added)}


@router.get("/membership/invitations")
def list_my_invitations(
    session: SessionContext = Depends(get_current_session), settings: Settings = Depends(get_settings)
):
    standalone(settings)
    with SessionLocal() as db:
        return {"invitations": membership.my_invites(db, session.user_id)}


@router.post("/membership/invitations/{invite_id}/accept")
def accept_my_invitation(
    invite_id: str,
    request: Request,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    standalone(settings)
    with SessionLocal() as db:
        membership.throttle(db, session.user_id)
        result = membership.accept_my_invite(db, session.user_id, invite_id)
        db.commit()
    notify(request, session.user_id)
    return result
