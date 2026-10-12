import html
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.account_api import router as account_router
from app.browser_bridge import pacewise_origin
from app.browser_bridge import router as browser_bridge_router
from app.course_management import router as course_management_router
from app.dates import LMSDateTime
from app.db import get_db, initialize_database
from app.extended_api import router as extended_router
from app.integration_api import router as integration_router
from app.learning_api import (
    assignment_extension_payload,
    can_access_resource,
    effective_assignment_window,
    record_submission_attempt,
    resource_extension_payload,
)
from app.learning_api import (
    router as learning_router,
)
from app.models import (
    Assignment,
    AuthSession,
    CalendarEvent,
    Conversation,
    ConversationMessage,
    ConversationParticipant,
    ConversationState,
    Course,
    CourseContent,
    Enrollment,
    MessageAttachment,
    Resource,
    Submission,
    TeachingEventLink,
    User,
)
from app.pacewise_contracts import course_actor, remove_quiz_assignment, submission_contract, sync_quiz_assignment
from app.schedule_import import router as schedule_import_router
from app.security import SessionAuthMiddleware, issue_session, set_browser_cookies, verify_password
from app.teacher_management import router as teacher_management_router
from app.telemetry import record_change

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Canvas LMS Lightweight Simulator",
    description="Lightweight Canvas-compatible development server",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[pacewise_origin()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionAuthMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"detail": "Invalid request data"}, status_code=422)


@app.exception_handler(HTTPException)
async def safe_http_error(request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail if exc.status_code < 500 else "Service temporarily unavailable"},
                        status_code=exc.status_code, headers=exc.headers)


@app.middleware("http")
async def private_responses(request: Request, call_next):
    try:
        # API-only deployment still supports service login, file downloads and
        # teacher authoring. Never serve SPA/static assets or Swagger there.
        if os.getenv("LMS_WEB_ENABLED", "true").lower() != "true" and not request.url.path.startswith("/api/"):
            response = JSONResponse({"detail": "LMS web is disabled"}, status_code=404)
        else:
            response = await call_next(request)
    except Exception as exc:
        logging.getLogger("canvas.http").error("request_failed error_type=%s", type(exc).__name__)
        response = JSONResponse({"detail": "Service temporarily unavailable"}, status_code=500)
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, private"
    return response


class LoginRequest(BaseModel):
    email: str
    password: str


class SubmitRequest(BaseModel):
    user_id: int


class CourseContentRequest(BaseModel):
    user_id: int
    title: str
    body: str = ""
    due_at: LMSDateTime | None = None
    points_possible: float | None = None
    published: bool = True


class CalendarEventRequest(BaseModel):
    user_id: int
    course_id: int | None = None
    title: str
    description: str = ""
    starts_at: LMSDateTime
    ends_at: LMSDateTime | None = None
    repeat_count: int = 1


class AttendanceRequest(BaseModel):
    status: Literal["scheduled", "attended", "absent"]


class ConversationRequest(BaseModel):
    sender_id: int
    recipient_ids: list[int]
    subject: str
    body: str


class MessageRequest(BaseModel):
    sender_id: int
    body: str


def user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.full_name,
        "role": user.role,
        "avatar_color": user.avatar_color,
        "demo_submission_timing_enabled": os.getenv("ALLOW_DEMO_SUBMISSION_TIMING", "false").lower() == "true",
    }


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def get_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def require_teacher(db: Session, user_id: int, course_id: int) -> User:
    user = get_user(db, user_id)
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.user_id == user.id,
            Enrollment.course_id == course_id,
            Enrollment.role == "instructor",
        )
    )
    if not enrollment:
        raise HTTPException(status_code=403, detail="Teacher enrollment required")
    return user


def serialize_content(item: CourseContent) -> dict:
    return {
        "id": item.id,
        "course_id": item.course_id,
        "kind": item.kind,
        "title": item.title,
        "body": item.body,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "points_possible": item.points_possible,
        "published": item.published,
        "created_at": item.created_at.isoformat(),
    }


def assignment_state(assignment: Assignment, submission: Submission | None) -> str:
    if submission and submission.workflow_state in {"submitted", "graded", "pending_review"}:
        return "late" if submission.late else "submitted"
    now = datetime.now(UTC)
    due_at = assignment.due_at.replace(tzinfo=UTC) if assignment.due_at.tzinfo is None else assignment.due_at
    if due_at < now:
        return "missing"
    return "upcoming"


def serialize_assignment(
    assignment: Assignment,
    course: Course,
    submission: Submission | None = None,
) -> dict:
    return {
        "id": assignment.id,
        "course_id": course.id,
        "course_code": course.code,
        "course_name": course.name,
        "title": assignment.title,
        "description": assignment.description,
        "due_at": assignment.due_at.isoformat(),
        "points_possible": assignment.points_possible,
        "submission_types": assignment.submission_types.split(","),
        "published": assignment.published,
        "state": assignment_state(assignment, submission),
        "submitted_at": submission.submitted_at.isoformat() if submission and submission.submitted_at else None,
        "score": submission.score if submission else None,
    }


def serialize_effective_assignment(
    db: Session,
    assignment: Assignment,
    course: Course,
    submission: Submission | None,
    user_id: int,
) -> dict:
    result = serialize_assignment(assignment, course, submission)
    extension = assignment_extension_payload(db, assignment, user_id)
    result.update(extension)
    state = submission_contract(db, submission)["workflow_state"] if submission else "unsubmitted"
    if state == "excused":
        result["state"] = "excused"
    elif state in {"submitted", "graded", "pending_review"}:
        result["state"] = "late" if submission.late else "submitted"
    else:
        effective_due = datetime.fromisoformat(extension["due_at"])
        if effective_due.tzinfo is None:
            effective_due = effective_due.replace(tzinfo=UTC)
        result["state"] = "missing" if effective_due < datetime.now(UTC) else "upcoming"
    return result


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "lms-simulator"}


@app.post("/api/session")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    service_key = request.headers.get("x-pacewise-key")
    if service_key:
        from app.integration_api import require_service_key
        require_service_key(service_key)
    elif request.headers.get("origin") and request.headers["origin"] != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Same-origin sign-in required")
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    access_token, csrf_token, _ = issue_session(db, user)
    record_change(
        db,
        actor_user_id=user.id,
        action="session.login",
        entity_type="user",
        entity_id=user.id,
        metadata={"role": user.role},
        emit_event=False,
    )
    db.commit()
    set_browser_cookies(response, access_token, csrf_token)
    result = {
        "user": user_payload(user),
        "csrf_token": csrf_token,
    }
    # Only a trusted backend gets a temporary bearer token, never browser JS.
    if service_key:
        result.update(access_token=access_token, token_type="bearer")
    return result


@app.get("/api/session/me")
def session_me(request: Request, db: Session = Depends(get_db)) -> dict:
    user = get_user(db, request.state.current_user_id)
    return {"user": user_payload(user)}


@app.delete("/api/session")
def logout_session(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    auth_session = db.get(AuthSession, request.state.auth_session_id)
    if auth_session:
        auth_session.revoked_at = datetime.now(UTC)
        record_change(
            db,
            actor_user_id=auth_session.user_id,
            action="session.logout",
            entity_type="user",
            entity_id=auth_session.user_id,
            emit_event=False,
        )
        db.commit()
    response.delete_cookie("canvas_session", path="/")
    response.delete_cookie("canvas_csrf", path="/")
    return {"ok": True}


@app.get("/api/users/{user_id}")
def read_user(user_id: int, db: Session = Depends(get_db)) -> dict:
    return user_payload(get_user(db, user_id))


@app.get("/api/users")
def list_users(request: Request, db: Session = Depends(get_db)) -> list[dict]:
    # Directory is scoped to shared classes, not an institution-wide email dump.
    courses = select(Enrollment.course_id).where(Enrollment.user_id == request.state.current_user_id)
    classmates = select(Enrollment.user_id).where(Enrollment.course_id.in_(courses))
    users = db.scalars(select(User).where((User.id.in_(classmates)) | (User.id == request.state.current_user_id))
                       .order_by(User.full_name)).all()
    return [{key: value for key, value in user_payload(user).items() if key in {"id", "name", "role", "avatar_color"}}
            for user in users]


@app.get("/api/dashboard/{user_id}")
def dashboard(user_id: int, db: Session = Depends(get_db)) -> dict:
    user = get_user(db, user_id)
    enrollments = db.scalars(select(Enrollment).where(Enrollment.user_id == user.id).order_by(Enrollment.id)).all()
    courses = [
        {
            "id": enrollment.course.id,
            "code": enrollment.course.code,
            "name": enrollment.course.name,
            "term": enrollment.course.term,
            "color": enrollment.course.color,
            "progress": enrollment.progress,
            "enrollment_role": enrollment.role,
        }
        for enrollment in enrollments
        if enrollment.role == "instructor" or enrollment.course.published
    ]

    assignment_rows = db.execute(
        select(Assignment, Course, Submission)
        .join(Course, Course.id == Assignment.course_id)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .outerjoin(
            Submission,
            (Submission.assignment_id == Assignment.id) & (Submission.user_id == user.id),
        )
        .where(Enrollment.user_id == user.id)
        .order_by(Assignment.due_at)
    ).all()
    assignments = [
        serialize_effective_assignment(db, assignment, course, submission, user.id)
        for assignment, course, submission in assignment_rows
        if user.role != "student" or (assignment.published and course.published)
    ]
    if user.role == "student":
        pending = [item for item in assignments if item["state"] not in {"submitted", "late", "excused"}]
        recent_feedback = [item for item in assignments if item["score"] is not None]
    else:
        pending = []
        recent_feedback = []
    return {
        "user": user_payload(user),
        "courses": courses,
        "todos": pending[:7],
        "recent_feedback": recent_feedback[:5],
    }


@app.get("/api/courses/{course_id}")
def course_detail(course_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    user = get_user(db, user_id)
    course = get_course(db, course_id)
    course_actor(db, course_id, user_id)
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.user_id == user.id,
            Enrollment.course_id == course.id,
        )
    )
    if not enrollment:
        raise HTTPException(status_code=403, detail="User is not enrolled in this course")

    assignments = db.scalars(
        select(Assignment).where(Assignment.course_id == course.id).order_by(Assignment.due_at)
    ).all()
    submission_map = {
        submission.assignment_id: submission
        for submission in db.scalars(select(Submission).where(Submission.user_id == user.id)).all()
    }
    resources = [
        resource
        for resource in db.scalars(select(Resource).where(Resource.course_id == course.id)).all()
        if enrollment.role == "instructor" or can_access_resource(db, resource, user.id)
    ]
    course_enrollments = db.scalars(
        select(Enrollment).where(Enrollment.course_id == course.id).order_by(Enrollment.role, Enrollment.id)
    ).all()
    course_submissions = db.scalars(
        select(Submission)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .where(Assignment.course_id == course.id)
    ).all()
    submission_lookup = {
        (submission.user_id, submission.assignment_id): submission for submission in course_submissions
    }
    content_items = db.scalars(
        select(CourseContent).where(CourseContent.course_id == course.id).order_by(CourseContent.created_at.desc())
    ).all()
    student_count = db.scalar(
        select(func.count(Enrollment.id)).where(
            Enrollment.course_id == course.id,
            Enrollment.role == "student",
        )
    )
    return {
        "course": {
            "id": course.id,
            "code": course.code,
            "name": course.name,
            "term": course.term,
            "color": course.color,
            "published": course.published,
            "progress": enrollment.progress,
            "student_count": student_count or 0,
        },
        "assignments": [
            serialize_effective_assignment(
                db,
                assignment,
                course,
                submission_map.get(assignment.id),
                user.id,
            )
            for assignment in assignments
            if enrollment.role == "instructor" or assignment.published
        ],
        "resources": [
            {
                "id": resource.id,
                "title": resource.title,
                "kind": resource.kind,
                "source_url": resource.source_url,
                **resource_extension_payload(db, resource),
            }
            for resource in resources
        ],
        "people": [
            {
                "id": item.user.id,
                "name": item.user.full_name,
                "email": item.user.email,
                "role": item.role,
            }
            for item in course_enrollments
        ],
        "gradebook": [
            {
                "user_id": item.user.id,
                "name": item.user.full_name,
                "grades": [
                    {
                        "assignment_id": assignment.id,
                        "score": submission_lookup[(item.user.id, assignment.id)].score,
                    }
                    if (item.user.id, assignment.id) in submission_lookup
                    else {"assignment_id": assignment.id, "score": None}
                    for assignment in assignments
                ],
            }
            for item in course_enrollments
            if item.role == "student" and (enrollment.role == "instructor" or item.user_id == user.id)
        ],
        "content": {
            kind: [serialize_content(item) for item in content_items if item.kind == kind and (enrollment.role == "instructor" or item.published)]
            for kind in {"announcement", "discussion", "page", "outcome", "quiz", "syllabus"}
        },
    }


@app.post("/api/assignments/{assignment_id}/submit")
def submit_assignment(
    assignment_id: int,
    payload: SubmitRequest,
    db: Session = Depends(get_db),
) -> dict:
    user = get_user(db, payload.user_id)
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can submit assignments")
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    course_actor(db, assignment.course_id, user.id)
    if not assignment.published:
        raise HTTPException(403, "Assignment is not published")
    submission = db.scalar(
        select(Submission).where(
            Submission.assignment_id == assignment.id,
            Submission.user_id == user.id,
        )
    )
    now = datetime.now(UTC)
    due_at, unlock_at, lock_at, _ = effective_assignment_window(db, assignment, user.id)
    due_at = due_at.replace(tzinfo=UTC) if due_at.tzinfo is None else due_at
    unlock_at = unlock_at.replace(tzinfo=UTC) if unlock_at and unlock_at.tzinfo is None else unlock_at
    lock_at = lock_at.replace(tzinfo=UTC) if lock_at and lock_at.tzinfo is None else lock_at
    if unlock_at and now < unlock_at:
        raise HTTPException(status_code=409, detail="Assignment is not available yet")
    if lock_at and now > lock_at:
        raise HTTPException(status_code=409, detail="Assignment is locked")
    if not submission:
        submission = Submission(assignment_id=assignment.id, user_id=user.id)
        db.add(submission)
    submission.submitted_at = now
    submission.workflow_state = "submitted"
    submission.late = now > due_at
    db.flush()
    record_submission_attempt(db, submission)
    record_change(
        db,
        actor_user_id=user.id,
        action="submission.submitted",
        entity_type="submission",
        entity_id=submission.id,
        course_id=assignment.course_id,
        metadata={"assignment_id": assignment.id, "late": submission.late},
    )
    db.commit()
    return {"status": "submitted", "late": submission.late, "submitted_at": now.isoformat()}


CONTENT_KINDS = {"announcement", "discussion", "page", "outcome", "quiz", "syllabus"}


@app.get("/api/courses/{course_id}/content/{kind}")
def list_course_content(course_id: int, kind: str, request: Request, db: Session = Depends(get_db)) -> list[dict]:
    get_course(db, course_id)
    actor = course_actor(db, course_id, request.state.current_user_id)
    if kind not in CONTENT_KINDS:
        raise HTTPException(status_code=404, detail="Unsupported Canvas content type")
    items = db.scalars(
        select(CourseContent)
        .where(CourseContent.course_id == course_id, CourseContent.kind == kind)
        .order_by(CourseContent.created_at.desc())
    ).all()
    return [serialize_content(item) for item in items if actor.role == "instructor" or item.published]


@app.post("/api/courses/{course_id}/content/{kind}")
def create_course_content(
    course_id: int,
    kind: str,
    payload: CourseContentRequest,
    db: Session = Depends(get_db),
) -> dict:
    get_course(db, course_id)
    require_teacher(db, payload.user_id, course_id)
    if kind not in CONTENT_KINDS:
        raise HTTPException(status_code=404, detail="Unsupported Canvas content type")
    item = CourseContent(
        course_id=course_id,
        kind=kind,
        title=payload.title.strip(),
        body=payload.body.strip(),
        due_at=payload.due_at,
        points_possible=payload.points_possible,
        published=payload.published,
    )
    if not item.title:
        raise HTTPException(status_code=422, detail="Title is required")
    db.add(item)
    db.flush()
    sync_quiz_assignment(db, item, payload.user_id)
    record_change(
        db,
        actor_user_id=payload.user_id,
        action="content.created",
        entity_type=kind,
        entity_id=item.id,
        course_id=course_id,
        metadata={"title": item.title, "published": item.published},
    )
    db.commit()
    db.refresh(item)
    return serialize_content(item)


@app.put("/api/courses/{course_id}/content/{kind}/{item_id}")
def update_course_content(
    course_id: int,
    kind: str,
    item_id: int,
    payload: CourseContentRequest,
    db: Session = Depends(get_db),
) -> dict:
    require_teacher(db, payload.user_id, course_id)
    item = db.scalar(
        select(CourseContent).where(
            CourseContent.id == item_id,
            CourseContent.course_id == course_id,
            CourseContent.kind == kind,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    if not payload.title.strip():
        raise HTTPException(status_code=422, detail="Title is required")
    item.title = payload.title.strip()
    item.body = payload.body.strip()
    item.due_at = payload.due_at
    item.points_possible = payload.points_possible
    item.published = payload.published
    sync_quiz_assignment(db, item, payload.user_id)
    record_change(
        db,
        actor_user_id=payload.user_id,
        action="content.updated",
        entity_type=kind,
        entity_id=item.id,
        course_id=course_id,
        metadata={"title": item.title, "published": item.published},
    )
    db.commit()
    return serialize_content(item)


@app.delete("/api/courses/{course_id}/content/{kind}/{item_id}")
def delete_course_content(
    course_id: int,
    kind: str,
    item_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    require_teacher(db, user_id, course_id)
    item = db.scalar(
        select(CourseContent).where(
            CourseContent.id == item_id,
            CourseContent.course_id == course_id,
            CourseContent.kind == kind,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    record_change(
        db,
        actor_user_id=user_id,
        action="content.deleted",
        entity_type=kind,
        entity_id=item.id,
        course_id=course_id,
        metadata={"title": item.title},
    )
    remove_quiz_assignment(db, item.id, user_id)
    db.delete(item)
    db.commit()
    return {"status": "deleted", "id": item_id}


@app.get("/api/calendar/{user_id}")
def calendar_items(user_id: int, db: Session = Depends(get_db)) -> list[dict]:
    user = get_user(db, user_id)
    enrolled_course_ids = set(
        db.scalars(select(Enrollment.course_id).join(Course, Course.id == Enrollment.course_id)
                   .where(Enrollment.user_id == user.id, (Enrollment.role == "instructor") | Course.published.is_(True))).all()
    )
    assignments = db.execute(
        select(Assignment, Course)
        .join(Course, Course.id == Assignment.course_id)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.user_id == user.id)
        .order_by(Assignment.due_at)
    ).all()
    events = db.scalars(
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user.id,
            or_(CalendarEvent.attendance_status.is_(None), CalendarEvent.attendance_status != "cancelled"),
            or_(
                CalendarEvent.course_id.is_(None),
                CalendarEvent.course_id.in_(enrolled_course_ids),
            ),
        )
        .order_by(CalendarEvent.starts_at)
    ).all()
    event_course_ids = {event.course_id for event in events if event.course_id is not None}
    event_courses = {
        course.id: course
        for course in db.scalars(select(Course).where(Course.id.in_(event_course_ids))).all()
    }
    assignment_items = [
        {
            "id": f"assignment-{assignment.id}",
            "source_id": assignment.id,
            "type": "assignment",
            "course_id": course.id,
            "course_code": course.code,
            "color": course.color,
            "title": assignment.title,
            "starts_at": effective_assignment_window(db, assignment, user.id)[0].isoformat(),
            "ends_at": None,
            "duration_minutes": None,
            "description": assignment.description,
            "event_kind": "assignment",
            "join_url": None,
            "attendance_status": None,
            "editable": False,
        }
        for assignment, course in assignments
        if user.role != "student" or (assignment.published and course.published)
    ]
    event_items = []
    teaching_course_ids = set(db.scalars(select(Enrollment.course_id).where(Enrollment.user_id == user.id, Enrollment.role == "instructor")).all())
    for event in events:
        course = event_courses.get(event.course_id)
        seeded = event.description.startswith("pacewise-2026-v1;")
        course_activity = event.description.startswith("course-activity-v1;")
        institutional = seeded or course_activity
        public_description = (
            event.description.split(";", 1)[1].strip()
            if course_activity and ";" in event.description
            else "" if seeded else event.description
        )
        event_items.append(
            {
                "id": f"event-{event.id}",
                "source_id": event.id,
                "type": "event",
                "course_id": event.course_id,
                "course_code": course.code if course else None,
                "color": course.color if course else "#0374b5",
                "title": event.title,
                "starts_at": event.starts_at.isoformat(),
                "ends_at": event.ends_at.isoformat() if event.ends_at else None,
                "duration_minutes": (
                    max(0, int((event.ends_at - event.starts_at).total_seconds() // 60))
                    if event.ends_at
                    else None
                ),
                "description": public_description,
                "event_kind": event.event_kind,
                "join_url": event.join_url,
                "attendance_status": event.attendance_status,
                "editable": not institutional or (event.course_id in teaching_course_ids and event.event_kind == "class_session"),
            }
        )
    return sorted(assignment_items + event_items, key=lambda item: item["starts_at"])


def _validate_personal_calendar(payload: CalendarEventRequest, db: Session) -> None:
    if not payload.title.strip():
        raise HTTPException(422, "Title is required")
    if payload.ends_at and payload.ends_at <= payload.starts_at:
        raise HTTPException(422, "ends_at must be after starts_at")
    if payload.course_id is not None:
        course_actor(db, payload.course_id, payload.user_id)


def _editable_calendar_targets(db: Session, event: CalendarEvent, actor_id: int) -> list[CalendarEvent]:
    if not event.description.startswith(("pacewise-2026-v1;", "course-activity-v1;")):
        return [event]
    actor = course_actor(db, event.course_id, actor_id) if event.course_id is not None else None
    if not actor or actor.role != "instructor" or event.event_kind != "class_session":
        raise HTTPException(403, "Course teaching events are LMS-owned; ask the instructor to change the course activity")
    link = db.get(TeachingEventLink, event.id)
    if link:
        return db.scalars(select(CalendarEvent).join(TeachingEventLink, TeachingEventLink.calendar_event_id == CalendarEvent.id)
                          .where(TeachingEventLink.occurrence_key == link.occurrence_key, CalendarEvent.course_id == event.course_id)).all()
    # Old seed rows predate occurrence IDs. Only treat exact, unambiguous copies
    # (one per user) as a single occurrence. Never guess between duplicate classes.
    copies = db.scalars(select(CalendarEvent).where(CalendarEvent.course_id == event.course_id,
                       CalendarEvent.title == event.title, CalendarEvent.starts_at == event.starts_at,
                       CalendarEvent.ends_at == event.ends_at, CalendarEvent.description == event.description,
                       CalendarEvent.event_kind == event.event_kind)).all()
    if len({row.user_id for row in copies}) != len(copies):
        raise HTTPException(409, "Legacy teaching occurrence is ambiguous; recreate it with an explicit occurrence ID")
    return copies


@app.post("/api/calendar")
def create_calendar_event(payload: CalendarEventRequest, db: Session = Depends(get_db)) -> dict:
    get_user(db, payload.user_id)
    _validate_personal_calendar(payload, db)
    if payload.course_id:
        get_course(db, payload.course_id)
    if not payload.title.strip():
        raise HTTPException(status_code=422, detail="Title is required")
    if payload.repeat_count < 1 or payload.repeat_count > 52:
        raise HTTPException(status_code=422, detail="Repeat count must be between 1 and 52")
    from datetime import timedelta

    events = []
    for index in range(payload.repeat_count):
        event = CalendarEvent(
            user_id=payload.user_id,
            course_id=payload.course_id,
            title=payload.title.strip(),
            description=payload.description.strip(),
            starts_at=payload.starts_at + timedelta(days=7 * index),
            ends_at=payload.ends_at + timedelta(days=7 * index) if payload.ends_at else None,
            event_kind="personal",
        )
        db.add(event)
        events.append(event)
        db.flush()
        record_change(db, actor_user_id=payload.user_id, action="calendar.created", entity_type="calendar_event", entity_id=event.id, course_id=event.course_id)
    db.commit()
    return {"status": "created", "id": events[0].id, "created": len(events)}


@app.put("/api/calendar/{event_id}")
def update_calendar_event(
    event_id: int,
    payload: CalendarEventRequest,
    db: Session = Depends(get_db),
) -> dict:
    event = db.get(CalendarEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    if event.user_id != payload.user_id:
        raise HTTPException(status_code=403, detail="You cannot edit this event")
    targets = _editable_calendar_targets(db, event, payload.user_id)
    _validate_personal_calendar(payload, db)
    institutional = event.description.startswith(("pacewise-2026-v1;", "course-activity-v1;"))
    if institutional and (payload.course_id != event.course_id or payload.ends_at is None):
        raise HTTPException(422, "Teaching occurrence must keep its course and a valid end time")
    for target in targets:
        target.course_id = payload.course_id
        target.title = payload.title.strip()
        target.description = f"course-activity-v1; {payload.description.strip()}" if institutional else payload.description.strip()
        target.starts_at = payload.starts_at
        target.ends_at = payload.ends_at
    record_change(db, actor_user_id=payload.user_id, action="calendar.updated", entity_type="calendar_event", entity_id=event.id, course_id=event.course_id, metadata={"affected_calendar_events": len(targets)})
    db.commit()
    return {"status": "updated", "id": event.id, "affected_calendar_events": len(targets)}


@app.delete("/api/calendar/{event_id}")
def delete_calendar_event(
    event_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    event = db.get(CalendarEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    if event.user_id != user_id:
        raise HTTPException(status_code=403, detail="You cannot delete this event")
    targets = _editable_calendar_targets(db, event, user_id)
    record_change(db, actor_user_id=user_id, action="calendar.deleted", entity_type="calendar_event", entity_id=event.id, course_id=event.course_id, metadata={"affected_calendar_events": len(targets)})
    for target in targets:
        link = db.get(TeachingEventLink, target.id)
        if link:
            db.delete(link)
        db.delete(target)
    db.commit()
    return {"status": "deleted", "id": event_id, "affected_calendar_events": len(targets)}


@app.patch("/api/calendar/events/{event_id}/attendance")
def update_calendar_attendance(
    event_id: int,
    payload: AttendanceRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    event = db.get(CalendarEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    current_user_id = getattr(request.state, "current_user_id", None)
    if event.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="You cannot update this attendance")
    if event.event_kind != "class_session":
        raise HTTPException(status_code=422, detail="Attendance applies only to online classes")
    event.attendance_status = payload.status
    record_change(
        db,
        actor_user_id=current_user_id,
        action="calendar.attendance.updated",
        entity_type="calendar_event",
        entity_id=event.id,
        course_id=event.course_id,
        metadata={"attendance_status": payload.status},
        emit_event=False,
    )
    db.commit()
    return {"status": "updated", "id": event.id, "attendance_status": payload.status}


@app.get("/api/calendar/events/{event_id}/join", response_class=HTMLResponse)
def join_mock_classroom(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    event = db.get(CalendarEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Online class not found")
    current_user_id = getattr(request.state, "current_user_id", None)
    if event.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="You cannot join this online class")
    if event.event_kind != "class_session":
        raise HTTPException(status_code=422, detail="This event is not an online class")

    title = html.escape(event.title)
    starts_at = html.escape(event.starts_at.isoformat())
    content = f"""<!doctype html>
<html lang="vi">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{title}</title>
    <style>
      body {{ margin:0; font-family:Arial,sans-serif; background:#f5f7fa; color:#2d3b45; }}
      main {{ max-width:720px; margin:10vh auto; padding:36px; background:white;
              border:1px solid #c7cdd1; border-radius:10px; text-align:center; }}
      .room {{ margin:24px 0; padding:48px 20px; background:#1f2937; color:white;
               border-radius:8px; }}
      button {{ padding:10px 18px; border:0; border-radius:4px; background:#0374b5;
                color:white; cursor:pointer; }}
    </style>
  </head>
  <body>
    <main>
      <h1>{title}</h1>
      <p>Bắt đầu: {starts_at}</p>
      <div class="room">
        <h2>Phòng học online mô phỏng</h2>
        <p>Không truyền âm thanh hoặc video thật. Trang này chỉ mô phỏng thao tác tham gia lớp.</p>
      </div>
      <button onclick="window.close()">Rời phòng học</button>
    </main>
  </body>
</html>"""
    return HTMLResponse(content=content)


def serialize_conversation(db: Session, conversation: Conversation, current_user_id: int) -> dict:
    participant_rows = (
        db.execute(
            select(User)
            .join(ConversationParticipant, ConversationParticipant.user_id == User.id)
            .where(ConversationParticipant.conversation_id == conversation.id)
            .order_by(User.full_name)
        )
        .scalars()
        .all()
    )
    messages = db.execute(
        select(ConversationMessage, User)
        .join(User, User.id == ConversationMessage.sender_id)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.created_at)
    ).all()
    conversation_state = db.scalar(
        select(ConversationState).where(
            ConversationState.conversation_id == conversation.id,
            ConversationState.user_id == current_user_id,
        )
    )
    return {
        "id": conversation.id,
        "subject": conversation.subject,
        "participants": [user_payload(user) for user in participant_rows],
        "messages": [
            {
                "id": message.id,
                "sender": user_payload(sender),
                "body": message.body,
                "created_at": message.created_at.isoformat(),
                "mine": message.sender_id == current_user_id,
                "attachments": [
                    {
                        "id": attachment.id,
                        "file_name": attachment.file_name,
                        "file_url": attachment.file_url,
                    }
                    for attachment in db.scalars(
                        select(MessageAttachment).where(MessageAttachment.message_id == message.id)
                    ).all()
                ],
            }
            for message, sender in messages
        ],
        "updated_at": messages[-1][0].created_at.isoformat() if messages else conversation.created_at.isoformat(),
        "unread": conversation_state.unread if conversation_state else False,
        "archived": conversation_state.archived if conversation_state else False,
    }


@app.get("/api/inbox/{user_id}")
def inbox(user_id: int, box: str = Query(default="inbox"), db: Session = Depends(get_db)) -> list[dict]:
    get_user(db, user_id)
    conversations = db.scalars(
        select(Conversation)
        .join(
            ConversationParticipant,
            ConversationParticipant.conversation_id == Conversation.id,
        )
        .where(ConversationParticipant.user_id == user_id)
        .order_by(Conversation.created_at.desc())
    ).all()
    serialized = [serialize_conversation(db, conversation, user_id) for conversation in conversations]
    if box == "archived":
        return [item for item in serialized if item["archived"]]
    if box == "unread":
        return [item for item in serialized if item["unread"] and not item["archived"]]
    if box == "sent":
        return [item for item in serialized if any(message["mine"] for message in item["messages"])]
    return [item for item in serialized if not item["archived"]]


@app.post("/api/inbox")
def create_conversation(payload: ConversationRequest, db: Session = Depends(get_db)) -> dict:
    sender = get_user(db, payload.sender_id)
    recipients = [get_user(db, user_id) for user_id in set(payload.recipient_ids)]
    if not payload.subject.strip() or not payload.body.strip() or not recipients:
        raise HTTPException(status_code=422, detail="Recipients, subject, and message are required")
    conversation = Conversation(subject=payload.subject.strip())
    db.add(conversation)
    db.flush()
    participant_ids = {sender.id, *(recipient.id for recipient in recipients)}
    db.add_all(
        [ConversationParticipant(conversation_id=conversation.id, user_id=user_id) for user_id in participant_ids]
    )
    db.add_all(
        [
            ConversationState(
                conversation_id=conversation.id,
                user_id=user_id,
                unread=user_id != sender.id,
            )
            for user_id in participant_ids
        ]
    )
    db.add(
        ConversationMessage(
            conversation_id=conversation.id,
            sender_id=sender.id,
            body=payload.body.strip(),
        )
    )
    db.commit()
    return serialize_conversation(db, conversation, sender.id)


@app.post("/api/inbox/{conversation_id}/messages")
def reply_to_conversation(
    conversation_id: int,
    payload: MessageRequest,
    db: Session = Depends(get_db),
) -> dict:
    get_user(db, payload.sender_id)
    participant = db.scalar(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == payload.sender_id,
        )
    )
    if not participant:
        raise HTTPException(status_code=403, detail="You are not part of this conversation")
    if not payload.body.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    db.add(
        ConversationMessage(
            conversation_id=conversation_id,
            sender_id=payload.sender_id,
            body=payload.body.strip(),
        )
    )
    states = db.scalars(select(ConversationState).where(ConversationState.conversation_id == conversation_id)).all()
    for conversation_state in states:
        conversation_state.unread = conversation_state.user_id != payload.sender_id
    if not any(conversation_state.user_id == payload.sender_id for conversation_state in states):
        db.add(
            ConversationState(
                conversation_id=conversation_id,
                user_id=payload.sender_id,
                unread=False,
            )
        )
    db.commit()
    conversation = db.get(Conversation, conversation_id)
    return serialize_conversation(db, conversation, payload.sender_id)


@app.get("/api/v1/courses")
def canvas_courses(
    request: Request,
    db: Session = Depends(get_db),
) -> list[dict]:
    user = get_user(db, request.state.current_user_id)
    enrollments = db.scalars(select(Enrollment).where(Enrollment.user_id == user.id)).all()
    return [
        {
            "id": item.course.id,
            "name": item.course.name,
            "course_code": item.course.code,
            "workflow_state": "available",
            "enrollment_term_id": 1,
            "enrollments": [{"type": item.role, "computed_current_score": item.progress}],
        }
        for item in enrollments
    ]


@app.get("/api/v1/courses/{course_id}/assignments")
def canvas_assignments(
    course_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> list[dict]:
    user = get_user(db, request.state.current_user_id)
    course = get_course(db, course_id)
    enrollment = db.scalar(
        select(Enrollment).where(Enrollment.user_id == user.id, Enrollment.course_id == course.id)
    )
    if not enrollment:
        raise HTTPException(status_code=403, detail="Course enrollment required")
    submissions = {
        item.assignment_id: item for item in db.scalars(select(Submission).where(Submission.user_id == user.id)).all()
    }
    assignments = db.scalars(
        select(Assignment).where(Assignment.course_id == course.id).order_by(Assignment.due_at)
    ).all()
    return [
        {
            "id": item.id,
            "course_id": course.id,
            "name": item.title,
            "description": item.description,
            "due_at": item.due_at.isoformat(),
            "points_possible": item.points_possible,
            "published": item.published,
            "submission": {
                "workflow_state": submissions[item.id].workflow_state,
                "submitted_at": submissions[item.id].submitted_at.isoformat()
                if submissions.get(item.id) and submissions[item.id].submitted_at
                else None,
                "late": submissions[item.id].late,
            }
            if submissions.get(item.id)
            else None,
        }
        for item in assignments
    ]


app.include_router(account_router)
app.include_router(learning_router)
app.include_router(extended_router)
app.include_router(integration_router)
app.include_router(browser_bridge_router)
app.include_router(teacher_management_router)
app.include_router(course_management_router)
app.include_router(schedule_import_router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/{path:path}", include_in_schema=False)
def spa_fallback(path: str, request: Request) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    return FileResponse(STATIC_DIR / "index.html")
