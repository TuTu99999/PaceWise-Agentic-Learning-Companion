import httpx
import pytest
from cryptography.fernet import Fernet

from src.config import Settings
from src.services.google_calendar import (
    GoogleCalendarClient,
    GoogleCalendarError,
    TokenCipher,
    canonical_google_scopes,
    hash_oauth_state,
    new_oauth_state,
    new_pkce_pair,
)


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "google_client_id": "client-id",
        "google_client_secret": "client-secret",
        "google_token_encryption_key": Fernet.generate_key().decode(),
        "google_redirect_uri": "https://pacewise.test/callback",
    }
    values.update(overrides)
    return Settings(**values)


def test_oauth_helpers_and_token_cipher_are_safe():
    state = new_oauth_state()
    verifier, challenge = new_pkce_pair()
    assert len(state) >= 32
    assert len(hash_oauth_state(state)) == 64
    assert verifier != challenge

    cipher = TokenCipher(_settings())
    encrypted = cipher.encrypt("refresh-token")
    assert encrypted != "refresh-token"
    assert cipher.decrypt(encrypted) == "refresh-token"

    with pytest.raises(GoogleCalendarError):
        TokenCipher(_settings(google_token_encryption_key="invalid"))


@pytest.mark.asyncio
async def test_google_calendar_client_complete_flow():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            body = request.content.decode()
            if "authorization_code" in body:
                return httpx.Response(
                    200, json={"access_token": "access", "refresh_token": "refresh", "scope": "calendar"}
                )
            return httpx.Response(200, json={"access_token": "renewed"})
        if path.endswith("/userinfo"):
            return httpx.Response(200, json={"email": "student@gmail.com"})
        if path.endswith("/freeBusy"):
            return httpx.Response(
                200,
                json={
                    "calendars": {
                        "primary": {"busy": [{"start": "2026-10-01T08:00:00Z", "end": "2026-10-01T09:00:00Z"}]}
                    }
                },
            )
        if path.endswith("/events"):
            import json

            event = json.loads(request.content)
            assert event["reminders"] == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 15}]}
            return httpx.Response(200, json={"id": "event-1", "htmlLink": "https://calendar.test/event-1"})
        if path.endswith("/revoke"):
            return httpx.Response(200, json={})
        raise AssertionError(request.url)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GoogleCalendarClient(_settings(), http_client)
        assert client.configured is True
        assert "code_challenge=challenge" in client.authorization_url("state", "challenge")
        tokens = await client.exchange_code("code", "verifier")
        assert tokens.refresh_token == "refresh"
        assert await client.access_token("refresh") == "renewed"
        assert await client.account_email("access") == "student@gmail.com"
        busy = await client.freebusy("access", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z", "Asia/Ho_Chi_Minh")
        assert busy[0]["start"] == "2026-10-01T08:00:00Z"
        event = await client.create_event(
            "access",
            "Study block",
            "2026-10-01T10:00:00+07:00",
            "2026-10-01T11:00:00+07:00",
            "Asia/Ho_Chi_Minh",
            "block-1",
        )
        assert event["id"] == "event-1"
        await client.revoke("refresh")


def test_google_calendar_requires_configuration():
    client = GoogleCalendarClient(_settings(google_client_secret=""))
    assert client.configured is False
    with pytest.raises(GoogleCalendarError):
        client.authorization_url("state", "challenge")


def test_google_scope_normalization_is_limited_to_known_identity_aliases():
    assert canonical_google_scopes("openid email profile") == canonical_google_scopes(
        "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile"
    )
    assert canonical_google_scopes("calendar https://www.googleapis.com/auth/calendar.events.owned") == {
        "calendar",
        "https://www.googleapis.com/auth/calendar.events.owned",
    }
    assert canonical_google_scopes("") == set()


@pytest.mark.asyncio
async def test_event_recovery_uses_stable_opaque_id_and_does_not_duplicate():
    calls = []

    def handler(request):
        import json

        calls.append(request)
        if request.method == "POST":
            event = json.loads(request.content)
            assert len(event["id"]) == 64 and "secret-block-id" not in request.content.decode()
            return httpx.Response(409)
        return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[1]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GoogleCalendarClient(_settings(), http_client, user_id=123)
        one = await client.create_event(
            "access", "Study", "2026-10-10T10:00:00Z", "2026-10-10T11:00:00Z", "UTC", "secret-block-id"
        )
        two = await client.create_event(
            "access", "Study", "2026-10-10T10:00:00Z", "2026-10-10T11:00:00Z", "UTC", "secret-block-id"
        )
        assert one["id"] == two["id"]
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_provider_throttle_is_shared_and_does_not_retry_forever():
    from fastapi import HTTPException

    calls = []

    def limited(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "30"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(limited)) as http_client:
        for user in [123, 456]:
            client = GoogleCalendarClient(_settings(), http_client, user_id=user)
            with pytest.raises(HTTPException) as rate:
                await client.freebusy("access", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z", "UTC")
            assert rate.value.status_code == 429 and int(rate.value.headers["Retry-After"]) > 0
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_access_token_cache_is_encrypted_and_scoped_to_grant():
    from src.db import SessionLocal
    from src.persistence_models import GoogleReadCache

    calls = []

    def token(request):
        from src.db import engine

        assert engine.pool.checkedout() == 0  # Cache read/admission transactions ended before network I/O.
        calls.append(request)
        return httpx.Response(200, json={"access_token": "SENSITIVE_TOKEN", "expires_in": 3600})

    async with httpx.AsyncClient(transport=httpx.MockTransport(token)) as http_client:
        client = GoogleCalendarClient(_settings(), http_client, user_id=123)
        assert await client.access_token("first-grant") == "SENSITIVE_TOKEN"
        assert await client.access_token("first-grant") == "SENSITIVE_TOKEN"
        assert len(calls) == 1
        await client.access_token("other-grant")
        assert len(calls) == 2
    with SessionLocal() as db:
        rows = db.query(GoogleReadCache).all()
        assert len(rows) == 2 and all("SENSITIVE_TOKEN" not in row.encrypted_json for row in rows)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope_payload", [{}, {"scope": None}, {"scope": ""}])
async def test_code_exchange_does_not_assume_unreported_permissions(scope_payload):
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200, json={"access_token": "access", "refresh_token": "refresh", **scope_payload}
        )
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GoogleCalendarClient(_settings(), http_client)
        tokens = await client.exchange_code("code", "verifier")
    assert tokens.scope == ""
