import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.dates import LMSDateTime
from app.db import get_db
from app.learning_api import (
    assignment_extension_payload,
    can_access_resource,
    effective_assignment_window,
    module_extension_payload,
    record_resource_version,
    record_submission_attempt,
    resource_extension_payload,
)
from app.models import (
    Assignment,
    CalendarEvent,
    ConversationMessage,
    ConversationParticipant,
    ConversationState,
    Course,
    CourseContent,
    CourseModule,
    DiscussionLike,
    DiscussionReply,
    Enrollment,
    GradeHistory,
    LearningEvidence,
    MessageAttachment,
    ModuleItem,
    OutcomeAlignment,
    QuizAttempt,
    QuizQuestion,
    Resource,
    Submission,
    SubmissionAttachment,
    SubmissionComment,
    SubmissionDetail,
    TeachingEventLink,
    User,
)
from app.pacewise_contracts import course_actor, sync_quiz_assignment, sync_quiz_submission, visible_module_item
from app.telemetry import record_change

router = APIRouter(prefix="/api")
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_UPLOADS = {".pdf", ".doc", ".docx", ".pptx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".zip"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class CourseRequest(BaseModel):
    user_id: int
    code: str
    name: str
    term: str
    color: str = "#0374b5"
    published: bool = True


class EnrollmentRequest(BaseModel):
    user_id: int
    member_id: int
    role: str = "student"


class AssignmentRequest(BaseModel):
    user_id: int
    title: str
    description: str = ""
    due_at: LMSDateTime
    points_possible: float = Field(default=10, ge=0, allow_inf_nan=False)
    submission_types: list[str] = ["online_text_entry"]
    published: bool = True


class CourseActivityRequest(BaseModel):
    user_id: int
    activity_type: Literal[
        "class_session",
        "lecture_video",
        "quiz",
        "assignment",
        "midterm",
        "final_exam",
    ]
    title: str
    description: str = ""
    starts_at: LMSDateTime
    ends_at: LMSDateTime | None = None
    repeat_count: int = 1
    source_url: str = ""
    points_possible: float = Field(default=10, ge=0, allow_inf_nan=False)


class SubmissionRequest(BaseModel):
    user_id: int
    text_entry: str = ""
    website_url: str = ""
    demo_submission_offset_minutes: int | None = Field(
        default=None,
        ge=-10_080,
        le=10_080,
        description="Simulator-only offset from the effective deadline; negative is early.",
    )


class GradeRequest(BaseModel):
    user_id: int
    score: float = Field(ge=0, allow_inf_nan=False)
    comment: str = ""
    rubric: dict[str, float] = {}


class ResourceRequest(BaseModel):
    user_id: int
    title: str
    kind: str = "file"
    source_url: str


class ModuleRequest(BaseModel):
    user_id: int
    name: str
    position: int = 1
    published: bool = True


class ModuleItemRequest(BaseModel):
    user_id: int
    title: str
    item_type: str = "resource"
    content_id: int | None = None
    external_url: str = ""
    position: int = 1
    published: bool = True


class DiscussionReplyRequest(BaseModel):
    user_id: int
    body: str
    parent_id: int | None = None


class QuizQuestionRequest(BaseModel):
    user_id: int
    prompt: str
    options: list[str]
    correct_answer: str
    points: float = Field(default=1, ge=0, allow_inf_nan=False)
    position: int = 1


class QuizAttemptRequest(BaseModel):
    user_id: int
    answers: dict[str, str]


class OutcomeAlignmentRequest(BaseModel):
    user_id: int
    assignment_id: int


class ConversationStateRequest(BaseModel):
    user_id: int
    unread: bool | None = None
    archived: bool | None = None


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


def require_enrollment(db: Session, user_id: int, course_id: int, role: str | None = None) -> Enrollment:
    enrollment = course_actor(db, course_id, user_id)
    if not enrollment or (role and enrollment.role != role):
        raise HTTPException(status_code=403, detail=f"{role or 'Course'} enrollment required")
    return enrollment


def assignment_json(db: Session, assignment: Assignment, student_id: int | None = None) -> dict:
    submission = None
    detail = None
    if student_id:
        submission = db.scalar(
            select(Submission).where(
                Submission.assignment_id == assignment.id,
                Submission.user_id == student_id,
            )
        )
        if submission:
            detail = db.scalar(select(SubmissionDetail).where(SubmissionDetail.submission_id == submission.id))
    return {
        "id": assignment.id,
        "course_id": assignment.course_id,
        "title": assignment.title,
        "description": assignment.description,
        "due_at": assignment.due_at.isoformat(),
        "points_possible": assignment.points_possible,
        "submission_types": assignment.submission_types.split(","),
        "published": assignment.published,
        "submission": submission_json(submission, detail) if submission else None,
        **assignment_extension_payload(db, assignment, student_id),
    }


def submission_json(submission: Submission, detail: SubmissionDetail | None) -> dict:
    return {
        "id": submission.id,
        "user_id": submission.user_id,
        "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
        "workflow_state": submission.workflow_state,
        "score": submission.score,
        "late": submission.late,
        "text_entry": detail.text_entry if detail else "",
        "website_url": detail.website_url if detail else "",
        "file_name": detail.file_name if detail else "",
        "file_url": detail.file_url if detail else "",
        "instructor_comment": detail.instructor_comment if detail else "",
        "rubric": json.loads(detail.rubric_json or "{}") if detail else {},
    }


def ensure_submission(db: Session, assignment: Assignment, user_id: int) -> tuple[Submission, SubmissionDetail]:
    require_enrollment(db, user_id, assignment.course_id, "student")
    if not assignment.published:
        raise HTTPException(403, "Assignment is not published")
    submission = db.scalar(
        select(Submission).where(
            Submission.assignment_id == assignment.id,
            Submission.user_id == user_id,
        )
    )
    if not submission:
        submission = Submission(assignment_id=assignment.id, user_id=user_id)
        db.add(submission)
        db.flush()
    detail = db.scalar(select(SubmissionDetail).where(SubmissionDetail.submission_id == submission.id))
    if not detail:
        detail = SubmissionDetail(submission_id=submission.id)
        db.add(detail)
    return submission, detail


def mark_submitted(
    db: Session,
    assignment: Assignment,
    submission: Submission,
    demo_submission_offset_minutes: int | None = None,
) -> None:
    if demo_submission_offset_minutes is not None:
        if os.getenv("ALLOW_DEMO_SUBMISSION_TIMING", "false").lower() != "true":
            raise HTTPException(422, "Simulated submission time is disabled outside explicit demo mode")
        if abs(demo_submission_offset_minutes) > 10_080:
            raise HTTPException(422, "Demo submission offset is outside the supported range")
    access_time = datetime.now(UTC)
    due_at, unlock_at, lock_at, _ = effective_assignment_window(
        db, assignment, submission.user_id
    )
    due_at = as_utc(due_at)
    unlock_at = as_utc(unlock_at) if unlock_at else None
    lock_at = as_utc(lock_at) if lock_at else None
    if unlock_at and access_time < unlock_at:
        raise HTTPException(status_code=409, detail="Assignment is not available yet")
    if lock_at and access_time > lock_at:
        raise HTTPException(status_code=409, detail="Assignment is locked")
    submitted_at = (
        due_at + timedelta(minutes=demo_submission_offset_minutes)
        if demo_submission_offset_minutes is not None
        else access_time
    )
    submission.submitted_at = submitted_at
    submission.workflow_state = "submitted"
    submission.late = submitted_at > due_at


@router.post("/courses")
def create_course(payload: CourseRequest, db: Session = Depends(get_db)) -> dict:
    user = get_user(db, payload.user_id)
    if user.role != "instructor":
        raise HTTPException(status_code=403, detail="Only instructors can create courses")
    if db.scalar(select(Course).where(Course.code == payload.code.strip())):
        raise HTTPException(status_code=409, detail="Course code already exists")
    course = Course(
        code=payload.code.strip(),
        name=payload.name.strip(),
        term=payload.term.strip(),
        color=payload.color,
        published=payload.published,
    )
    db.add(course)
    db.flush()
    db.add(Enrollment(user_id=user.id, course_id=course.id, role="instructor", progress=100))
    record_change(
        db,
        actor_user_id=user.id,
        action="course.created",
        entity_type="course",
        entity_id=course.id,
        course_id=course.id,
        metadata={"code": course.code, "name": course.name},
    )
    db.commit()
    return {"id": course.id, "code": course.code, "name": course.name}


@router.put("/courses/{course_id}/settings")
def update_course(course_id: int, payload: CourseRequest, db: Session = Depends(get_db)) -> dict:
    course = get_course(db, course_id)
    require_enrollment(db, payload.user_id, course_id, "instructor")
    duplicate = db.scalar(select(Course).where(Course.code == payload.code.strip(), Course.id != course_id))
    if duplicate:
        raise HTTPException(status_code=409, detail="Course code already exists")
    course.code, course.name, course.term = payload.code.strip(), payload.name.strip(), payload.term.strip()
    course.color, course.published = payload.color, payload.published
    record_change(
        db,
        actor_user_id=payload.user_id,
        action="course.updated",
        entity_type="course",
        entity_id=course.id,
        course_id=course.id,
        metadata={"code": course.code, "name": course.name, "published": course.published},
    )
    db.commit()
    return {"status": "updated", "id": course.id}


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    course = get_course(db, course_id)
    require_enrollment(db, user_id, course_id, "instructor")
    stored_urls = [
        resource.source_url
        for resource in db.scalars(select(Resource).where(Resource.course_id == course_id)).all()
        if resource.source_url.startswith("/api/files/")
    ]
    stored_urls.extend(
        detail.file_url
        for detail in db.scalars(
            select(SubmissionDetail)
            .join(Submission, Submission.id == SubmissionDetail.submission_id)
            .join(Assignment, Assignment.id == Submission.assignment_id)
            .where(Assignment.course_id == course_id)
        ).all()
        if detail.file_url.startswith("/api/files/")
    )
    record_change(
        db,
        actor_user_id=user_id,
        action="course.deleted",
        entity_type="course",
        entity_id=course_id,
        metadata={"code": course.code, "name": course.name},
    )
    db.flush()
    db.execute(delete(Course).where(Course.id == course_id))
    db.commit()
    for url in stored_urls:
        (UPLOAD_DIR / url.rsplit("/", 1)[-1]).unlink(missing_ok=True)
    return {"status": "deleted", "id": course_id}


@router.post("/courses/{course_id}/enrollments")
def add_enrollment(course_id: int, payload: EnrollmentRequest, db: Session = Depends(get_db)) -> dict:
    require_enrollment(db, payload.user_id, course_id, "instructor")
    get_user(db, payload.member_id)
    if payload.role not in {"student", "instructor"}:
        raise HTTPException(status_code=422, detail="Unsupported enrollment role")
    existing = db.scalar(
        select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.user_id == payload.member_id)
    )
    if existing:
        existing.role = payload.role
    else:
        enrollment = Enrollment(course_id=course_id, user_id=payload.member_id, role=payload.role, progress=0)
        db.add(enrollment)
    db.flush()
    existing_event_keys = {
        (item.title, as_utc(item.starts_at), item.event_kind)
        for item in db.scalars(
            select(CalendarEvent).where(
                CalendarEvent.course_id == course_id,
                CalendarEvent.user_id == payload.member_id,
            )
        ).all()
    }
    templates = db.scalars(
        select(CalendarEvent).where(
            CalendarEvent.course_id == course_id,
            CalendarEvent.user_id == payload.user_id,
        )
    ).all()
    for template in templates:
        if not template.description.startswith(("pacewise-2026-v1;", "course-activity-v1;")):
            continue
        key = (template.title, as_utc(template.starts_at), template.event_kind)
        if key in existing_event_keys:
            continue
        copied_event = CalendarEvent(
            user_id=payload.member_id,
            course_id=course_id,
            title=template.title,
            description=template.description,
            starts_at=template.starts_at,
            ends_at=template.ends_at,
            event_kind=template.event_kind,
            attendance_status=(
                "scheduled" if template.event_kind == "class_session" else None
            ),
        )
        db.add(copied_event)
        db.flush()
        if copied_event.event_kind == "class_session":
            copied_event.join_url = f"/api/calendar/events/{copied_event.id}/join"
        existing_event_keys.add(key)
    record_change(
        db,
        actor_user_id=payload.user_id,
        action="enrollment.updated",
        entity_type="enrollment",
        entity_id=f"{course_id}:{payload.member_id}",
        course_id=course_id,
        metadata={"member_id": payload.member_id, "role": payload.role},
    )
    db.commit()
    return {"status": "enrolled"}


@router.delete("/courses/{course_id}/enrollments/{member_id}")
def remove_enrollment(course_id: int, member_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    require_enrollment(db, user_id, course_id, "instructor")
    enrollment = db.scalar(select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.user_id == member_id))
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    if member_id == user_id:
        raise HTTPException(status_code=422, detail="You cannot remove your own teacher enrollment")
    record_change(
        db,
        actor_user_id=user_id,
        action="enrollment.deleted",
        entity_type="enrollment",
        entity_id=enrollment.id,
        course_id=course_id,
        metadata={"member_id": member_id, "role": enrollment.role},
    )
    db.delete(enrollment)
    db.commit()
    return {"status": "deleted"}


@router.post("/courses/{course_id}/activities")
def create_course_activity(
    course_id: int,
    payload: CourseActivityRequest,
    db: Session = Depends(get_db),
) -> dict:
    course = get_course(db, course_id)
    require_enrollment(db, payload.user_id, course_id, "instructor")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title is required")
    if payload.repeat_count < 1 or payload.repeat_count > 52:
        raise HTTPException(status_code=422, detail="Repeat count must be between 1 and 52")
    if payload.activity_type != "class_session" and payload.repeat_count != 1:
        raise HTTPException(status_code=422, detail="Only online classes can repeat weekly")

    starts_at = as_utc(payload.starts_at)
    ends_at = as_utc(payload.ends_at) if payload.ends_at else None
    if payload.activity_type != "assignment" and (ends_at is None or ends_at <= starts_at):
        raise HTTPException(status_code=422, detail="End time must be after start time")

    if payload.activity_type == "assignment":
        assignment = Assignment(
            course_id=course_id,
            title=title,
            description=payload.description.strip(),
            due_at=starts_at,
            points_possible=payload.points_possible,
            submission_types="online_text_entry",
            published=True,
        )
        db.add(assignment)
        db.flush()
        entity_type, entity_id = "assignment", assignment.id
        created_events = 0
    else:
        entity_type = payload.activity_type
        entity_id: int | None = None
        if payload.activity_type == "lecture_video":
            resource = Resource(
                course_id=course_id,
                title=title,
                kind="video",
                source_url=(
                    payload.source_url.strip()
                    or f"/mock-videos/{course.code.lower()}-{uuid4().hex[:12]}.mp4"
                ),
            )
            db.add(resource)
            db.flush()
            entity_id = resource.id
        elif payload.activity_type in {"quiz", "midterm", "final_exam"}:
            content = CourseContent(
                course_id=course_id,
                kind="quiz",
                title=title,
                body=payload.description.strip(),
                due_at=ends_at,
                points_possible=payload.points_possible,
                published=True,
            )
            db.add(content)
            db.flush()
            sync_quiz_assignment(db, content, payload.user_id)
            entity_id = content.id

        enrollments = db.scalars(
            select(Enrollment).where(Enrollment.course_id == course_id)
        ).all()
        created_events = 0
        for occurrence in range(payload.repeat_count):
            occurrence_key = str(uuid4())
            occurrence_start = starts_at + timedelta(days=7 * occurrence)
            occurrence_end = ends_at + timedelta(days=7 * occurrence) if ends_at else None
            for enrollment in enrollments:
                calendar_event = CalendarEvent(
                    user_id=enrollment.user_id,
                    course_id=course_id,
                    title=f"[{course.code}] {title}",
                    description=f"course-activity-v1; {payload.description.strip()}",
                    starts_at=occurrence_start,
                    ends_at=occurrence_end,
                    event_kind=payload.activity_type,
                    attendance_status=(
                        "scheduled" if payload.activity_type == "class_session" else None
                    ),
                )
                db.add(calendar_event)
                db.flush()
                if payload.activity_type == "class_session":
                    db.add(TeachingEventLink(calendar_event_id=calendar_event.id, occurrence_key=occurrence_key))
                if payload.activity_type == "class_session":
                    calendar_event.join_url = (
                        f"/api/calendar/events/{calendar_event.id}/join"
                    )
                created_events += 1

    record_change(
        db,
        actor_user_id=payload.user_id,
        action="course.activity.created",
        entity_type=entity_type,
        entity_id=entity_id,
        course_id=course_id,
        metadata={
            "activity_type": payload.activity_type,
            "title": title,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "repeat_count": payload.repeat_count,
            "calendar_events_created": created_events,
        },
    )
    db.commit()
    return {
        "status": "created",
        "activity_type": payload.activity_type,
        "entity_id": entity_id,
        "calendar_events_created": created_events,
    }


@router.post("/courses/{course_id}/assignments")
def create_assignment(course_id: int, payload: AssignmentRequest, db: Session = Depends(get_db)) -> dict:
    get_course(db, course_id)
    require_enrollment(db, payload.user_id, course_id, "instructor")
    assignment = Assignment(
        course_id=course_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        due_at=payload.due_at,
        points_possible=payload.points_possible,
        submission_types=",".join(payload.submission_types),
        published=payload.published,
    )
    if not assignment.title:
        raise HTTPException(status_code=422, detail="Title is required")
    db.add(assignment)
    db.flush()
    record_change(
        db,
        actor_user_id=payload.user_id,
        action="assignment.created",
        entity_type="assignment",
        entity_id=assignment.id,
        course_id=course_id,
        metadata={"title": assignment.title, "due_at": assignment.due_at},
    )
    db.commit()
    db.refresh(assignment)
    return assignment_json(db, assignment)


@router.put("/courses/{course_id}/assignments/{assignment_id}")
def update_assignment(
    course_id: int, assignment_id: int, payload: AssignmentRequest, db: Session = Depends(get_db)
) -> dict:
    require_enrollment(db, payload.user_id, course_id, "instructor")
    assignment = db.get(Assignment, assignment_id)
    if not assignment or assignment.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment not found")
    assignment.title, assignment.description = payload.title.strip(), payload.description.strip()
    assignment.due_at, assignment.points_possible = payload.due_at, payload.points_possible
    assignment.submission_types, assignment.published = ",".join(payload.submission_types), payload.published
    record_change(
        db,
        actor_user_id=payload.user_id,
        action="assignment.updated",
        entity_type="assignment",
        entity_id=assignment.id,
        course_id=course_id,
        metadata={"title": assignment.title, "due_at": assignment.due_at},
    )
    db.commit()
    return assignment_json(db, assignment)


@router.delete("/courses/{course_id}/assignments/{assignment_id}")
def delete_assignment(
    course_id: int, assignment_id: int, user_id: int = Query(...), db: Session = Depends(get_db)
) -> dict:
    require_enrollment(db, user_id, course_id, "instructor")
    assignment = db.get(Assignment, assignment_id)
    if not assignment or assignment.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment not found")
    record_change(
        db,
        actor_user_id=user_id,
        action="assignment.deleted",
        entity_type="assignment",
        entity_id=assignment.id,
        course_id=course_id,
        metadata={"title": assignment.title},
    )
    db.delete(assignment)
    db.commit()
    return {"status": "deleted"}


@router.post("/assignments/{assignment_id}/submissions")
def submit_assignment_content(assignment_id: int, payload: SubmissionRequest, db: Session = Depends(get_db)) -> dict:
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if not payload.text_entry.strip() and not payload.website_url.strip():
        raise HTTPException(status_code=422, detail="Enter text or a website URL")
    submission, detail = ensure_submission(db, assignment, payload.user_id)
    detail.text_entry, detail.website_url = payload.text_entry.strip(), payload.website_url.strip()
    mark_submitted(
        db,
        assignment,
        submission,
        payload.demo_submission_offset_minutes,
    )
    record_submission_attempt(
        db,
        submission,
        text_entry=detail.text_entry,
        website_url=detail.website_url,
    )
    record_change(
        db,
        actor_user_id=payload.user_id,
        action="submission.submitted",
        entity_type="submission",
        entity_id=submission.id,
        course_id=assignment.course_id,
        metadata={
            "assignment_id": assignment.id,
            "late": submission.late,
            "type": "text_or_url",
            "demo_submission_offset_minutes": payload.demo_submission_offset_minutes,
        },
    )
    db.commit()
    return submission_json(submission, detail)


def save_upload(upload: UploadFile, prefix: str) -> tuple[str, str]:
    suffix = Path(upload.filename or "file").suffix.lower()
    if suffix not in ALLOWED_UPLOADS:
        raise HTTPException(status_code=422, detail="Unsupported file type")
    safe_name = f"{prefix}-{uuid4().hex}{suffix}"
    target = UPLOAD_DIR / safe_name
    try:
        size = 0
        with target.open("wb") as output:
            while chunk := upload.file.read(64 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File exceeds 20 MB")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return upload.filename or safe_name, f"/api/files/{safe_name}"


@router.get("/files/{file_name}")
def download_file(file_name: str, user_id: int = Query(...), db: Session = Depends(get_db)) -> FileResponse:
    if Path(file_name).name != file_name:
        raise HTTPException(status_code=404, detail="File not found")
    file_url = f"/api/files/{file_name}"
    resource = db.scalar(select(Resource).where(Resource.source_url == file_url))
    original_name = resource.title if resource else file_name
    if resource:
        if not can_access_resource(db, resource, user_id):
            raise HTTPException(status_code=403, detail="You cannot access this resource")
    else:
        row = db.execute(
            select(SubmissionDetail, Submission, Assignment)
            .join(Submission, Submission.id == SubmissionDetail.submission_id)
            .join(Assignment, Assignment.id == Submission.assignment_id)
            .where(SubmissionDetail.file_url == file_url)
        ).first()
        if row:
            detail, submission, assignment = row
            enrollment = require_enrollment(db, user_id, assignment.course_id)
            if enrollment.role != "instructor" and submission.user_id != user_id:
                raise HTTPException(status_code=403, detail="You cannot access this submission")
            original_name = detail.file_name
        else:
            attachment_row = db.execute(
                select(MessageAttachment, ConversationMessage)
                .join(ConversationMessage, ConversationMessage.id == MessageAttachment.message_id)
                .where(MessageAttachment.file_url == file_url)
            ).first()
            if not attachment_row:
                raise HTTPException(status_code=404, detail="File not found")
            attachment, message = attachment_row
            participant = db.scalar(
                select(ConversationParticipant).where(
                    ConversationParticipant.conversation_id == message.conversation_id,
                    ConversationParticipant.user_id == user_id,
                )
            )
            if not participant:
                raise HTTPException(status_code=403, detail="You cannot access this attachment")
            original_name = attachment.file_name
    target = UPLOAD_DIR / file_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target, filename=original_name)


@router.post("/assignments/{assignment_id}/submissions/file")
def submit_assignment_file(
    assignment_id: int,
    user_id: int = Form(...),
    demo_submission_offset_minutes: int | None = Form(None),
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    submission, detail = ensure_submission(db, assignment, user_id)
    detail.file_name, detail.file_url = save_upload(upload, f"submission-{assignment_id}-{user_id}")
    mark_submitted(db, assignment, submission, demo_submission_offset_minutes)
    record_submission_attempt(
        db,
        submission,
        file_name=detail.file_name,
        file_url=detail.file_url,
    )
    record_change(
        db,
        actor_user_id=user_id,
        action="submission.submitted",
        entity_type="submission",
        entity_id=submission.id,
        course_id=assignment.course_id,
        metadata={
            "assignment_id": assignment.id,
            "late": submission.late,
            "type": "file",
            "demo_submission_offset_minutes": demo_submission_offset_minutes,
        },
    )
    db.commit()
    return submission_json(submission, detail)


@router.post("/assignments/{assignment_id}/submissions/files")
def submit_assignment_files(
    assignment_id: int,
    user_id: int = Form(...),
    demo_submission_offset_minutes: int | None = Form(None),
    uploads: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> dict:
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if not uploads or len(uploads) > 10:
        raise HTTPException(status_code=422, detail="Upload between 1 and 10 files")
    unsupported = [
        upload.filename or "file"
        for upload in uploads
        if Path(upload.filename or "file").suffix.lower() not in ALLOWED_UPLOADS
    ]
    if unsupported:
        raise HTTPException(status_code=422, detail=f"Unsupported file type: {unsupported[0]}")
    submission, detail = ensure_submission(db, assignment, user_id)
    saved_files = [
        save_upload(upload, f"submission-{assignment_id}-{user_id}") for upload in uploads
    ]
    detail.file_name, detail.file_url = saved_files[0]
    mark_submitted(db, assignment, submission, demo_submission_offset_minutes)
    attempt = record_submission_attempt(db, submission)
    db.add_all(
        [
            SubmissionAttachment(attempt_id=attempt.id, file_name=name, file_url=url)
            for name, url in saved_files
        ]
    )
    record_change(
        db,
        actor_user_id=user_id,
        action="submission.submitted",
        entity_type="submission",
        entity_id=submission.id,
        course_id=assignment.course_id,
        metadata={
            "assignment_id": assignment.id,
            "late": submission.late,
            "type": "files",
            "file_count": len(saved_files),
            "demo_submission_offset_minutes": demo_submission_offset_minutes,
        },
    )
    db.commit()
    result = submission_json(submission, detail)
    result["files"] = [{"file_name": name, "file_url": url} for name, url in saved_files]
    return result


@router.get("/assignments/{assignment_id}/submissions")
def assignment_submissions(assignment_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> list[dict]:
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    require_enrollment(db, user_id, assignment.course_id, "instructor")
    rows = db.execute(
        select(Submission, User)
        .join(User, User.id == Submission.user_id)
        .where(Submission.assignment_id == assignment_id)
    ).all()
    result = []
    for submission, student in rows:
        detail = db.scalar(select(SubmissionDetail).where(SubmissionDetail.submission_id == submission.id))
        result.append(
            {**submission_json(submission, detail), "student_name": student.full_name, "student_email": student.email}
        )
    return result


@router.put("/assignments/{assignment_id}/submissions/{student_id}/grade")
def grade_submission(assignment_id: int, student_id: int, payload: GradeRequest, db: Session = Depends(get_db)) -> dict:
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    require_enrollment(db, payload.user_id, assignment.course_id, "instructor")
    require_enrollment(db, student_id, assignment.course_id, "student")
    submission = db.scalar(
        select(Submission).where(Submission.assignment_id == assignment_id, Submission.user_id == student_id)
    )
    if not submission:
        submission = Submission(assignment_id=assignment_id, user_id=student_id, workflow_state="unsubmitted")
        db.add(submission)
        db.flush()
    detail = db.scalar(select(SubmissionDetail).where(SubmissionDetail.submission_id == submission.id))
    if not detail:
        detail = SubmissionDetail(submission_id=submission.id)
        db.add(detail)
    if payload.score < 0 or payload.score > assignment.points_possible:
        raise HTTPException(status_code=422, detail="Score is outside the assignment range")
    submission.score = payload.score
    detail.instructor_comment = payload.comment.strip()
    detail.rubric_json = json.dumps(payload.rubric)
    if detail.instructor_comment:
        db.add(
            SubmissionComment(
                submission_id=submission.id,
                author_id=payload.user_id,
                body=detail.instructor_comment,
            )
        )
    db.add(
        GradeHistory(
            submission_id=submission.id,
            assignment_id=assignment.id,
            user_id=student_id,
            grader_id=payload.user_id,
            score=payload.score,
            comment=payload.comment.strip(),
            rubric_json=json.dumps(payload.rubric),
        )
    )
    alignments = db.scalars(
        select(OutcomeAlignment).where(OutcomeAlignment.assignment_id == assignment.id)
    ).all()
    competencies = [f"outcome:{item.outcome_id}" for item in alignments] or [
        f"course:{assignment.course_id}:assignment-performance"
    ]
    for competency in competencies:
        db.add(
            LearningEvidence(
                user_id=student_id,
                course_id=assignment.course_id,
                evidence_type="graded_assignment",
                source_type="submission",
                source_id=str(submission.id),
                competency_key=competency,
                score=payload.score,
                max_score=assignment.points_possible,
                details_json=json.dumps({"rubric": payload.rubric, "comment": payload.comment}),
            )
        )
    record_change(
        db,
        actor_user_id=payload.user_id,
        action="grade.updated",
        entity_type="submission",
        entity_id=submission.id,
        course_id=assignment.course_id,
        metadata={"assignment_id": assignment.id, "student_id": student_id, "score": payload.score},
    )
    db.commit()
    return submission_json(submission, detail)


def resource_json(resource: Resource, db: Session | None = None) -> dict:
    result = {
        "id": resource.id,
        "course_id": resource.course_id,
        "title": resource.title,
        "kind": resource.kind,
        "source_url": resource.source_url,
    }
    if db is not None:
        result.update(resource_extension_payload(db, resource))
    return result


@router.post("/courses/{course_id}/resources")
def create_resource(course_id: int, payload: ResourceRequest, db: Session = Depends(get_db)) -> dict:
    require_enrollment(db, payload.user_id, course_id, "instructor")
    resource = Resource(
        course_id=course_id, title=payload.title.strip(), kind=payload.kind, source_url=payload.source_url.strip()
    )
    db.add(resource)
    db.flush()
    record_resource_version(db, resource)
    record_change(db, actor_user_id=payload.user_id, action="resource.created", entity_type="resource", entity_id=resource.id, course_id=course_id)
    db.commit()
    return resource_json(resource, db)


@router.post("/courses/{course_id}/resources/upload")
def upload_resource(
    course_id: int, user_id: int = Form(...), upload: UploadFile = File(...), db: Session = Depends(get_db)
) -> dict:
    require_enrollment(db, user_id, course_id, "instructor")
    original, url = save_upload(upload, f"course-{course_id}")
    resource = Resource(course_id=course_id, title=original, kind="file", source_url=url)
    db.add(resource)
    db.flush()
    target = UPLOAD_DIR / url.rsplit("/", 1)[-1]
    record_resource_version(
        db,
        resource,
        checksum=hashlib.sha256(target.read_bytes()).hexdigest(),
        size_bytes=target.stat().st_size,
        content_type=upload.content_type or "application/octet-stream",
    )
    record_change(db, actor_user_id=user_id, action="resource.created", entity_type="resource", entity_id=resource.id, course_id=course_id)
    db.commit()
    return resource_json(resource, db)


@router.put("/courses/{course_id}/resources/{resource_id}/upload")
def replace_resource_file(
    course_id: int, resource_id: int, user_id: int = Form(...),
    upload: UploadFile = File(...), db: Session = Depends(get_db),
) -> dict:
    require_enrollment(db, user_id, course_id, "instructor")
    resource = db.get(Resource, resource_id)
    if not resource or resource.course_id != course_id:
        raise HTTPException(status_code=404, detail="File not found")
    original, url = save_upload(upload, f"course-{course_id}")
    target = UPLOAD_DIR / url.rsplit("/", 1)[-1]
    resource.title, resource.kind, resource.source_url = original, "file", url
    record_resource_version(db, resource, checksum=hashlib.sha256(target.read_bytes()).hexdigest(),
                            size_bytes=target.stat().st_size, content_type=upload.content_type or "application/octet-stream")
    record_change(db, actor_user_id=user_id, action="resource.updated", entity_type="resource", entity_id=resource.id, course_id=course_id)
    db.commit()
    return resource_json(resource, db)


@router.put("/courses/{course_id}/resources/{resource_id}")
def update_resource(course_id: int, resource_id: int, payload: ResourceRequest, db: Session = Depends(get_db)) -> dict:
    require_enrollment(db, payload.user_id, course_id, "instructor")
    resource = db.get(Resource, resource_id)
    if not resource or resource.course_id != course_id:
        raise HTTPException(status_code=404, detail="File not found")
    resource.title, resource.kind, resource.source_url = payload.title.strip(), payload.kind, payload.source_url.strip()
    if resource.source_url.startswith("/api/files/"):
        name = resource.source_url.removeprefix("/api/files/")
        path = (UPLOAD_DIR / name).resolve()
        if Path(name).name != name or path.parent != UPLOAD_DIR.resolve() or not path.is_file():
            raise HTTPException(status_code=422, detail="Invalid LMS-owned file")
        record_resource_version(db, resource, checksum=hashlib.sha256(path.read_bytes()).hexdigest(), size_bytes=path.stat().st_size)
    else:
        record_resource_version(db, resource)
    record_change(db, actor_user_id=payload.user_id, action="resource.updated", entity_type="resource", entity_id=resource.id, course_id=course_id)
    db.commit()
    return resource_json(resource, db)


@router.delete("/courses/{course_id}/resources/{resource_id}")
def delete_resource(course_id: int, resource_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    require_enrollment(db, user_id, course_id, "instructor")
    resource = db.get(Resource, resource_id)
    if not resource or resource.course_id != course_id:
        raise HTTPException(status_code=404, detail="File not found")
    stored_path = (
        UPLOAD_DIR / resource.source_url.rsplit("/", 1)[-1] if resource.source_url.startswith("/api/files/") else None
    )
    record_change(db, actor_user_id=user_id, action="resource.deleted", entity_type="resource", entity_id=resource.id, course_id=course_id)
    db.delete(resource)
    db.commit()
    if stored_path:
        stored_path.unlink(missing_ok=True)
    return {"status": "deleted"}


def module_json(db: Session, module: CourseModule, user_id: int | None = None) -> dict:
    items = db.scalars(
        select(ModuleItem).where(ModuleItem.module_id == module.id).order_by(ModuleItem.position, ModuleItem.id)
    ).all()
    return {
        "id": module.id,
        "course_id": module.course_id,
        "name": module.name,
        "position": module.position,
        "published": module.published,
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "item_type": item.item_type,
                "content_id": item.content_id,
                "external_url": item.external_url,
                "position": item.position,
                "published": item.published,
            }
            for item in items
        ],
        **module_extension_payload(db, module, user_id),
    }


@router.get("/courses/{course_id}/modules")
def list_modules(course_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> list[dict]:
    actor = require_enrollment(db, user_id, course_id)
    modules = db.scalars(
        select(CourseModule).where(CourseModule.course_id == course_id).order_by(CourseModule.position, CourseModule.id)
    ).all()
    result = [module_json(db, module, user_id) for module in modules if actor.role == "instructor" or module.published]
    if actor.role != "instructor":
        for module in result:
            module["items"] = [raw for raw in module["items"] if visible_module_item(db, db.get(ModuleItem, raw["id"]), course_id, user_id)]
    return result


@router.post("/courses/{course_id}/modules")
def create_module(course_id: int, payload: ModuleRequest, db: Session = Depends(get_db)) -> dict:
    require_enrollment(db, payload.user_id, course_id, "instructor")
    module = CourseModule(
        course_id=course_id, name=payload.name.strip(), position=payload.position, published=payload.published
    )
    db.add(module)
    db.flush()
    record_change(db, actor_user_id=payload.user_id, action="module.created", entity_type="module", entity_id=module.id, course_id=course_id)
    db.commit()
    db.refresh(module)
    return module_json(db, module)


@router.put("/courses/{course_id}/modules/{module_id}")
def update_module(course_id: int, module_id: int, payload: ModuleRequest, db: Session = Depends(get_db)) -> dict:
    require_enrollment(db, payload.user_id, course_id, "instructor")
    module = db.get(CourseModule, module_id)
    if not module or module.course_id != course_id:
        raise HTTPException(status_code=404, detail="Module not found")
    module.name, module.position, module.published = payload.name.strip(), payload.position, payload.published
    record_change(db, actor_user_id=payload.user_id, action="module.updated", entity_type="module", entity_id=module.id, course_id=course_id)
    db.commit()
    return module_json(db, module)


@router.delete("/courses/{course_id}/modules/{module_id}")
def delete_module(course_id: int, module_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    require_enrollment(db, user_id, course_id, "instructor")
    module = db.get(CourseModule, module_id)
    if not module or module.course_id != course_id:
        raise HTTPException(status_code=404, detail="Module not found")
    record_change(db, actor_user_id=user_id, action="module.deleted", entity_type="module", entity_id=module.id, course_id=course_id)
    db.delete(module)
    db.commit()
    return {"status": "deleted"}


@router.post("/courses/{course_id}/modules/{module_id}/items")
def create_module_item(
    course_id: int, module_id: int, payload: ModuleItemRequest, db: Session = Depends(get_db)
) -> dict:
    require_enrollment(db, payload.user_id, course_id, "instructor")
    module = db.get(CourseModule, module_id)
    if not module or module.course_id != course_id:
        raise HTTPException(status_code=404, detail="Module not found")
    kind = payload.item_type.lower()
    if not payload.title.strip() or kind not in {"assignment", "quiz", "page", "discussion", "resource", "file", "external_url", "subheader"}:
        raise HTTPException(422, "Valid title and module item type are required")
    if kind not in {"external_url", "subheader"}:
        model = Resource if kind in {"resource", "file"} else Assignment if kind == "assignment" else CourseContent
        target = db.get(model, payload.content_id) if payload.content_id is not None else None
        if not target or target.course_id != course_id or (model is CourseContent and target.kind != kind):
            raise HTTPException(422, "Module item must reference matching content in this course")
    elif kind == "external_url" and not payload.external_url.startswith(("https://", "http://")):
        raise HTTPException(422, "External module URL must use http or https")
    item = ModuleItem(
        module_id=module_id,
        title=payload.title.strip(),
        item_type=kind,
        content_id=payload.content_id,
        external_url=payload.external_url,
        position=payload.position,
        published=payload.published,
    )
    db.add(item)
    db.flush()
    record_change(db, actor_user_id=payload.user_id, action="module_item.created", entity_type="module_item", entity_id=item.id, course_id=course_id)
    db.commit()
    return module_json(db, module)


@router.delete("/courses/{course_id}/modules/{module_id}/items/{item_id}")
def delete_module_item(
    course_id: int, module_id: int, item_id: int, user_id: int = Query(...), db: Session = Depends(get_db)
) -> dict:
    require_enrollment(db, user_id, course_id, "instructor")
    module = db.get(CourseModule, module_id)
    if not module or module.course_id != course_id:
        raise HTTPException(404, "Module not found")
    item = db.get(ModuleItem, item_id)
    if not item or item.module_id != module_id:
        raise HTTPException(status_code=404, detail="Module item not found")
    record_change(db, actor_user_id=user_id, action="module_item.deleted", entity_type="module_item", entity_id=item.id, course_id=course_id)
    db.delete(item)
    db.commit()
    return {"status": "deleted"}


@router.get("/discussions/{discussion_id}/replies")
def discussion_replies(discussion_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> list[dict]:
    discussion = db.get(CourseContent, discussion_id)
    if not discussion or discussion.kind != "discussion":
        raise HTTPException(status_code=404, detail="Discussion not found")
    require_enrollment(db, user_id, discussion.course_id)
    rows = db.execute(
        select(DiscussionReply, User)
        .join(User, User.id == DiscussionReply.user_id)
        .where(DiscussionReply.discussion_id == discussion_id)
        .order_by(DiscussionReply.created_at)
    ).all()
    return [
        {
            "id": reply.id,
            "body": reply.body,
            "parent_id": reply.parent_id,
            "created_at": reply.created_at.isoformat(),
            "author": {"id": author.id, "name": author.full_name},
            "likes": db.scalar(select(func.count(DiscussionLike.id)).where(DiscussionLike.reply_id == reply.id)) or 0,
        }
        for reply, author in rows
    ]


@router.post("/discussions/{discussion_id}/replies")
def create_discussion_reply(discussion_id: int, payload: DiscussionReplyRequest, db: Session = Depends(get_db)) -> dict:
    discussion = db.get(CourseContent, discussion_id)
    if not discussion or discussion.kind != "discussion":
        raise HTTPException(status_code=404, detail="Discussion not found")
    require_enrollment(db, payload.user_id, discussion.course_id)
    reply = DiscussionReply(
        discussion_id=discussion_id, user_id=payload.user_id, parent_id=payload.parent_id, body=payload.body.strip()
    )
    if not reply.body:
        raise HTTPException(status_code=422, detail="Reply cannot be empty")
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return {"id": reply.id, "status": "created"}


@router.post("/discussions/replies/{reply_id}/like")
def toggle_discussion_like(reply_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    reply = db.get(DiscussionReply, reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    discussion = db.get(CourseContent, reply.discussion_id)
    require_enrollment(db, user_id, discussion.course_id)
    like = db.scalar(
        select(DiscussionLike).where(DiscussionLike.reply_id == reply_id, DiscussionLike.user_id == user_id)
    )
    if like:
        db.delete(like)
        liked = False
    else:
        db.add(DiscussionLike(reply_id=reply_id, user_id=user_id))
        liked = True
    db.commit()
    count = db.scalar(select(func.count(DiscussionLike.id)).where(DiscussionLike.reply_id == reply_id)) or 0
    return {"liked": liked, "likes": count}


def require_quiz(db: Session, quiz_id: int) -> CourseContent:
    quiz = db.get(CourseContent, quiz_id)
    if not quiz or quiz.kind != "quiz":
        raise HTTPException(status_code=404, detail="Quiz not found")
    return quiz


@router.get("/quizzes/{quiz_id}/questions")
def quiz_questions(quiz_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> list[dict]:
    quiz = require_quiz(db, quiz_id)
    enrollment = require_enrollment(db, user_id, quiz.course_id)
    if enrollment.role != "instructor" and not quiz.published:
        raise HTTPException(403, "Quiz is not published")
    questions = db.scalars(
        select(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id).order_by(QuizQuestion.position, QuizQuestion.id)
    ).all()
    return [
        {
            "id": q.id,
            "prompt": q.prompt,
            "options": json.loads(q.options_json),
            "correct_answer": q.correct_answer if enrollment.role == "instructor" else None,
            "points": q.points,
            "position": q.position,
        }
        for q in questions
    ]


@router.post("/quizzes/{quiz_id}/questions")
def create_quiz_question(quiz_id: int, payload: QuizQuestionRequest, db: Session = Depends(get_db)) -> dict:
    quiz = require_quiz(db, quiz_id)
    require_enrollment(db, payload.user_id, quiz.course_id, "instructor")
    if payload.correct_answer not in payload.options:
        raise HTTPException(status_code=422, detail="Correct answer must be one of the options")
    question = QuizQuestion(
        quiz_id=quiz_id,
        prompt=payload.prompt.strip(),
        options_json=json.dumps(payload.options),
        correct_answer=payload.correct_answer,
        points=payload.points,
        position=payload.position,
    )
    db.add(question)
    db.flush()
    sync_quiz_assignment(db, quiz, payload.user_id)
    record_change(db, actor_user_id=payload.user_id, action="quiz.questions.updated", entity_type="quiz", entity_id=quiz_id, course_id=quiz.course_id)
    db.commit()
    db.refresh(question)
    return {"id": question.id, "status": "created"}


@router.delete("/quizzes/{quiz_id}/questions/{question_id}")
def delete_quiz_question(
    quiz_id: int, question_id: int, user_id: int = Query(...), db: Session = Depends(get_db)
) -> dict:
    quiz = require_quiz(db, quiz_id)
    require_enrollment(db, user_id, quiz.course_id, "instructor")
    question = db.get(QuizQuestion, question_id)
    if not question or question.quiz_id != quiz_id:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(question)
    db.flush()
    sync_quiz_assignment(db, quiz, user_id)
    record_change(db, actor_user_id=user_id, action="quiz.questions.updated", entity_type="quiz", entity_id=quiz_id, course_id=quiz.course_id)
    db.commit()
    return {"status": "deleted"}


@router.post("/quizzes/{quiz_id}/attempts")
def submit_quiz(quiz_id: int, payload: QuizAttemptRequest, db: Session = Depends(get_db)) -> dict:
    quiz = require_quiz(db, quiz_id)
    require_enrollment(db, payload.user_id, quiz.course_id, "student")
    if not quiz.published:
        raise HTTPException(status_code=403, detail="Quiz is not published")
    assignment = sync_quiz_assignment(db, quiz, payload.user_id)
    if assignment:
        _, unlock_at, lock_at, _ = effective_assignment_window(db, assignment, payload.user_id)
        now = datetime.now(UTC)
        if unlock_at and now < (unlock_at.replace(tzinfo=UTC) if unlock_at.tzinfo is None else unlock_at):
            raise HTTPException(409, "Quiz is not available yet")
        if lock_at and now > (lock_at.replace(tzinfo=UTC) if lock_at.tzinfo is None else lock_at):
            raise HTTPException(409, "Quiz is locked")
    questions = db.scalars(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id)).all()
    if not questions:
        raise HTTPException(status_code=409, detail="Quiz has no questions")
    unknown = set(payload.answers) - {str(q.id) for q in questions}
    if unknown:
        raise HTTPException(status_code=422, detail="Answers reference an unknown question")
    score = sum(q.points for q in questions if payload.answers.get(str(q.id)) == q.correct_answer)
    attempt = db.scalar(
        select(QuizAttempt).where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.user_id == payload.user_id)
    )
    if not attempt:
        attempt = QuizAttempt(quiz_id=quiz_id, user_id=payload.user_id)
        db.add(attempt)
    attempt.answers_json, attempt.score, attempt.submitted_at = json.dumps(payload.answers), score, datetime.now(UTC)
    sync_quiz_submission(db, quiz, payload.user_id, score, attempt.submitted_at)
    for question in questions:
        correct = payload.answers.get(str(question.id)) == question.correct_answer
        db.add(
            LearningEvidence(
                user_id=payload.user_id,
                course_id=quiz.course_id,
                evidence_type="quiz_response",
                source_type="quiz_question",
                source_id=str(question.id),
                competency_key=f"quiz:{quiz.id}:question:{question.id}",
                score=question.points if correct else 0,
                max_score=question.points,
                details_json=json.dumps({"correct": correct}),
            )
        )
    db.flush()
    record_change(
        db,
        actor_user_id=payload.user_id,
        action="quiz.attempted",
        entity_type="quiz_attempt",
        entity_id=attempt.id,
        course_id=quiz.course_id,
        metadata={"quiz_id": quiz.id, "score": score, "points_possible": sum(q.points for q in questions)},
    )
    db.commit()
    return {
        "score": score,
        "points_possible": sum(q.points for q in questions),
        "submitted_at": attempt.submitted_at.isoformat(),
    }


@router.post("/outcomes/{outcome_id}/alignments")
def align_outcome(outcome_id: int, payload: OutcomeAlignmentRequest, db: Session = Depends(get_db)) -> dict:
    outcome = db.get(CourseContent, outcome_id)
    assignment = db.get(Assignment, payload.assignment_id)
    if not outcome or outcome.kind != "outcome" or not assignment or assignment.course_id != outcome.course_id:
        raise HTTPException(status_code=404, detail="Outcome or assignment not found")
    require_enrollment(db, payload.user_id, outcome.course_id, "instructor")
    existing = db.scalar(
        select(OutcomeAlignment).where(
            OutcomeAlignment.outcome_id == outcome_id, OutcomeAlignment.assignment_id == assignment.id
        )
    )
    if not existing:
        alignment = OutcomeAlignment(outcome_id=outcome_id, assignment_id=assignment.id)
        db.add(alignment)
        db.flush()
        record_change(
            db,
            actor_user_id=payload.user_id,
            action="outcome.aligned",
            entity_type="outcome_alignment",
            entity_id=alignment.id,
            course_id=outcome.course_id,
            metadata={"outcome_id": outcome_id, "assignment_id": assignment.id},
        )
        db.commit()
    return {"status": "aligned"}


@router.get("/courses/{course_id}/mastery")
def course_mastery(course_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> list[dict]:
    require_enrollment(db, user_id, course_id)
    outcomes = db.scalars(
        select(CourseContent).where(CourseContent.course_id == course_id, CourseContent.kind == "outcome")
    ).all()
    result = []
    for outcome in outcomes:
        alignment_rows = db.execute(
            select(OutcomeAlignment, Assignment)
            .join(Assignment, Assignment.id == OutcomeAlignment.assignment_id)
            .where(OutcomeAlignment.outcome_id == outcome.id)
        ).all()
        scores = []
        for _, assignment in alignment_rows:
            submission = db.scalar(
                select(Submission).where(Submission.assignment_id == assignment.id, Submission.user_id == user_id)
            )
            if submission and submission.score is not None and assignment.points_possible:
                scores.append(submission.score / assignment.points_possible * 100)
        result.append(
            {
                "outcome_id": outcome.id,
                "title": outcome.title,
                "mastery": round(sum(scores) / len(scores), 1) if scores else None,
                "aligned_assignments": len(alignment_rows),
            }
        )
    return result


@router.get("/search")
def search(q: str = Query(..., min_length=2), user_id: int = Query(...), db: Session = Depends(get_db)) -> list[dict]:
    course_ids = select(Enrollment.course_id).where(Enrollment.user_id == user_id)
    pattern = f"%{q.strip()}%"
    assignments = db.scalars(
        select(Assignment).where(Assignment.course_id.in_(course_ids), Assignment.title.ilike(pattern))
    ).all()
    contents = db.scalars(
        select(CourseContent).where(CourseContent.course_id.in_(course_ids), CourseContent.title.ilike(pattern))
    ).all()
    return (
        [
            {"type": "assignment", "id": item.id, "course_id": item.course_id, "title": item.title}
            for item in assignments
        ]
        + [{"type": item.kind, "id": item.id, "course_id": item.course_id, "title": item.title} for item in contents]
    )[:30]


@router.put("/inbox/{conversation_id}/state")
def update_conversation_state(
    conversation_id: int,
    payload: ConversationStateRequest,
    db: Session = Depends(get_db),
) -> dict:
    participant = db.scalar(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == payload.user_id,
        )
    )
    if not participant:
        raise HTTPException(status_code=403, detail="You are not part of this conversation")
    state = db.scalar(
        select(ConversationState).where(
            ConversationState.conversation_id == conversation_id,
            ConversationState.user_id == payload.user_id,
        )
    )
    if not state:
        state = ConversationState(conversation_id=conversation_id, user_id=payload.user_id)
        db.add(state)
    if payload.unread is not None:
        state.unread = payload.unread
    if payload.archived is not None:
        state.archived = payload.archived
    db.commit()
    return {"status": "updated", "unread": state.unread, "archived": state.archived}


@router.post("/inbox/{conversation_id}/attachments")
def attach_to_conversation(
    conversation_id: int,
    sender_id: int = Form(...),
    body: str = Form(default=""),
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    participant = db.scalar(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == sender_id,
        )
    )
    if not participant:
        raise HTTPException(status_code=403, detail="You are not part of this conversation")
    original, url = save_upload(upload, f"message-{conversation_id}-{sender_id}")
    message = ConversationMessage(
        conversation_id=conversation_id,
        sender_id=sender_id,
        body=body.strip() or f"Attachment: {original}",
    )
    db.add(message)
    db.flush()
    db.add(MessageAttachment(message_id=message.id, file_name=original, file_url=url))
    states = db.scalars(select(ConversationState).where(ConversationState.conversation_id == conversation_id)).all()
    for state in states:
        state.unread = state.user_id != sender_id
    db.commit()
    return {"status": "sent", "message_id": message.id}
