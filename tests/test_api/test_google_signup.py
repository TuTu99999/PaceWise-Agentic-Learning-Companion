from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, func, select, text

from src.api.google_signup import _account
from src.config import get_settings
from src.course_source.db import Base as CourseBase
from src.course_source.db import SessionLocal as CourseSession
from src.course_source.db import engine, initialize_database
from src.course_source.models import (
    Assignment,
    CalendarEvent,
    Course,
    CourseLifecycle,
    Enrollment,
    GoogleIdentity,
    Resource,
    TeachingEventLink,
    User,
)
from src.db import SessionLocal
from src.main import app
from src.persistence_models import GoogleCalendarConnection
from src.services.google_calendar import GoogleCalendarError, OAuthTokens


@pytest.fixture
def signup(auth_settings, monkeypatch):
    assert engine.dialect.name == "sqlite"
    initialize_database()
    with engine.begin() as connection:
        for table in reversed(CourseBase.metadata.sorted_tables):
            connection.execute(delete(table))
    settings = auth_settings.model_copy(
        update={
            "course_source_mode": "standalone",
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_token_encryption_key": Fernet.generate_key().decode(),
        }
    )
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient.exchange_code",
        AsyncMock(return_value=OAuthTokens("access", None, "openid email profile")),
    )

    class ProfileResponse:
        def json(self):
            return {
                "sub": "verified-google-subject",
                "email": "new@gmail.com",
                "name": "New student",
                "email_verified": True,
            }

    monkeypatch.setattr(
        "src.services.google_calendar.GoogleCalendarClient._get", AsyncMock(return_value=ProfileResponse())
    )
    yield settings


async def begin(client):
    response = await client.post("/api/v1/auth/google/start", json={})
    assert response.status_code == 200
    url = urlsplit(response.json()["authorizationUrl"])
    params = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    assert params["scope"] == ["openid email profile"]
    assert "calendar" not in params["scope"][0]
    assert params["code_challenge_method"] == ["S256"]
    assert "login_hint" not in params
    assert params["prompt"] == ["select_account"]
    assert "HttpOnly" in response.headers["set-cookie"]
    return params["state"][0]


@pytest.mark.asyncio
async def test_signup_creates_student_without_course_or_calendar_access(client, signup):
    state = await begin(client)
    result = await client.get("/api/v1/integrations/google-calendar/callback", params={"state": state, "code": "code"})
    assert result.status_code == 303 and "#/settings?welcome=1" in result.headers["location"]
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["role"] == "student" and me.json()["user"]["courseIds"] == []
    assert (await client.post("/api/v1/chat", json={"message": "test"})).status_code in {403, 422}
    with SessionLocal() as db:
        assert db.get(GoogleCalendarConnection, int(me.json()["user"]["id"])) is None
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT email, full_name FROM users WHERE password_hash = 'google-only'")).first()
    assert stored.email.startswith("pwenc:v1:") and "new@gmail.com" not in stored.email
    assert stored.full_name.startswith("pwenc:v1:")
    # Reusing a consumed state fails even if the browser cookie is restored.
    client.cookies.set("pacewise_google_signup", "unknown")
    replay = await client.get("/api/v1/integrations/google-calendar/callback", params={"state": state, "code": "code"})
    assert replay.status_code == 400


@pytest.mark.asyncio
async def test_cookie_binding_denial_and_untrusted_fields(client, signup):
    assert (
        await client.post("/api/v1/auth/google/start", json={"role": "instructor"})
    ).status_code == 422
    state = await begin(client)
    browser = client.cookies["pacewise_google_signup"]
    client.cookies.clear()
    missing = await client.get("/api/v1/integrations/google-calendar/callback", params={"state": state, "code": "code"})
    assert missing.status_code == 400
    client.cookies.set("pacewise_google_signup", browser)
    denied = await client.get(
        "/api/v1/integrations/google-calendar/callback", params={"state": state, "error": "access_denied"}
    )
    assert denied.status_code == 303 and "google_auth=denied" in denied.headers["location"]
    client.cookies.set("pacewise_google_signup", browser)
    replay = await client.get("/api/v1/integrations/google-calendar/callback", params={"state": state, "code": "code"})
    assert replay.status_code == 400


@pytest.mark.asyncio
async def test_signin_rate_limit_applies_to_account_chooser(client, signup):
    for index in range(signup.login_rate_limit):
        result = await client.post("/api/v1/auth/google/start", json={})
        assert result.status_code == 200
    result = await client.post("/api/v1/auth/google/start", json={})
    assert result.status_code == 429


def test_existing_native_account_not_silently_linked(signup):
    with CourseSession() as db:
        db.add(User(email="existing@gmail.com", full_name="Existing", role="instructor", password_hash="preserved"))
        db.commit()
    with pytest.raises(GoogleCalendarError, match="native_account_exists"):
        _account({"sub": "other-subject", "email": "existing@gmail.com", "email_verified": True})
    with CourseSession() as db:
        assert db.get(GoogleIdentity, "other-subject") is None


@pytest.mark.parametrize(
    "profile",
    [
        {"sub": "id", "email": "new@gmail.com", "email_verified": False},
        {"sub": "id", "email": "foreign@example.com", "email_verified": True},
    ],
)
def test_unverified_or_non_gmail_identity_rejected(signup, profile):
    with pytest.raises(GoogleCalendarError):
        _account(profile)


def test_verified_identity_reuses_account(signup):
    profile = {"sub": "same-sub", "email": "new@gmail.com", "name": "New", "email_verified": True}
    first, _ = _account(profile)
    second, _ = _account(profile)
    assert first["sub"] == second["sub"]


def test_verified_google_student_receives_active_course_schedule_tasks_and_pdf_access(signup):
    now = datetime.now(UTC)
    with CourseSession() as db:
        teacher = User(
            id=100,
            email="teacher@example.edu",
            full_name="Demo teacher",
            role="instructor",
            password_hash="not-a-login",
        )
        other_teacher = User(
            id=101,
            email="other-teacher@example.edu",
            full_name="Other teacher",
            role="instructor",
            password_hash="not-a-login",
        )
        active = Course(id=100, code="AUTO101", name="Demo active", term="Demo", color="#4169e1", published=True)
        archived = Course(id=101, code="OLD101", name="Demo archived", term="Demo", color="#4169e1", published=True)
        hidden = Course(id=102, code="HIDDEN101", name="Demo hidden", term="Demo", color="#4169e1", published=False)
        excluded = Course(id=103, code="CS101", name="Incomplete demo", term="Demo", color="#4169e1", published=True)
        db.add_all([teacher, other_teacher, active, archived, hidden, excluded])
        db.flush()
        db.add_all(
            [
                Enrollment(user_id=teacher.id, course_id=active.id, role="instructor"),
                Enrollment(user_id=teacher.id, course_id=archived.id, role="instructor"),
                Enrollment(user_id=teacher.id, course_id=hidden.id, role="instructor"),
                Enrollment(user_id=other_teacher.id, course_id=excluded.id, role="instructor"),
                CourseLifecycle(course_id=active.id, archived=False),
                CourseLifecycle(course_id=archived.id, archived=True),
                CourseLifecycle(course_id=hidden.id, archived=False),
                CourseLifecycle(course_id=excluded.id, archived=False),
                Resource(course_id=active.id, title="Slide demo.pdf", kind="file", source_url="/files/slide-demo.pdf"),
                Assignment(
                    course_id=active.id,
                    title="Bài tập demo",
                    description="Demo",
                    due_at=now + timedelta(days=2),
                    points_possible=10,
                    published=True,
                ),
            ]
        )
        lesson = CalendarEvent(
            user_id=teacher.id,
            course_id=active.id,
            title="Lịch học demo",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=1, hours=2),
            event_kind="class",
            attendance_status="scheduled",
        )
        db.add(lesson)
        db.flush()
        db.add(TeachingEventLink(calendar_event_id=lesson.id, occurrence_key="auto-demo-lesson"))
        db.commit()

    settings = signup.model_copy(
        update={
            "google_signup_auto_enroll_courses": True,
            "google_signup_auto_enroll_teacher_email": "teacher@example.edu",
        }
    )
    profile = {
        "sub": "auto-enroll-subject",
        "email": "new@gmail.com",
        "name": "New student",
        "email_verified": True,
    }
    claims, courses = _account(profile, settings)
    _, repeated_courses = _account(profile, settings)

    assert courses == [100] and repeated_courses == [100]
    assert claims["course_id"] == 100
    with CourseSession() as db:
        student_id = int(claims["sub"])
        assert db.scalar(
            select(func.count()).select_from(Enrollment).where(
                Enrollment.user_id == student_id,
                Enrollment.course_id == 100,
                Enrollment.role == "student",
            )
        ) == 1
        assert db.scalar(
            select(func.count()).select_from(CalendarEvent).where(
                CalendarEvent.user_id == student_id,
                CalendarEvent.course_id == 100,
                CalendarEvent.title == "Lịch học demo",
            )
        ) == 1
        # Resources and tasks remain single course-owned records; enrollment is
        # the ACL that makes the slide/PDF and assignment visible to the student.
        assert db.scalar(select(Resource.id).where(Resource.course_id == 100)) is not None
        assert db.scalar(select(Assignment.id).where(Assignment.course_id == 100)) is not None
        assert not db.scalar(
            select(Enrollment.id).where(
                Enrollment.user_id == student_id,
                Enrollment.course_id.in_([101, 102, 103]),
            )
        )

        # A later source-teacher import is reconciled on the existing Gmail
        # student's next sign-in, without any invitation or copied resources.
        later = Course(id=104, code="FUTURE999", name="Imported later", term="Demo", color="#4169e1", published=True)
        db.add(later)
        db.flush()
        db.add(Enrollment(user_id=teacher.id, course_id=later.id, role="instructor"))
        db.add(CourseLifecycle(course_id=later.id, archived=False))
        db.commit()

    _, refreshed_courses = _account(profile, settings)
    assert refreshed_courses == [100, 104]
