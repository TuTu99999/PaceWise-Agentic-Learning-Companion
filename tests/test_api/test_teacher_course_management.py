import base64
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.api import instructor_management
from src.main import app
from src.security import SessionContext, get_current_session, require_csrf


@pytest.fixture
def authoring_session():
    session = SessionContext(
        12, 7, (7,), "instructor", "Teacher", "teacher@example.test", "hash", "course-test", 4_102_444_800
    )
    app.dependency_overrides[get_current_session] = lambda: session
    app.dependency_overrides[require_csrf] = lambda: session
    yield session
    app.dependency_overrides.pop(get_current_session, None)
    app.dependency_overrides.pop(require_csrf, None)


@pytest.mark.asyncio
async def test_new_course_refreshes_scope_and_does_not_shadow_task_route(client, authoring_session, monkeypatch):
    upstream = AsyncMock(return_value={"id": 8})
    refresh = AsyncMock()
    monkeypatch.setattr(instructor_management.LMSClient, "teacher_request", upstream)
    monkeypatch.setattr(instructor_management, "refresh_courses", refresh)
    result = await client.post("/api/v1/instructor/manage/courses", json={"code": "NEW101", "name": "New"})
    assert result.status_code == 201
    refresh.assert_awaited_once()
    assert (await client.post("/api/v1/instructor/manage/courses/7/tasks", json={"title": "Task"})).status_code == 201
    assert upstream.await_args.args[1] == "/api/pacewise/v1/teacher/courses/7/tasks"


@pytest.mark.asyncio
async def test_delete_resource_is_scoped_and_hides_internal_storage_details(client, authoring_session, monkeypatch):
    upstream = AsyncMock(return_value={
        "status": "deleted",
        "source_url": "https://external-lms.test/file/9",
        "delete_stored_object": False,
    })
    monkeypatch.setattr(instructor_management.LMSClient, "teacher_request", upstream)

    response = await client.delete("/api/v1/instructor/manage/courses/7/resources/9")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    upstream.assert_awaited_once_with(
        "DELETE", "/api/pacewise/v1/teacher/courses/7/resources/9", user_id=12, payload=None
    )


def test_delete_resource_removes_the_production_s3_object(monkeypatch):
    from types import SimpleNamespace

    from src.services import course_object_store

    deleted = []
    monkeypatch.setattr(course_object_store, "delete_object", lambda settings, key: deleted.append((settings, key)))
    settings = SimpleNamespace(course_source_mode="standalone")

    instructor_management.cleanup_owned_resource(
        "pacewise-object://demo/courses/7/file.docx",
        settings,
    )

    assert deleted == [(settings, "demo/courses/7/file.docx")]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["preview", "demo-preview", "series-preview"])
async def test_schedule_cannot_select_foreign_course(client, authoring_session, monkeypatch, action):
    upstream = AsyncMock()
    monkeypatch.setattr(instructor_management.LMSClient, "teacher_request", upstream)
    response = await client.post(f"/api/v1/instructor/manage/schedule/{action}", json={"course_ids": [999]})
    assert response.status_code == 403
    upstream.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("identifiers", [None, [], ["bad"], [True], [0], {"id": 7}])
async def test_malformed_schedule_scope_returns_validation_error(client, authoring_session, monkeypatch, identifiers):
    upstream = AsyncMock()
    monkeypatch.setattr(instructor_management.LMSClient, "teacher_request", upstream)
    response = await client.post("/api/v1/instructor/manage/schedule/preview", json={"course_ids": identifiers})
    assert response.status_code == 422
    upstream.assert_not_awaited()


@pytest.mark.asyncio
async def test_xlsx_is_parsed_then_previewed_not_confirmed(client, authoring_session, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "frontend/pacewise/public/templates/pacewise-schedule-template.xlsx"
    upstream = AsyncMock(side_effect=[[{"id": 7, "code": "CS101", "archived": False}], {"ticket": "preview-only"}])
    monkeypatch.setattr(instructor_management.LMSClient, "teacher_request", upstream)
    response = await client.post(
        "/api/v1/instructor/manage/schedule/import-preview",
        json={"data_base64": base64.b64encode(path.read_bytes()).decode(), "mode": "append"},
    )
    assert response.status_code == 200
    assert upstream.await_args.args[1].endswith("/schedule/preview")
    assert upstream.await_args.kwargs["payload"]["course_ids"] == [7]
    assert all("confirm" not in call.args[1] for call in upstream.await_args_list)


@pytest.mark.asyncio
async def test_workbook_error_never_reaches_source_preview(client, authoring_session, monkeypatch):
    upstream = AsyncMock(return_value=[])
    monkeypatch.setattr(instructor_management.LMSClient, "teacher_request", upstream)
    response = await client.post("/api/v1/instructor/manage/schedule/import-preview", json={"data_base64": "bad"})
    assert response.status_code == 422 and upstream.await_count == 1


@pytest.mark.asyncio
async def test_delete_empty_checks_pacewise_history_before_source_write(client, authoring_session, monkeypatch):
    from fastapi import HTTPException

    def guard(*_):
        raise HTTPException(409, "History exists")

    monkeypatch.setattr(instructor_management, "assert_no_learning_history", guard)
    upstream = AsyncMock(return_value=[{"id": 7}])
    monkeypatch.setattr(instructor_management.LMSClient, "teacher_request", upstream)
    response = await client.post(
        "/api/v1/instructor/manage/courses/7/lifecycle/delete-empty", json={"expected_version": "v1"}
    )
    assert response.status_code == 409
    upstream.assert_awaited_once()
    assert upstream.await_args.args[0] == "GET"


@pytest.mark.asyncio
async def test_restore_archived_course_is_live_owner_checked_not_blocked_by_active_session_scope(
    client, authoring_session, monkeypatch
):
    upstream = AsyncMock(return_value={"id": 99, "archived": False})
    monkeypatch.setattr(instructor_management.LMSClient, "teacher_request", upstream)
    monkeypatch.setattr(instructor_management, "refresh_courses", AsyncMock())
    response = await client.post(
        "/api/v1/instructor/manage/courses/99/lifecycle/restore", json={"expected_version": "v1"}
    )
    assert response.status_code == 200
    upstream.assert_awaited_with(
        "POST", "/api/pacewise/v1/teacher/courses/99/restore", user_id=12, payload={"expected_version": "v1"}
    )
