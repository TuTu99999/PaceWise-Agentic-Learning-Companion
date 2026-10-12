"""Demo-only browser SSO: server-issued, short-lived, single-use POST tickets."""

import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.integration_api import require_service_key
from app.models import AuthSession, BrowserBridgeSession, BrowserBridgeTicket, User
from app.pacewise_contracts import course_actor
from app.security import hash_token, issue_session, set_browser_cookies

router = APIRouter()


def pacewise_origin() -> str:
    """One configured browser origin; never allow null or wildcard origins."""
    configured = urlsplit(os.getenv("PACEWISE_URL", "http://localhost:5173"))
    if configured.scheme not in {"http", "https"} or not configured.netloc or configured.username or configured.password:
        raise ValueError("PACEWISE_URL must be an HTTP(S) browser URL without credentials")
    return f"{configured.scheme}://{configured.netloc}"


class BridgeRequest(BaseModel):
    user_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    role: str
    session_reference: str = Field(pattern=r"^[a-f0-9]{64}$")


class RevokeRequest(BaseModel):
    user_id: int = Field(gt=0)
    session_reference: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.post("/api/pacewise/v1/browser-bridge", dependencies=[Depends(require_service_key)])
def create_bridge(payload: BridgeRequest, db: Session = Depends(get_db)) -> dict:
    actor = course_actor(db, payload.course_id, payload.user_id)
    if not actor or actor.role != payload.role:
        raise HTTPException(403, "Enrollment role changed; sign in again")
    now = datetime.now(UTC)
    db.execute(
        delete(BrowserBridgeTicket).where(
            (BrowserBridgeTicket.expires_at <= now)
            | (BrowserBridgeTicket.session_reference == payload.session_reference)
        )
    )
    code = secrets.token_urlsafe(32)
    expires_at = now + timedelta(seconds=60)
    db.add(
        BrowserBridgeTicket(
            token_hash=hash_token(code),
            user_id=actor.user_id,
            course_id=payload.course_id,
            role=actor.role,
            session_reference=payload.session_reference,
            expires_at=expires_at,
        )
    )
    db.commit()
    return {"code": code, "expires_in": 60}


@router.post("/api/pacewise/sso/consume")
def consume_bridge(request: Request, code: str = Form(min_length=32, max_length=128), db: Session = Depends(get_db)):
    if request.headers.get("origin") != pacewise_origin():
        raise HTTPException(403, "PaceWise origin required")
    now = datetime.now(UTC)
    ticket = db.get(BrowserBridgeTicket, hash_token(code))
    expires = (
        ticket.expires_at.replace(tzinfo=UTC)
        if ticket and ticket.expires_at.tzinfo is None
        else (ticket.expires_at if ticket else now)
    )
    if not ticket or ticket.consumed_at or expires <= now:
        raise HTTPException(401, "Bridge expired or already used; return to PaceWise")
    actor = course_actor(db, ticket.course_id, ticket.user_id)
    if not actor or actor.role != ticket.role:
        raise HTTPException(403, "Enrollment role changed; sign in again")
    claimed = db.execute(
        update(BrowserBridgeTicket)
        .where(
            BrowserBridgeTicket.token_hash == ticket.token_hash,
            BrowserBridgeTicket.consumed_at.is_(None),
            BrowserBridgeTicket.expires_at > now,
        )
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(401, "Bridge expired or already used")
    old_token = request.cookies.get("canvas_session")
    if old_token:
        db.execute(update(AuthSession).where(AuthSession.token_hash == hash_token(old_token)).values(revoked_at=now))
    access, csrf, session = issue_session(db, db.get(User, ticket.user_id))
    db.add(
        BrowserBridgeSession(
            auth_session_id=session.id, user_id=ticket.user_id, session_reference=ticket.session_reference
        )
    )
    db.commit()
    # Fetch must not follow a cross-origin redirect before navigation: it needs
    # to receive the session cookies and a CORS-readable acknowledgement first.
    wants_json = "application/json" in request.headers.get("accept", "").lower()
    response = JSONResponse({"redirect": "/"}) if wants_json else RedirectResponse("/", status_code=303)
    set_browser_cookies(response, access, csrf)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.post("/api/pacewise/v1/browser-bridge/revoke", dependencies=[Depends(require_service_key)])
def revoke_bridge(payload: RevokeRequest, db: Session = Depends(get_db)) -> dict:
    linked = select(BrowserBridgeSession.auth_session_id).where(
        BrowserBridgeSession.user_id == payload.user_id,
        BrowserBridgeSession.session_reference == payload.session_reference,
    )
    db.execute(update(AuthSession).where(AuthSession.id.in_(linked)).values(revoked_at=datetime.now(UTC)))
    db.execute(
        delete(BrowserBridgeTicket).where(
            BrowserBridgeTicket.user_id == payload.user_id,
            BrowserBridgeTicket.session_reference == payload.session_reference,
        )
    )
    db.commit()
    return {"ok": True}
