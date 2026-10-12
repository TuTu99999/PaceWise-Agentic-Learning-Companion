import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db import SessionLocal, get_db
from src.persistence_models import PaceWiseSession


@dataclass(frozen=True)
class SessionContext:
    user_id: int
    course_id: int
    course_ids: tuple[int, ...]
    role: str
    name: str
    email: str
    csrf_hash: str
    sid: str
    exp: int

    def public_user(self) -> dict:
        return {
            "id": str(self.user_id),
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "course_id": str(self.course_id),
            "course_ids": [str(value) for value in self.course_ids],
        }


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret(settings: Settings) -> bytes:
    secret = settings.pacewise_session_secret.strip()
    if len(secret) < 32 or (
        settings.app_env in {"staging", "production"} and secret.startswith("development-only")
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PACEWISE_SESSION_SECRET must be a unique value of at least 32 characters",
        )
    return secret.encode()


def _sign(encoded: str, settings: Settings) -> str:
    return _b64encode(hmac.new(_secret(settings), encoded.encode(), hashlib.sha256).digest())


def issue_session(
    db: Session,
    claims: dict,
    settings: Settings,
    course_ids: list[int] | None = None,
) -> tuple[str, str]:
    role = claims.get("role")
    if role not in {"student", "instructor"}:
        raise HTTPException(status_code=403, detail="Unsupported LMS role")
    csrf_token = secrets.token_urlsafe(32)
    now = int(time.time())
    sid = secrets.token_urlsafe(24)
    selected = int(claims["course_id"])
    allowed = sorted(set(course_ids if course_ids is not None else ([selected] if selected > 0 else [])))
    if selected > 0 and selected not in allowed:
        allowed.append(int(claims["course_id"]))
    payload = {
        "iss": "pacewise-api",
        "aud": "pacewise-web",
        "sid": sid,
        "iat": now,
        "exp": now + settings.pacewise_session_minutes * 60,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    token = f"{encoded}.{_sign(encoded, settings)}"
    db.add(
        PaceWiseSession(
            id=sid,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            csrf_hash=hashlib.sha256(csrf_token.encode()).hexdigest(),
            user_id=int(claims["sub"]),
            role=role,
            name=str(claims.get("name", "")),
            email=str(claims.get("email", "")),
            active_course_id=int(claims["course_id"]),
            course_ids_json=json.dumps(allowed),
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.pacewise_session_minutes),
        )
    )
    db.commit()
    return token, csrf_token


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def live_membership(session: SessionContext, settings: Settings) -> SessionContext:
    if settings.course_source_mode != "standalone":
        return session
    from sqlalchemy import select

    from src.course_source.db import SessionLocal as SourceSession
    from src.course_source.models import Course, CourseLifecycle, Enrollment, User

    with SourceSession() as source:
        user = source.get(User, session.user_id)
        if not user or user.role != session.role:
            raise HTTPException(401, "Account is no longer available")
        allowed = tuple(
            source.scalars(
                select(Enrollment.course_id)
                .join(Course)
                .outerjoin(CourseLifecycle, CourseLifecycle.course_id == Course.id)
                .where(
                    Enrollment.user_id == session.user_id,
                    Enrollment.role == session.role,
                    (CourseLifecycle.archived.is_(False) | CourseLifecycle.course_id.is_(None)),
                    Course.published.is_(True) if session.role == "student" else True,
                )
                .order_by(Enrollment.course_id)
            )
        )
        return replace(
            session,
            course_ids=allowed,
            course_id=session.course_id if session.course_id in allowed else next(iter(allowed), 0),
        )


def decode_session(token: str, settings: Settings, db: Session) -> SessionContext:
    try:
        encoded, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, _sign(encoded, settings)):
            raise ValueError("signature")
        payload = json.loads(_b64decode(encoded))
        if payload.get("iss") != "pacewise-api" or payload.get("aud") != "pacewise-web":
            raise ValueError("audience")
        if int(payload["exp"]) <= int(time.time()):
            raise ValueError("expired")
        row = db.get(PaceWiseSession, str(payload["sid"]))
        if not row or row.revoked_at or _as_utc(row.expires_at) <= datetime.now(UTC):
            raise ValueError("revoked")
        if not hmac.compare_digest(row.token_hash, hashlib.sha256(token.encode()).hexdigest()):
            raise ValueError("token")
        if _as_utc(row.last_seen_at) < datetime.now(UTC) - timedelta(minutes=5):
            row.last_seen_at = datetime.now(UTC)
            db.commit()
        allowed = tuple(int(value) for value in json.loads(row.course_ids_json))
        return SessionContext(
            user_id=row.user_id,
            course_id=row.active_course_id,
            course_ids=allowed,
            role=row.role,
            name=row.name,
            email=row.email,
            csrf_hash=row.csrf_hash,
            sid=row.id,
            exp=int(payload["exp"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired PaceWise session") from exc


def get_current_session(
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> SessionContext:
    token = request.cookies.get(settings.pacewise_session_cookie, "")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    session = decode_session(token, settings, db)
    # End the authentication read transaction before async route work; retaining
    # every connection while awaiting upstream quota/I/O can exhaust the pool.
    db.commit()
    return live_membership(session, settings)


def get_detached_session(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> SessionContext:
    """Authenticate a long-lived request without retaining a DB connection.

    Streaming endpoints must not keep a SQLAlchemy session checked out for the
    entire lifetime of the client connection. Each stream poll opens its own
    short-lived session instead.
    """
    token = request.cookies.get(settings.pacewise_session_cookie, "")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    with SessionLocal() as db:
        session = decode_session(token, settings, db)
    return live_membership(session, settings)


def require_instructor(session: SessionContext = Depends(get_current_session)) -> SessionContext:
    if session.role != "instructor":
        raise HTTPException(status_code=403, detail="Instructor role required")
    return session


def require_course(course_id: int, session: SessionContext) -> None:
    if course_id not in session.course_ids:
        raise HTTPException(status_code=403, detail="Course is outside the authenticated LMS launch")


def require_csrf(
    request: Request,
    session: SessionContext = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
) -> SessionContext:
    header = request.headers.get("X-CSRF-Token", "")
    cookie = request.cookies.get(settings.pacewise_csrf_cookie, "")
    supplied_hash = hashlib.sha256(header.encode()).hexdigest() if header else ""
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    if not hmac.compare_digest(supplied_hash, session.csrf_hash):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    return session


def session_debug_payload(session: SessionContext) -> dict:
    """Intentionally excludes signed-token and CSRF material."""
    return {key: value for key, value in asdict(session).items() if key != "csrf_hash"}
