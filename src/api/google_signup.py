"""Google-verified student registration. Calendar remains an independent consent."""

import asyncio
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, String, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from src.api.lms_integration import _set_session_cookies
from src.api.workspace import check_login_rate_limit, record_failed_login
from src.config import Settings, get_settings
from src.db import Base, get_db
from src.services.customer_crypto import EncryptedText
from src.services.google_calendar import (
    GOOGLE_AUTHORIZE_URL,
    GOOGLE_USERINFO_URL,
    GoogleCalendarClient,
    GoogleCalendarError,
    hash_oauth_state,
    new_oauth_state,
    new_pkce_pair,
)

router = APIRouter(prefix="/auth/google", tags=["Google sign-in"])
COOKIE = "pacewise_google_signup"


class GoogleSignInState(Base):
    __tablename__ = "pacewise_google_signin_states"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    cookie_hash: Mapped[str] = mapped_column(String(64))
    verifier: Mapped[str] = mapped_column(EncryptedText("google-signin-verifier"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def enabled(settings):
    return (
        settings.course_source_mode == "standalone"
        and settings.google_signup_enabled
        and GoogleCalendarClient(settings).configured
    )


def _return(settings, error=None):
    parts = urlsplit(settings.google_oauth_success_url)
    fragment = "/signup?" + urlencode({"google_auth": error}) if error else "/settings?welcome=1"
    return RedirectResponse(urlunsplit((parts.scheme, parts.netloc, parts.path, "", fragment)), status_code=303)


@router.get("/status")
def status(settings: Settings = Depends(get_settings)):
    return {"configured": enabled(settings)}


@router.post("/start")
def start(
    payload: SignInRequest,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    if not enabled(settings):
        raise HTTPException(503, "Google registration is unavailable")
    # A fixed per-IP bucket prevents bypass by changing the typed email hint.
    check_login_rate_limit(request, "google-signin", db, settings)
    record_failed_login(request, "google-signin", db)
    state, browser = "signup." + new_oauth_state(), secrets.token_urlsafe(32)
    verifier, challenge = new_pkce_pair()
    now = datetime.now(UTC)
    db.execute(delete(GoogleSignInState).where(GoogleSignInState.expires_at < now))
    db.add(
        GoogleSignInState(
            state_hash=hash_oauth_state(state),
            cookie_hash=hashlib.sha256(browser.encode()).hexdigest(),
            verifier=verifier,
            expires_at=now + timedelta(minutes=10),
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE,
        browser,
        max_age=600,
        httponly=True,
        samesite="lax",
        path="/",
        secure=settings.session_cookie_secure or settings.force_https or settings.app_env == "production",
    )
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return {"authorizationUrl": GOOGLE_AUTHORIZE_URL + "?" + urlencode(params)}


def _identity(profile):
    email, subject = profile.get("email", ""), profile.get("sub", "")
    if (
        profile.get("email_verified") is not True
        or not isinstance(email, str)
        or not email.lower().endswith("@gmail.com")
        or not isinstance(subject, str)
        or not subject
        or len(subject) > 255
    ):
        raise GoogleCalendarError("Verified Gmail identity required")
    return email.strip().lower(), subject, str(profile.get("name") or "Sinh viên")[:255]


def _account(profile, settings: Settings | None = None):
    from src.course_source.db import SessionLocal
    from src.course_source.models import Course, CourseLifecycle, Enrollment, GoogleIdentity, User

    email, subject, name = _identity(profile)
    with SessionLocal() as db:
        identity = db.get(GoogleIdentity, subject)
        if identity:
            user = db.get(User, identity.user_id)
        else:
            # Never silently link an existing native account by email alone.
            if db.scalar(select(User.id).where(User.email == email)):
                raise GoogleCalendarError("native_account_exists")
            user = User(email=email, full_name=name, role="student", password_hash="google-only")
            db.add(user)
            db.flush()
            db.add(GoogleIdentity(subject=subject, user_id=user.id))
            db.commit()
        if not user or user.role != "student":
            raise GoogleCalendarError("Student identity required")
        if (settings or get_settings()).google_signup_auto_enroll_courses:
            from src.course_source.membership import auto_enroll_google_student

            auto_enroll_google_student(
                db,
                user.id,
                (settings or get_settings()).google_signup_auto_enroll_teacher_email,
            )
            db.commit()
        courses = list(
            db.scalars(
                select(Enrollment.course_id)
                .join(Course, Course.id == Enrollment.course_id)
                .outerjoin(CourseLifecycle, CourseLifecycle.course_id == Course.id)
                .where(
                    Enrollment.user_id == user.id,
                    Enrollment.role == "student",
                    (CourseLifecycle.archived.is_(False) | CourseLifecycle.course_id.is_(None)),
                )
                .order_by(Enrollment.course_id)
            )
        )
        claims = {
            "sub": str(user.id),
            "course_id": courses[0] if courses else 0,
            "role": "student",
            "name": user.full_name,
            "email": user.email,
        }
        return claims, courses


async def callback(state, code, error, request, settings, db):
    if not enabled(settings):
        raise HTTPException(503, "Google registration is unavailable")
    row = db.get(GoogleSignInState, hash_oauth_state(state))
    browser = request.cookies.get(COOKIE, "")
    if not row or not browser or not hmac.compare_digest(row.cookie_hash, hashlib.sha256(browser.encode()).hexdigest()):
        raise HTTPException(400, "Invalid Google sign-in state")
    now = datetime.now(UTC)
    verifier = row.verifier
    consumed = db.execute(
        update(GoogleSignInState)
        .where(
            GoogleSignInState.state_hash == row.state_hash,
            GoogleSignInState.used_at.is_(None),
            GoogleSignInState.expires_at > now,
        )
        .values(used_at=now)
        .execution_options(synchronize_session=False)
    ).rowcount
    db.commit()  # Atomic single-use + return connection before Google I/O.
    if not consumed:
        raise HTTPException(400, "Expired or used Google sign-in state")
    result = _return(settings, "denied")
    if not error and code:
        try:
            client = GoogleCalendarClient(settings)
            tokens = await client.exchange_code(code, verifier)
            upstream = await client._get(
                GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {tokens.access_token}"}
            )
            claims, courses = await asyncio.to_thread(_account, upstream.json(), settings)
            result = _return(settings)
            _set_session_cookies(result, claims, settings, db, courses)
        except GoogleCalendarError as exc:
            result = _return(settings, "existing" if str(exc) == "native_account_exists" else "failed")
        except (IntegrityError, ValueError, TypeError):
            db.rollback()
            result = _return(settings, "failed")
    result.delete_cookie(COOKIE, path="/")
    return result
