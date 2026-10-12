"""Exercise real authenticated routes with a one-connection database pool.

Only Google I/O is replaced. A concurrent authenticated request must still
acquire the only DB connection while the Calendar route waits for upstream.
"""

import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from src.db import engine, get_db
from src.main import app
from src.services.google_calendar import OAuthTokens
from tests.test_api.test_google_calendar import add_connection, login_student
from tests.test_api.test_google_calendar import calendar_settings as shared_calendar_settings
from tests.test_api.test_google_calendar import clean_google_calendar_tables as shared_clean_google_tables

calendar_settings = shared_calendar_settings
clean_google_calendar_tables = shared_clean_google_tables


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["status", "freebusy", "export", "callback", "disconnect"])
async def test_calendar_releases_database_during_upstream_wait(client, monkeypatch, calendar_settings, route):
    import src.services.calendar_quota as quota

    limited = create_engine(
        engine.url,
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.2,
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=limited, autoflush=False, expire_on_commit=False)

    def isolated_pool_db():
        with factory() as db:
            yield db

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = isolated_pool_db
    monkeypatch.setattr(quota, "SessionLocal", factory)
    entered, release = asyncio.Event(), asyncio.Event()

    async def wait_for_google(*args, **kwargs):
        assert limited.pool.checkedout() == 0, "Route retained a DB connection across upstream await"
        entered.set()
        await release.wait()
        if route == "callback":
            return OAuthTokens(
                access_token="access", refresh_token="refresh", scope=calendar_settings.google_calendar_scopes
            )
        if route == "disconnect":
            return None
        return "access"

    async def account_email(*args):
        assert limited.pool.checkedout() == 0
        return "pool@example.test"

    async def freebusy(*args):
        assert limited.pool.checkedout() == 0
        return []

    async def create_event(*args):
        assert limited.pool.checkedout() == 0
        return {"id": "opaque-event"}

    task = None
    try:
        headers = await login_student(client, monkeypatch)
        if route != "callback":
            add_connection(calendar_settings)
        for method, replacement in [
            ("access_token", wait_for_google),
            ("exchange_code", wait_for_google),
            ("revoke", wait_for_google),
            ("account_email", account_email),
            ("freebusy", freebusy),
            ("create_event", create_event),
        ]:
            monkeypatch.setattr(f"src.services.google_calendar.GoogleCalendarClient.{method}", replacement)
        prefix = "/api/v1/integrations/google-calendar"
        if route == "callback":
            started = await client.post(f"{prefix}/connect", headers=headers)
            state = parse_qs(urlsplit(started.json()["authorizationUrl"]).query)["state"][0]
            request = client.get(f"{prefix}/callback", params={"state": state, "code": "code"}, follow_redirects=False)
        elif route == "status":
            request = client.get(f"{prefix}/status")
        elif route == "freebusy":
            request = client.post(
                f"{prefix}/freebusy",
                headers=headers,
                json={"timeMin": "2026-10-12T00:00:00Z", "timeMax": "2026-10-13T00:00:00Z", "timeZone": "UTC"},
            )
        elif route == "export":
            request = client.post(
                f"{prefix}/events",
                headers=headers,
                json={
                    "confirmed": True,
                    "timeZone": "UTC",
                    "blocks": [
                        {
                            "blockId": "pool-block",
                            "title": "Study",
                            "start": "2026-10-12T09:00:00Z",
                            "end": "2026-10-12T10:00:00Z",
                        }
                    ],
                },
            )
        else:
            request = client.delete(prefix, headers=headers)
        task = asyncio.create_task(request)
        await asyncio.wait_for(entered.wait(), timeout=3)
        another_request = await asyncio.wait_for(client.get("/api/v1/auth/me"), timeout=3)
        assert another_request.status_code == 200
        release.set()
        response = await asyncio.wait_for(task, timeout=3)
        assert response.status_code == (303 if route == "callback" else 200)
        assert limited.pool.checkedout() == 0
    finally:
        release.set()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        limited.dispose()
