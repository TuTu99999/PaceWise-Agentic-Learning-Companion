"""LMS contract regression: real HTTP + isolated SQL, no external services."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from app import security
from app.learning_api import effective_assignment_window
from app.main import app
from app.models import (
    Assignment,
    AssignmentOverride,
    CalendarEvent,
    Course,
    CourseContent,
    CourseModule,
    CourseSection,
    Enrollment,
    IntegrationEvent,
    ModuleItem,
    ModulePrerequisite,
    ModuleRequirement,
    PlannerItem,
    QuizAssignmentLink,
    Resource,
    ResourceAccess,
    SectionMembership,
    Submission,
    User,
)
from app.pacewise_contracts import sync_quiz_assignment
from sqlalchemy import select
from test_learning_api import _client, _login


@pytest.fixture
def env(monkeypatch):
    previous_factory, previous_overrides = security.SessionLocal, app.dependency_overrides.copy()
    monkeypatch.setenv("PACEWISE_API_KEY", "contract-test-key")
    client, factory = _client()
    teacher = _login(client, "teacher@example.test")
    student = _login(client, "student@example.test")
    with factory() as db:
        db.add(Course(id=2, code="PRIVATE", name="Not enrolled", term="Fall", color="#111111"))
        db.add(
            Assignment(
                id=2,
                course_id=1,
                title="Hidden",
                description="",
                due_at=datetime.now(UTC) + timedelta(days=8),
                published=False,
            )
        )
        db.add(CourseContent(id=1, course_id=1, kind="page", title="Hidden page", body="Private", published=False))
        db.add(CourseModule(id=2, course_id=1, name="Hidden module", position=2, published=False))
        db.commit()
    yield client, factory, teacher, student, {"X-PaceWise-Key": "contract-test-key"}
    client.close()
    security.SessionLocal = previous_factory
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous_overrides)


@pytest.mark.parametrize(
    "endpoint",
    ["assignments", "submissions", "modules", "content", "grades", "quizzes", "outcomes", "appointment-groups"],
)
def test_scoped_service_requires_enrollment(env, endpoint):
    client, _, _, _, headers = env
    assert client.get(f"/api/pacewise/v1/courses/2/{endpoint}?user_id=2", headers=headers).status_code == 403


def test_service_requires_key(env):
    client, *_ = env
    assert client.get("/api/pacewise/v1/courses/1/assignments?user_id=2").status_code == 401


def test_bundled_slide_download_checks_permissions_and_stays_in_demo_directory(env, monkeypatch, tmp_path):
    from app import integration_api

    client, factory, _, _, headers = env
    app_directory = tmp_path / "app"
    app_directory.mkdir()
    monkeypatch.setattr(integration_api, "__file__", str(app_directory / "integration_api.py"))
    slides_directory = tmp_path / "static" / "mock-files"
    slides_directory.mkdir(parents=True)
    slide = b"%PDF-1.4\nTest slides"
    (slides_directory / "chapter3.pdf").write_bytes(slide)
    with factory() as db:
        for identifier, url in [(101, "/static/mock-files/chapter3.pdf"),
                                (102, "/static/mock-files/../../secret.pdf"),
                                (103, "https://example.test/secret.pdf")]:
            db.add(Resource(id=identifier, course_id=1, title="Chapter 3 slides", kind="slides", source_url=url))
            db.add(ResourceAccess(resource_id=identifier, scope_type="course", scope_id=1, permission="read"))
        db.commit()
    path = "/api/pacewise/v1/courses/1/files"
    downloaded = client.get(f"{path}/101/download?user_id=2", headers=headers)
    assert downloaded.status_code == 200 and downloaded.content == slide
    assert client.get(f"{path}/102/download?user_id=2", headers=headers).status_code == 404
    assert client.get(f"{path}/103/download?user_id=2", headers=headers).status_code == 422
    with factory() as db:
        access = db.scalar(select(ResourceAccess).where(ResourceAccess.resource_id == 101))
        access.scope_type, access.scope_id = "student", 1
        db.commit()
    assert client.get(f"{path}/101/download?user_id=2", headers=headers).status_code == 403


def test_unpublished_course_is_hidden_from_student_but_editable_by_teacher(env):
    client, factory, teacher, student, headers = env
    with factory() as db:
        db.get(Course, 1).published = False
        db.commit()
    assert client.get("/api/pacewise/v1/courses?user_id=2", headers=headers).json() == []
    assert client.get("/api/pacewise/v1/courses/1/assignments?user_id=2", headers=headers).status_code == 403
    assert client.get("/api/courses/1?user_id=2", headers=student).status_code == 403
    assert client.get("/api/dashboard/2", headers=student).json()["courses"] == []
    assert client.get("/api/calendar/2", headers=student).json() == []
    assert client.get("/api/courses/1?user_id=1", headers=teacher).status_code == 200


@pytest.mark.parametrize("endpoint,expected", [("assignments", "Project"), ("modules", "Week 1")])
def test_student_sees_only_published_teacher_sees_drafts(env, endpoint, expected):
    client, _, _, _, headers = env
    student = client.get(f"/api/pacewise/v1/courses/1/{endpoint}?user_id=2", headers=headers).json()
    teacher = client.get(f"/api/pacewise/v1/courses/1/{endpoint}?user_id=1", headers=headers).json()
    assert len(student) == 1 and len(teacher) == 2
    assert student[0].get("title", student[0].get("name")) == expected


def test_hidden_pages_not_visible_in_ui_or_student_service(env):
    client, _, teacher, student, headers = env
    assert client.get("/api/courses/1/content/page", headers=student).json() == []
    assert client.get("/api/pacewise/v1/courses/1/content?user_id=2", headers=headers).json() == []
    assert len(client.get("/api/courses/1/content/page", headers=teacher).json()) == 1


def test_module_cannot_expose_hidden_target(env):
    client, factory, _, _, headers = env
    with factory() as db:
        db.add(ModuleItem(module_id=1, title="Private reference", item_type="page", content_id=1, position=3))
        db.commit()
    items = client.get("/api/pacewise/v1/courses/1/modules?user_id=2", headers=headers).json()[0]["items"]
    assert not any(item["title"] == "Private reference" for item in items)


def test_module_file_references_use_acl_not_nonexistent_publish_field(env):
    client, factory, teacher, student, headers = env
    with factory() as db:
        db.get(ModuleItem, 1).content_id = 1
        db.commit()
    rows = client.get("/api/pacewise/v1/courses/1/modules?user_id=2", headers=headers)
    assert rows.status_code == 200 and rows.json()[0]["items"][0]["content_id"] == 1
    changed = client.put("/api/resources/1/access", headers=teacher, json={"published": True, "target_user_id": 1})
    assert changed.status_code == 200, changed.text
    assert client.get("/api/courses/1/modules?user_id=2", headers=student).json()[0]["items"] == []


def test_planner_cannot_forge_deadline_or_submission(env):
    client, factory, _, student, headers = env
    requested = {
        "course_id": 1,
        "assignment_id": 1,
        "title": "Fake",
        "due_at": "2099-01-01T00:00:00Z",
        "completed": True,
    }
    created = client.post("/api/planner", headers=student, json=requested)
    assert created.status_code == 201, created.text
    assert created.json()["title"] == "Project" and not created.json()["completed"]
    with factory() as db:
        due = datetime(2026, 10, 8, 12, 17, tzinfo=UTC)
        db.add(AssignmentOverride(assignment_id=1, title="Extension", target_type="student", target_id=2, due_at=due))
        db.add(Submission(assignment_id=1, user_id=2, workflow_state="graded", submitted_at=datetime.now(UTC), score=8))
        db.commit()
    rows = client.get("/api/pacewise/v1/users/2/planner", headers=headers).json()
    assert rows[0]["due_at"].startswith("2026-10-08T12:17") and rows[0]["completed"]
    assignment = client.get("/api/pacewise/v1/courses/1/assignments?user_id=2", headers=headers).json()[0]
    assert assignment["due_at"] == rows[0]["due_at"]


@pytest.mark.parametrize("method", ["post", "put"])
def test_planner_rejects_cross_course_assignment(env, method):
    client, factory, _, student, _ = env
    with factory() as db:
        db.add(PlannerItem(id=1, user_id=2, title="Note", due_at=datetime.now(UTC)))
        db.commit()
    response = getattr(client, method)(
        "/api/planner" + ("/1" if method == "put" else ""),
        headers=student,
        json={"course_id": None, "assignment_id": 1, "title": "Fake", "due_at": "2026-10-10T12:00:00Z"},
    )
    assert response.status_code == 422


def test_override_fields_collapsed_independently_with_student_precedence(env):
    _, factory, *_ = env
    base = datetime(2026, 10, 8, 12, tzinfo=UTC)
    with factory() as db:
        db.add_all([CourseSection(id=1, course_id=1, name="A"), CourseSection(id=2, course_id=1, name="B")])
        db.flush()
        db.add_all([SectionMembership(section_id=1, user_id=2), SectionMembership(section_id=2, user_id=2)])
        db.add_all(
            [
                AssignmentOverride(
                    assignment_id=1,
                    title="A",
                    target_type="section",
                    target_id=1,
                    due_at=base,
                    unlock_at=base - timedelta(days=2),
                    lock_at=base + timedelta(days=1),
                ),
                AssignmentOverride(
                    assignment_id=1,
                    title="B",
                    target_type="section",
                    target_id=2,
                    due_at=base + timedelta(days=1),
                    unlock_at=base - timedelta(days=1),
                    lock_at=base + timedelta(days=3),
                ),
            ]
        )
        db.commit()

        def utc(value):
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

        due, unlock, lock, _ = effective_assignment_window(db, db.get(Assignment, 1), 2)
        assert utc(due) == base + timedelta(days=1)
        assert utc(unlock) == base - timedelta(days=2)
        assert utc(lock) == base + timedelta(days=3)
        db.add(
            AssignmentOverride(
                assignment_id=1,
                title="Individual",
                target_type="student",
                target_id=2,
                due_at=base - timedelta(hours=1),
            )
        )
        db.commit()
        due, unlock, _, _ = effective_assignment_window(db, db.get(Assignment, 1), 2)
        assert utc(due) == base - timedelta(hours=1) and utc(unlock) == base - timedelta(days=2)


def _quiz(client, teacher):
    response = client.post(
        "/api/courses/1/content/quiz",
        headers=teacher,
        json={
            "user_id": 1,
            "title": "Relations quiz",
            "body": "Chapter 3",
            "due_at": "2026-10-15T12:17:00Z",
            "points_possible": 5,
            "published": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_quiz_lifecycle_is_a_real_plan_task_and_submission(env):
    client, factory, teacher, student, headers = env
    quiz_id = _quiz(client, teacher)
    question = client.post(
        f"/api/quizzes/{quiz_id}/questions",
        headers=teacher,
        json={
            "user_id": 1,
            "prompt": "Is equality symmetric?",
            "options": ["yes", "no"],
            "correct_answer": "yes",
            "points": 2,
            "position": 1,
        },
    )
    assert question.status_code == 200, question.text
    assignment = next(
        item
        for item in client.get("/api/pacewise/v1/courses/1/assignments?user_id=2", headers=headers).json()
        if item["title"] == "Relations quiz"
    )
    assert assignment["submission_types"] == ["online_quiz"] and assignment["points_possible"] == 2
    assert (
        client.get("/api/pacewise/v1/courses/1/quizzes?user_id=2&include_answers=true", headers=headers).status_code
        == 403
    )
    attempt = client.post(
        f"/api/quizzes/{quiz_id}/attempts",
        headers=student,
        json={"user_id": 2, "answers": {str(question.json()["id"]): "yes"}},
    )
    assert attempt.status_code == 200 and attempt.json()["score"] == 2, attempt.text
    rows = client.get("/api/pacewise/v1/courses/1/submissions?user_id=2", headers=headers).json()
    assert rows[0]["assignment_id"] == assignment["id"] and rows[0]["workflow_state"] == "graded"
    assert rows[0]["score"] == 2
    assert client.delete(f"/api/courses/1/content/quiz/{quiz_id}?user_id=1", headers=teacher).status_code == 200
    assert assignment["id"] not in {
        item["id"] for item in client.get("/api/pacewise/v1/courses/1/assignments?user_id=2", headers=headers).json()
    }
    with factory() as db:
        assert db.get(Assignment, assignment["id"]) is not None  # evidence preserved


def test_quiz_sync_is_idempotent_and_undated_does_not_invent_deadline(env):
    client, factory, teacher, _, _ = env
    quiz_id = _quiz(client, teacher)
    with factory() as db:
        quiz = db.get(CourseContent, quiz_id)
        assignment_id = db.get(QuizAssignmentLink, quiz_id).assignment_id
        before = len(db.scalars(select(IntegrationEvent)).all())
        sync_quiz_assignment(db, quiz)
        db.commit()
        assert len(db.scalars(select(IntegrationEvent)).all()) == before
        assert db.get(QuizAssignmentLink, quiz_id).assignment_id == assignment_id
        quiz.due_at = None
        assert sync_quiz_assignment(db, quiz) is None
        assert not db.get(Assignment, assignment_id).published


@pytest.mark.parametrize("action", ["questions", "attempts"])
def test_unpublished_quiz_is_not_accessible_to_student(env, action):
    client, factory, teacher, student, _ = env
    quiz_id = _quiz(client, teacher)
    with factory() as db:
        db.get(CourseContent, quiz_id).published = False
        db.commit()
    response = (
        client.get(f"/api/quizzes/{quiz_id}/questions?user_id=2", headers=student)
        if action == "questions"
        else client.post(f"/api/quizzes/{quiz_id}/attempts", headers=student, json={"user_id": 2, "answers": {}})
    )
    assert response.status_code == 403


def test_grades_service_works_and_student_gradebook_is_private(env):
    client, factory, _, student, headers = env
    with factory() as db:
        db.add(Submission(assignment_id=1, user_id=2, workflow_state="graded", score=8))
        db.commit()
    result = client.get("/api/pacewise/v1/courses/1/grades?user_id=2", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["current"][0]["score"] == 8
    gradebook = client.get("/api/courses/1?user_id=2", headers=student).json()["gradebook"]
    assert {row["user_id"] for row in gradebook} == {2}


def test_teacher_cannot_grade_non_enrolled_student(env):
    client, _, teacher, _, _ = env
    assert (
        client.put(
            "/api/assignments/1/submissions/999/grade",
            headers=teacher,
            json={"user_id": 1, "score": 5, "comment": "", "rubric": {}},
        ).status_code
        == 403
    )


def test_modules_reject_cycles_and_cannot_start_before_prerequisite(env):
    client, factory, teacher, student, _ = env
    with factory() as db:
        db.get(CourseModule, 2).published = True
        db.add(
            ModuleItem(
                id=3,
                module_id=2,
                title="Next",
                item_type="external_url",
                external_url="https://example.test",
                position=1,
            )
        )
        db.add(ModulePrerequisite(module_id=2, prerequisite_module_id=1))
        db.add(ModuleRequirement(module_item_id=1, requirement_type="must_view"))
        db.commit()
    response = client.put(
        "/api/modules/1/rules", headers=teacher, json={"prerequisite_module_ids": [2], "requirements": []}
    )
    assert response.status_code == 422
    assert client.put("/api/module-items/3/progress", headers=student, json={"status": "started"}).status_code == 409


def test_graded_submission_satisfies_module_score_requirement(env):
    client, factory, _, student, _ = env
    with factory() as db:
        item = db.get(ModuleItem, 1)
        item.item_type, item.content_id = "assignment", 1
        db.add(ModuleRequirement(module_item_id=1, requirement_type="must_score", min_score=5))
        db.add(Submission(assignment_id=1, user_id=2, workflow_state="graded", score=8))
        db.commit()
    result = client.put("/api/module-items/1/progress", headers=student, json={"status": "completed"})
    assert result.status_code == 200, result.text


@pytest.mark.parametrize("method", ["put", "delete"])
def test_student_cannot_move_or_delete_lms_teaching_event(env, method):
    client, factory, _, student, _ = env
    with factory() as db:
        db.add(
            CalendarEvent(
                id=1,
                user_id=2,
                course_id=1,
                title="Class",
                description="course-activity-v1;type=class_session",
                starts_at=datetime.now(UTC),
            )
        )
        db.commit()
    if method == "delete":
        response = client.delete("/api/calendar/1?user_id=2", headers=student)
    else:
        response = client.put(
            "/api/calendar/1",
            headers=student,
            json={
                "user_id": 2,
                "course_id": 1,
                "title": "Moved",
                "starts_at": "2026-10-15T09:00:00Z",
                "ends_at": "2026-10-15T10:00:00Z",
            },
        )
    assert response.status_code == 403 and "instructor" in response.json()["detail"]


def test_calendar_validates_interval_and_emits_changes(env):
    client, _, _, student, headers = env
    payload = {
        "user_id": 2,
        "title": "Self study",
        "starts_at": "2026-10-15T09:17:00Z",
        "ends_at": "2026-10-15T10:03:00Z",
    }
    assert (
        client.post("/api/calendar", headers=student, json={**payload, "ends_at": payload["starts_at"]}).status_code
        == 422
    )
    created = client.post("/api/calendar", headers=student, json=payload)
    assert created.status_code == 200, created.text
    row = client.get("/api/pacewise/v1/users/2/calendar", headers=headers).json()[0]
    assert row["duration_minutes"] == 46 and row["editable"]
    events = client.get("/api/pacewise/v1/events", headers=headers).json()
    assert any(event["type"] == "calendar.created" for event in events)


def test_personal_calendar_can_be_moved_even_when_event_id_differs_from_user(env):
    client, factory, _, student, _ = env
    with factory() as db:
        db.add(CalendarEvent(id=40, user_id=2, title="Study", starts_at=datetime.now(UTC)))
        db.commit()
    payload = {"user_id": 2, "title": "Moved", "starts_at": "2026-10-16T09:17:00Z", "ends_at": "2026-10-16T10:03:00Z"}
    assert client.put("/api/calendar/40", headers=student, json=payload).status_code == 200
    assert client.get("/api/calendar/40", headers=student).status_code == 403  # GET is a user ID
    assert client.delete("/api/calendar/40?user_id=2", headers=student).status_code == 200


@pytest.mark.parametrize("endpoint", ["submit", "submissions"])
def test_unpublished_assignment_cannot_be_submitted(env, endpoint):
    client, _, _, student, _ = env
    assert (
        client.post(
            f"/api/assignments/2/{endpoint}", headers=student, json={"user_id": 2, "text_entry": "Answer"}
        ).status_code
        == 403
    )


def test_teacher_class_update_delete_fans_out_only_selected_occurrence(env):
    client, _, teacher, _, headers = env
    payload = {
        "user_id": 1,
        "activity_type": "class_session",
        "title": "Relations class",
        "starts_at": "2099-10-05T09:00:00Z",
        "ends_at": "2099-10-05T10:30:00Z",
        "repeat_count": 2,
    }
    assert client.post("/api/courses/1/activities", headers=teacher, json=payload).status_code == 200
    teacher_rows = client.get("/api/calendar/1", headers=teacher).json()
    selected = next(row for row in teacher_rows if row["type"] == "event")
    assert selected["editable"]
    moved = client.put(
        f"/api/calendar/{selected['source_id']}",
        headers=teacher,
        json={
            "user_id": 1,
            "course_id": 1,
            "title": "Moved class",
            "starts_at": "2099-10-06T09:17:00Z",
            "ends_at": "2099-10-06T10:03:00Z",
        },
    )
    assert moved.status_code == 200 and moved.json()["affected_calendar_events"] == 2, moved.text
    student_rows = client.get("/api/pacewise/v1/users/2/calendar", headers=headers).json()
    assert len(student_rows) == 2
    assert student_rows[0]["starts_at"].startswith("2099-10-06T09:17") and student_rows[0]["duration_minutes"] == 46
    assert student_rows[1]["starts_at"].startswith("2099-10-12T09:00")
    assert not student_rows[0]["editable"]
    deleted = client.delete(f"/api/calendar/{selected['source_id']}?user_id=1", headers=teacher)
    assert deleted.status_code == 200 and deleted.json()["affected_calendar_events"] == 2
    assert len(client.get("/api/pacewise/v1/users/2/calendar", headers=headers).json()) == 1


def test_identical_new_class_occurrences_do_not_get_merged_by_title_and_time(env):
    client, factory, teacher, _, headers = env
    payload = {
        "user_id": 1,
        "activity_type": "class_session",
        "title": "Same name",
        "starts_at": "2099-10-05T09:00:00Z",
        "ends_at": "2099-10-05T10:00:00Z",
    }
    for _ in range(2):
        assert client.post("/api/courses/1/activities", headers=teacher, json=payload).status_code == 200
    with factory() as db:
        event_id = db.scalar(select(CalendarEvent.id).where(CalendarEvent.user_id == 1).order_by(CalendarEvent.id))
    deleted = client.delete(f"/api/calendar/{event_id}?user_id=1", headers=teacher)
    assert deleted.status_code == 200 and deleted.json()["affected_calendar_events"] == 2
    assert len(client.get("/api/pacewise/v1/users/2/calendar", headers=headers).json()) == 1


def test_ambiguous_legacy_class_occurrence_is_not_modified(env):
    client, factory, teacher, _, _ = env
    with factory() as db:
        for event_id in [20, 21]:
            db.add(
                CalendarEvent(
                    id=event_id,
                    user_id=1,
                    course_id=1,
                    title="Legacy duplicate",
                    description="pacewise-2026-v1;",
                    event_kind="class_session",
                    starts_at=datetime(2099, 10, 5, 9, tzinfo=UTC),
                )
            )
        db.commit()
    assert client.delete("/api/calendar/20?user_id=1", headers=teacher).status_code == 409
    with factory() as db:
        assert db.get(CalendarEvent, 20) is not None and db.get(CalendarEvent, 21) is not None


def test_quiz_rejects_unknown_answer_and_locked_window(env):
    client, factory, teacher, student, _ = env
    quiz_id = _quiz(client, teacher)
    question = client.post(
        f"/api/quizzes/{quiz_id}/questions",
        headers=teacher,
        json={"user_id": 1, "prompt": "Reflexive?", "options": ["yes", "no"], "correct_answer": "yes", "points": 1},
    )
    assert question.status_code == 200
    assert (
        client.post(
            f"/api/quizzes/{quiz_id}/attempts", headers=student, json={"user_id": 2, "answers": {"9999": "yes"}}
        ).status_code
        == 422
    )
    from app.models import AssignmentConfiguration

    with factory() as db:
        assignment_id = db.get(QuizAssignmentLink, quiz_id).assignment_id
        db.add(AssignmentConfiguration(assignment_id=assignment_id, unlock_at=datetime.now(UTC) + timedelta(days=30)))
        db.commit()
    assert (
        client.post(
            f"/api/quizzes/{quiz_id}/attempts",
            headers=student,
            json={"user_id": 2, "answers": {str(question.json()["id"]): "yes"}},
        ).status_code
        == 409
    )


def test_quiz_update_changes_plan_title_and_exact_due(env):
    client, _, teacher, _, headers = env
    quiz_id = _quiz(client, teacher)
    response = client.put(
        f"/api/courses/1/content/quiz/{quiz_id}",
        headers=teacher,
        json={
            "user_id": 1,
            "title": "Relations chapter 3",
            "body": "New description",
            "due_at": "2026-10-16T05:17:00Z",
            "published": True,
            "points_possible": 3,
        },
    )
    assert response.status_code == 200
    row = next(
        item
        for item in client.get("/api/pacewise/v1/courses/1/assignments?user_id=2", headers=headers).json()
        if item["title"] == "Relations chapter 3"
    )
    assert row["due_at"].startswith("2026-10-16T05:17") and row["description"] == "New description"


def test_submission_workflow_and_rubric_reach_service(env):
    client, factory, teacher, student, headers = env
    submitted = client.post(
        "/api/assignments/1/submissions", headers=student, json={"user_id": 2, "text_entry": "Answer"}
    )
    assert submitted.status_code == 200
    submission_id = submitted.json()["id"]
    rubric = client.post(
        "/api/courses/1/rubrics",
        headers=teacher,
        json={
            "title": "Reasoning",
            "criteria": [
                {"description": "Explains why", "points": 10, "ratings": [{"description": "Correct", "points": 10}]}
            ],
        },
    )
    assert rubric.status_code == 201, rubric.text
    rubric_id, criterion_id = rubric.json()["id"], rubric.json()["criteria"][0]["id"]
    assert client.put(f"/api/assignments/1/rubric/{rubric_id}", headers=teacher, json={}).status_code == 200
    assessed = client.put(
        f"/api/submissions/{submission_id}/rubric-assessment",
        headers=teacher,
        json={"ratings": {str(criterion_id): 8}, "comments": {str(criterion_id): "Clear reasoning"}},
    )
    assert assessed.status_code == 200, assessed.text
    for state, flags in [("excused", {"excused": True}), ("reassigned", {"reassigned": True})]:
        changed = client.put(f"/api/submissions/{submission_id}/workflow", headers=teacher, json=flags)
        assert changed.status_code == 200
        for summary in [False, True]:
            row = client.get(
                f"/api/pacewise/v1/courses/1/submissions?user_id=2&summary={str(summary).lower()}", headers=headers
            ).json()[0]
            assert row["workflow_state"] == state and row["source_workflow_state"] == "submitted"
            assert row["rubric"][str(criterion_id)]["points"] == 8


def test_launch_is_single_use_and_revoked_enrollment_blocks_it(env, monkeypatch):
    client, factory, _, student, headers = env
    monkeypatch.setenv("PACEWISE_LAUNCH_SECRET", "launch-test-secret-at-least-32-characters")

    def token():
        response = client.post("/api/pacewise/launch/1", headers=student)
        assert response.status_code == 200
        return parse_qs(urlparse(response.json()["launch_url"]).fragment.partition("?")[2])["token"][0]

    first = token()
    assert client.post("/api/pacewise/v1/launch/verify", headers=headers, json={"token": first}).status_code == 200
    assert client.post("/api/pacewise/v1/launch/verify", headers=headers, json={"token": first}).status_code == 401
    second = token()
    with factory() as db:
        db.delete(db.scalar(select(Enrollment).where(Enrollment.user_id == 2, Enrollment.course_id == 1)))
        db.commit()
    assert client.post("/api/pacewise/v1/launch/verify", headers=headers, json={"token": second}).status_code == 403


def test_appointment_slots_duplicate_validation_and_private_reservations(env):
    client, factory, teacher, student, headers = env
    created = client.post(
        "/api/courses/1/appointment-groups",
        headers=teacher,
        json={
            "title": "Office hours",
            "starts_at": "2026-10-15T09:00:00Z",
            "ends_at": "2026-10-15T10:00:00Z",
            "slot_minutes": 15,
            "participants_per_slot": 2,
        },
    )
    assert created.status_code == 201
    group_id = created.json()["id"]
    assert (
        client.post(
            f"/api/appointment-groups/{group_id}/reservations",
            headers=student,
            json={"starts_at": "2026-10-15T09:07:00Z"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/appointment-groups/{group_id}/reservations",
            headers=student,
            json={"starts_at": "2026-10-15T09:00:00Z"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/appointment-groups/{group_id}/reservations",
            headers=student,
            json={"starts_at": "2026-10-15T09:15:00Z"},
        ).status_code
        == 409
    )
    from app.models import AppointmentReservation

    with factory() as db:
        password_hash = db.get(User, 2).password_hash
        db.add(
            User(
                id=3,
                email="another@example.test",
                full_name="Another",
                role="student",
                password_hash=password_hash,
                avatar_color="#111111",
            )
        )
        db.flush()
        db.add(Enrollment(user_id=3, course_id=1, role="student"))
        db.add(
            AppointmentReservation(
                appointment_group_id=group_id,
                user_id=3,
                starts_at=datetime(2026, 10, 15, 9, tzinfo=UTC),
                ends_at=datetime(2026, 10, 15, 9, 15, tzinfo=UTC),
            )
        )
        db.commit()
    rows = client.get("/api/pacewise/v1/courses/1/appointment-groups?user_id=2", headers=headers).json()
    assert {row["user_id"] for row in rows[0]["reservations"]} == {2}
    assert (
        len(
            client.get("/api/pacewise/v1/courses/1/appointment-groups?user_id=1", headers=headers).json()[0][
                "reservations"
            ]
        )
        == 2
    )
    commitments = client.get("/api/pacewise/v1/users/2/calendar", headers=headers).json()
    assert len(commitments) == 1 and commitments[0]["event_kind"] == "appointment"
    assert commitments[0]["duration_minutes"] == 15 and not commitments[0]["editable"]


def test_module_crud_emits_projection_events(env):
    client, _, teacher, _, headers = env
    created = client.post(
        "/api/courses/1/modules", headers=teacher, json={"user_id": 1, "name": "Relations", "position": 3}
    )
    assert created.status_code == 200
    module_id = created.json()["id"]
    added = client.post(
        f"/api/courses/1/modules/{module_id}/items",
        headers=teacher,
        json={"user_id": 1, "title": "Practice", "item_type": "assignment", "content_id": 1},
    )
    assert added.status_code == 200
    item_id = added.json()["items"][0]["id"]
    assert (
        client.delete(f"/api/courses/1/modules/{module_id}/items/{item_id}?user_id=1", headers=teacher).status_code
        == 200
    )
    assert client.delete(f"/api/courses/1/modules/{module_id}?user_id=1", headers=teacher).status_code == 200
    events = {event["type"] for event in client.get("/api/pacewise/v1/events", headers=headers).json()}
    assert {"module.created", "module_item.created", "module_item.deleted", "module.deleted"} <= events


def test_module_rejects_unlinked_or_wrong_course_content(env):
    client, _, teacher, _, _ = env
    for kind, content_id in [("assignment", None), ("resource", 9999), ("quiz", 1)]:
        response = client.post(
            "/api/courses/1/modules/1/items",
            headers=teacher,
            json={"user_id": 1, "title": "Invalid", "item_type": kind, "content_id": content_id},
        )
        assert response.status_code == 422


def test_submission_timestamp_simulation_requires_explicit_demo_mode(env, monkeypatch):
    client, _, _, student, _ = env
    monkeypatch.setenv("ALLOW_DEMO_SUBMISSION_TIMING", "false")
    response = client.post(
        "/api/assignments/1/submissions",
        headers=student,
        json={"user_id": 2, "text_entry": "Answer", "demo_submission_offset_minutes": -60},
    )
    assert response.status_code == 422 and "demo mode" in response.json()["detail"]
    assert not client.get("/api/session/me", headers=student).json()["user"]["demo_submission_timing_enabled"]


def test_quiz_module_score_requirement_resolves_canonical_assignment_id(env):
    client, _, teacher, student, _ = env
    quiz_id = _quiz(client, teacher)
    question = client.post(
        f"/api/quizzes/{quiz_id}/questions",
        headers=teacher,
        json={"user_id": 1, "prompt": "Symmetric?", "options": ["yes", "no"], "correct_answer": "yes", "points": 2},
    )
    assert question.status_code == 200
    added = client.post(
        "/api/courses/1/modules/1/items",
        headers=teacher,
        json={"user_id": 1, "title": "Quiz", "item_type": "quiz", "content_id": quiz_id},
    ).json()["items"]
    item = next(row for row in added if row["item_type"] == "quiz")
    rules = client.put(
        "/api/modules/1/rules",
        headers=teacher,
        json={"requirements": [{"module_item_id": item["id"], "requirement_type": "must_score", "min_score": 1}]},
    )
    assert rules.status_code == 200
    assert (
        client.put(
            f"/api/module-items/{item['id']}/progress", headers=student, json={"status": "completed"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/quizzes/{quiz_id}/attempts",
            headers=student,
            json={"user_id": 2, "answers": {str(question.json()["id"]): "yes"}},
        ).status_code
        == 200
    )
    response = client.put(f"/api/module-items/{item['id']}/progress", headers=student, json={"status": "completed"})
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("source", ["quiz", "assignment", "override"])
def test_offset_deadlines_are_normalized_before_sqlite_persistence(env, source):
    client, _, teacher, _, headers = env
    due = "2026-10-15T12:17:00+07:00"
    if source == "quiz":
        response = client.post(
            "/api/courses/1/content/quiz", headers=teacher, json={"user_id": 1, "title": "Offset quiz", "due_at": due}
        )
    elif source == "assignment":
        response = client.post(
            "/api/courses/1/assignments", headers=teacher, json={"user_id": 1, "title": "Offset task", "due_at": due}
        )
    else:
        response = client.post(
            "/api/assignments/1/overrides",
            headers=teacher,
            json={"title": "Offset extension", "target_type": "student", "target_id": 2, "due_at": due},
        )
    assert response.status_code in {200, 201}, response.text
    rows = client.get("/api/pacewise/v1/courses/1/assignments?user_id=2", headers=headers).json()
    assert any(row["due_at"].startswith("2026-10-15T05:17") for row in rows)
