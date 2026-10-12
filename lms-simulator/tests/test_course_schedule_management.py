import copy
from datetime import UTC, datetime, timedelta

import pytest
from app import security
from app.main import app
from app.models import Assignment, CalendarEvent, Course, CourseContent, Enrollment, ModuleItem, Submission
from sqlalchemy import select
from test_learning_api import _client

BASE = "/api/pacewise/v1/teacher"
HEADERS = {"X-PaceWise-Key": "authoring-test"}


@pytest.fixture
def authoring(monkeypatch):
    old_factory, old_overrides = security.SessionLocal, app.dependency_overrides.copy()
    monkeypatch.setenv("PACEWISE_API_KEY", "authoring-test")
    client, factory = _client()
    try:
        yield client, factory
    finally:
        client.close()
        security.SessionLocal = old_factory
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)


def call(client, method, path, data=None, user=1):
    return client.request(method, BASE + path, params={"user_id": user}, headers=HEADERS, json=data)


def new_course(client, code="NEW101", students=None):
    result = call(client, "POST", "/courses", {"code": code, "name": "New course", "student_ids": students or []})
    assert result.status_code == 201, result.text
    return result.json()


def lesson(days=2, hour=8):
    start = (datetime.now(UTC) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return {
        "title": "Upcoming lesson",
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=1)).isoformat(),
    }


def row(data=None, course=1, sheet="Lessons"):
    return {"course_id": course, "sheet": sheet, "row": 2, "data": data or lesson()}


def preview(client, rows=None, mode="append", ids=None):
    response = call(client, "POST", "/schedule/preview", {"rows": rows or [], "mode": mode, "course_ids": ids or [1]})
    assert response.status_code == 200, response.text
    return response.json()


def apply(client, body):
    return call(client, "POST", "/schedule/confirm", {"ticket": body["ticket"]})


def test_course_create_edit_roster_enrollment_and_uniqueness(authoring):
    client, _ = authoring
    assert call(client, "GET", "/roster").json() == [{"id": 2, "name": "Student"}]
    course = new_course(client, students=[2])
    assert call(client, "GET", f"/courses/{course['id']}").status_code == 200
    payload = {"code": "EDIT101", "name": "Edited", "expected_version": course["version"]}
    result = call(client, "PUT", f"/courses/{course['id']}/info", payload)
    assert result.status_code == 200
    assert call(client, "PUT", f"/courses/{course['id']}/info", payload).status_code == 409
    assert call(client, "POST", "/courses", {"code": "edit101", "name": "Duplicate"}).status_code == 409
    assert call(client, "POST", "/courses", {"code": "BAD", "name": "Bad", "student_ids": [999]}).status_code == 403


@pytest.mark.parametrize(
    "path,method,payload",
    [
        ("/courses", "GET", None),
        ("/courses", "POST", {"code": "BAD", "name": "Bad"}),
        ("/roster", "GET", None),
        ("/schedule/preview", "POST", {"course_ids": [1]}),
    ],
)
def test_student_cannot_manage(authoring, path, method, payload):
    assert call(authoring[0], method, path, payload, user=2).status_code == 403


def test_archive_preserves_history_excludes_sync_and_can_restore(authoring):
    client, factory = authoring
    new_course(client)
    original = call(client, "GET", "/courses").json()[0]
    result = call(client, "POST", "/courses/1/archive", {"expected_version": original["version"]})
    assert result.status_code == 200, result.text
    assert call(client, "GET", "/courses/1").status_code == 403
    sync = client.get("/api/pacewise/v1/courses", params={"user_id": 2}, headers=HEADERS)
    assert not sync.json()
    assert call(client, "POST", "/courses/1/restore", {"expected_version": result.json()["version"]}).status_code == 200
    assert call(client, "GET", "/courses/1").json()["tasks"]
    with factory() as db:
        assert db.get(Course, 1)


def test_empty_delete_but_not_populated_or_enrolled_course(authoring):
    client, factory = authoring
    empty = new_course(client)
    assert (
        call(client, "POST", f"/courses/{empty['id']}/delete-empty", {"expected_version": empty["version"]}).status_code
        == 200
    )
    new_course(client, "ENROLLED", [2])
    original = next(item for item in call(client, "GET", "/courses").json() if item["id"] == 1)
    assert call(client, "POST", "/courses/1/delete-empty", {"expected_version": original["version"]}).status_code == 409
    with factory() as db:
        assert db.get(Course, 1) and not db.scalar(select(Course).where(Course.code == "NEW101"))


def test_preview_does_not_write_and_confirm_is_idempotent(authoring):
    client, factory = authoring
    data = row()
    data["data"]["repeat_count"] = 3
    draft = preview(client, [data])
    assert draft["counts"]["lessons"] == 3 and not draft["errors"]
    with factory() as db:
        assert not db.scalars(select(CalendarEvent)).all()
    assert apply(client, draft).status_code == 200
    assert apply(client, draft).status_code == 200
    assert preview(client, [data])["applied"]
    with factory() as db:
        events = db.scalars(select(CalendarEvent)).all()
        assert len(events) == 6  # Teacher and student, not one private calendar only.


def test_conflicts_historical_import_foreign_courses_and_duplicate_rows(authoring):
    client, _ = authoring
    one = row()
    assert preview(client, [one, copy.deepcopy(one)])["errors"]
    historical = preview(client, [row(lesson(-1))])
    assert not historical["errors"]
    assert historical["counts"]["historical_lessons"] == 1
    foreign = call(client, "POST", "/schedule/preview", {"course_ids": [999], "rows": [row(course=999)]})
    assert foreign.status_code == 403
    draft = preview(client, [one])
    assert apply(client, draft).status_code == 200
    different = copy.deepcopy(one)
    different["data"]["title"] = "Collision"
    assert preview(client, [different])["errors"]


def test_stale_snapshot_blocks_all_changes(authoring):
    client, factory = authoring
    draft = preview(client, [row()])
    assert call(client, "POST", "/courses/1/lessons", lesson(3)).status_code == 201
    assert apply(client, draft).status_code == 409
    with factory() as db:
        assert len(db.scalars(select(CalendarEvent)).all()) == 2


def test_cleanup_scoped_future_restore_preserves_tasks_and_past(authoring):
    client, factory = authoring
    one = apply(client, preview(client, [row()])).json()
    other = new_course(client)
    assert call(client, "POST", f"/courses/{other['id']}/lessons", lesson(3)).status_code == 201
    with factory() as db:
        old = lesson(-3)
        db.add(
            CalendarEvent(
                user_id=1,
                course_id=1,
                title="Past",
                starts_at=datetime.fromisoformat(old["starts_at"]),
                ends_at=datetime.fromisoformat(old["ends_at"]),
                event_kind="class",
                attendance_status="scheduled",
            )
        )
        db.commit()
    cleanup = preview(client, mode="cleanup")
    assert cleanup["counts"]["cancelled_lessons"] == 1
    assert apply(client, cleanup).status_code == 200
    with factory() as db:
        assert db.scalar(select(CalendarEvent).where(CalendarEvent.title == "Past")).attendance_status == "scheduled"
        assert (
            db.scalar(select(CalendarEvent).where(CalendarEvent.course_id == other["id"])).attendance_status
            == "scheduled"
        )
    assert call(client, "GET", "/courses/1").json()["tasks"]
    assert call(client, "POST", "/schedule/restore", {"ticket": cleanup["ticket"]}).status_code == 200
    assert call(client, "POST", "/schedule/restore", {"ticket": cleanup["ticket"]}).status_code == 200
    assert all(not item["cancelled"] for item in call(client, "GET", "/courses/1").json()["lessons"])
    assert one["applied"]


def test_replace_does_not_touch_task_only_courses_or_other_courses(authoring):
    client, _ = authoring
    assert apply(client, preview(client, [row()])).status_code == 200
    task = {"title": "New task", "points_possible": 10, "due_at": lesson(4)["starts_at"]}
    draft = preview(client, [row(task, sheet="Tasks")], mode="replace_future")
    assert draft["counts"]["cancelled_lessons"] == 0
    assert apply(client, draft).status_code == 200
    replacement = preview(client, [row(lesson(5))], mode="replace_future")
    assert replacement["counts"]["cancelled_lessons"] == 1
    assert apply(client, replacement).status_code == 200
    assert call(client, "POST", "/schedule/restore", {"ticket": replacement["ticket"]}).status_code == 200


def test_demo_preview_contains_grounded_current_chapter_no_automatic_seed(authoring):
    client, factory = authoring
    draft = call(client, "POST", "/schedule/demo-preview", {"course_ids": [1]}).json()
    assert not draft["errors"] and draft["counts"]["materials"] == 1
    with factory() as db:
        assert not db.scalars(select(CourseContent)).all()
    assert apply(client, draft).status_code == 200
    content = call(client, "GET", "/courses/1").json()
    assert (
        content["materials"][0]["chapter"]
        == next(item for item in content["tasks"] if item["title"].startswith("Demo"))["chapter"]
    )
    with factory() as db:
        assert db.scalar(select(ModuleItem).where(ModuleItem.item_type == "page"))


def test_quiz_cannot_publish_empty_and_invalid_weights_cannot_commit(authoring):
    client, _ = authoring
    task = {"title": "Quiz", "kind": "quiz", "published": True, "points_possible": 10, "due_at": lesson(4)["starts_at"]}
    draft = preview(client, [row(task, sheet="Tasks")])
    assert draft["errors"] and apply(client, draft).status_code == 409
    weights = {"groups": [{"name": "Assignments", "weight": 20}]}
    assert preview(client, [row(weights, sheet="Weights")])["errors"]


def test_cleanup_series_cancels_only_explicit_series_and_all_enrollment_copies(authoring):
    client, factory = authoring
    recurring = lesson()
    recurring["repeat_count"] = 3
    assert call(client, "POST", "/courses/1/lessons", recurring).status_code == 201
    assert call(client, "POST", "/courses/1/lessons", lesson(3)).status_code == 201
    lessons = call(client, "GET", "/courses/1").json()["lessons"]
    linked = next(item for item in lessons if item["series_key"])
    draft_response = call(
        client,
        "POST",
        "/schedule/preview",
        {
            "mode": "cleanup",
            "course_ids": [1],
            "rows": [],
            "series_lesson_id": linked["id"],
        },
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["counts"]["cancelled_lessons"] == 3
    assert apply(client, draft).status_code == 200
    with factory() as db:
        events = db.scalars(select(CalendarEvent)).all()
        assert sum(event.attendance_status == "cancelled" for event in events) == 6
        assert sum(event.attendance_status == "scheduled" for event in events) == 2
    assert call(client, "POST", "/schedule/restore", {"ticket": draft["ticket"]}).status_code == 200


def test_import_failure_rolls_back_cancellations_and_new_lessons(authoring, monkeypatch):
    from app import schedule_import
    from fastapi import HTTPException

    client, factory = authoring
    assert apply(client, preview(client, [row()])).status_code == 200
    task = {"title": "Task", "points_possible": 10, "due_at": lesson(6)["starts_at"]}
    draft = preview(client, [row(lesson(5)), row(task, sheet="Tasks")], mode="replace_future")
    assert not draft["errors"] and draft["counts"]["cancelled_lessons"] == 1

    def fail_task(*args, **kwargs):
        raise HTTPException(503, "Simulated source failure")

    monkeypatch.setattr(schedule_import, "save_task", fail_task)
    assert apply(client, draft).status_code == 503
    with factory() as db:
        events = db.scalars(select(CalendarEvent)).all()
        assert len(events) == 2
        assert all(event.attendance_status == "scheduled" for event in events)
    assert not preview(client, [row(lesson(5)), row(task, sheet="Tasks")], mode="replace_future")["applied"]


def test_edit_series_preserves_past_other_series_and_updates_all_remaining_copies(authoring):
    client, factory = authoring
    repeating = lesson()
    repeating["repeat_count"] = 3
    assert call(client, "POST", "/courses/1/lessons", repeating).status_code == 201
    assert call(client, "POST", "/courses/1/lessons", lesson(3)).status_code == 201
    with factory() as db:
        events = db.scalars(select(CalendarEvent).order_by(CalendarEvent.starts_at)).all()
        first_start = events[0].starts_at
        for event in events:
            if event.starts_at == first_start:
                event.starts_at -= timedelta(days=8)
                event.ends_at -= timedelta(days=8)
        db.commit()
    snapshot = call(client, "GET", "/courses/1").json()["lessons"]
    origin = min(
        (
            item
            for item in snapshot
            if item["series_key"] and datetime.fromisoformat(item["starts_at"]) > datetime.now(UTC)
        ),
        key=lambda item: item["starts_at"],
    )
    data = lesson(9, hour=10)
    data.update(
        course_ids=[1], series_lesson_id=origin["id"], expected_version=origin["version"], title="Rescheduled series"
    )
    draft = call(client, "POST", "/schedule/series-preview", data).json()
    assert not draft["errors"] and draft["counts"]["lessons"] == draft["counts"]["cancelled_lessons"] == 2
    with factory() as db:
        assert len(db.scalars(select(CalendarEvent)).all()) == 8  # Preview is not a write.
    assert apply(client, draft).status_code == 200
    assert apply(client, draft).status_code == 200
    with factory() as db:
        events = db.scalars(select(CalendarEvent)).all()
        assert len(events) == 12
        assert sum(event.attendance_status == "cancelled" for event in events) == 4
        assert sum(event.title == "Rescheduled series" for event in events) == 4
        assert (
            sum(
                event.attendance_status == "scheduled" and event.starts_at.replace(tzinfo=UTC) < datetime.now(UTC)
                for event in events
            )
            == 2
        )
    result = call(client, "GET", "/courses/1").json()["lessons"]
    assert all(item["series_key"] == origin["series_key"] for item in result if item["title"] == "Rescheduled series")


def test_edit_series_rejects_unknown_link_and_stale_lesson_version(authoring):
    client, _ = authoring
    assert call(client, "POST", "/courses/1/lessons", lesson()).status_code == 201
    origin = call(client, "GET", "/courses/1").json()["lessons"][0]
    data = {**lesson(3), "course_ids": [1], "series_lesson_id": origin["id"], "expected_version": origin["version"]}
    assert call(client, "POST", "/schedule/series-preview", data).status_code == 409
    data["expected_version"] = "stale"
    assert call(client, "POST", "/schedule/series-preview", data).status_code == 409


def test_import_checks_overlap_with_currently_running_lesson(authoring):
    client, factory = authoring
    now = datetime.now(UTC)
    with factory() as db:
        db.add(
            CalendarEvent(
                user_id=1,
                course_id=1,
                title="Ongoing",
                starts_at=now - timedelta(minutes=10),
                ends_at=now + timedelta(hours=2),
                event_kind="class",
                attendance_status=None,
            )
        )
        db.commit()
    data = {
        "title": "Overlapping",
        "starts_at": (now + timedelta(minutes=15)).isoformat(),
        "ends_at": (now + timedelta(minutes=45)).isoformat(),
    }
    assert preview(client, [row(data)])["errors"]


def test_startup_seed_keeps_only_explicit_members_in_new_course(authoring):
    from app.seed import seed_demo_data

    client, factory = authoring
    course = new_course(client, students=[2])
    with factory() as db:
        seed_demo_data(db)
        members = db.scalars(select(Enrollment).where(Enrollment.course_id == course["id"])).all()
        assert {(item.user_id, item.role) for item in members} == {(1, "instructor"), (2, "student")}
        assert not db.scalars(select(Assignment).where(Assignment.course_id == course["id"])).all()
        assert not db.scalars(select(CourseContent).where(CourseContent.course_id == course["id"])).all()
        assert not db.scalars(select(CalendarEvent).where(CalendarEvent.course_id == course["id"])).all()


def test_startup_seed_does_not_enroll_fake_students_or_submit_teacher_tasks(authoring):
    from app.seed import seed_demo_data

    client, factory = authoring
    empty = new_course(client)
    teacher_task = {
        "title": "Teacher-created task",
        "points_possible": 10,
        "due_at": lesson(4)["starts_at"],
        "published": True,
    }
    assert call(client, "POST", "/courses/1/tasks", teacher_task).status_code == 201
    with factory() as db:
        before_enrollments = [(row.user_id, row.course_id) for row in db.scalars(select(Enrollment)).all()]
        before_tasks = [row.id for row in db.scalars(select(Assignment)).all()]
        seed_demo_data(db)
        assert [(row.user_id, row.course_id) for row in db.scalars(select(Enrollment)).all()] == before_enrollments
        assert [row.id for row in db.scalars(select(Assignment)).all()] == before_tasks
        assert not db.scalars(select(Submission)).all()
        assert not db.scalars(select(CourseContent).where(CourseContent.course_id == empty["id"])).all()
    current = next(item for item in call(client, "GET", "/courses").json() if item["id"] == empty["id"])
    assert (
        call(
            client, "POST", f"/courses/{empty['id']}/delete-empty", {"expected_version": current["version"]}
        ).status_code
        == 200
    )
