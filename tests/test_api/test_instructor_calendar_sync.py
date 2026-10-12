from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.api import lms_integration
from src.config import Settings
from src.security import SessionContext


@pytest.mark.asyncio
async def test_instructor_sync_reads_calendar_for_all_enrolled_courses(monkeypatch):
    session = SessionContext(
        user_id=22, course_id=701, course_ids=(701, 702), role="instructor",
        name="Teacher", email="teacher@example.edu", csrf_hash="hash", sid="sid", exp=4_102_444_800,
    )
    calls = []
    calendar = [
        {
            "id": f"event-{course_id}", "course_id": course_id,
            "starts_at": "2026-10-05T09:07:00+07:00",
            "ends_at": "2026-10-05T10:22:00+07:00", "title": f"Class {course_id}",
        }
        for course_id in (701, 702, 999)
    ]

    async def service_get(path, params=None):
        calls.append((path, params))
        if path == "/api/pacewise/v1/courses":
            return [{"id": course_id, "code": f"C{course_id}", "name": f"Course {course_id}"} for course_id in (701, 702, 999)]
        if path == "/api/pacewise/v1/users/22/calendar":
            return calendar
        if path.endswith("/analytics"):
            return {}
        if path.endswith(("/assignments", "/submissions", "/modules", "/files", "/appointment-groups", "/sections", "/groups", "/quizzes")):
            return []
        raise AssertionError(f"Unexpected LMS request: {path}")

    client = SimpleNamespace(service_get=AsyncMock(side_effect=service_get))
    monkeypatch.setattr(lms_integration, "_client", lambda _settings: client)
    # This regression only reads the sync contract, with an empty action store.
    db = SimpleNamespace(
        scalars=lambda _query: SimpleNamespace(all=lambda: []), commit=Mock(),
    )
    result = await lms_integration._sync_payload(session, Settings(_env_file=None, app_env="test"), db)

    assert [course["id"] for course in result["courses"]] == ["701", "702"]
    assert [item["course_id"] for item in result["courseData"]["701"]["calendarItems"]] == [701]
    assert [item["course_id"] for item in result["courseData"]["702"]["calendarItems"]] == [702]
    assert "999" not in result["courseData"]
    assert sum(path.endswith("/calendar") for path, _params in calls) == 1
    assert not any(path.endswith("/planner") for path, _params in calls)
    assert not any("/courses/999/" in path for path, _params in calls)
