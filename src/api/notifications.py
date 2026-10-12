"""Student-only, CSRF-protected push subscriptions. No arbitrary URL delivery."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db import get_db
from src.persistence_models import NotificationJob, UserWorkspace, WebPushSubscription
from src.security import SessionContext, get_current_session, require_csrf
from src.services.notification_policy import ReminderPreferences
from src.services.web_push import daily_budget, utc, validate_subscription, vapid_keys

router = APIRouter(prefix="/notifications", tags=["Student notifications"])


def student(session: SessionContext):
    if session.role != "student":
        raise HTTPException(status_code=403, detail="Student notifications only")


class SubscriptionRequest(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2048)
    keys: dict[str, str]


@router.get("/push")
def push_status(
    session: SessionContext = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    student(session)
    try:
        _, public = vapid_keys(settings)
    except (OSError, ValueError):
        return {"configured": False, "publicKey": None, "subscribed": False}
    subscribed = (
        db.scalar(
            select(WebPushSubscription.id).where(
                WebPushSubscription.user_id == session.user_id, WebPushSubscription.session_id == session.sid
            )
        )
        is not None
    )
    return {"configured": True, "publicKey": public, "subscribed": subscribed}


@router.post("/push")
def subscribe(
    payload: SubscriptionRequest,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    student(session)
    try:
        vapid_keys(settings)
        subscription = validate_subscription(payload.model_dump())
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail="Invalid subscription or Web Push configuration") from exc
    key = hashlib.sha256(subscription["endpoint"].encode()).hexdigest()
    existing = db.get(WebPushSubscription, key)
    if existing and existing.user_id != session.user_id:
        raise HTTPException(status_code=409, detail="Unsubscribe this browser before connecting another account")
    subscriptions = list(db.scalars(select(WebPushSubscription).where(WebPushSubscription.user_id == session.user_id)))
    if not existing and len(subscriptions) >= 5:
        raise HTTPException(status_code=409, detail="At most five push devices per student")
    row = existing or WebPushSubscription(id=key, user_id=session.user_id)
    row.session_id, row.subscription_json = session.sid, json.dumps(subscription)
    db.add(row)
    db.commit()
    return {"ok": True}


@router.delete("/push")
def unsubscribe(session: SessionContext = Depends(require_csrf), db: Session = Depends(get_db)):
    student(session)
    db.execute(
        delete(WebPushSubscription).where(
            WebPushSubscription.user_id == session.user_id, WebPushSubscription.session_id == session.sid
        )
    )
    db.commit()
    return {"ok": True}


class ClaimRequest(BaseModel):
    ids: list[Annotated[str, Field(max_length=512)]] = Field(max_length=3)


@router.post("/claim")
def claim(payload: ClaimRequest, session: SessionContext = Depends(require_csrf), db: Session = Depends(get_db)):
    """Foreground notifications share receipts/cap with background delivery."""
    student(session)
    now = datetime.now(UTC)
    workspace = db.get(UserWorkspace, session.user_id)
    state = json.loads(workspace.state_json) if workspace else {}
    prefs = ReminderPreferences.model_validate((state.get("reminders") or {}).get("preferences") or {})
    if not prefs.enabled or not prefs.browser_enabled or prefs.push_enabled or prefs.quiet(now):
        return {"ids": []}
    budget = daily_budget(db, session.user_id, state, now)
    accepted = []
    for reminder_key in payload.ids:
        job = db.scalar(
            select(NotificationJob)
            .where(
                NotificationJob.user_id == session.user_id,
                NotificationJob.reminder_key == reminder_key,
                NotificationJob.status == "pending",
            )
            .with_for_update(skip_locked=True)
        )
        if (
            not job
            or not prefs.allows(job.kind)
            or not (utc(job.scheduled_at) <= now <= utc(job.expires_at))
            or budget.count >= prefs.daily_cap
        ):
            continue
        job.status, job.delivered_at = "delivered", now
        budget.count += 1
        accepted.append(reminder_key)
    db.commit()
    return {"ids": accepted}
