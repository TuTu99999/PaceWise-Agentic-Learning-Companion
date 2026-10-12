import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from urllib.parse import parse_qs

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.db import SessionLocal
from app.models import AuthSession, User


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"{base64.urlsafe_b64encode(salt).decode()}:{base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        salt_raw, expected_raw = encoded.split(":", 1)
        salt = base64.urlsafe_b64decode(salt_raw.encode())
        expected = base64.urlsafe_b64decode(expected_raw.encode())
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return hmac.compare_digest(actual, expected)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def set_browser_cookies(response, access: str, csrf: str) -> None:
    options = {"secure": os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
               "samesite": "lax", "max_age": int(os.getenv("SESSION_LIFETIME_HOURS", "12")) * 3600,
               "path": "/"}
    response.set_cookie("canvas_session", access, httponly=True, **options)
    response.set_cookie("canvas_csrf", csrf, httponly=False, **options)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def issue_session(db: Session, user: User) -> tuple[str, str, AuthSession]:
    access_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    lifetime_hours = int(os.getenv("SESSION_LIFETIME_HOURS", "12"))
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(access_token),
        csrf_hash=hash_token(csrf_token),
        expires_at=datetime.now(UTC) + timedelta(hours=lifetime_hours),
    )
    db.add(session)
    db.flush()
    return access_token, csrf_token, session


def find_session(db: Session, access_token: str) -> AuthSession | None:
    if not access_token:
        return None
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(access_token)))
    now = datetime.now(UTC)
    if not session or session.revoked_at or _as_utc(session.expires_at) <= now:
        return None
    if _as_utc(session.last_seen_at) < now - timedelta(minutes=5):
        session.last_seen_at = now
        db.commit()
    return session


def bearer_token(headers: dict[str, str]) -> str:
    authorization = headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    cookie_header = headers.get("cookie", "")
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get("canvas_session")
    return morsel.value if morsel else ""


def _claimed_actor_ids(path: str, query_string: bytes, body: bytes, content_type: str, method: str = "GET") -> set[int]:
    claimed: set[int] = set()
    query = parse_qs(query_string.decode(errors="ignore"))
    for key in ("user_id", "sender_id"):
        for value in query.get(key, []):
            if value.isdigit():
                claimed.add(int(value))

    path_patterns = (
        r"^/api/users/(\d+)$",
        r"^/api/dashboard/(\d+)$",
        r"^/api/inbox/(\d+)$",
    )
    for pattern in path_patterns:
        match = re.match(pattern, path)
        if match:
            claimed.add(int(match.group(1)))
    # GET /calendar/{user_id}, but PUT/DELETE /calendar/{event_id}.
    if method == "GET" and (match := re.match(r"^/api/calendar/(\d+)$", path)):
        claimed.add(int(match.group(1)))

    if body and "application/json" in content_type:
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        if isinstance(payload, dict):
            for key in ("user_id", "sender_id"):
                value = payload.get(key)
                if isinstance(value, int):
                    claimed.add(value)
    elif body and "multipart/form-data" in content_type:
        text = body.decode("latin-1", errors="ignore")
        for key in ("user_id", "sender_id"):
            match = re.search(rf'name="{key}"\r\n\r\n(\d+)', text)
            if match:
                claimed.add(int(match.group(1)))
    return claimed


class SessionAuthMiddleware:
    """Authenticate UI APIs and reject attempts to impersonate another user.

    Legacy handlers still accept actor IDs for backwards-compatible request
    shapes. This middleware binds every such claim to the authenticated session,
    so clients cannot select a different acting user.
    """

    PUBLIC_PATHS = {"/api/health"}
    EXEMPT_PREFIXES = ("/api/pacewise/v1",)
    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if (
            not path.startswith("/api/")
            or method == "OPTIONS"
            or path in self.PUBLIC_PATHS
            or (path in {"/api/session", "/api/pacewise/sso/consume"} and method == "POST")
            or path.startswith(self.EXEMPT_PREFIXES)
        ):
            await self.app(scope, receive, send)
            return

        body = b""
        more_body = True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        token = bearer_token(headers)
        db = SessionLocal()
        try:
            auth_session = find_session(db, token)
            if not auth_session:
                response = JSONResponse({"detail": "Authentication required"}, status_code=401)
                await response(scope, _empty_receive, send)
                return

            claimed_ids = _claimed_actor_ids(
                path,
                scope.get("query_string", b""),
                body,
                headers.get("content-type", ""),
                method,
            )
            if any(user_id != auth_session.user_id for user_id in claimed_ids):
                response = JSONResponse({"detail": "Authenticated user does not match request actor"}, status_code=403)
                await response(scope, _empty_receive, send)
                return

            if method in self.WRITE_METHODS and not headers.get("authorization", "").lower().startswith("bearer "):
                csrf_token = headers.get("x-csrf-token", "")
                if not csrf_token or not hmac.compare_digest(hash_token(csrf_token), auth_session.csrf_hash):
                    response = JSONResponse({"detail": "CSRF token required"}, status_code=403)
                    await response(scope, _empty_receive, send)
                    return

            scope.setdefault("state", {})["current_user_id"] = auth_session.user_id
            scope["state"]["auth_session_id"] = auth_session.id
        finally:
            db.close()

        sent = False

        async def replay_receive():
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay_receive, send)


async def _empty_receive():
    return {"type": "http.request", "body": b"", "more_body": False}
