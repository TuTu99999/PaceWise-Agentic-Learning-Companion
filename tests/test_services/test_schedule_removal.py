"""Native schedule deletion regressions, using only the isolated SQLite fixture."""

# Imported fixtures are intentionally re-exported for pytest discovery.
# ruff: noqa: F811

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.course_source.db import SessionLocal as CourseSession
from src.course_source.models import CalendarEvent, IntegrationEvent, TeacherScheduleBatch
from src.course_source.teacher_management import lesson_json
from tests.test_services.test_standalone_source import native, sign_in  # noqa: F401

ROOT = "/api/v1/instructor/manage/schedule"


def seed_lessons():
    now = datetime.now(UTC)
    records = [
        (10, 1, "Old lesson", now - timedelta(days=30), "class", "attended"),
        (11, 2, "Old lesson", now - timedelta(days=30), "class", "absent"),
        (20, 1, "Upcoming lesson", now + timedelta(days=30), "class_session", "scheduled"),
        (21, 2, "Upcoming lesson", now + timedelta(days=30), "class_session", "scheduled"),
        (30, 1, "Cancelled lesson", now - timedelta(days=20), "class", "cancelled"),
        (31, 2, "Cancelled lesson", now - timedelta(days=20), "class", "cancelled"),
        (40, 1, "Personal event", now - timedelta(days=30), "personal", None),
        (50, 4, "Foreign lesson", now - timedelta(days=30), "class", "attended"),
    ]
    with CourseSession() as db:
        for identifier, user, title, start, kind, status in records:
            db.add(CalendarEvent(id=identifier, user_id=user, course_id=2 if user == 4 else 1,
                                 title=title, starts_at=start, ends_at=start + timedelta(hours=1),
                                 event_kind=kind, attendance_status=status, description=""))
        db.commit()


async def preview(client, headers, **kwargs):
    return await client.post(ROOT + "/preview", headers=headers,
                             json={"mode": "remove", "course_ids": [1], "rows": [], **kwargs})


async def confirm(client, headers, ticket):
    response = await client.post(ROOT + "/confirm", headers=headers, json={"ticket": ticket})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_remove_one_old_lesson_preserves_attendance_and_is_reversible(client, native):
    seed_lessons()
    headers = await sign_in(client)
    draft = (await preview(client, headers, lesson_ids=[10])).json()
    assert draft["counts"]["removed_lessons"] == 1 and not draft["applied"]
    with CourseSession() as db:
        assert db.get(CalendarEvent, 10).event_kind == "class"  # Preview never writes a lesson.
    done = await confirm(client, headers, draft["ticket"])
    assert done["applied"]
    assert (await confirm(client, headers, draft["ticket"])) == done  # Retried confirmation is safe.
    with CourseSession() as db:
        assert db.get(CalendarEvent, 10).attendance_status == "attended"
        assert db.get(CalendarEvent, 11).attendance_status == "absent"
        assert db.get(CalendarEvent, 10).event_kind == "removed_class"
        assert db.get(CalendarEvent, 11).event_kind == "removed_class"
        assert db.get(CalendarEvent, 20).event_kind == "class_session"
        assert len(db.scalars(select(IntegrationEvent).where(IntegrationEvent.event_type == "calendar.deleted")).all()) == 1
        # New attendance information must not be overwritten by undo.
        db.get(CalendarEvent, 11).attendance_status = "attended"
        db.commit()
    snapshot = (await client.get("/api/v1/instructor/manage/courses/1")).json()
    assert 10 not in {item["id"] for item in snapshot["lessons"]}
    from src.services.lms_client import LMSClient

    calendar = await LMSClient(native).service_get("/api/pacewise/v1/users/2/calendar")
    assert "event-11" not in {str(item["id"]) for item in calendar}
    undone = await client.post(ROOT + "/restore", headers=headers, json={"ticket": draft["ticket"]})
    assert undone.status_code == 200, undone.text
    with CourseSession() as db:
        assert db.get(CalendarEvent, 10).event_kind == "class"
        assert db.get(CalendarEvent, 11).event_kind == "class"
        assert db.get(CalendarEvent, 11).attendance_status == "attended"
    assert "event-11" in {str(item["id"]) for item in await LMSClient(native).service_get("/api/pacewise/v1/users/2/calendar")}


@pytest.mark.asyncio
@pytest.mark.parametrize("period,expected", [("past", {10, 30}), ("future", {20}), ("all", {10, 20, 30})])
async def test_bulk_removal_periods_include_old_and_cancelled_but_never_personal_or_foreign(client, native, period, expected):
    seed_lessons()
    headers = await sign_in(client)
    draft = (await preview(client, headers, period=period)).json()
    assert {item["id"] for item in draft["cancellations"]} == expected
    assert draft["counts"]["removed_lessons"] == len(expected)
    await confirm(client, headers, draft["ticket"])
    with CourseSession() as db:
        for identifier in expected:
            assert db.get(CalendarEvent, identifier).event_kind.startswith("removed_")
            assert db.get(CalendarEvent, identifier + 1).event_kind.startswith("removed_")
        assert db.get(CalendarEvent, 40).event_kind == "personal"
        assert db.get(CalendarEvent, 50).event_kind == "class"
        assert len(db.scalars(select(CalendarEvent)).all()) == 8  # No hard delete or cascading loss.


@pytest.mark.asyncio
async def test_date_window_honors_old_dates_and_inclusive_day_end_from_ui(client, native):
    seed_lessons()
    headers = await sign_in(client)
    with CourseSession() as db:
        for identifier in [10, 11]:
            row = db.get(CalendarEvent, identifier)
            row.starts_at = datetime(2026, 1, 1, 16, 30, tzinfo=UTC)  # 23:30 GMT+7
            row.ends_at = row.starts_at + timedelta(minutes=20)
        db.commit()
    draft = (await preview(client, headers, period="past", from_at="2026-01-01T00:00:00+07:00",
                           until_at="2026-01-02T00:00:00+07:00")).json()
    assert {item["id"] for item in draft["cancellations"]} == {10}
    await confirm(client, headers, draft["ticket"])


@pytest.mark.asyncio
async def test_same_cleanup_filters_find_new_lessons_and_can_be_used_again_after_restore(client, native):
    seed_lessons()
    headers = await sign_in(client)
    first = (await preview(client, headers, period="past")).json()
    await confirm(client, headers, first["ticket"])
    with CourseSession() as db:
        start = datetime.now(UTC) - timedelta(days=5)
        db.add(CalendarEvent(id=60, user_id=1, course_id=1, title="New old lesson", starts_at=start,
                             ends_at=start + timedelta(hours=1), event_kind="class", attendance_status="attended"))
        db.commit()
    second = (await preview(client, headers, period="past")).json()
    assert second["ticket"] != first["ticket"] and not second["applied"]
    assert {item["id"] for item in second["cancellations"]} == {60}
    await confirm(client, headers, second["ticket"])
    assert (await client.post(ROOT + "/restore", headers=headers, json={"ticket": second["ticket"]})).status_code == 200
    again = (await preview(client, headers, period="past")).json()
    assert again["ticket"] != second["ticket"] and not again["applied"]
    await confirm(client, headers, again["ticket"])


@pytest.mark.asyncio
async def test_removal_rechecks_scope_and_rejects_stale_preview_without_partial_changes(client, native):
    seed_lessons()
    headers = await sign_in(client)
    assert (await preview(client, headers, lesson_ids=[10, 50])).status_code == 404
    assert (await preview(client, headers, course_ids=[2])).status_code == 403
    assert (await preview(client, headers, lesson_ids=[40])).status_code == 404
    draft = (await preview(client, headers, period="all")).json()
    with CourseSession() as db:
        db.get(CalendarEvent, 20).title = "Changed since preview"
        db.commit()
    stale = await client.post(ROOT + "/confirm", headers=headers, json={"ticket": draft["ticket"]})
    assert stale.status_code == 409
    with CourseSession() as db:
        assert all(not row.event_kind.startswith("removed_") for row in db.scalars(select(CalendarEvent)).all())


@pytest.mark.asyncio
async def test_empty_scope_has_clear_error_and_student_cannot_remove(client, native):
    headers = await sign_in(client)
    draft = (await preview(client, headers)).json()
    assert draft["counts"]["removed_lessons"] == 0 and draft["errors"]
    assert (await client.post(ROOT + "/confirm", headers=headers, json={"ticket": draft["ticket"]})).status_code == 409
    await client.post("/api/v1/auth/logout", headers=headers)
    student_headers = await sign_in(client, "student@native.test")
    assert (await preview(client, student_headers)).status_code == 403


def test_ordinary_lesson_version_does_not_invalidate_previous_restore_tickets():
    from src.course_source.teacher_management import revision

    now = datetime.now(UTC)
    row = CalendarEvent(id=1, title="Lesson", starts_at=now, ends_at=now + timedelta(hours=1),
                        event_kind="class", attendance_status="scheduled", description="")
    body = lesson_json(row)
    assert body["version"] == revision({key: value for key, value in body.items() if key not in {"version", "removed"}})


@pytest.mark.asyncio
async def test_restore_conflict_rolls_back_entire_batch_and_expired_preview_cannot_apply(client, native):
    seed_lessons()
    headers = await sign_in(client)
    draft = (await preview(client, headers, period="all")).json()
    await confirm(client, headers, draft["ticket"])
    with CourseSession() as db:
        original = db.get(CalendarEvent, 20)
        db.add(CalendarEvent(user_id=1, course_id=1, title="New conflicting commitment", starts_at=original.starts_at,
                             ends_at=original.ends_at, event_kind="class", attendance_status="scheduled"))
        db.commit()
    conflict = await client.post(ROOT + "/restore", headers=headers, json={"ticket": draft["ticket"]})
    assert conflict.status_code == 409
    with CourseSession() as db:
        assert db.get(CalendarEvent, 10).event_kind == "removed_class"
        assert db.get(CalendarEvent, 20).event_kind == "removed_class_session"
        assert db.get(TeacherScheduleBatch, draft["ticket"]).restored_at is None
    upcoming = (await preview(client, headers, period="future")).json()
    with CourseSession() as db:
        db.get(TeacherScheduleBatch, upcoming["ticket"]).expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert (await client.post(ROOT + "/confirm", headers=headers, json={"ticket": upcoming["ticket"]})).status_code == 409


@pytest.mark.asyncio
async def test_existing_future_cancel_remains_future_only_and_undoable(client, native):
    seed_lessons()
    headers = await sign_in(client)
    result = await client.post(ROOT + "/preview", headers=headers,
                               json={"mode": "cleanup", "course_ids": [1], "rows": []})
    draft = result.json()
    assert {item["id"] for item in draft["cancellations"]} == {20}
    await confirm(client, headers, draft["ticket"])
    with CourseSession() as db:
        assert db.get(CalendarEvent, 20).attendance_status == "cancelled"
        assert db.get(CalendarEvent, 10).attendance_status == "attended"
    assert (await client.post(ROOT + "/restore", headers=headers, json={"ticket": draft["ticket"]})).status_code == 200
    with CourseSession() as db:
        assert db.get(CalendarEvent, 20).attendance_status == "scheduled"


@pytest.mark.asyncio
@pytest.mark.parametrize("single", [False, True])
async def test_remove_non_lesson_calendar_entries_keeps_tasks_and_materials(client, native, single):
    """A course calendar also contains videos, quizzes and exams, not just classes."""
    from src.course_source.models import Assignment, Resource, Submission
    from src.services.lms_client import LMSClient

    seed_lessons()
    kinds = ["lecture_video", "quiz", "midterm", "final_exam"]
    with CourseSession() as db:
        for index, kind in enumerate(kinds):
            start = datetime.now(UTC) - timedelta(days=10 - index)
            for user in [1, 2]:
                db.add(CalendarEvent(id=100 + index * 10 + user, user_id=user, course_id=1,
                                     title=f"Old {kind}", starts_at=start,
                                     ends_at=start + timedelta(minutes=40), event_kind=kind,
                                     description=""))
        # Unsupported/private events remain outside a teaching-calendar cleanup.
        db.add(CalendarEvent(id=190, user_id=1, course_id=1, title="Private reminder",
                             starts_at=start, ends_at=start + timedelta(minutes=10),
                             event_kind="personal", description=""))
        db.add(Assignment(id=90, course_id=1, title="Graded quiz task", description="Keep this task",
                          due_at=start, points_possible=20, published=True))
        db.add(Resource(id=90, course_id=1, title="Chapter slide", kind="pdf",
                        source_url="https://example.edu/chapter.pdf"))
        db.flush()
        db.add(Submission(id=90, assignment_id=90, user_id=2, submitted_at=start,
                          workflow_state="graded", score=18))
        db.commit()
        protected_before = {model.__tablename__: db.query(model).count() for model in [Assignment, Resource, Submission]}
    headers = await sign_in(client)
    authoring = (await client.get("/api/v1/instructor/manage/courses/1")).json()
    assert {row["id"] for row in authoring["lessons"]} == {10, 20, 30}
    assert {row["event_kind"] for row in authoring["calendar_events"] if "event_kind" in row} == set(kinds)
    draft = (await preview(client, headers, **({"lesson_ids": [111]} if single else {}))).json()
    selected = {111} if single else {10, 20, 30, 101, 111, 121, 131}
    assert {row["id"] for row in draft["cancellations"]} == selected
    await confirm(client, headers, draft["ticket"])
    source = LMSClient(native)
    for user in [1, 2]:
        live = await source.service_get(f"/api/pacewise/v1/users/{user}/calendar")
        selected_for_user = {identifier + (user - 1) for identifier in selected}
        assert not selected_for_user.intersection(row["source_id"] for row in live)
    synchronized = await client.get("/api/v1/lms/sync")
    assert synchronized.status_code == 200, synchronized.text
    assert not selected.intersection(
        row["source_id"] for row in synchronized.json()["courseData"]["1"]["calendarItems"]
    )
    with CourseSession() as db:
        assert db.get(CalendarEvent, 190).event_kind == "personal"
        assert {model.__tablename__: db.query(model).count() for model in [Assignment, Resource, Submission]} == protected_before
        assert db.get(Assignment, 90).points_possible == 20
        assert db.get(Submission, 90).score == 18
        assert db.get(Resource, 90).source_url == "https://example.edu/chapter.pdf"
    assert (await client.post(ROOT + "/restore", headers=headers, json={"ticket": draft["ticket"]})).status_code == 200
    with CourseSession() as db:
        for index, kind in enumerate(kinds):
            assert db.get(CalendarEvent, 101 + index * 10).event_kind == kind
            assert db.get(CalendarEvent, 102 + index * 10).event_kind == kind
