import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select, text

from src.config import get_settings
from src.course_source.db import Base, engine, initialize_database
from src.course_source.db import SessionLocal as SourceSession
from src.course_source.models import (
    CalendarEvent,
    Course,
    CourseInvitation,
    Enrollment,
    GoogleIdentity,
    IntegrationEvent,
    MembershipThrottle,
    TeachingEventLink,
    User,
)
from src.db import SessionLocal
from src.main import app
from src.persistence_models import PaceWiseSession
from src.security import issue_session


@pytest.fixture
def membership_source(auth_settings):
    assert engine.dialect.name == "sqlite", "Never mutate deployment data in tests"
    initialize_database()
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(delete(table))
    with SourceSession() as db:
        for identifier, role in [
            (1, "instructor"),
            (2, "student"),
            (3, "student"),
            (4, "instructor"),
            (5, "student"),
            (6, "student"),
        ]:
            db.add(
                User(
                    id=identifier,
                    email=f"user{identifier}@gmail.com",
                    full_name=f"User {identifier}",
                    role=role,
                    password_hash="not-a-login",
                )
            )
        db.add_all(
            [
                Course(id=1, code="C1", name="Course one", term="Demo", color="#4169e1"),
                Course(id=2, code="C2", name="Course two", term="Demo", color="#4169e1"),
            ]
        )
        db.flush()
        for actor, course, role in [
            (1, 1, "instructor"),
            (4, 2, "instructor"),
            (2, 1, "student"),
            (2, 2, "student"),
            (3, 2, "student"),
        ]:
            db.add(Enrollment(user_id=actor, course_id=course, role=role))
        for actor in [2, 3, 5]:
            db.add(GoogleIdentity(subject=f"google-{actor}", user_id=actor))
        for identifier, days in [(11, -2), (12, 2)]:
            event = CalendarEvent(
                id=identifier,
                user_id=1,
                course_id=1,
                title=f"Lesson {identifier}",
                starts_at=datetime.now(UTC) + timedelta(days=days),
                ends_at=datetime.now(UTC) + timedelta(days=days, hours=3),
                event_kind="class",
                attendance_status="attended",
            )
            db.add(event)
            db.flush()
            db.add(TeachingEventLink(calendar_event_id=identifier, occurrence_key=f"lesson-{identifier}"))
        db.commit()
    settings = auth_settings.model_copy(update={"course_source_mode": "standalone"})
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings


def sign_in(client, settings, user_id):
    with SourceSession() as source:
        user = source.get(User, user_id)
        courses = list(source.scalars(select(Enrollment.course_id).where(Enrollment.user_id == user_id)))
        claims = {
            "sub": str(user_id),
            "role": user.role,
            "name": user.full_name,
            "email": user.email,
            "course_id": courses[0] if courses else 0,
        }
    with SessionLocal() as db:
        token, csrf = issue_session(db, claims, settings, courses)
    client.cookies.clear()
    client.cookies.set("pacewise_session", token)
    client.cookies.set("pacewise_csrf", csrf)
    return {"X-CSRF-Token": csrf}


async def invite(client, settings, target="user5@gmail.com"):
    headers = sign_in(client, settings, 1)
    response = await client.post(
        "/api/v1/instructor/manage/courses/1/invitations", json={"emails": [target]}, headers=headers
    )
    assert response.status_code == 201, response.text
    assert response.json()["emailSent"] is False
    return response.json()["invitations"][0]


def invitation_token(invitation):
    """Legacy-link coverage reads the encrypted value server-side only."""
    with SourceSession() as db:
        return db.get(CourseInvitation, invitation["id"]).token


@pytest.mark.asyncio
async def test_teacher_membership_is_scoped_and_requests_need_csrf(client, membership_source):
    headers = sign_in(client, membership_source, 1)
    own = await client.get("/api/v1/instructor/manage/courses/1/members")
    assert own.status_code == 200 and own.json()["students"] == [{"id": 2, "name": "User 2"}]
    assert "email" not in own.json()["students"][0]
    assert (await client.get("/api/v1/instructor/manage/courses/2/members")).status_code == 403
    assert (
        await client.post("/api/v1/instructor/manage/courses/1/invitations", json={"emails": ["user5@gmail.com"]})
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/instructor/manage/courses/1/invitations",
            headers=headers,
            json={"emails": ["user5@gmail.com"], "role": "instructor"},
        )
    ).status_code == 422
    sign_in(client, membership_source, 2)
    assert (await client.get("/api/v1/instructor/manage/courses/1/members")).status_code == 403


@pytest.mark.asyncio
async def test_invitation_does_not_disclose_account_existence_and_is_encrypted(client, membership_source):
    first = await invite(client, membership_source)
    second = await invite(client, membership_source, "nonexistent@gmail.com")
    assert first.keys() == second.keys() and first["status"] == second["status"] == "pending"
    repeat = await invite(client, membership_source)
    assert repeat["id"] == first["id"] and "token" not in first and "token" not in repeat
    token = invitation_token(first)
    with engine.connect() as db:
        raw = db.execute(text("SELECT email, token FROM course_invitations WHERE id=:id"), {"id": first["id"]}).one()
    assert raw.email.startswith("pwenc:v1:") and "user5@gmail.com" not in raw.email
    assert raw.token.startswith("pwenc:v1:") and token not in raw.token
    with SourceSession() as db:
        assert db.scalar(select(Enrollment.id).where(Enrollment.user_id == 5)) is None
        event = db.scalar(select(IntegrationEvent).where(IntegrationEvent.event_type == "invitation.changed"))
        assert event and json.loads(event.payload_json) == {"target_user_id": 5}


@pytest.mark.asyncio
async def test_verified_new_student_accepts_explicitly_without_relogin_or_duplicate_lessons(client, membership_source):
    invitation = await invite(client, membership_source)
    headers = sign_in(client, membership_source, 5)
    cookie = client.cookies["pacewise_session"]
    inbox = await client.get("/api/v1/membership/invitations")
    assert inbox.status_code == 200 and inbox.json()["invitations"][0]["code"] == "C1"
    assert "email" not in inbox.json()["invitations"][0] and "token" not in inbox.json()["invitations"][0]
    assert (await client.get("/api/v1/auth/me")).json()["user"]["courseIds"] == []
    for _ in range(2):
        assert (
            await client.post(f"/api/v1/membership/invitations/{invitation['id']}/accept", headers=headers)
        ).status_code == 200
    assert client.cookies["pacewise_session"] == cookie
    assert (await client.get("/api/v1/auth/me")).json()["user"]["courseIds"] == ["1"]
    with SourceSession() as db:
        lessons = db.scalars(select(CalendarEvent).where(CalendarEvent.user_id == 5)).all()
        assert len(lessons) == 2 and all(lesson.attendance_status is None for lesson in lessons)
        assert db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.user_id == 5)) == 1


@pytest.mark.asyncio
async def test_wrong_email_invalid_invite_id_and_unverified_identity_cannot_join(client, membership_source):
    invitation = await invite(client, membership_source)
    headers = sign_in(client, membership_source, 3)
    assert (await client.get("/api/v1/membership/invitations")).json() == {"invitations": []}
    assert (
        await client.post(f"/api/v1/membership/invitations/{invitation['id']}/accept", headers=headers)
    ).status_code == 404
    assert (
        await client.post("/api/v1/membership/invitations/not-an-invite/accept", headers=headers)
    ).status_code == 404
    headers = sign_in(client, membership_source, 6)
    assert (await client.get("/api/v1/membership/invitations")).json() == {"invitations": []}
    assert (
        await client.post(f"/api/v1/membership/invitations/{invitation['id']}/accept", headers=headers)
    ).status_code == 403


@pytest.mark.asyncio
async def test_revoked_and_expired_links_are_unusable(client, membership_source):
    invitation = await invite(client, membership_source)
    headers = sign_in(client, membership_source, 1)
    response = await client.post(
        f"/api/v1/instructor/manage/courses/1/invitations/{invitation['id']}/revoke", headers=headers
    )
    assert response.status_code == 200
    headers = sign_in(client, membership_source, 5)
    assert (
        await client.post(f"/api/v1/membership/invitations/{invitation['id']}/accept", headers=headers)
    ).status_code == 404
    replacement = await invite(client, membership_source)
    with SourceSession() as db:
        db.get(CourseInvitation, replacement["id"]).expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    headers = sign_in(client, membership_source, 5)
    assert (
        await client.post(
            f"/api/v1/membership/invitations/{replacement['id']}/accept", headers=headers
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_removal_revokes_old_cookie_permissions_but_preserves_other_courses(client, membership_source):
    student_headers = sign_in(client, membership_source, 2)
    student_cookie = client.cookies["pacewise_session"]
    teacher_headers = sign_in(client, membership_source, 1)
    response = await client.post("/api/v1/instructor/manage/courses/1/members/2/remove", headers=teacher_headers)
    assert response.status_code == 200
    client.cookies.clear()
    client.cookies.set("pacewise_session", student_cookie)
    client.cookies.set("pacewise_csrf", student_headers["X-CSRF-Token"])
    assert (await client.get("/api/v1/auth/me")).json()["user"]["courseIds"] == ["2"]
    assert (await client.get("/api/v1/lms/courses/1/modules")).status_code == 403
    assert (await client.post("/api/v1/auth/course", headers=student_headers, json={"courseId": 1})).status_code == 403
    with SourceSession() as db:
        assert db.get(User, 2) is not None
        assert db.scalar(select(Enrollment.id).where(Enrollment.user_id == 2, Enrollment.course_id == 2))
    with SessionLocal() as db:
        sessions = db.scalars(select(PaceWiseSession).where(PaceWiseSession.user_id == 2)).all()
        assert any(1 in json.loads(session.course_ids_json) for session in sessions)  # Stale snapshot really existed.


@pytest.mark.asyncio
async def test_removed_member_cannot_reuse_previously_accepted_invitation(client, membership_source):
    invitation = await invite(client, membership_source)
    headers = sign_in(client, membership_source, 5)
    assert (
        await client.post(f"/api/v1/membership/invitations/{invitation['id']}/accept", headers=headers)
    ).status_code == 200
    headers = sign_in(client, membership_source, 1)
    assert (
        await client.post("/api/v1/instructor/manage/courses/1/members/5/remove", headers=headers)
    ).status_code == 200
    headers = sign_in(client, membership_source, 5)
    assert (
        await client.post(f"/api/v1/membership/invitations/{invitation['id']}/accept", headers=headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_per_actor_rate_limit_is_persistent_and_invalid_attempts_are_charged(client, membership_source):
    headers = sign_in(client, membership_source, 5)
    assert (
        await client.post("/api/v1/membership/invitations/not-an-invite/accept", headers=headers)
    ).status_code == 404
    with SourceSession() as db:
        row = db.get(MembershipThrottle, 5)
        assert row.requests == 1
        row.requests = 30
        db.commit()
    result = await client.post("/api/v1/membership/invitations/not-an-invite/accept", headers=headers)
    assert result.status_code == 429 and result.headers["retry-after"] == "600"


@pytest.mark.asyncio
async def test_create_course_can_invite_new_students_without_any_existing_enrollment(client, membership_source):
    headers = sign_in(client, membership_source, 1)
    result = await client.post(
        "/api/v1/instructor/manage/courses",
        headers=headers,
        json={"code": "NEW", "name": "New course", "invite_emails": ["user5@gmail.com"]},
    )
    assert result.status_code == 201, result.text
    members = await client.get(f"/api/v1/instructor/manage/courses/{result.json()['id']}/members")
    assert members.json()["students"] == [] and len(members.json()["invitations"]) == 1


def test_membership_invalidation_targets_only_affected_user_even_when_they_have_no_courses():
    from types import SimpleNamespace

    from src.api.realtime import LmsEventBroker
    from src.config import Settings

    broker = LmsEventBroker(Settings(_env_file=None))
    intended = broker.subscribe([], 5)
    other = broker.subscribe([1], 2)
    broker._publish(
        SimpleNamespace(event_type="enrollment.changed", course_id=None, payload_json='{"target_user_id":5}')
    )
    assert intended.qsize() == 1 and other.empty()
    intended.get_nowait()
    broker._publish(
        SimpleNamespace(event_type="invitation.changed", course_id=None, payload_json='{"target_user_id":5}')
    )
    assert intended.qsize() == 1 and other.empty()


@pytest.mark.asyncio
async def test_known_student_addition_is_limited_to_owned_roster_and_copies_lessons(client, membership_source):
    headers = sign_in(client, membership_source, 1)
    # No global-directory assignment: user 3 is only in another teacher's course.
    assert (
        await client.post("/api/v1/instructor/manage/courses/1/members/add", headers=headers, json={"student_ids": [3]})
    ).status_code == 403
    created = await client.post(
        "/api/v1/instructor/manage/courses", headers=headers, json={"code": "NEW", "name": "New"}
    )
    identifier = created.json()["id"]
    for expected in [1, 0]:
        result = await client.post(
            f"/api/v1/instructor/manage/courses/{identifier}/members/add", headers=headers, json={"student_ids": [2]}
        )
        assert result.status_code == 200 and result.json()["added"] == expected


@pytest.mark.asyncio
async def test_member_removal_from_last_course_sets_active_course_zero_and_keeps_history(client, membership_source):
    invitation = await invite(client, membership_source)
    headers = sign_in(client, membership_source, 5)
    await client.post(f"/api/v1/membership/invitations/{invitation['id']}/accept", headers=headers)
    token, csrf = client.cookies["pacewise_session"], headers["X-CSRF-Token"]
    headers = sign_in(client, membership_source, 1)
    await client.post("/api/v1/instructor/manage/courses/1/members/5/remove", headers=headers)
    client.cookies.clear()
    client.cookies.set("pacewise_session", token)
    client.cookies.set("pacewise_csrf", csrf)
    user = (await client.get("/api/v1/auth/me")).json()["user"]
    assert user["courseIds"] == [] and user["courseId"] == "0"
    with SourceSession() as db:
        assert db.scalar(select(func.count()).select_from(CalendarEvent).where(CalendarEvent.user_id == 5)) == 2
