import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api import study_sessions as api
from src.config import Settings, get_settings
from src.db import Base, get_db
from src.main import app
from src.persistence_models import LearnerMemory, LearningEvent, StudyTimerSession, UserWorkspace
from src.security import SessionContext, get_current_session, require_csrf


@pytest.fixture
def timer_env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(_env_file=None, app_env="test", institution_id="rhythm-test")
    user = SessionContext(9001, 1, (1, 2), "student", "Fixture", "fixture@example.edu", "x", "test", 4102444800)
    clock = [datetime(2026, 10, 10, 8, tzinfo=UTC)]
    monkeypatch.setattr(api, "now", lambda: clock[0])
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_session] = lambda: user
    app.dependency_overrides[require_csrf] = lambda: user
    with factory() as db:
        db.add(LearnerMemory(id="rhythm-test:9001:1", institution_id="rhythm-test", user_id=9001, course_id=1,
            profile_json=json.dumps({"last_confirmed_plan": {"blocks": [
                {"id": "b1", "taskId": "1:a", "date": "2026-10-10", "start": "16:00", "end": "17:00"}]}}),
            mastery_json=json.dumps({"relation": {"level": "application", "source_evidence_ids": ["e1"]}})))
        db.add(UserWorkspace(user_id=9001, state_json=json.dumps({"studyPreferences": {"sessionMinutes": 60, "breakMinutes": 10},
                    "plan": {"id": "confirmed"}, "taskProgress": {"1:a": {"estimateMin": 120}}})))
        db.commit()
    yield factory, clock, user
    for dependency in [get_db, get_settings, get_current_session, require_csrf]:
        app.dependency_overrides.pop(dependency, None)
    engine.dispose()


async def start(client):
    response = await client.post("/api/v1/study-sessions", json={"courseId": 1, "blockId": "b1"})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_prepare_is_canonical_light_scoped_and_revalidates_acl(client, timer_env, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.services import do_preparation as service
    factory, _, _ = timer_env
    calls, visible = [], [11, 12]
    async def upstream(self, path, params=None):
        calls.append(path)
        assert params == {"user_id": 9001}
        assert not any(word in path for word in ("planner", "submissions", "/courses/2/"))
        with factory() as db:
            assert api.confirmed_block(db, app.dependency_overrides[get_current_session](),
                app.dependency_overrides[get_settings](), "b1")
        if path.endswith("/courses"):
            return [{"id": 1, "code": "CS101", "enrollment_role": "student"}]
        if path.endswith("/assignments"):
            return [{"id": "a", "title": "Whole assignment", "description": "Read the problem.", "published": True}]
        if path.endswith("/modules"):
            return [{"id": 3, "name": "Chapter 3", "published": True, "items": [
                {"id": 1, "type": "assignment", "content_id": "a"},
                {"id": 2, "type": "file", "content_id": 11},
            ]}, {"id": 4, "name": "Chapter 4", "items": [{"id": 3, "type": "file", "content_id": 12}]}]
        if path.endswith("/files"):
            return [{"id": identifier, "title": f"Slide {identifier}", "kind": "slides", "source_url": f"/api/files/course-1-{identifier}.pdf"}
                for identifier in visible]
        if path.endswith("/content"):
            return []
        raise AssertionError(path)
    monkeypatch.setattr(service.LMSClient, "service_get", upstream)
    with factory() as db:
        memory = db.get(LearnerMemory, "rhythm-test:9001:1")
        profile = json.loads(memory.profile_json)
        profile["last_confirmed_plan"]["blocks"][0]["milestoneTitle"] = "Read requirements"
        memory.profile_json = json.dumps(profile)
        db.commit()
    response = await client.post('/api/v1/study-sessions/prepare', json={"courseId": 1, "blockId": "b1"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["objective"] == "Read requirements" and data["planned_minutes"] == 60
    assert data["scope"]["module_ids"] == ["3"]
    assert [resource["id"] for resource in data["recommended_resources"]] == ["file:11", "assignment:1:a"]
    assert len(calls) == 5
    visible.remove(11)
    response = await client.post('/api/v1/study-sessions/prepare', json={"courseId": 1, "blockId": "b1"})
    assert response.status_code == 200
    assert all(resource["id"] != "file:11" for resource in response.json()["recommended_resources"])
    assert response.json()["resource_version"] != data["resource_version"]
    visible.append(11)
    agent = AsyncMock(return_value={"workflow": "qa", "status": "completed", "response": "Guided support", "source_refs": []})
    monkeypatch.setattr(app.state, "agent", SimpleNamespace(ainvoke=agent), raising=False)
    response = await client.post('/api/v1/chat', json={"workflow": "qa", "message": "Explain this step",
        "context": {"do_course_id": 1, "do_block_id": "b1", "allowed_resource_ids": ["file:12"]}})
    assert response.status_code == 200, response.text
    context = agent.await_args.args[0]
    assert context["allowed_resource_ids"] == ["assignment:1:a", "file:11", "file:12"]
    assert context["preferred_resource_ids"] == ["assignment:1:a", "file:11"]
    assert context["do_scope"]["module_ids"] == ["3"]
    assert context["do_session"]["objective"] == data["objective"]
    assert len(context["assignments"]) == 1 and len(calls) == 15


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,status", [
    ({"courseId": 999, "blockId": "b1"}, 403),
    ({"courseId": 2, "blockId": "b1"}, 409),
    ({"courseId": 1, "blockId": "draft"}, 409),
    ({"courseId": 1, "blockId": "b1", "objective": "Client fabricated"}, 422),
])
async def test_prepare_rejects_unconfirmed_cross_course_and_client_objectives(client, timer_env, monkeypatch, payload, status):
    from src.services import do_preparation as service
    async def forbidden(*args, **kwargs):
        raise AssertionError("Rejected requests must not contact LMS or LLM")
    monkeypatch.setattr(service.LMSClient, "service_get", forbidden)
    response = await client.post('/api/v1/study-sessions/prepare', json=payload)
    assert response.status_code == status


@pytest.mark.asyncio
async def test_session_keeps_confirmed_activity_and_rhythm_not_later_preferences(client, timer_env):
    factory, clock, _ = timer_env
    with factory() as db:
        memory = db.get(LearnerMemory, "rhythm-test:9001:1")
        profile = json.loads(memory.profile_json)
        profile["last_confirmed_plan"]["blocks"][0].update(activityType="coding", activitySource="milestone_action_rule",
            rhythm={"sessionMinutes": 40, "breakMinutes": 5}, checkpointMinutes=5)
        memory.profile_json = json.dumps(profile)
        workspace = db.get(UserWorkspace, 9001)
        workspace.state_json = json.dumps({"studyPreferences": {"sessionMinutes": 120, "breakMinutes": 20}})
        db.commit()
    row = await start(client)
    assert row["rhythm"] == {"sessionMinutes": 40, "breakMinutes": 5}
    assert row["activity_type"] == "coding" and row["checkpoint_minutes"] == 5
    clock[0] += timedelta(seconds=20)
    result = await event(client, row, "complete", completionPercent=50)
    assert result.status_code == 200
    evaluation = result.json()["evaluation"]
    assert evaluation["activity_type"] == "coding"
    assert evaluation["rhythm"] == row["rhythm"]
    assert evaluation["checkpoint_minutes"] == 5


@pytest.mark.asyncio
async def test_legacy_unclassified_session_does_not_invent_activity(client, timer_env):
    row = await start(client)
    assert row["activity_type"] == "unknown"
    assert row["rhythm"] == {"sessionMinutes": 60, "breakMinutes": 10}


async def event(client, row, action, key="event-key-01", **extra):
    return await client.post(f"/api/v1/study-sessions/{row['id']}/events", json={
        "action": action, "expectedVersion": row["version"], "eventKey": key, **extra})


@pytest.mark.asyncio
async def test_checkpoint_pause_resume_recovery_and_no_inactivity_inference(client, timer_env):
    _, clock, _ = timer_env
    row = await start(client)
    clock[0] += timedelta(seconds=20)
    checkpoint = await event(client, row, "checkpoint")
    row = checkpoint.json()
    assert row["observed_seconds"] == 20
    assert row["status"] == "running"  # no keyboard/mouse activity required
    clock[0] += timedelta(seconds=10)
    row = (await event(client, row, "pause", "event-pause-01", interruptionReason="unexpected")).json()
    assert row["observed_seconds"] == 30
    clock[0] += timedelta(hours=8)
    row = (await event(client, row, "resume", "event-resume-01", interruptionReason="unexpected")).json()
    assert row["observed_seconds"] == 30
    clock[0] += timedelta(seconds=20)
    row = (await event(client, row, "checkpoint", "event-check-02")).json()
    assert row["observed_seconds"] == 50
    clock[0] += timedelta(hours=2)
    row = (await event(client, row, "checkpoint", "event-check-03")).json()
    assert row["observed_seconds"] == 50
    assert row["status"] == "paused" and row["unobserved_gap"]


@pytest.mark.asyncio
async def test_retry_after_response_loss_does_not_add_time_or_duplicate_completion(client, timer_env):
    factory, clock, _ = timer_env
    row = await start(client)
    clock[0] += timedelta(seconds=20)
    first = await event(client, row, "checkpoint")
    retry = await event(client, row, "checkpoint")
    assert first.json() == retry.json()
    row = first.json()
    finished = await event(client, row, "complete", "finish-key-01", completionPercent=100, interruptionReason="unexpected")
    again = await event(client, row, "complete", "finish-key-01", completionPercent=100, interruptionReason="unexpected")
    assert finished.status_code == again.status_code == 200
    assert finished.json() == again.json()
    with factory() as db:
        memory = db.get(LearnerMemory, "rhythm-test:9001:1")
        assert json.loads(memory.mastery_json)["relation"]["level"] == "application"
        history = json.loads(memory.profile_json)["do_history"]
        assert len(history) == 1
        assert history[0]["interruption_reason"] == "unexpected"
        assert len(list(db.scalars(select(LearningEvent).where(LearningEvent.event_type == "STUDY_SESSION_COMPLETED")))) == 1


@pytest.mark.asyncio
async def test_stale_tab_and_reused_key_with_different_body_are_rejected(client, timer_env):
    row = await start(client)
    assert (await event(client, row, "checkpoint")).status_code == 200
    assert (await event(client, row, "pause", "other-tab-01")).status_code == 409
    assert (await event(client, row, "complete")).status_code == 409


@pytest.mark.asyncio
async def test_one_active_block_per_learner_and_cancelled_block_can_restart(client, timer_env):
    factory, _, _ = timer_env
    with factory() as db:
        memory = db.get(LearnerMemory, "rhythm-test:9001:1")
        profile = json.loads(memory.profile_json)
        profile["last_confirmed_plan"]["blocks"].append(
            {"id": "b2", "taskId": "1:a", "date": "2026-10-10", "start": "17:10", "end": "18:00"})
        memory.profile_json = json.dumps(profile)
        db.commit()
    row = await start(client)
    current = (await client.get("/api/v1/study-sessions/current?blockId=b2")).json()
    assert current["session"] is None and current["activeSession"]["blockId"] == "b1"
    assert (await client.post("/api/v1/study-sessions", json={"courseId": 1, "blockId": "b2"})).status_code == 409
    assert (await event(client, row, "cancel")).status_code == 200
    restarted = await start(client)
    assert restarted["id"] == row["id"] and restarted["version"] > row["version"]
    assert restarted["observed_seconds"] == 0
    assert (await event(client, restarted, "cancel", "cancel-key-02")).status_code == 200
    other = await client.post("/api/v1/study-sessions", json={"courseId": 1, "blockId": "b2"})
    assert other.status_code == 200


@pytest.mark.asyncio
async def test_note_checkpoint_survives_reload_recovery(client, timer_env):
    row = await start(client)
    row = (await event(client, row, "checkpoint", note="Learner draft note")).json()
    row = (await event(client, row, "recover", "recover-key-01")).json()
    assert row["note"] == "Learner draft note"


@pytest.mark.asyncio
async def test_start_is_idempotent_and_requires_confirmed_enrolled_block(client, timer_env):
    first = await start(client)
    assert (await start(client))["id"] == first["id"]
    assert (await client.post("/api/v1/study-sessions", json={"courseId": 1, "blockId": "draft-block"})).status_code == 409
    assert (await client.post("/api/v1/study-sessions", json={"courseId": 9, "blockId": "b1"})).status_code == 403


@pytest.mark.asyncio
async def test_other_user_and_teacher_cannot_read_or_mutate_timer(client, timer_env):
    _, _, user = timer_env
    row = await start(client)
    other = replace(user, user_id=9002)
    app.dependency_overrides[require_csrf] = lambda: other
    app.dependency_overrides[get_current_session] = lambda: other
    assert (await event(client, row, "pause")).status_code == 404
    assert (await client.get("/api/v1/study-sessions/current?blockId=b1")).json()["session"] is None
    teacher = replace(user, role="instructor")
    app.dependency_overrides[get_current_session] = lambda: teacher
    assert (await client.get("/api/v1/study-sessions/current?blockId=b1")).status_code == 403


@pytest.mark.asyncio
async def test_outside_minutes_are_labelled_self_report_not_mastery(client, timer_env):
    factory, _, _ = timer_env
    row = await start(client)
    result = await event(client, row, "complete", outsideMinutes=60, completionPercent=100)
    assert result.json()["evaluation"]["time_source"] == "self_report"
    assert result.json()["evaluation"]["actual_minutes"] == 60
    with factory() as db:
        assert json.loads(db.get(LearnerMemory, "rhythm-test:9001:1").mastery_json)["relation"]["level"] == "application"


@pytest.mark.asyncio
async def test_rhythm_never_auto_applies_and_confirmation_rechecks_current_preferences(client, timer_env):
    factory, _, _ = timer_env
    with factory() as db:
        for i in range(3):
            observation = {"session_id": f"fixture-{i}", "task_id": "1:a", "course_id": 1, "actual_minutes": 60, "planned_minutes": 60, "activity_type": "concept",
                           "interruption_reason": "none", "length_feeling": "too_long", "time_source": "timer",
                           "rhythm": {"sessionMinutes": 60, "breakMinutes": 10}, "readiness_key": "same"}
            db.add(StudyTimerSession(id=f"fixture-{i}", institution_id="rhythm-test", user_id=9001, course_id=1,
                                    block_id=f"fixture-b{i}", task_id="1:a", state_json=json.dumps({"evaluation": observation})))
        db.commit()
        before = db.get(UserWorkspace, 9001).state_json
    report = (await client.get("/api/v1/study-sessions/rhythm/proposal")).json()
    assert report["proposal"]["preferences"]["sessionMinutes"] == 45
    proposal_id = report["proposal"]["id"]
    response = await client.post("/api/v1/study-sessions/rhythm/confirm", json={"proposalId": proposal_id})
    assert response.status_code == 200
    assert not response.json()["planChanged"]
    assert response.json()["scope"] == {"courseId": 1, "activityType": "concept"}
    with factory() as db:
        workspace = db.get(UserWorkspace, 9001)
        assert workspace.state_json == before  # explicit choice is persisted by versioned workspace, never the proposal GET
        saved = json.loads(before)
        saved["studyPreferences"]["sessionMinutes"] = 90
        workspace.state_json = json.dumps(saved)
        db.commit()
    assert (await client.post("/api/v1/study-sessions/rhythm/confirm", json={"proposalId": proposal_id})).status_code == 409
