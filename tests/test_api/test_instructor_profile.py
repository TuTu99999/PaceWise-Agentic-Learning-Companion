from unittest.mock import AsyncMock

import pytest

from src.api import instructor_management
from src.main import app
from src.security import SessionContext, get_current_session, require_csrf


@pytest.fixture
def teacher_session():
    session = SessionContext(user_id=12, course_id=7, course_ids=(7,), role="instructor", name="Teacher",
                             email="teacher@example.test", csrf_hash="hash", sid="test-profile", exp=4_102_444_800)
    app.dependency_overrides[get_current_session] = lambda: session
    app.dependency_overrides[require_csrf] = lambda: session
    yield session
    app.dependency_overrides.pop(get_current_session, None)
    app.dependency_overrides.pop(require_csrf, None)


@pytest.mark.asyncio
async def test_profile_uses_authenticated_actor_for_read_and_save(client, teacher_session, monkeypatch):
    forward = AsyncMock(return_value={"details": {}, "version": "v1"})
    monkeypatch.setattr(instructor_management.LMSClient, "teacher_request", forward)
    assert (await client.get("/api/v1/instructor/manage/profile")).status_code == 200
    forward.assert_awaited_with("GET", "/api/pacewise/v1/teacher/profile", user_id=12, payload=None)
    payload = {"title": "Lecturer", "expected_version": "v1"}
    assert (await client.put("/api/v1/instructor/manage/profile", json=payload)).status_code == 200
    forward.assert_awaited_with("PUT", "/api/pacewise/v1/teacher/profile", user_id=12, payload=payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["user_id", "role", "course_id", "headers"])
async def test_profile_cannot_override_authenticated_actor(client, teacher_session, monkeypatch, field):
    forward = AsyncMock()
    monkeypatch.setattr(instructor_management.LMSClient, "teacher_request", forward)
    assert (await client.put("/api/v1/instructor/manage/profile", json={field: "spoof"})).status_code == 422
    forward.assert_not_awaited()


@pytest.mark.asyncio
async def test_student_cannot_access_teacher_profile(client, monkeypatch):
    student = SessionContext(2, 7, (7,), "student", "Student", "student@example.test", "hash", "test-profile", 4_102_444_800)
    app.dependency_overrides[get_current_session] = lambda: student
    app.dependency_overrides[require_csrf] = lambda: student
    forward = AsyncMock()
    monkeypatch.setattr(instructor_management.LMSClient, "teacher_request", forward)
    try:
        assert (await client.get("/api/v1/instructor/manage/profile")).status_code == 403
        assert (await client.put("/api/v1/instructor/manage/profile", json={})).status_code == 403
        forward.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_current_session, None)
        app.dependency_overrides.pop(require_csrf, None)
