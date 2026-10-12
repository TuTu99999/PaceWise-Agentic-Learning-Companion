from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from src.api.google_signup import _account
from src.config import get_settings
from src.course_source.db import SessionLocal as CourseSession
from src.course_source.db import engine, initialize_database
from src.course_source.models import GoogleIdentity, User
from src.db import SessionLocal
from src.main import app
from src.persistence_models import GoogleCalendarConnection
from src.services.google_calendar import GoogleCalendarError, OAuthTokens


@pytest.fixture
def signup(auth_settings, monkeypatch):
    assert engine.dialect.name == "sqlite"
    initialize_database()
    with CourseSession() as db:
        db.query(GoogleIdentity).delete()
        db.query(User).filter(User.email.in_(["new@gmail.com", "existing@gmail.com"])).delete()
        db.commit()
    settings = auth_settings.model_copy(
        update={
            "course_source_mode": "standalone",
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_token_encryption_key": Fernet.generate_key().decode(),
        }
    )
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.exchange_code",
        AsyncMock(return_value=OAuthTokens("access", None, "openid email profile")),
    )

    class ProfileResponse:
        def json(self):
            return {
                "sub": "verified-google-subject",
                "email": "new@gmail.com",
                "name": "New student",
                "email_verified": True,
            }

    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient._get", AsyncMock(return_value=ProfileResponse())
    )
    yield settings


async def begin(client):
    response = await client.post("/api/v1/auth/google/start", json={})
    assert response.status_code == 200
    url = urlsplit(response.json()["authorizationUrl"])
    params = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    assert params["scope"] == ["openid email profile"]
    assert "calendar" not in params["scope"][0]
    assert params["code_challenge_method"] == ["S256"]
    assert "login_hint" not in params
    assert params["prompt"] == ["select_account"]
    assert "HttpOnly" in response.headers["set-cookie"]
    return params["state"][0]


@pytest.mark.asyncio
async def test_signup_creates_student_without_course_or_calendar_access(client, signup):
    state = await begin(client)
    result = await client.get("/api/v1/integrations/google-calendar/callback", params={"state": state, "code": "code"})
    assert result.status_code == 303 and "#/settings?welcome=1" in result.headers["location"]
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["role"] == "student" and me.json()["user"]["courseIds"] == []
    assert (await client.post("/api/v1/chat", json={"message": "test"})).status_code in {403, 422}
    with SessionLocal() as db:
        assert db.get(GoogleCalendarConnection, int(me.json()["user"]["id"])) is None
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT email, full_name FROM users WHERE password_hash = 'google-only'")).first()
    assert stored.email.startswith("pwenc:v1:") and "new@gmail.com" not in stored.email
    assert stored.full_name.startswith("pwenc:v1:")
    # Reusing a consumed state fails even if the browser cookie is restored.
    client.cookies.set("pacewise_google_signup", "unknown")
    replay = await client.get("/api/v1/integrations/google-calendar/callback", params={"state": state, "code": "code"})
    assert replay.status_code == 400


@pytest.mark.asyncio
async def test_cookie_binding_denial_and_untrusted_fields(client, signup):
    assert (
        await client.post("/api/v1/auth/google/start", json={"role": "instructor"})
    ).status_code == 422
    state = await begin(client)
    browser = client.cookies["pacewise_google_signup"]
    client.cookies.clear()
    missing = await client.get("/api/v1/integrations/google-calendar/callback", params={"state": state, "code": "code"})
    assert missing.status_code == 400
    client.cookies.set("pacewise_google_signup", browser)
    denied = await client.get(
        "/api/v1/integrations/google-calendar/callback", params={"state": state, "error": "access_denied"}
    )
    assert denied.status_code == 303 and "google_auth=denied" in denied.headers["location"]
    client.cookies.set("pacewise_google_signup", browser)
    replay = await client.get("/api/v1/integrations/google-calendar/callback", params={"state": state, "code": "code"})
    assert replay.status_code == 400


@pytest.mark.asyncio
async def test_signin_rate_limit_applies_to_account_chooser(client, signup):
    for index in range(signup.login_rate_limit):
        result = await client.post("/api/v1/auth/google/start", json={})
        assert result.status_code == 200
    result = await client.post("/api/v1/auth/google/start", json={})
    assert result.status_code == 429


def test_existing_native_account_not_silently_linked(signup):
    with CourseSession() as db:
        db.add(User(email="existing@gmail.com", full_name="Existing", role="instructor", password_hash="preserved"))
        db.commit()
    with pytest.raises(GoogleCalendarError, match="native_account_exists"):
        _account({"sub": "other-subject", "email": "existing@gmail.com", "email_verified": True})
    with CourseSession() as db:
        assert db.get(GoogleIdentity, "other-subject") is None


@pytest.mark.parametrize(
    "profile",
    [
        {"sub": "id", "email": "new@gmail.com", "email_verified": False},
        {"sub": "id", "email": "foreign@example.com", "email_verified": True},
    ],
)
def test_unverified_or_non_gmail_identity_rejected(signup, profile):
    with pytest.raises(GoogleCalendarError):
        _account(profile)


def test_verified_identity_reuses_account(signup):
    profile = {"sub": "same-sub", "email": "new@gmail.com", "name": "New", "email_verified": True}
    first, _ = _account(profile)
    second, _ = _account(profile)
    assert first["sub"] == second["sub"]
