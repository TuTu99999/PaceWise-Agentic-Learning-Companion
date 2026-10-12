import hashlib
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from src.api.google_calendar import FreeBusyRequest
from src.config import Settings, get_settings
from src.db import SessionLocal
from src.main import app
from src.persistence_models import (
    GoogleCalendarConnection,
    GoogleCalendarEventLink,
    GoogleOAuthState,
    IntegrationAuditLog,
)
from src.security import decode_session
from src.services.google_calendar import GoogleCalendarError, OAuthTokens, TokenCipher


@pytest.fixture
def calendar_settings():
    settings = Settings(
        _env_file=None,
        app_env="test",
        pacewise_api_key="test-service-key",
        pacewise_session_secret="test-session-secret-with-at-least-32-characters",
        google_client_id="google-client-id",
        google_client_secret="google-client-secret",
        google_token_encryption_key=Fernet.generate_key().decode(),
        google_oauth_success_url="http://localhost:5173/app#/settings",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture(autouse=True)
def clean_google_calendar_tables():
    with SessionLocal() as db:
        db.query(GoogleCalendarEventLink).delete()
        db.query(GoogleCalendarConnection).delete()
        db.query(GoogleOAuthState).delete()
        db.query(IntegrationAuditLog).delete()
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(GoogleCalendarEventLink).delete()
        db.query(GoogleCalendarConnection).delete()
        db.query(GoogleOAuthState).delete()
        db.query(IntegrationAuditLog).delete()
        db.commit()


async def login_student(client, monkeypatch, role="student"):
    claims = {
        "iss": "canvas-lms-simulator",
        "aud": "pacewise",
        "sub": "42",
        "course_id": 7,
        "role": role,
        "name": "Calendar Student",
        "email": "student@example.edu",
    }
    monkeypatch.setattr("src.services.lms_client.LMSClient.verify_launch", AsyncMock(return_value=claims))
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.service_get",
        AsyncMock(return_value=[{"id": 7}]),
    )
    response = await client.post("/api/v1/auth/lms-launch", json={"token": "x" * 40})
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies["pacewise_csrf"]}


@pytest.mark.asyncio
async def test_connect_uses_minimal_scopes_state_and_pkce(client, monkeypatch, calendar_settings):
    headers = await login_student(client, monkeypatch)

    response = await client.post("/api/v1/integrations/google-calendar/connect", headers=headers)

    assert response.status_code == 200
    authorization_url = response.json()["authorizationUrl"]
    query = parse_qs(urlparse(authorization_url).query)
    assert query["access_type"] == ["offline"]
    assert query["code_challenge_method"] == ["S256"]
    assert set(query["scope"][0].split()) == set(calendar_settings.google_calendar_scopes.split())
    with SessionLocal() as db:
        state = db.get(GoogleOAuthState, hashlib.sha256(query["state"][0].encode()).hexdigest())
        assert state is not None
        assert state.session_id
        assert "google" not in state.encrypted_code_verifier.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("email_scope", ["email", "https://www.googleapis.com/auth/userinfo.email"])
async def test_callback_encrypts_refresh_token_and_rejects_replay(client, monkeypatch, calendar_settings, email_scope):
    headers = await login_student(client, monkeypatch)
    started = await client.post("/api/v1/integrations/google-calendar/connect", headers=headers)
    state = parse_qs(urlparse(started.json()["authorizationUrl"]).query)["state"][0]
    with SessionLocal() as db:
        state_row = db.get(GoogleOAuthState, hashlib.sha256(state.encode()).hexdigest())
        session = decode_session(client.cookies["pacewise_session"], calendar_settings, db)
        assert state_row is not None
        assert state_row.session_id == session.sid
    exchange = AsyncMock(
        return_value=OAuthTokens(
            access_token="short-lived-access-token",
            refresh_token="long-lived-refresh-token",
            scope=calendar_settings.google_calendar_scopes.replace("email", email_scope),
        )
    )
    monkeypatch.setattr("src.services.google_calendar.GoogleCalendarClient.exchange_code", exchange)

    callback = await client.get(
        "/api/v1/integrations/google-calendar/callback",
        params={"state": state, "code": "authorization-code"},
        follow_redirects=False,
    )
    assert callback.status_code == 303, callback.text
    replay = await client.get(
        "/api/v1/integrations/google-calendar/callback",
        params={"state": state, "code": "authorization-code"},
        follow_redirects=False,
    )

    assert "google_calendar=connected" in callback.headers["location"]
    returned = urlparse(callback.headers["location"])
    assert returned.path == "/app"
    assert returned.fragment == "/settings?google_calendar=connected"
    assert replay.status_code == 400
    with SessionLocal() as db:
        connection = db.get(GoogleCalendarConnection, 42)
        assert connection is not None
        assert "long-lived-refresh-token" not in connection.encrypted_refresh_token
        assert TokenCipher(calendar_settings).decrypt(connection.encrypted_refresh_token) == "long-lived-refresh-token"


def add_connection(settings: Settings) -> None:
    with SessionLocal() as db:
        db.add(
            GoogleCalendarConnection(
                user_id=42,
                encrypted_refresh_token=TokenCipher(settings).encrypt("refresh-token"),
                granted_scopes=settings.google_calendar_scopes,
            )
        )
        db.commit()


@pytest.mark.asyncio
async def test_freebusy_converts_google_intervals_without_event_details(client, monkeypatch, calendar_settings):
    headers = await login_student(client, monkeypatch)
    add_connection(calendar_settings)
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.access_token", AsyncMock(return_value="access")
    )
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.freebusy",
        AsyncMock(
            return_value=[
                {"start": "2026-09-29T09:00:00+07:00", "end": "2026-09-29T10:30:00+07:00"},
            ]
        ),
    )

    response = await client.post(
        "/api/v1/integrations/google-calendar/freebusy",
        headers=headers,
        json={
            "timeMin": "2026-09-28T00:00:00+07:00",
            "timeMax": "2026-10-05T00:00:00+07:00",
            "timeZone": "Asia/Ho_Chi_Minh",
        },
    )

    assert response.status_code == 200
    assert response.json()["unavailableSlots"][0] == {
        "id": "google-2026-09-29-0900-1030",
        "label": "Google Calendar",
        "date": "2026-09-29",
        "weekday": 1,
        "start": "09:00",
        "end": "10:30",
    }
    assert "summary" not in response.text


@pytest.mark.asyncio
async def test_event_export_requires_confirmation_and_is_idempotent(client, monkeypatch, calendar_settings):
    headers = await login_student(client, monkeypatch)
    add_connection(calendar_settings)
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.access_token", AsyncMock(return_value="access")
    )
    create = AsyncMock(return_value={"id": "google-event-1", "htmlLink": "https://calendar.google.com/event/1"})
    monkeypatch.setattr("src.services.google_calendar.GoogleCalendarClient.create_event", create)
    payload = {
        "confirmed": False,
        "timeZone": "Asia/Ho_Chi_Minh",
        "blocks": [
            {
                "blockId": "plan-1:block-1",
                "title": "PaceWise: Ôn tập",
                "start": "2026-09-29T19:00:00+07:00",
                "end": "2026-09-29T20:00:00+07:00",
            }
        ],
    }

    rejected = await client.post("/api/v1/integrations/google-calendar/events", headers=headers, json=payload)
    payload["confirmed"] = True
    created = await client.post("/api/v1/integrations/google-calendar/events", headers=headers, json=payload)
    duplicate = await client.post("/api/v1/integrations/google-calendar/events", headers=headers, json=payload)

    assert rejected.status_code == 409
    assert created.status_code == 200
    assert created.json()["created"][0]["eventId"] == "google-event-1"
    assert duplicate.json() == {"created": [], "skipped": ["plan-1:block-1"]}
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_revokes_google_token_before_removing_connection(client, monkeypatch, calendar_settings):
    headers = await login_student(client, monkeypatch)
    add_connection(calendar_settings)
    revoke = AsyncMock(return_value=None)
    monkeypatch.setattr("src.services.google_calendar.GoogleCalendarClient.revoke", revoke)

    response = await client.delete("/api/v1/integrations/google-calendar", headers=headers)

    assert response.status_code == 200
    revoke.assert_awaited_once_with("refresh-token")
    with SessionLocal() as db:
        assert db.get(GoogleCalendarConnection, 42) is None


@pytest.mark.asyncio
async def test_status_displays_the_connected_google_account(client, monkeypatch, calendar_settings):
    await login_student(client, monkeypatch)
    add_connection(calendar_settings)
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.access_token", AsyncMock(return_value="access")
    )
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.account_email",
        AsyncMock(return_value="personal.calendar@gmail.com"),
    )

    response = await client.get("/api/v1/integrations/google-calendar/status")

    assert response.status_code == 200
    assert response.json()["accountEmail"] == "personal.calendar@gmail.com"
    repeated = await client.get("/api/v1/integrations/google-calendar/status")
    assert repeated.status_code == 200
    from src.services.google_calendar import GoogleCalendarClient

    assert GoogleCalendarClient.account_email.await_count == 1


@pytest.mark.asyncio
async def test_freebusy_cache_is_encrypted_and_repeated_reads_avoid_google(client, monkeypatch, calendar_settings):
    from src.persistence_models import GoogleReadCache

    headers = await login_student(client, monkeypatch)
    add_connection(calendar_settings)
    access = AsyncMock(return_value="access")
    read = AsyncMock(return_value=[{"start": "2026-10-12T08:00:00Z", "end": "2026-10-12T09:00:00Z"}])
    monkeypatch.setattr("src.services.google_calendar.GoogleCalendarClient.access_token", access)
    monkeypatch.setattr("src.services.google_calendar.GoogleCalendarClient.freebusy", read)
    payload = {"timeMin": "2026-10-12T00:00:00Z", "timeMax": "2026-10-13T00:00:00Z", "timeZone": "UTC"}
    first = await client.post("/api/v1/integrations/google-calendar/freebusy", headers=headers, json=payload)
    second = await client.post("/api/v1/integrations/google-calendar/freebusy", headers=headers, json=payload)
    assert first.status_code == second.status_code == 200 and first.json() == second.json()
    assert access.await_count == read.await_count == 1
    with SessionLocal() as db:
        cached = db.query(GoogleReadCache).filter_by(user_id=42).all()
        assert cached and all("2026-10-12" not in row.encrypted_json for row in cached)


@pytest.mark.asyncio
async def test_export_rate_limit_preserves_partial_progress_and_retry(client, monkeypatch, calendar_settings):
    from src.services.calendar_quota import CalendarQuotaExceeded

    headers = await login_student(client, monkeypatch)
    add_connection(calendar_settings)
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.access_token", AsyncMock(return_value="access")
    )
    create = AsyncMock(side_effect=[{"id": "one"}, CalendarQuotaExceeded(20), {"id": "two"}])
    monkeypatch.setattr("src.services.google_calendar.GoogleCalendarClient.create_event", create)
    payload = {
        "confirmed": True,
        "timeZone": "UTC",
        "blocks": [
            {"blockId": block, "title": "Study", "start": "2026-10-12T10:00:00Z", "end": "2026-10-12T11:00:00Z"}
            for block in ["one", "two"]
        ],
    }
    first = await client.post("/api/v1/integrations/google-calendar/events", json=payload, headers=headers)
    assert first.status_code == 429 and first.headers["Retry-After"] == "20"
    assert first.headers["X-PaceWise-Partial-Created"] == "1"
    second = await client.post("/api/v1/integrations/google-calendar/events", json=payload, headers=headers)
    assert second.status_code == 200 and second.json()["skipped"] == ["one"]
    assert len(second.json()["created"]) == 1 and create.await_count == 3


@pytest.mark.asyncio
async def test_instructor_cannot_connect_personal_calendar(client, monkeypatch, calendar_settings):
    headers = await login_student(client, monkeypatch, role="instructor")
    response = await client.post("/api/v1/integrations/google-calendar/connect", headers=headers)
    assert response.status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {
            "timeMin": "2026-10-02T10:00:00+07:00",
            "timeMax": "2026-10-02T09:00:00+07:00",
            "timeZone": "Asia/Ho_Chi_Minh",
        },
        {
            "timeMin": "2026-10-01T00:00:00+07:00",
            "timeMax": "2026-12-01T00:00:00+07:00",
            "timeZone": "Asia/Ho_Chi_Minh",
        },
        {
            "timeMin": "2026-10-01T00:00:00+07:00",
            "timeMax": "2026-10-02T00:00:00+07:00",
            "timeZone": "Mars/Olympus_Mons",
        },
    ],
)
def test_freebusy_request_rejects_invalid_windows_and_timezones(payload):
    with pytest.raises(ValidationError):
        FreeBusyRequest.model_validate(payload)


@pytest.mark.asyncio
async def test_status_hides_provider_error_and_multiday_busy_is_split(client, monkeypatch, calendar_settings):
    headers = await login_student(client, monkeypatch)
    add_connection(calendar_settings)
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.access_token",
        AsyncMock(side_effect=GoogleCalendarError("provider unavailable")),
    )
    status_response = await client.get("/api/v1/integrations/google-calendar/status")
    assert status_response.status_code == 200
    assert status_response.json()["accountEmail"] is None

    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.access_token",
        AsyncMock(return_value="access"),
    )
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.freebusy",
        AsyncMock(return_value=[{"start": "2026-10-02T23:00:00+07:00", "end": "2026-10-04T01:00:00+07:00"}]),
    )
    response = await client.post(
        "/api/v1/integrations/google-calendar/freebusy",
        headers=headers,
        json={
            "timeMin": "2026-10-02T00:00:00+07:00",
            "timeMax": "2026-10-05T00:00:00+07:00",
            "timeZone": "Asia/Ho_Chi_Minh",
        },
    )
    assert [slot["date"] for slot in response.json()["unavailableSlots"]] == [
        "2026-10-02",
        "2026-10-03",
        "2026-10-04",
    ]


@pytest.mark.asyncio
async def test_callback_handles_denial_missing_refresh_and_existing_connection(client, monkeypatch, calendar_settings):
    headers = await login_student(client, monkeypatch)

    async def new_state():
        started = await client.post("/api/v1/integrations/google-calendar/connect", headers=headers)
        return parse_qs(urlparse(started.json()["authorizationUrl"]).query)["state"][0]

    denied_state = await new_state()
    denied = await client.get(
        "/api/v1/integrations/google-calendar/callback",
        params={"state": denied_state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert "google_calendar=denied" in denied.headers["location"]
    assert urlparse(denied.headers["location"]).path == "/app"

    missing_state = await new_state()
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.exchange_code",
        AsyncMock(
            return_value=OAuthTokens(
                access_token="access",
                refresh_token="",
                scope=calendar_settings.google_calendar_scopes,
            )
        ),
    )
    missing = await client.get(
        "/api/v1/integrations/google-calendar/callback",
        params={"state": missing_state, "code": "code"},
        follow_redirects=False,
    )
    assert "google_calendar=error" in missing.headers["location"]
    assert urlparse(missing.headers["location"]).path == "/app"

    add_connection(calendar_settings)
    existing_state = await new_state()
    existing = await client.get(
        "/api/v1/integrations/google-calendar/callback",
        params={"state": existing_state, "code": "code"},
        follow_redirects=False,
    )
    assert "google_calendar=connected" in existing.headers["location"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "granted_scopes",
    [
        "https://www.googleapis.com/auth/calendar.freebusy",
        "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/calendar.freebusy",
        "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/calendar.events.owned",
        "openid https://www.googleapis.com/auth/calendar.freebusy https://www.googleapis.com/auth/calendar.events.owned",
        "openid https://www.googleapis.com/auth/userinfo.email calendar",
        "",
    ],
)
async def test_callback_rejects_missing_required_scope(client, monkeypatch, calendar_settings, granted_scopes):
    headers = await login_student(client, monkeypatch)
    started = await client.post("/api/v1/integrations/google-calendar/connect", headers=headers)
    state = parse_qs(urlparse(started.json()["authorizationUrl"]).query)["state"][0]
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.exchange_code",
        AsyncMock(
            return_value=OAuthTokens(
                access_token="access",
                refresh_token="refresh",
                scope=granted_scopes,
            )
        ),
    )
    response = await client.get(
        "/api/v1/integrations/google-calendar/callback",
        # Browser-supplied scope must not override the token endpoint's grant.
        params={"state": state, "code": "code", "scope": calendar_settings.google_calendar_scopes},
        follow_redirects=False,
    )
    assert "google_calendar=error" in response.headers["location"]
    assert urlparse(response.headers["location"]).path == "/app"
    with SessionLocal() as db:
        assert db.get(GoogleCalendarConnection, 42) is None


@pytest.mark.asyncio
async def test_provider_failures_return_gateway_errors(client, monkeypatch, calendar_settings):
    headers = await login_student(client, monkeypatch)
    add_connection(calendar_settings)
    provider_error = AsyncMock(side_effect=GoogleCalendarError("provider timeout"))
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.access_token",
        provider_error,
    )
    window = {
        "timeMin": "2026-10-02T00:00:00+07:00",
        "timeMax": "2026-10-03T00:00:00+07:00",
        "timeZone": "Asia/Ho_Chi_Minh",
    }
    assert (
        await client.post("/api/v1/integrations/google-calendar/freebusy", headers=headers, json=window)
    ).status_code == 502
    event_payload = {
        "confirmed": True,
        "timeZone": "Asia/Ho_Chi_Minh",
        "blocks": [
            {
                "blockId": "failure-block",
                "title": "Study",
                "start": "2026-10-02T09:00:00+07:00",
                "end": "2026-10-02T10:00:00+07:00",
            }
        ],
    }
    assert (
        await client.post("/api/v1/integrations/google-calendar/events", headers=headers, json=event_payload)
    ).status_code == 502

    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.revoke",
        AsyncMock(side_effect=GoogleCalendarError("revocation failed")),
    )
    assert (await client.delete("/api/v1/integrations/google-calendar", headers=headers)).status_code == 502


@pytest.mark.asyncio
async def test_event_creation_failure_reports_partial_progress(client, monkeypatch, calendar_settings):
    headers = await login_student(client, monkeypatch)
    add_connection(calendar_settings)
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.access_token",
        AsyncMock(return_value="access"),
    )
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.create_event",
        AsyncMock(side_effect=GoogleCalendarError("quota exceeded")),
    )
    response = await client.post(
        "/api/v1/integrations/google-calendar/events",
        headers=headers,
        json={
            "confirmed": True,
            "timeZone": "Asia/Ho_Chi_Minh",
            "blocks": [
                {
                    "blockId": "quota-block",
                    "title": "Study",
                    "start": "2026-10-02T09:00:00+07:00",
                    "end": "2026-10-02T10:00:00+07:00",
                }
            ],
        },
    )
    assert response.status_code == 502
    assert "Created 0 event" in response.json()["detail"]
