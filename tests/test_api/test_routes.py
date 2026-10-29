import asyncio
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.api.routes import _attach_learning_availability, _learning_thread_id, _load_lms_agent_context
from src.config import get_settings
from src.db import SessionLocal
from src.main import app
from src.persistence_models import (
    InstructorAction,
    KnowledgeStateSnapshot,
    LearnerMemory,
    LearningEvent,
    LearningEvidenceRecord,
    LmsCourseContextProjection,
)
from src.security import SessionContext, require_csrf
from src.services.agent_memory import persist_agent_outcome


def _seed_plan_draft(session, draft):
    with SessionLocal() as db:
        persist_agent_outcome(
            db,
            session,
            get_settings(),
            {"workflow": "plan", "status": "awaiting_student", "output": {"plan_draft": draft}},
            None,
        )


def _seed_confirmed_do_block(session):
    settings = get_settings()
    with SessionLocal() as db:
        identifier = f"{settings.institution_id}:{session.user_id}:{session.course_id}"
        row = db.get(LearnerMemory, identifier) or LearnerMemory(id=identifier,
            institution_id=settings.institution_id, user_id=session.user_id, course_id=session.course_id)
        profile = json.loads(row.profile_json or "{}")
        profile["last_confirmed_plan"] = {"blocks": [{"id": "block-1", "taskId": f"{session.course_id}:21",
            "date": "2099-10-01", "start": "09:00", "end": "10:00", "status": "confirmed"}]}
        row.profile_json = json.dumps(profile)
        db.add(row)
        db.commit()


@pytest.mark.asyncio
async def test_plan_rejects_invalid_study_rhythm_before_model_call(client, authenticated_student, monkeypatch):
    ainvoke = AsyncMock()
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=ainvoke))
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    response = await client.post("/api/v1/chat", json={
        "workflow": "plan", "message": "Plan my week",
        "context": {"plan_input": {"studyPreferences": {"sessionMinutes": 999, "breakMinutes": -1}}},
    })
    assert response.status_code == 422
    ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_stream_returns_ndjson_final_after_authenticated_qa(client, authenticated_student, monkeypatch):
    async def ainvoke(*_args, **_kwargs):
        from src.agents.workflows.qa import _stream_sink

        sink = _stream_sink.get()
        assert sink is not None
        sink("Chào ")
        await asyncio.sleep(0)
        sink("bạn!")
        return {
            "workflow": "qa", "status": "completed", "mode": "conversation",
            "response": "Chào bạn!", "source_refs": [],
        }

    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=ainvoke))
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    response = await client.post("/api/v1/chat/stream", json={"workflow": "qa", "message": "xin chào"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["type"] == "status"
    assert [event["text"] for event in events if event["type"] == "delta"] == ["Chào ", "bạn!"]
    assert events[-1]["type"] == "final"
    assert events[-1]["result"]["response"] == "Chào bạn!"
    assert events[-1]["result"]["mode"] == "conversation"


@pytest.mark.asyncio
async def test_plan_model_context_excludes_expired_assignment_even_when_client_requests_it(client, authenticated_student, monkeypatch):
    def upstream(path, params=None):
        data = _lms_response(path, params)
        if path.endswith('/assignments'):
            return [*data, {'id': 22, 'title': 'Expired quiz', 'due_at': '2000-01-01T00:00:00Z', 'points_possible': 10}]
        return data
    ainvoke = AsyncMock(return_value={'workflow': 'plan', 'status': 'awaiting_student', 'response': 'Review current goals',
                                     'output': {'weekly_goals': [], 'plan_validation': {'valid': True}}})
    monkeypatch.setattr('src.api.routes.agent', SimpleNamespace(ainvoke=ainvoke))
    monkeypatch.setattr('src.api.routes.LMSClient.service_get', AsyncMock(side_effect=upstream))
    response = await client.post('/api/v1/chat', json={'workflow': 'plan', 'message': 'Propose weekly goals',
        'context': {'planning_stage': 'goal_proposal', 'goals': [{'taskId': '7:21'}, {'taskId': '7:22'}]}})
    assert response.status_code == 200
    state = ainvoke.await_args.args[0]
    assert [a['id'] for a in state['assignments']] == ['7:21']
    assert state['goals'] == [{'taskId': '7:21'}]


@pytest.mark.asyncio
async def test_plan_model_context_keeps_future_assignment_and_its_start_boundary(client, authenticated_student, monkeypatch):
    def upstream(path, params=None):
        data = _lms_response(path, params)
        if path.endswith('/assignments'):
            return [{
                **data[0],
                'unlock_at': '2098-10-01T14:00:00+07:00',
            }]
        return data

    ainvoke = AsyncMock(return_value={
        'workflow': 'plan',
        'status': 'awaiting_student',
        'response': 'Future work remains visible',
        'output': {'weekly_goals': [], 'plan_validation': {'valid': True}},
    })
    monkeypatch.setattr('src.api.routes.agent', SimpleNamespace(ainvoke=ainvoke))
    monkeypatch.setattr('src.api.routes.LMSClient.service_get', AsyncMock(side_effect=upstream))

    response = await client.post('/api/v1/chat', json={
        'workflow': 'plan',
        'message': 'Propose future goals',
        'context': {'planning_stage': 'goal_proposal', 'goals': [{'taskId': '7:21'}]},
    })

    assert response.status_code == 200
    state = ainvoke.await_args.args[0]
    assert [assignment['id'] for assignment in state['assignments']] == ['7:21']
    assert state['assignments'][0]['unlock_at'] == '2098-10-01T14:00:00+07:00'
    assert state['goals'] == [{'taskId': '7:21'}]


@pytest.mark.asyncio
async def test_reflect_api_keeps_client_totals_separate_from_persisted_observations(
    client, authenticated_student, monkeypatch,
):
    now = datetime.now(UTC).isoformat()
    settings = get_settings()
    with SessionLocal() as db:
        db.query(LearnerMemory).filter(
            LearnerMemory.user_id == authenticated_student.user_id,
            LearnerMemory.course_id == authenticated_student.course_id,
        ).delete()
        persist_agent_outcome(db, authenticated_student, settings, {
            "workflow": "do", "output": {"do_session": {
                "action": "complete", "block_id": "reflection-api-block",
                "planned_minutes": 60, "actual_minutes": 90,
            }},
        }, None)
    ainvoke = AsyncMock(return_value={"workflow": "reflect", "status": "awaiting_student", "response": "Review"})
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=ainvoke))
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    response = await client.post("/api/v1/chat", json={
        "workflow": "reflect", "message": "Review this week",
        "context": {"progress_metrics": {"week_start": now[:10], "planned_minutes": 999}},
    })
    assert response.status_code == 200, response.text
    metrics = ainvoke.call_args.args[0]["progress_metrics"]
    assert metrics["planned_minutes"] == 60
    assert metrics["actual_minutes"] == 90
    assert metrics["self_report"]["planned_minutes"] == 999
    assert metrics["source_refs"]
    assert metrics["provenance"]["sessions"] == "persisted_student_report"


@pytest.mark.asyncio
async def test_reflect_rejects_invalid_week_before_model_call(client, authenticated_student, monkeypatch):
    ainvoke = AsyncMock()
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=ainvoke))
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    response = await client.post("/api/v1/chat", json={
        "workflow": "reflect", "message": "Review",
        "context": {"progress_metrics": {"week_start": "not-a-date"}},
    })
    assert response.status_code == 422
    ainvoke.assert_not_awaited()


def _confirmation_draft(**extra):
    return {
        "createdAt": "2026-10-08T10:00:00+07:00",
        "scheduleStart": "2099-10-01",
        "horizonEnd": "2099-10-07",
        "blocks": [],
        "milestones": [],
        "feasibility": {"feasible": True, "robustFeasible": True},
        **extra,
    }


@pytest.mark.asyncio
async def test_partial_confirmation_is_explicit_canonical_retry_safe_and_opens_do(client, authenticated_student, monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    safe, bad = f"partial-safe-{suffix}", f"partial-bad-{suffix}"
    draft = _confirmation_draft(input={"unavailable": [], "availability": []},
        blocks=[{"id": safe, "taskId": "7:21", "milestoneId": "safe-m", "date": "2099-10-01", "start": "09:00", "end": "10:00"},
                {"id": bad, "taskId": "7:21", "date": "2099-10-01", "start": "18:00", "end": "19:00"}],
        milestones=[{"milestoneId": "safe-m", "taskId": "7:21", "title": "Read requirements", "targetMin": 60}],
        feasibility={"feasible": False, "deficitMin": 540, "shortfalls": [{"taskId": "7:21", "missingMin": 540}]})
    _seed_plan_draft(authenticated_student, draft)
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    ainvoke = AsyncMock()
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=ainvoke))
    body = {"workflow": "plan", "message": "Tôi xác nhận kế hoạch này.",
            "context": {"plan_confirmation_id": draft["createdAt"]}}
    assert (await client.post("/api/v1/chat", json=body)).status_code == 409
    body["context"].update(accept_partial_plan=True, partial_block_ids=[safe, bad])
    assert (await client.post("/api/v1/chat", json=body)).status_code == 409  # No forged selection.
    body["context"]["partial_block_ids"] = [safe]
    response = await client.post("/api/v1/chat", json=body)
    assert response.status_code == 200, response.text
    confirmed = response.json()["output"]["confirmed_plan"]
    assert [b["id"] for b in confirmed["blocks"]] == [safe]
    assert confirmed["confirmation"]["mode"] == "partial"
    assert not confirmed["feasibility"]["feasible"]
    assert confirmed["feasibility"]["shortfalls"] == [{"taskId": "7:21", "missingMin": 600}]
    assert confirmed["measurement"]["objectives"]
    retry = await client.post("/api/v1/chat", json=body)
    assert retry.status_code == 200
    assert retry.json()["output"]["confirmed_plan"] == confirmed
    with SessionLocal() as db:
        row = db.scalar(select(LearnerMemory).where(LearnerMemory.user_id == authenticated_student.user_id,
                                                  LearnerMemory.course_id == 7))
        assert json.loads(row.profile_json)["outstanding_plan_work"]["shortfalls"] == confirmed["feasibility"]["shortfalls"]
    denied = await client.post("/api/v1/study-sessions", json={"courseId": 7, "blockId": bad})
    assert denied.status_code == 409
    started = await client.post("/api/v1/study-sessions", json={"courseId": 7, "blockId": safe})
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "running"
    ainvoke.assert_not_awaited()
    from src.persistence_models import StudyTimerSession
    with SessionLocal() as db:
        db.delete(db.get(StudyTimerSession, started.json()["id"]))
        db.commit()


@pytest.mark.asyncio
async def test_partial_confirmation_rechecks_fresh_calendar_and_does_not_mutate_plan_on_failure(client, authenticated_student, monkeypatch):
    draft = _confirmation_draft(input={"unavailable": []},
        blocks=[{"id": "partial-calendar", "taskId": "7:21", "date": "2099-10-01", "start": "09:00", "end": "10:00"}],
        feasibility={"feasible": False, "deficitMin": 540, "shortfalls": [{"taskId": "7:21", "missingMin": 540}]})
    _seed_plan_draft(authenticated_student, draft)
    def upstream(path, params=None):
        if path.endswith("/calendar"):
            return [{"type": "event", "starts_at": "2099-10-01T09:00:00+07:00", "ends_at": "2099-10-01T10:00:00+07:00"}]
        return _lms_response(path, params)
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=upstream))
    response = await client.post("/api/v1/chat", json={"workflow": "plan", "message": "Confirm",
        "context": {"plan_confirmation_id": draft["createdAt"], "accept_partial_plan": True, "partial_block_ids": ["partial-calendar"]}})
    assert response.status_code == 409
    with SessionLocal() as db:
        row = db.scalar(select(LearnerMemory).where(LearnerMemory.user_id == authenticated_student.user_id, LearnerMemory.course_id == 7))
        assert json.loads(row.profile_json)["pending_plan_draft"] == draft


@pytest.mark.asyncio
async def test_confirmation_blocks_invalid_server_draft_before_agent_call(client, authenticated_student, monkeypatch):
    _seed_plan_draft(
        authenticated_student, _confirmation_draft(milestones=[{"milestoneId": "M1", "dependsOn": ["unknown"]}])
    )
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    ainvoke = AsyncMock()
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=ainvoke))
    response = await client.post(
        "/api/v1/chat",
        json={
            "workflow": "plan",
            "message": "Tôi xác nhận kế hoạch này.",
            "context": {"current_plan": _confirmation_draft()},
        },
    )
    assert response.status_code == 409
    assert "UNKNOWN_DEPENDENCY" in response.text
    ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmation_rechecks_updated_lms_deadline(client, authenticated_student, monkeypatch):
    draft = _confirmation_draft(
        blocks=[{"id": "b1", "taskId": "7:21", "date": "2099-10-01", "start": "18:00", "end": "19:00"}]
    )
    _seed_plan_draft(authenticated_student, draft)
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    response = await client.post("/api/v1/chat", json={"workflow": "plan", "message": "Tôi xác nhận kế hoạch này."})
    assert response.status_code == 409
    assert "AFTER_DEADLINE" in response.text


@pytest.mark.asyncio
async def test_confirmation_uses_server_draft_and_clears_pending(client, authenticated_student, monkeypatch):
    draft = _confirmation_draft(feasibility={"feasible": True, "robustFeasible": False})
    _seed_plan_draft(authenticated_student, draft)
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    ainvoke = AsyncMock()
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=ainvoke))
    response = await client.post("/api/v1/chat", json={"workflow": "plan", "message": "Tôi xác nhận kế hoạch này."})
    assert response.status_code == 200, response.text
    assert response.json()["output"]["confirmed_plan"]["qualityEvaluation"]["canConfirm"]
    assert response.json()["output"]["confirmed_plan"]["qualityEvaluation"]["warnings"]
    measurement = response.json()["output"]["confirmed_plan"]["measurement"]
    assert measurement["version"] == "plan-measurement-v1"
    assert measurement["objectives"] == []  # Empty plans cannot fabricate progress.
    ainvoke.assert_not_awaited()
    with SessionLocal() as db:
        row = db.scalar(
            select(LearnerMemory).where(
                LearnerMemory.user_id == authenticated_student.user_id, LearnerMemory.course_id == 7
            )
        )
        assert "pending_plan_draft" not in json.loads(row.profile_json)
        latest = db.scalars(select(LearningEvent).where(
            LearningEvent.student_user_id == authenticated_student.user_id,
            LearningEvent.course_id == 7, LearningEvent.event_type == "PLAN_CONFIRMED",
        )).all()
        assert any(json.loads(item.payload_json)["confirmed_plan"]["measurement"] == measurement for item in latest)


@pytest.mark.asyncio
async def test_confirmation_cannot_use_only_client_supplied_draft(client, authenticated_student, monkeypatch):
    with SessionLocal() as db:
        db.query(LearnerMemory).filter(
            LearnerMemory.user_id == authenticated_student.user_id, LearnerMemory.course_id == 7
        ).delete()
        db.commit()
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    response = await client.post(
        "/api/v1/chat",
        json={
            "workflow": "plan",
            "message": "Tôi xác nhận kế hoạch này.",
            "context": {"current_plan": _confirmation_draft()},
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_confirmation_retry_is_idempotent_and_stale_preview_is_rejected(
    client, authenticated_student, monkeypatch
):
    draft = _confirmation_draft()
    _seed_plan_draft(authenticated_student, draft)
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    body = {
        "workflow": "plan",
        "message": "Tôi xác nhận kế hoạch này.",
        "context": {"plan_confirmation_id": draft["createdAt"]},
    }
    first = await client.post("/api/v1/chat", json=body)
    assert first.status_code == 200
    with SessionLocal() as db:
        first_event_ids = set(db.scalars(select(LearningEvent.id).where(
            LearningEvent.student_user_id == authenticated_student.user_id,
            LearningEvent.course_id == 7,
            LearningEvent.event_type == "PLAN_CONFIRMED",
        )).all())
    retry = await client.post("/api/v1/chat", json=body)
    assert retry.status_code == 200
    assert retry.json()["output"]["confirmed_plan"] == first.json()["output"]["confirmed_plan"]
    with SessionLocal() as db:
        confirmations = db.scalars(select(LearningEvent).where(
            LearningEvent.student_user_id == authenticated_student.user_id,
            LearningEvent.course_id == 7,
            LearningEvent.event_type == "PLAN_CONFIRMED",
        )).all()
        assert {event.id for event in confirmations} == first_event_ids
        assert any(json.loads(event.payload_json)["confirmed_plan"]["measurement"] ==
                   first.json()["output"]["confirmed_plan"]["measurement"] for event in confirmations)
    _seed_plan_draft(authenticated_student, {**draft, "createdAt": "2026-10-08T11:00:00+07:00"})
    assert (await client.post("/api/v1/chat", json=body)).status_code == 409


@pytest.mark.asyncio
async def test_confirmation_refreshes_cached_lms_projection(client, authenticated_student, monkeypatch):
    changed = False

    def upstream(path, params=None):
        result = _lms_response(path, params)
        if changed and path.endswith("/assignments"):
            result[0]["due_at"] = "2099-10-01T00:00:00Z"
        return result

    service = AsyncMock(side_effect=upstream)
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", service)
    with SessionLocal() as db:
        await _load_lms_agent_context(authenticated_student, get_settings(), db)
    draft = _confirmation_draft(
        blocks=[{"id": "b1", "taskId": "7:21", "date": "2099-10-01", "start": "09:00", "end": "10:00"}]
    )
    _seed_plan_draft(authenticated_student, draft)
    changed = True
    response = await client.post("/api/v1/chat", json={"workflow": "plan", "message": "Tôi xác nhận kế hoạch này."})
    assert response.status_code == 409
    assert "AFTER_DEADLINE" in response.text
    assert sum(call.args[0].endswith("/assignments") for call in service.await_args_list) == 2


@pytest.fixture
def authenticated_student():
    session = SessionContext(
        user_id=12,
        course_id=7,
        course_ids=(7,),
        role="student",
        name="Student Test",
        email="student@example.edu",
        csrf_hash="test",
        sid="server-side-session",
        exp=4_102_444_800,
    )
    with SessionLocal() as db:
        db.query(LmsCourseContextProjection).filter(LmsCourseContextProjection.course_id == session.course_id).delete()
        db.commit()
    app.dependency_overrides[require_csrf] = lambda: session
    yield session
    app.dependency_overrides.pop(require_csrf, None)


@pytest.mark.asyncio
async def test_qa_loads_only_current_course_and_live_acl(client, authenticated_student, monkeypatch):
    calls = []
    def read(path, params=None):
        calls.append(path)
        return _lms_response(path, params)
    fake = AsyncMock(return_value={"workflow": "qa", "response": "Chưa đủ nguồn", "status": "completed"})
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=read))
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=fake))
    response = await client.post('/api/v1/chat', json={"workflow": "qa", "message": "Khái niệm là gì?", "qa_history": [{"role": "user", "content": "Hỏi về quan hệ"}]})
    assert response.status_code == 200, response.text
    assert calls == ['/api/pacewise/v1/courses', '/api/pacewise/v1/courses/7/files']
    assert fake.call_args.args[0]['qa_history'][0]['content'] == 'Hỏi về quan hệ'
    assert fake.call_args.args[0]['allowed_resource_ids'] is None


@pytest.mark.asyncio
async def test_chat_enforces_shared_rate_limit_before_model(client, authenticated_student, auth_settings, monkeypatch):
    from src.db import engine
    from src.persistence_models import AiUsageBucket, AiUsageReservation
    assert engine.dialect.name == 'sqlite'
    with SessionLocal() as db:
        db.query(AiUsageReservation).delete()
        db.query(AiUsageBucket).delete()
        db.commit()
    auth_settings.ai_rate_limit_enabled = True
    auth_settings.ai_burst_requests = 1
    auth_settings.ai_burst_window_seconds = 3600
    fake = AsyncMock(return_value={"workflow": "qa", "response": "Chưa đủ nguồn", "status": "completed"})
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=fake))
    first = await client.post('/api/v1/chat', json={"workflow": "qa", "message": "Khái niệm là gì?"})
    assert first.status_code == 200, first.text
    second = await client.post('/api/v1/chat', json={"workflow": "qa", "message": "Khái niệm là gì?"})
    assert second.status_code == 429
    assert int(second.headers['Retry-After']) >= 1
    assert fake.await_count == 1
    with SessionLocal() as db:
        assert all(row.used == 0 for row in db.scalars(select(AiUsageBucket).where(AiUsageBucket.limit_type == 'concurrent')))


def _lms_response(path: str, _params=None):
    if path == "/api/pacewise/v1/courses":
        return [{"id": 7, "code": "AI101", "name": "Nhập môn AI"}]
    if path.endswith("/assignments"):
        return [
            {
                "id": 21,
                "title": "Bài giữa kỳ",
                "description": "Giải thích overfitting",
                "due_at": "2099-10-01T10:00:00Z",
                "points_possible": 10,
            }
        ]
    if path.endswith("/content"):
        return [{"id": 1, "title": "Giáo trình AI", "body": "Overfitting là học quá sát dữ liệu."}]
    if path.endswith("/submissions"):
        return [{"assignment_id": 21, "workflow_state": "unsubmitted"}]
    if path.endswith("/modules") or path.endswith("/planner") or path.endswith("/files") or path.endswith("/calendar"):
        return []
    raise AssertionError(f"Unexpected LMS path: {path}")


def test_learning_availability_uses_linked_lesson_end_without_guessing_completion():
    assignment = {"course_id": "7", "chapter": "Chương 2", "resource_ids": [91, 92]}
    events = [
        {"course_id": 7, "event_kind": "class_session", "title": "Buổi A", "ends_at": "2026-10-18T09:00:00+07:00", "resource_ids": [91]},
        {"course_id": 7, "event_kind": "class", "title": "Buổi B", "ends_at": "2026-10-18T11:00:00+07:00", "resource_ids": [92]},
        {"course_id": 8, "event_kind": "class", "title": "Wrong course", "ends_at": "2026-10-19T11:00:00+07:00", "resource_ids": [92]},
    ]

    _attach_learning_availability(assignment, events, "Asia/Ho_Chi_Minh")

    assert assignment["learning_available_at"] == "2026-10-18T11:00:00+07:00"


def test_learning_availability_supports_exact_legacy_chapter_title_only():
    assignment = {"course_id": "7", "chapter": "Chương 2: Kỹ thuật tìm kiếm", "resource_ids": []}
    events = [
        {"course_id": 7, "event_kind": "class", "title": "Chương 2: Kỹ thuật tìm kiếm", "ends_at": "2026-10-18T11:00:00+07:00"},
        {"course_id": 7, "event_kind": "class", "title": "Chương 2: SQL", "ends_at": "2026-10-19T11:00:00+07:00"},
    ]

    _attach_learning_availability(assignment, events, "Asia/Ho_Chi_Minh")

    assert assignment["learning_available_at"] == "2026-10-18T11:00:00+07:00"


@pytest.mark.asyncio
async def test_student_context_never_uses_global_projection_or_forged_planner(authenticated_student, monkeypatch):
    settings = get_settings()
    with SessionLocal() as db:
        db.add(LmsCourseContextProjection(
            id=f"{settings.institution_id}:7", institution_id=settings.institution_id, course_id=7,
            course_json=json.dumps({"id": 7, "code": "AI101"}),
            assignments_json=json.dumps([{"id": 999, "title": "Teacher-only draft", "published": False}]),
            modules_json="[]",
        ))
        db.commit()
    async def upstream(path, params=None):
        if path.endswith("/planner"):
            return [{"id": 1, "course_id": 7, "assignment_id": 21, "due_at": "2099-12-31T00:00:00Z", "completed": True}]
        if path.endswith("/submissions"):
            assert params == {"user_id": 12}
            return []
        if path.endswith("/assignments"):
            assert params == {"user_id": 12}
        return _lms_response(path, params)
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=upstream))
    with SessionLocal() as db:
        context = await _load_lms_agent_context(authenticated_student, settings, db)
        assert [item["lms_assignment_id"] for item in context["assignments"]] == ["21"]
        assert context["assignments"][0]["deadline"] == "2099-10-01T10:00:00Z"
        assert context["assignments"][0]["submission"] is None
        assert json.loads(db.get(LmsCourseContextProjection, f"{settings.institution_id}:7").assignments_json)[0]["id"] == 999


@pytest.mark.asyncio
async def test_cached_context_does_not_bypass_revoked_enrollment(authenticated_student, monkeypatch):
    settings = get_settings()
    with SessionLocal() as db:
        db.add(LmsCourseContextProjection(id=f"{settings.institution_id}:7", institution_id=settings.institution_id,
                                          course_id=7, course_json=json.dumps({"id": 7}), assignments_json="[]", modules_json="[]"))
        db.commit()
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(return_value=[]))
    from fastapi import HTTPException
    with SessionLocal() as db, pytest.raises(HTTPException) as error:
        await _load_lms_agent_context(authenticated_student, settings, db)
    assert error.value.status_code == 403


def test_learning_thread_is_stable_across_login_sessions_and_isolated_by_course():
    now = datetime(2026, 9, 29, tzinfo=UTC)
    settings = get_settings()
    first = SessionContext(12, 7, (7,), "student", "A", "a@x.edu", "x", "sid-1", 1)
    relogin = SessionContext(12, 7, (7,), "student", "A", "a@x.edu", "y", "sid-2", 2)
    other_course = SessionContext(12, 8, (8,), "student", "A", "a@x.edu", "z", "sid-3", 3)

    assert _learning_thread_id(first, settings, now) == _learning_thread_id(relogin, settings, now)
    assert _learning_thread_id(first, settings, now) != _learning_thread_id(other_course, settings, now)


@pytest.mark.asyncio
async def test_lms_context_normalizes_assignment_ids_across_courses(monkeypatch):
    session = SessionContext(12, 7, (7, 8), "student", "A", "a@x.edu", "x", "sid", 1)

    async def service_get(_client, path, _params=None):
        if path == "/api/pacewise/v1/courses":
            return [
                {"id": 7, "code": "AI101", "name": "AI"},
                {"id": 8, "code": "DB101", "name": "Database"},
            ]
        if path.endswith("/7/assignments"):
            return [{"id": 21, "title": "AI task", "points_possible": 10}]
        if path.endswith("/8/assignments"):
            return [{"id": 31, "title": "DB task", "points_possible": 5}]
        if path.endswith("/submissions"):
            return []
        if path.endswith("/modules") or path.endswith("/planner") or path.endswith("/files"):
            return []
        raise AssertionError(path)

    monkeypatch.setattr("src.api.routes.LMSClient.service_get", service_get)
    context = await _load_lms_agent_context(session, get_settings())

    assert [item["id"] for item in context["assignments"]] == ["7:21", "8:31"]


@pytest.mark.asyncio
async def test_lms_context_degrades_when_planner_is_temporarily_unavailable(monkeypatch):
    session = SessionContext(12, 7, (7,), "student", "A", "a@x.edu", "x", "sid", 1)

    async def service_get(_client, path, params=None):
        if path.endswith("/planner"):
            raise RuntimeError("temporary planner outage")
        return _lms_response(path, params)

    monkeypatch.setattr("src.api.routes.LMSClient.service_get", service_get)
    context = await _load_lms_agent_context(session, get_settings())

    assert context["planner_items"] == []
    assert context["assignments"][0]["title"] == "Bài giữa kỳ"


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "# PaceWise application metrics" in response.text


@pytest.mark.asyncio
async def test_chat_empty_message(client, authenticated_student):
    response = await client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_agent_status(client):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_requires_pacewise_session(client):
    response = await client.post("/api/v1/chat", json={"message": "Giải thích overfitting"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_uses_authenticated_identity_and_lms_context(
    client,
    authenticated_student,
    monkeypatch,
):
    service_get = AsyncMock(side_effect=_lms_response)
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", service_get)
    ainvoke = AsyncMock(
        return_value={
            "response": "Overfitting là học quá sát dữ liệu. [Giáo trình AI, Trang 1, Đoạn 1]",
            "workflow": "qa",
            "status": "completed",
            "progress_metrics": {"completion_rate": 0.5},
            "risk_signals": [{"assignment_id": "21", "level": "high"}],
            "source_refs": [{"citation": "[Giáo trình AI, Trang 1, Đoạn 1]"}],
        }
    )
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=ainvoke))

    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "Giải thích overfitting",
            "workflow": "qa",
            "locale": "en",
            "context": {
                "student_id": "attacker",
                "course_id": "999",
                "role": "instructor",
                "approved_rubric": [{"criterion_id": "c1", "description": "Correct explanation"}],
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "grounded"
    assert response.json()["progress_metrics"]["completion_rate"] == 0.5
    assert response.json()["risk_signals"] == []
    state = ainvoke.await_args.args[0]
    config = ainvoke.await_args.kwargs["config"]
    assert state["student_id"] == str(authenticated_student.user_id)
    assert state["course_id"] == str(authenticated_student.course_id)
    assert state["course_code"] == "AI101"
    assert state["role"] == "student"
    assert state["request"]["locale"] == "en"
    assert "approved_rubric" not in state
    assert state["assignments"] == []  # QA no longer loads tasks from every course.
    assert state["learning_resources"] == []
    assert state["modules"] == []
    assert state["planner_items"] == []
    assert not any(call.args[0].endswith("/content") for call in service_get.await_args_list)
    thread_id = config["configurable"]["thread_id"]
    assert thread_id.startswith("university-x:12:7:")
    assert "week-" in thread_id


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_mode", ["conversation", "out_of_scope"])
async def test_chat_preserves_safe_qa_display_mode(
    client,
    authenticated_student,
    monkeypatch,
    explicit_mode,
):
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    monkeypatch.setattr(
        "src.api.routes.agent",
        SimpleNamespace(
            ainvoke=AsyncMock(
                return_value={
                    "response": "Phản hồi không cần nguồn học liệu.",
                    "workflow": "qa",
                    "mode": explicit_mode,
                    "status": "completed",
                    "source_refs": [],
                }
            )
        ),
    )

    response = await client.post(
        "/api/v1/chat",
        json={"message": "xin chào", "workflow": "qa"},
    )

    assert response.status_code == 200
    assert response.json()["mode"] == explicit_mode
    assert response.json()["source_refs"] == []


@pytest.mark.asyncio
async def test_do_workflow_keeps_resources_and_scopes_to_enrolled_course(
    client,
    authenticated_student,
    monkeypatch,
):
    _seed_confirmed_do_block(authenticated_student)
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    ainvoke = AsyncMock(
        return_value={
            "response": "Phiên học đã sẵn sàng.",
            "workflow": "do",
            "status": "completed",
            "source_refs": [{"id": "m1", "citation": "[Module 1]"}],
            "output": {"do_session": {"action": "prepare", "status": "ready"}},
        }
    )
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=ainvoke))

    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "Chuẩn bị phiên học",
            "workflow": "do",
            "context": {
                "do_course_id": str(authenticated_student.course_id),
                "do_block_id": "block-1",
                "progress_metrics": {"do_session": {"action": "prepare"}},
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["workflow"] == "do"
    assert response.json()["source_refs"][0]["citation"] == "[Module 1]"
    state = ainvoke.await_args.args[0]
    assert state["course_id"] == str(authenticated_student.course_id)


@pytest.mark.asyncio
async def test_do_workflow_rejects_course_outside_enrollment(client, authenticated_student):
    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "Chuẩn bị phiên học",
            "workflow": "do",
            "context": {"do_course_id": "999", "do_block_id": "block-1"},
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_do_assessment_uses_approved_server_contract_and_persists_evidence(
    client,
    authenticated_student,
    monkeypatch,
):
    assessment_id = "Q-998"
    _seed_confirmed_do_block(authenticated_student)
    with SessionLocal() as db:
        db.query(InstructorAction).filter(InstructorAction.entity_id == assessment_id).delete()
        db.query(KnowledgeStateSnapshot).filter(
            KnowledgeStateSnapshot.student_user_id == authenticated_student.user_id
        ).delete()
        db.query(LearningEvidenceRecord).filter(
            LearningEvidenceRecord.student_user_id == authenticated_student.user_id
        ).delete()
        db.query(LearningEvent).filter(LearningEvent.student_user_id == authenticated_student.user_id).delete()
        db.add(
            InstructorAction(
                id=str(uuid.uuid4()),
                course_id=authenticated_student.course_id,
                actor_user_id=501,
                action_type="assessment",
                entity_id=assessment_id,
                payload_json=json.dumps(
                    {
                        "status": "approved",
                        "topic": "Khái quát AI",
                        "question": "Overfitting là gì?",
                        "source": "ai-introduction.pdf · page 4",
                        "answerType": "exact_text",
                        "correctAnswer": "Học quá sát dữ liệu huấn luyện",
                        "rubric": ["Đúng khái niệm", "Có lập luận"],
                        "version": 2,
                        "level": "conceptual",
                        "knowledgeComponentIds": ["kc-overfitting"],
                    },
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()

    async def service_get(_client, path, params=None):
        if path.endswith("/quizzes"):
            raise AssertionError("Assessment must not read legacy quizzes")
        return _lms_response(path, params)

    monkeypatch.setattr("src.api.routes.LMSClient.service_get", service_get)
    ainvoke = AsyncMock(
        return_value={
            "response": "Đã ghi nhận bằng chứng.",
            "workflow": "do",
            "status": "completed",
            "do_session": {"action": "assess", "block_id": "block-1"},
            "assessment_result": {
                "status": "đã thể hiện được",
                "confidence": "Cao",
                "evaluator_version": "closed-v2",
                "evidence_quotes": ["Học quá sát dữ liệu huấn luyện"],
                "dimensions": {"recall": "passed", "transfer": "not_tested"},
            },
            "output": {"do_session": {"action": "assess", "block_id": "block-1"}},
        }
    )
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=ainvoke))

    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "Học quá sát dữ liệu huấn luyện",
            "workflow": "do",
            "context": {
                "assessment_id": assessment_id,
                "do_course_id": str(authenticated_student.course_id),
                "do_block_id": "block-1",
                "progress_metrics": {
                    "do_session": {
                        "action": "assess",
                        "block_id": "block-1",
                        "assessment_attempt": {
                            "event_key": "route-assessment-attempt-1",
                            "response": "Học quá sát dữ liệu huấn luyện",
                            "first_attempt": True,
                            "hint_level": 0,
                        },
                    }
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow"] == "do"
    assert payload["assessment_result"]["knowledge_component_ids"] == ["kc-overfitting"]
    assert payload["assessment_result"]["provisional"] is False
    state = ainvoke.await_args.args[0]
    assert state["approved_rubric"][0]["description"] == "Đúng khái niệm"
    assert state["request"]["correct_answer"] == "Học quá sát dữ liệu huấn luyện"
    with SessionLocal() as db:
        evidence = db.scalar(
            select(LearningEvidenceRecord).where(
                LearningEvidenceRecord.assessment_id == assessment_id,
                LearningEvidenceRecord.student_user_id == authenticated_student.user_id,
            )
        )
        snapshots = db.scalars(
            select(KnowledgeStateSnapshot).where(KnowledgeStateSnapshot.evidence_id == evidence.id)
        ).all()
    assert evidence.valid == 1
    assert len(snapshots) == 1
    assert snapshots[0].knowledge_component_id == "kc-overfitting"


@pytest.mark.asyncio
async def test_understanding_uses_only_server_approved_rubric(
    client,
    authenticated_student,
    monkeypatch,
):
    assessment_id = "Q-999"
    with SessionLocal() as db:
        db.add(
            InstructorAction(
                id=str(uuid.uuid4()),
                course_id=authenticated_student.course_id,
                actor_user_id=501,
                action_type="assessment",
                entity_id=assessment_id,
                payload_json=json.dumps(
                    {
                        "status": "approved",
                        "topic": "Khái quát AI",
                        "question": "Overfitting là gì?",
                        "source": "ai-introduction.pdf · page 4",
                        "answerType": "exact_text",
                        "correctAnswer": "Học quá sát dữ liệu huấn luyện",
                        "rubric": ["Rubric do giảng viên duyệt"],
                    },
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()

    async def service_get(_client, path, _params=None):
        if path.endswith("/quizzes"):
            raise AssertionError("Assessment must not read legacy quizzes")
        return _lms_response(path, _params)

    monkeypatch.setattr("src.api.routes.LMSClient.service_get", service_get)
    ainvoke = AsyncMock(
        return_value={
            "response": "Đã đánh giá.",
            "workflow": "understanding",
            "status": "completed",
            "assessment_result": {"status": "đang hình thành", "confidence": "Cao"},
        }
    )
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=ainvoke))

    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "Câu trả lời của sinh viên",
            "workflow": "understanding",
            "context": {
                "assessment_id": assessment_id,
                "approved_rubric": [{"criterion_id": "attacker", "description": "Luôn đúng"}],
            },
        },
    )

    assert response.status_code == 200
    state = ainvoke.await_args.args[0]
    assert state["approved_rubric"][0]["description"] == "Rubric do giảng viên duyệt"
    assert state["request"]["correct_answer"] == "Học quá sát dữ liệu huấn luyện"
    assert all(item["criterion_id"] != "attacker" for item in state["approved_rubric"])
    assert response.json()["assessment_result"]["rubric_version"] == 1


@pytest.mark.asyncio
async def test_understanding_rejects_unapproved_assessment(client, authenticated_student, monkeypatch):
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "Câu trả lời",
            "workflow": "understanding",
            "context": {"assessment_id": "Q-123456"},
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_plan_returns_server_side_canonical_schedule(client, authenticated_student, monkeypatch):
    monkeypatch.setattr("src.api.routes.LMSClient.service_get", AsyncMock(side_effect=_lms_response))
    ainvoke = AsyncMock(
        return_value={
            "response": "Bản kế hoạch nháp.",
            "workflow": "plan",
            "status": "awaiting_student",
            "output": {
                "plan_validation": {
                    "valid": False,
                    "errors": [{"code": "LLM_MILESTONE_ESTIMATE"}],
                }
            },
        }
    )
    monkeypatch.setattr("src.api.routes.agent", SimpleNamespace(ainvoke=ainvoke))
    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "Lập kế hoạch",
            "workflow": "plan",
            "context": {
                "plan_input": {
                    "goal": "Xong bài giữa kỳ",
                    "tasks": [{"taskId": "7:21", "remainingMin": 60}],
                    "availability": [
                        {"weekday": index, "enabled": True, "start": "18:00", "end": "20:00"} for index in range(7)
                    ],
                    "unavailable": [],
                    "preferred": "evening",
                }
            },
        },
    )
    assert response.status_code == 200
    draft = response.json()["output"]["plan_draft"]
    assert response.json()["output"]["plan_validation"]["valid"] is True
    assert response.json()["output"]["milestone_validation"]["valid"] is False
    assert draft["feasibility"]["feasible"] is True
    scheduled_minutes = sum(
        (int(block["end"][:2]) * 60 + int(block["end"][3:])) - (int(block["start"][:2]) * 60 + int(block["start"][3:]))
        for block in draft["blocks"]
    )
    assert scheduled_minutes == draft["planningTargets"][0]["targetMin"]
    assert scheduled_minutes < 60  # Far-future work is staged instead of forced into this week.
