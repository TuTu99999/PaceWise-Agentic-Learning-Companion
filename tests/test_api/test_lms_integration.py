import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from src.api.lms_integration import (
    _aggregate_dashboard_weeks,
    _assignment_risk_summary,
    _dashboard_course_summary,
    _dashboard_current_week,
    _task_payload,
    _weekly_completion,
)
from src.api.workspace import (
    InstructorActionRequest,
    _safe_workspace,
    _versioned_assessment_payload,
    check_login_rate_limit,
    create_instructor_action,
    delete_assessment_design,
    record_failed_login,
)
from src.config import Settings, get_settings
from src.course_source.db import SessionLocal as CourseSourceSessionLocal
from src.course_source.db import initialize_database as initialize_course_source
from src.course_source.models import Course, CourseModule, ModuleItem, Resource
from src.db import SessionLocal
from src.main import app
from src.persistence_models import AgentReviewCase, InstructorAction, StudyTimerSession
from src.security import SessionContext


@pytest.fixture
def integration_settings():
    settings = Settings(
        _env_file=None,
        app_env="test",
        pacewise_api_key="test-service-key",
        pacewise_session_secret="test-session-secret-with-at-least-32-characters",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def launch_claims():
    return {
        "iss": "canvas-lms-simulator",
        "aud": "pacewise",
        "sub": "12",
        "course_id": 7,
        "role": "student",
        "name": "Student Test",
        "email": "student@example.edu",
    }


@pytest.mark.asyncio
async def test_launch_creates_http_only_session(client, monkeypatch, integration_settings, launch_claims):
    verify = AsyncMock(return_value=launch_claims)
    monkeypatch.setattr("src.services.lms_client.LMSClient.verify_launch", verify)
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.service_get",
        AsyncMock(return_value=[{"id": 7}]),
    )

    response = await client.post("/api/v1/auth/lms-launch", json={"token": "x" * 40})

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "student"
    cookies = response.headers.get_list("set-cookie")
    assert any("pacewise_session=" in value and "HttpOnly" in value for value in cookies)
    assert any("pacewise_csrf=" in value and "HttpOnly" not in value for value in cookies)
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["courseId"] == "7"


@pytest.mark.asyncio
async def test_session_cannot_cross_course_or_instructor_boundary(
    client, monkeypatch, integration_settings, launch_claims
):
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.verify_launch",
        AsyncMock(return_value=launch_claims),
    )
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.service_get",
        AsyncMock(return_value=[{"id": 7}]),
    )
    assert (await client.post("/api/v1/auth/lms-launch", json={"token": "x" * 40})).status_code == 200

    cross_course = await client.get("/api/v1/lms/courses/8/assignments")
    instructor_only = await client.get("/api/v1/instructor/overview")
    assessment_designs = await client.get("/api/v1/instructor/assessment-designs")

    assert cross_course.status_code == 403
    assert instructor_only.status_code == 403
    assert assessment_designs.status_code == 403


@pytest.mark.asyncio
async def test_logout_requires_csrf(client, monkeypatch, integration_settings, launch_claims):
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.verify_launch",
        AsyncMock(return_value=launch_claims),
    )
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.service_get",
        AsyncMock(return_value=[{"id": 7}]),
    )
    await client.post("/api/v1/auth/lms-launch", json={"token": "x" * 40})
    stolen_session = client.cookies["pacewise_session"]

    rejected = await client.post("/api/v1/auth/logout")
    accepted = await client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": client.cookies["pacewise_csrf"]},
    )

    assert rejected.status_code == 403
    assert accepted.status_code == 200
    client.cookies.set("pacewise_session", stolen_session)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_logout_pauses_running_study_timer_without_counting_absence(
    client, monkeypatch, integration_settings, launch_claims
):
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.verify_launch",
        AsyncMock(return_value=launch_claims),
    )
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.service_get",
        AsyncMock(return_value=[{"id": 7}]),
    )
    await client.post("/api/v1/auth/lms-launch", json={"token": "x" * 40})
    with SessionLocal() as db:
        db.add(StudyTimerSession(
            id="SS-LOGOUT",
            institution_id=integration_settings.institution_id,
            user_id=12,
            course_id=7,
            block_id="block-logout",
            task_id="7:task",
            active_scope=f"{integration_settings.institution_id}:12",
            version=3,
            state_json=json.dumps({
                "status": "running",
                "observed_seconds": 120,
                "checkpoint_at": "2026-10-10T08:00:00+00:00",
                "interruption_reason": "none",
                "unobserved_gap": False,
            }),
        ))
        db.commit()

    response = await client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": client.cookies["pacewise_csrf"]},
    )

    assert response.status_code == 200
    assert response.json()["studySessionPaused"] is True
    with SessionLocal() as db:
        saved = db.get(StudyTimerSession, "SS-LOGOUT")
        state = json.loads(saved.state_json)
        assert saved.version == 4
        assert state["status"] == "paused"
        assert state["observed_seconds"] == 120
        assert state["unobserved_gap"] is True


@pytest.mark.asyncio
async def test_switch_course_and_persist_workspace(client, monkeypatch, integration_settings, launch_claims):
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.verify_launch",
        AsyncMock(return_value=launch_claims),
    )
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.service_get",
        AsyncMock(return_value=[{"id": 7}, {"id": 8}]),
    )
    await client.post("/api/v1/auth/lms-launch", json={"token": "x" * 40})
    csrf = client.cookies["pacewise_csrf"]

    switched = await client.post(
        "/api/v1/auth/course",
        json={"courseId": 8},
        headers={"X-CSRF-Token": csrf},
    )
    saved = await client.put(
        "/api/v1/workspace",
        json={
            "state": {
                "plan": {"id": "plan-1"},
                "calendarDraft": {"blocks": [{"id": "draft-only", "date": "2026-10-10", "start": "19:07", "end": "20:22"}], "needsAnalysis": True, "updatedAt": "2026-10-10T00:00:00Z"},
                "taskProgress": {
                    "7:10": {
                        "estimateMin": 90,
                        "loggedMin": 45,
                        "status": "in_progress",
                        "updatedAt": "2026-10-02T08:00:00Z",
                    }
                },
                "reflections": {"8": {"courseId": "8", "answers": ["a", "b", "c"]}},
                "recoveryOptions": [{"id": "A", "newBlocks": []}],
                "recoveryOptionsKey": "drift:7:10:60:plan-1",
                "reminders": {
                    "preferences": {
                        "enabled": True,
                        "browserEnabled": True,
                        "dailyCap": 3,
                        "studyBlockLeadMinutes": 15,
                        "digestHour": 20,
                    },
                    "deliveredAt": {"study-block:1": "2026-10-03T02:00:00Z"},
                    "readIds": [],
                },
                "user": {"should": "not persist"},
            }
        },
        headers={"X-CSRF-Token": csrf},
    )
    loaded = await client.get("/api/v1/workspace")

    assert switched.json()["courseId"] == "8"
    assert saved.status_code == 200
    assert loaded.json()["state"]["plan"]["id"] == "plan-1"
    assert loaded.json()["state"]["calendarDraft"]["blocks"][0]["start"] == "19:07"
    assert loaded.json()["state"]["calendarDraft"]["needsAnalysis"] is True
    assert loaded.json()["state"]["taskProgress"]["7:10"]["loggedMin"] == 45
    assert loaded.json()["state"]["reflections"]["8"]["courseId"] == "8"
    assert loaded.json()["state"]["recoveryOptions"][0]["id"] == "A"
    assert loaded.json()["state"]["recoveryOptionsKey"] == "drift:7:10:60:plan-1"
    assert loaded.json()["state"]["reminders"]["preferences"]["dailyCap"] == 3
    assert loaded.json()["state"]["reminders"]["deliveredAt"]["study-block:1"]
    assert "user" not in loaded.json()["state"]

    updated = await client.put(
        "/api/v1/workspace",
        json={"state": {"plan": {"id": "plan-2"}}},
        headers={"X-CSRF-Token": csrf},
    )
    assert updated.json()["version"] == saved.json()["version"] + 1

    conflicted = await client.put(
        "/api/v1/workspace",
        json={"state": {"plan": {"id": "stale-plan"}}, "expectedVersion": saved.json()["version"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert conflicted.status_code == 409
    assert (await client.get("/api/v1/workspace")).json()["state"]["plan"]["id"] == "plan-2"


def test_login_rate_limit_is_shared_in_database():
    settings = Settings(_env_file=None, login_rate_limit=2, login_rate_window_seconds=600)
    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.10"))
    with SessionLocal() as db:
        record_failed_login(request, "student@example.edu", db)
        check_login_rate_limit(request, "student@example.edu", db, settings)
        record_failed_login(request, "student@example.edu", db)
        with pytest.raises(HTTPException) as blocked:
            check_login_rate_limit(request, "student@example.edu", db, settings)
    assert blocked.value.status_code == 429


def test_workspace_rejects_payload_larger_than_one_megabyte():
    with pytest.raises(HTTPException) as too_large:
        _safe_workspace({"settings": {"blob": "x" * 1_000_001}})
    assert too_large.value.status_code == 413


def test_instructor_actions_validate_and_persist_review_workflow(monkeypatch):
    invalidations = []
    monkeypatch.setattr(
        "src.api.workspace._notify_instructor_action_change",
        lambda **payload: invalidations.append(payload),
    )
    settings = Settings(_env_file=None, institution_id="test-university")
    session = SessionContext(
        user_id=22,
        course_id=707,
        course_ids=(707,),
        role="instructor",
        name="Teacher",
        email="teacher@example.edu",
        csrf_hash="hash",
        sid="sid",
        exp=4_102_444_800,
    )
    with SessionLocal() as db:
        db.query(InstructorAction).filter(InstructorAction.course_id == 707).delete()
        db.query(AgentReviewCase).filter(AgentReviewCase.course_id == 707).delete()
        db.add(
            AgentReviewCase(
                id="review-action-case",
                institution_id=settings.institution_id,
                course_id=707,
                student_user_id=12,
                case_type="understanding_review",
                entity_id="Q-7",
                status="pending",
                payload_json=json.dumps({"assessment_result": {"status": "developing"}}),
            )
        )
        db.commit()

        assessment = create_instructor_action(
            InstructorActionRequest(
                actionType="assessment",
                entityId="Q-7",
                payload={"status": "approved", "rubric": ["Reasoning"]},
            ),
            session,
            session,
            settings,
            db,
        )
        assert assessment["payload"]["version"] == 1

        with pytest.raises(HTTPException, match="Unsupported review"):
            create_instructor_action(
                InstructorActionRequest(
                    actionType="review",
                    entityId="review-action-case",
                    payload={"status": "unknown"},
                ),
                session,
                session,
                settings,
                db,
            )

        with pytest.raises(HTTPException, match="decision note"):
            create_instructor_action(
                InstructorActionRequest(
                    actionType="review",
                    entityId="review-action-case",
                    payload={"status": "needs_evidence"},
                ),
                session,
                session,
                settings,
                db,
            )

        resolved = []
        monkeypatch.setattr(
            "src.api.workspace.resolve_review_case",
            lambda _db, case, payload, _settings: resolved.append((case.id, payload["status"])),
        )
        review = create_instructor_action(
            InstructorActionRequest(
                actionType="review",
                entityId="review-action-case",
                payload={
                    "status": "edited",
                    "note": "Corrected after reviewing evidence",
                    "edited_result": {"status": "mastered"},
                },
            ),
            session,
            session,
            settings,
            db,
        )
        case = db.get(AgentReviewCase, "review-action-case")
        case_payload = json.loads(case.payload_json)

    assert review["payload"]["status"] == "edited"
    assert case_payload["instructor_note"] == "Corrected after reviewing evidence"
    assert resolved == [("review-action-case", "edited")]
    assert invalidations == [
        {"course_id": 707, "actor_user_id": 22, "action_type": "assessment", "entity_id": "Q-7"},
        {"course_id": 707, "actor_user_id": 22, "action_type": "review", "entity_id": "review-action-case"},
    ]


def test_task_payload_preserves_effective_lms_policy_and_evidence():
    assignment = {
        "id": 5,
        "title": "Capstone",
        "description": "Explain the trade-offs",
        "due_at": "2026-10-10T23:59:00+07:00",
        "unlock_at": "2026-10-01T08:00:00+07:00",
        "lock_at": "2026-10-11T00:00:00+07:00",
        "override_target": "student",
        "points_possible": 20,
        "assignment_group": {"id": 2, "name": "Projects", "weight": 60},
        "grading_type": "points",
        "peer_reviews": True,
        "group_category_id": 9,
        "rubric": {"id": 4, "title": "Reasoning", "criteria": []},
    }
    submission = {
        "workflow_state": "submitted",
        "late": False,
        "score": 17,
        "feedback": "Good evidence",
        "rubric": {"reasoning": 8},
        "history": [{"attempt_number": 1}, {"attempt_number": 2}],
    }

    task = _task_payload(7, assignment, submission)

    assert task["id"] == "7:5"
    assert task["deadline"] == "2026-10-10"
    assert task["overrideTarget"] == "student"
    assert task["assignmentGroup"] == {"id": "2", "name": "Projects", "weight": 60.0}
    assert task["submission"]["attempts"] == 2
    assert task["rubric"]["title"] == "Reasoning"


def test_weekly_completion_uses_real_due_weeks_and_on_time_submissions():
    assignments = [
        {"id": 10, "due_at": "2026-10-06T23:59:00+07:00"},
        {"id": 11, "due_at": "2026-10-14T23:59:00+07:00"},
    ]
    submissions = [
        {"assignment_id": 10, "user_id": 1, "late": False, "workflow_state": "submitted"},
        {"assignment_id": 10, "user_id": 2, "late": True, "workflow_state": "submitted"},
        {"assignment_id": 11, "user_id": 1, "late": False, "workflow_state": "graded"},
    ]

    rows = _weekly_completion(
        assignments,
        submissions,
        {1, 2},
        as_of=datetime(2026, 10, 20, tzinfo=UTC),
    )

    assert [row["week"] for row in rows] == ["05/10", "12/10"]
    assert [row["rate"] for row in rows] == [0.5, 0.5]


def test_weekly_completion_excludes_future_due_weeks():
    assignments = [
        {"id": 10, "due_at": "2026-10-01T23:59:00Z"},
        {"id": 11, "due_at": "2026-11-01T23:59:00Z"},
    ]
    submissions = [
        {"assignment_id": 10, "user_id": 1, "late": False, "workflow_state": "submitted"},
        {"assignment_id": 11, "user_id": 1, "late": False, "workflow_state": "submitted"},
    ]

    rows = _weekly_completion(
        assignments,
        submissions,
        {1},
        as_of=datetime(2026, 10, 3, tzinfo=UTC),
    )

    assert [row["week"] for row in rows] == ["28/09"]


def test_assignment_risk_uses_near_term_unsubmitted_work_not_all_year():
    now = datetime(2026, 10, 3, 8, tzinfo=UTC)
    assignments = [
        {
            "id": 10,
            "title": "Near deadline",
            "due_at": "2026-10-05T08:00:00Z",
            "points_possible": 10,
        },
        {
            "id": 11,
            "title": "End of year",
            "due_at": "2026-12-20T08:00:00Z",
            "points_possible": 20,
        },
    ]
    submissions = [
        {"assignment_id": 10, "user_id": 1, "late": False, "workflow_state": "submitted"},
    ]

    rows, student_ids = _assignment_risk_summary(
        assignments,
        submissions,
        {1, 2, 3},
        as_of=now,
    )

    assert [row["assignmentId"] for row in rows] == ["10"]
    assert rows[0]["atRiskCount"] == 2
    assert "missingMinutes" not in rows[0]  # Points cannot establish an unprotected time budget.
    assert student_ids == {2, 3}


def test_dashboard_summary_uses_real_obligations_for_each_student_even_in_small_classes():
    now = datetime(2026, 10, 14, tzinfo=UTC)
    course = {"id": 1, "code": "CS101", "name": "Python", "term": "HK1"}
    enrollments = [
        {"user_id": 99, "name": "Teacher", "role": "instructor"},
        *[
            {"user_id": index, "name": f"Student {index}", "role": "student"}
            for index in range(1, 6)
        ],
    ]
    assignments = [
        {"id": 10, "title": "Overdue A", "due_at": "2026-10-10T00:00:00Z"},
        {"id": 11, "title": "Overdue B", "due_at": "2026-10-11T00:00:00Z"},
        {"id": 12, "title": "Soon", "due_at": "2026-10-15T00:00:00Z"},
    ]
    submissions = [
        {"assignment_id": 10, "user_id": 1, "workflow_state": "submitted", "submitted_at": "2026-10-09T00:00:00Z"}
    ]

    summary, alerts, weeks = _dashboard_course_summary(
        course, enrollments, assignments, submissions, as_of=now
    )

    assert summary == {
        "id": "1", "code": "CS101", "name": "Python", "term": "HK1", "studentCount": 5,
        "highRisk": 5, "openWarnings": 0, "overdue": 5, "completionRate": 0.1,
        "completionCount": 1, "completionTotal": 10,
    }
    assert alerts[0]["studentName"] == "Student 1"
    assert alerts[0]["overdueCount"] == 1 and alerts[0]["upcomingCount"] == 1
    assert weeks[-1]["count"] == 1 and weeks[-1]["total"] == 10

    small_summary, small_alerts, small_weeks = _dashboard_course_summary(
        course, enrollments[:2], assignments, submissions, as_of=now
    )
    assert small_summary["studentCount"] == 1
    assert small_summary["highRisk"] == 1
    assert [(item["studentId"], item["studentName"]) for item in small_alerts] == [
        ("1", "Student 1")
    ]
    assert small_weeks[-1]["count"] == 1 and small_weeks[-1]["total"] == 2

    _summary, _alerts, public_schedule = _dashboard_course_summary(
        course,
        enrollments[:2],
        assignments,
        submissions,
        as_of=now,
        schedule_items=[],
    )
    assert public_schedule
    assert public_schedule[0]["rate"] == 0.5 and public_schedule[0]["total"] == 2
    assert public_schedule[-1]["status"] == "current"
    assert sum(item["taskCount"] for item in public_schedule) == 3


def test_dashboard_weekly_aggregation_weights_courses_by_real_opportunities():
    rows = _aggregate_dashboard_weeks([
        [{
            "week": "05/10", "weekStart": "2026-10-05", "weekEnd": "2026-10-11",
            "count": 1, "total": 2, "rate": 0.5,
        }],
        [{
            "week": "05/10", "weekStart": "2026-10-05", "weekEnd": "2026-10-11",
            "count": 8, "total": 8, "rate": 1.0,
        }],
    ])
    assert rows == [{
        "week": "05/10", "weekNumber": None, "weekStart": "2026-10-05",
        "weekEnd": "2026-10-11", "count": 9, "total": 10,
        "scheduledTotal": 0, "taskCount": 0, "lessonCount": 0,
        "status": None, "rate": 0.9,
    }]


def test_dashboard_current_week_uses_vietnam_calendar_not_latest_history():
    weeks = [{
        "week": "05/10", "weekStart": "2026-10-05", "weekEnd": "2026-10-11",
        "count": 33, "total": 56, "rate": 33 / 56,
    }]
    result = _dashboard_current_week(
        weeks,
        as_of=datetime(2026, 10, 14, 10, 30, tzinfo=UTC),
    )
    assert result == {
        "weekNumber": None,
        "weekStart": "2026-10-12",
        "weekEnd": "2026-10-18",
        "rate": None,
        "count": 0,
        "total": 0,
        "scheduledTotal": 0,
        "taskCount": 0,
        "lessonCount": 0,
    }

    current = _dashboard_current_week(
        weeks + [{
            "week": "12/10", "weekStart": "2026-10-12", "weekEnd": "2026-10-18",
            "count": 15, "total": 20, "rate": 0.75,
        }],
        as_of=datetime(2026, 10, 18, 16, 59, tzinfo=UTC),
    )
    assert current["weekStart"] == "2026-10-12"
    assert current["rate"] == 0.75

    next_week_in_vietnam = _dashboard_current_week(
        weeks,
        as_of=datetime(2026, 10, 18, 17, 1, tzinfo=UTC),
    )
    assert next_week_in_vietnam["weekStart"] == "2026-10-19"


def test_dashboard_kpis_and_student_feed_share_the_same_enrolled_students():
    now = datetime(2026, 10, 14, tzinfo=UTC)
    course = {"id": 701, "code": "CS101", "name": "Python", "term": "HK1"}
    enrollments = [
        {"user_id": 22, "name": "Teacher", "role": "instructor"},
        *[
            {"user_id": index, "name": f"Student {index}", "role": "student"}
            for index in range(1, 6)
        ],
    ]
    assignments = [
        {"id": 10, "title": "Overdue A", "due_at": "2026-10-10T00:00:00Z"},
        {"id": 11, "title": "Overdue B", "due_at": "2026-10-11T00:00:00Z"},
        {"id": 12, "title": "Soon", "due_at": "2026-10-15T00:00:00Z"},
    ]
    submissions = [
        {
            "assignment_id": assignment_id,
            "user_id": student_id,
            "workflow_state": "submitted",
            "submitted_at": "2026-10-09T00:00:00Z",
        }
        for student_id, assignment_ids in {
            2: [11, 12],
            3: [10, 11],
            4: [10, 11, 12],
            5: [10, 11, 12],
            999: [10, 11, 12],  # Not enrolled in CS101; must not affect any metric.
        }.items()
        for assignment_id in assignment_ids
    ]

    summary, alerts, _weeks = _dashboard_course_summary(
        course, enrollments, assignments, submissions, as_of=now
    )

    assert summary["studentCount"] == 5
    assert summary["highRisk"] == 1
    assert summary["openWarnings"] == 2
    assert summary["overdue"] == 2
    assert summary["completionCount"] == 7
    assert summary["completionTotal"] == 10
    assert {
        (item["studentId"], item["studentName"], item["severity"], item["overdueCount"], item["upcomingCount"])
        for item in alerts
    } == {
        ("1", "Student 1", "high", 2, 1),
        ("2", "Student 2", "warning", 1, 0),
        ("3", "Student 3", "warning", 0, 1),
    }


def test_assessment_version_changes_only_when_rubric_content_changes():
    entity_id = "Q-version-test"
    with SessionLocal() as db:
        db.query(InstructorAction).filter(InstructorAction.entity_id == entity_id).delete()
        first = _versioned_assessment_payload(
            db,
            7,
            entity_id,
            {"status": "review", "rubric": ["Reasoning"], "assessmentSetId": "SET-chapter-2"},
        )
        db.add(InstructorAction(
            id="version-action-1",
            course_id=7,
            actor_user_id=1,
            action_type="assessment",
            entity_id=entity_id,
            payload_json=json.dumps(first),
        ))
        db.commit()
        approved = _versioned_assessment_payload(db, 7, entity_id, {"status": "approved"})
        changed = _versioned_assessment_payload(
            db,
            7,
            entity_id,
            {"status": "approved", "rubric": ["Reasoning", "Application"]},
        )

    assert first["version"] == 1
    assert approved["version"] == 1
    assert approved["rubric"] == ["Reasoning"]
    assert approved["assessmentSetId"] == "SET-chapter-2"
    assert changed["version"] == 2


def test_delete_assessment_uses_a_tombstone_and_keeps_the_approval_audit():
    entity_id = "Q-delete-test"
    session = SessionContext(
        user_id=22,
        course_id=707,
        course_ids=(707,),
        role="instructor",
        name="Teacher",
        email="teacher@example.edu",
        csrf_hash="hash",
        sid="sid",
        exp=4_102_444_800,
    )
    settings = Settings(_env_file=None, institution_id="test-university")
    with SessionLocal() as db:
        db.query(InstructorAction).filter(
            InstructorAction.course_id == session.course_id,
            InstructorAction.entity_id == entity_id,
        ).delete()
        db.commit()
        create_instructor_action(
            InstructorActionRequest(
                actionType="assessment",
                entityId=entity_id,
                payload={"status": "approved", "question": "Question", "rubric": ["Reasoning"]},
            ),
            session,
            session,
            settings,
            db,
        )
        deleted = delete_assessment_design(entity_id, session, session, db)
        actions = db.scalars(
            select(InstructorAction)
            .where(
                InstructorAction.course_id == session.course_id,
                InstructorAction.entity_id == entity_id,
            )
            .order_by(InstructorAction.created_at)
        ).all()
        latest = json.loads(actions[-1].payload_json)

    assert deleted == {"entityId": entity_id, "deleted": True, "retainedAudit": True}
    assert len(actions) == 2
    assert json.loads(actions[0].payload_json)["status"] == "approved"
    assert latest["status"] == "deleted"
    assert latest["question"] == "Question"
    assert latest["deletedAt"]


def test_assessment_source_is_resolved_from_the_uploaded_course_chapter_and_cross_course_is_blocked():
    initialize_course_source()
    with CourseSourceSessionLocal() as source_db:
        course = Course(
            code=f"ASSESS-{uuid4().hex}", name="Assessment source course", term="Test", color="#2563eb"
        )
        source_db.add(course)
        source_db.flush()
        resource = Resource(
            course_id=course.id,
            title="Chapter_2.pdf",
            kind="file",
            source_url="pacewise-object://test/chapter-2.pdf",
        )
        module = CourseModule(course_id=course.id, name="Chương 2", position=2, published=True)
        source_db.add_all([resource, module])
        source_db.flush()
        module_item = ModuleItem(
            module_id=module.id,
            title=resource.title,
            item_type="resource",
            content_id=resource.id,
            position=1,
            published=True,
        )
        source_db.add(module_item)
        source_db.commit()
        course_id, resource_id = course.id, resource.id

    try:
        with SessionLocal() as db:
            saved = _versioned_assessment_payload(
                db,
                course_id,
                "Q-valid-source",
                {
                    "question": "Explain the chapter concept.",
                    "rubric": ["Correct concept", "Grounded reasoning"],
                    "sourceResourceId": resource_id,
                    "sourceChapter": "Untrusted client value",
                },
            )
            with pytest.raises(HTTPException) as error:
                _versioned_assessment_payload(
                    db,
                    course_id + 1,
                    "Q-cross-course-source",
                    {"sourceResourceId": resource_id, "sourceChapter": "Chương 2"},
                )
    finally:
        with CourseSourceSessionLocal() as source_db:
            source_db.query(ModuleItem).filter(ModuleItem.id == module_item.id).delete()
            source_db.query(Resource).filter(Resource.id == resource_id).delete()
            source_db.query(CourseModule).filter(CourseModule.id == module.id).delete()
            source_db.query(Course).filter(Course.id == course_id).delete()
            source_db.commit()

    assert saved["source"] == "Chapter_2.pdf"
    assert saved["sourceChapter"] == "Chương 2"
    assert saved["sourceResourceId"] == resource_id
    assert error.value.status_code == 422
    assert error.value.detail == "Assessment source must be an uploaded file in this course"


def test_settings_can_read_mounted_secret_files(tmp_path):
    api_key_file = tmp_path / "api-key"
    session_secret_file = tmp_path / "session-secret"
    api_key_file.write_text("mounted-api-key", encoding="utf-8")
    session_secret_file.write_text("mounted-session-secret-with-32-characters", encoding="utf-8")

    settings = Settings(
        _env_file=None,
        pacewise_api_key_file=str(api_key_file),
        pacewise_session_secret_file=str(session_secret_file),
    )

    assert settings.pacewise_api_key == "mounted-api-key"
    assert settings.pacewise_session_secret == "mounted-session-secret-with-32-characters"


@pytest.mark.asyncio
async def test_security_headers_are_present(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
