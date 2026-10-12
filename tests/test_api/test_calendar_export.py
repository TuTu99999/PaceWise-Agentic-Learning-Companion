from unittest.mock import AsyncMock

import pytest

from src.config import Settings, get_settings
from src.main import app
from src.models.calendar import CalendarBlock
from src.services.ics_calendar import build_ics


@pytest.fixture
def export_settings():
    settings = Settings(
        _env_file=None,
        app_env="test",
        pacewise_api_key="test-service-key",
        pacewise_session_secret="test-session-secret-with-at-least-32-characters",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


async def login(client, monkeypatch) -> dict[str, str]:
    claims = {
        "iss": "canvas-lms-simulator",
        "aud": "pacewise",
        "sub": "88",
        "course_id": 7,
        "role": "student",
        "name": "ICS Student",
        "email": "student@university.example",
    }
    monkeypatch.setattr("src.services.lms_client.LMSClient.verify_launch", AsyncMock(return_value=claims))
    monkeypatch.setattr("src.services.lms_client.LMSClient.service_get", AsyncMock(return_value=[{"id": 7}]))
    response = await client.post("/api/v1/auth/lms-launch", json={"token": "x" * 40})
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies["pacewise_csrf"]}


def test_build_ics_uses_utc_stamps_stable_uid_and_escaping():
    block = CalendarBlock.model_validate(
        {
            "blockId": "block-1",
            "title": "Ôn tập: A, B; C\r\nATTENDEE:mallory@example.com",
            "start": "2026-09-29T19:00:00+07:00",
            "end": "2026-09-29T20:00:00+07:00",
        }
    )

    first = build_ics(88, "PaceWise", [block]).decode()
    second = build_ics(88, "PaceWise", [block]).decode()

    assert "BEGIN:VCALENDAR\r\n" in first
    assert "DTSTART:20260929T120000Z" in first
    assert "DTEND:20260929T130000Z" in first
    assert "SUMMARY:Ôn tập: A\\, B\\; C\\nATTENDEE:mallory@example.com" in first
    assert "\r\nATTENDEE:mallory@example.com" not in first
    assert first.split("UID:", 1)[1].split("\r\n", 1)[0] == second.split("UID:", 1)[1].split("\r\n", 1)[0]


@pytest.mark.asyncio
async def test_ics_export_requires_session_and_csrf_but_not_google(client, monkeypatch, export_settings):
    payload = {
        "calendarName": "PaceWise Study Plan",
        "blocks": [
            {
                "blockId": "block-1",
                "title": "Study block",
                "start": "2026-09-29T19:00:00+07:00",
                "end": "2026-09-29T20:00:00+07:00",
            }
        ],
    }
    unauthenticated = await client.post("/api/v1/calendar/pacewise-study-plan.ics", json=payload)
    headers = await login(client, monkeypatch)
    missing_csrf = await client.post("/api/v1/calendar/pacewise-study-plan.ics", json=payload)
    exported = await client.post("/api/v1/calendar/pacewise-study-plan.ics", json=payload, headers=headers)

    assert unauthenticated.status_code == 401
    assert missing_csrf.status_code == 403
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/calendar")
    assert "no-store" in exported.headers["cache-control"] and "private" in exported.headers["cache-control"]
    assert exported.headers["content-disposition"] == 'attachment; filename="pacewise-study-plan.ics"'
    assert b"BEGIN:VEVENT" in exported.content
