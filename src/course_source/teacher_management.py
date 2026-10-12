"""PaceWise-owned authoring domain with live enrollment and atomic writes.

Compatibility-shaped routes are used only by the private in-process gateway.
Browser-selected actor IDs are never accepted by the public PaceWise facade.
"""

import base64
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from src.course_source.db import get_db
from src.course_source.integration_api import require_service_key
from src.course_source.learning_api import record_resource_version
from src.course_source.models import (
    Assignment,
    AssignmentConfiguration,
    AssignmentGroup,
    CalendarEvent,
    Course,
    CourseContent,
    CourseModule,
    Enrollment,
    ModuleItem,
    QuizAssignmentLink,
    QuizQuestion,
    Resource,
    Submission,
    TeacherProfile,
    TeacherTaskMetadata,
    TeachingEventLink,
    User,
)
from src.course_source.pacewise_contracts import course_actor, sync_quiz_assignment
from src.course_source.telemetry import record_change

router = APIRouter(prefix="/api/pacewise/v1/teacher", dependencies=[Depends(require_service_key)])


def teacher(db, course_id, user_id):
    db.get(User, user_id, with_for_update=True)
    db.get(Course, course_id, with_for_update=True)
    actor = course_actor(db, course_id, user_id)
    if actor.role != "instructor":
        raise HTTPException(403, "Instructor enrollment required")


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Question(StrictModel):
    prompt: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(min_length=2, max_length=6)
    correct_answer: str = Field(min_length=1, max_length=1000)
    points: float = Field(gt=0, le=10000, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_answer(self):
        if any(not option.strip() or len(option) > 1000 for option in self.options) or len(set(self.options)) != len(
            self.options
        ):
            raise ValueError("Options must be distinct and nonempty")
        if self.correct_answer not in self.options:
            raise ValueError("Answer must belong to options")
        return self


class TaskInput(StrictModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=20000)
    chapter: str = Field(default="", max_length=255)
    kind: Literal["assignment", "quiz", "midterm", "final_exam"] = "assignment"
    due_at: datetime
    points_possible: float = Field(ge=0, le=10000, allow_inf_nan=False)
    published: bool = False
    group_id: int | None = None
    group_name: str = Field(default="", max_length=255)
    resource_ids: list[int] = Field(default_factory=list, max_length=30)
    questions: list[Question] = Field(default_factory=list, max_length=100)
    expected_version: str | None = Field(default=None, max_length=64)

    @field_validator("due_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone is required")
        return utc(value)

    @model_validator(mode="after")
    def quiz_policy(self):
        if self.kind == "quiz" and self.published and not self.questions:
            raise ValueError("Published quizzes need questions")
        if self.kind != "quiz" and self.questions:
            raise ValueError("Only quiz tasks accept questions")
        if self.questions and abs(sum(q.points for q in self.questions) - self.points_possible) > 0.005:
            raise ValueError("Question points must equal the quiz maximum")
        return self


class GroupInput(StrictModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    weight: float = Field(ge=0, le=100, allow_inf_nan=False)


class WeightsInput(StrictModel):
    groups: list[GroupInput] = Field(min_length=1, max_length=20)
    expected_version: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def total(self):
        ids = [row.id for row in self.groups if row.id is not None]
        if abs(sum(row.weight for row in self.groups) - 100) > 0.005 or len(ids) != len(set(ids)):
            raise ValueError("Weights must sum to 100 and IDs must be unique")
        if len({row.name.casefold() for row in self.groups}) != len(self.groups):
            raise ValueError("Group names must be unique")
        return self


class VersionInput(StrictModel):
    expected_version: str = Field(min_length=64, max_length=64)


class LessonInput(StrictModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=5000)
    starts_at: datetime
    ends_at: datetime
    mode: Literal["offline", "online"] = "offline"
    location: str = Field(default="", max_length=255)
    meeting_url: str = Field(default="", max_length=500)
    resource_ids: list[int] = Field(default_factory=list, max_length=30)
    repeat_count: int = Field(default=1, ge=1, le=16)
    expected_version: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def valid_time(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Timezone is required")
        self.starts_at, self.ends_at = utc(self.starts_at), utc(self.ends_at)
        if not 0 < (self.ends_at - self.starts_at).total_seconds() <= 12 * 3600:
            raise ValueError("Session must be between zero and twelve hours")
        if self.mode == "online" and not self.meeting_url.startswith("https://"):
            raise ValueError("Online sessions require an HTTPS meeting URL")
        return self


class ProfileInput(StrictModel):
    title: str = Field(default="", max_length=120)
    department: str = Field(default="", max_length=200)
    office: str = Field(default="", max_length=200)
    office_hours: str = Field(default="", max_length=500)
    bio: str = Field(default="", max_length=2000)
    contact_url: str = Field(default="", max_length=500)
    expected_version: str | None = Field(default=None, max_length=64)

    @field_validator("contact_url")
    @classmethod
    def safe_url(cls, value):
        if value and not value.startswith("https://"):
            raise ValueError("Contact URL must use HTTPS")
        return value


def check_version(expected, actual):
    if not expected or expected != actual:
        raise HTTPException(409, "Dữ liệu đã thay đổi. Hãy làm mới trước khi lưu.")


def check_resources(db, course_id, ids):
    found = set(db.scalars(select(Resource.id).where(Resource.course_id == course_id, Resource.id.in_(ids))).all())
    if found != set(ids):
        raise HTTPException(422, "Tài liệu không thuộc môn học này.")


def task_json(db, item):
    meta = db.get(TeacherTaskMetadata, item.id)
    config = db.scalar(select(AssignmentConfiguration).where(AssignmentConfiguration.assignment_id == item.id))
    link = db.scalar(select(QuizAssignmentLink).where(QuizAssignmentLink.assignment_id == item.id))
    questions = (
        db.scalars(
            select(QuizQuestion).where(QuizQuestion.quiz_id == link.quiz_id).order_by(QuizQuestion.position)
        ).all()
        if link
        else []
    )
    has_submissions = bool(
        db.scalar(
            select(Submission.id)
            .where(Submission.assignment_id == item.id, Submission.workflow_state != "unsubmitted")
            .limit(1)
        )
    )
    chapter = db.scalar(
        select(CourseModule.name)
        .join(ModuleItem)
        .where(
            CourseModule.course_id == item.course_id,
            ModuleItem.item_type == "assignment",
            ModuleItem.content_id == item.id,
        )
        .order_by(CourseModule.id)
        .limit(1)
    )
    body = {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "chapter": chapter or "",
        "kind": meta.kind if meta else "quiz" if link else "assignment",
        "due_at": utc(item.due_at).isoformat(),
        "points_possible": item.points_possible,
        "published": item.published,
        "archived": bool(meta and meta.archived),
        "group_id": config.assignment_group_id if config else None,
        "resource_ids": json.loads(meta.resource_ids_json) if meta else [],
        "questions": [
            {
                "prompt": q.prompt,
                "options": json.loads(q.options_json),
                "correct_answer": q.correct_answer,
                "points": q.points,
            }
            for q in questions
        ],
        "has_submissions": has_submissions,
    }
    return {**body, "version": revision(body)}


def weights_json(db, course_id):
    rows = db.scalars(
        select(AssignmentGroup)
        .where(AssignmentGroup.course_id == course_id)
        .order_by(AssignmentGroup.position, AssignmentGroup.id)
    ).all()
    groups = [{"id": row.id, "name": row.name, "weight": row.group_weight} for row in rows]
    return {"groups": groups, "version": revision(groups)}


def lesson_metadata(item):
    try:
        value = json.loads((item.description or "").removeprefix("course-activity-v1; "))
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def lesson_json(item):
    from src.course_source.schedule_policy import LESSON_KINDS, REMOVED_SCHEDULE_KINDS

    metadata = lesson_metadata(item)
    body = {
        "id": item.id,
        "title": item.title,
        "starts_at": utc(item.starts_at).isoformat(),
        "ends_at": utc(item.ends_at).isoformat() if item.ends_at else None,
        "description": metadata.get("description", ""),
        "mode": "online" if item.event_kind in {"class_session", "removed_class_session"} else "offline",
        "location": metadata.get("location", ""),
        "meeting_url": metadata.get("meeting_url", ""),
        "resource_ids": metadata.get("resource_ids", []),
        "cancelled": item.attendance_status == "cancelled",
        "removed": item.event_kind in REMOVED_SCHEDULE_KINDS,
        "series_key": metadata.get("series_key"),
    }
    # Non-lesson entries retain their kind in the version; a quiz is not a video.
    if item.event_kind.removeprefix("removed_") not in LESSON_KINDS:
        body["event_kind"] = item.event_kind
    # Keep existing preview/restore tickets compatible for non-removed lessons.
    version_body = {key: value for key, value in body.items() if key != "removed" or value}
    return {**body, "version": revision(version_body)}


@router.get("/courses/{course_id}")
def snapshot(course_id: int, user_id: int, db: Session = Depends(get_db)):
    from src.course_source.schedule_policy import SCHEDULE_KINDS
    teacher(db, course_id, user_id)
    tasks = db.scalars(
        select(Assignment).where(Assignment.course_id == course_id).order_by(Assignment.due_at, Assignment.id)
    ).all()
    lessons = db.scalars(
        select(CalendarEvent)
        .where(
            CalendarEvent.course_id == course_id,
            CalendarEvent.user_id == user_id,
            CalendarEvent.event_kind.in_(["class", "class_session"]),
        )
        .order_by(CalendarEvent.starts_at)
    ).all()
    resources = db.scalars(select(Resource).where(Resource.course_id == course_id)).all()
    calendar_events = db.scalars(
        select(CalendarEvent).where(
            CalendarEvent.course_id == course_id,
            CalendarEvent.user_id == user_id,
            CalendarEvent.event_kind.in_(SCHEDULE_KINDS),
        ).order_by(CalendarEvent.starts_at, CalendarEvent.id)
    ).all()
    pages = db.scalars(
        select(CourseContent).where(CourseContent.course_id == course_id, CourseContent.kind == "page")
    ).all()

    def chapter_for(kind, identifier):
        return (
            db.scalar(
                select(CourseModule.name)
                .join(ModuleItem)
                .where(
                    CourseModule.course_id == course_id,
                    ModuleItem.item_type == kind,
                    ModuleItem.content_id == identifier,
                )
                .limit(1)
            )
            or ""
        )

    return {
        "tasks": [task_json(db, item) for item in tasks],
        "weights": weights_json(db, course_id),
        "lessons": [lesson_json(item) for item in lessons],
        "calendar_events": [lesson_json(item) for item in calendar_events],
        "resources": [
            {"id": item.id, "title": item.title, "chapter": chapter_for("resource", item.id)} for item in resources
        ],
        "materials": [
            {
                "id": item.id,
                "title": item.title,
                "chapter": chapter_for("page", item.id),
                "content": item.body,
                "published": item.published,
            }
            for item in pages
        ],
    }


def map_chapter(db, course_id, chapter, item_type, item_id, title):
    if not chapter:
        return
    module = db.scalar(select(CourseModule).where(CourseModule.course_id == course_id, CourseModule.name == chapter))
    if not module:
        module = CourseModule(course_id=course_id, name=chapter, published=True)
        db.add(module)
        db.flush()
    for previous in db.scalars(
        select(ModuleItem)
        .join(CourseModule)
        .where(CourseModule.course_id == course_id, ModuleItem.item_type == item_type, ModuleItem.content_id == item_id)
    ).all():
        db.delete(previous)
    db.add(ModuleItem(module_id=module.id, item_type=item_type, content_id=item_id, title=title, published=True))


def save_task(db, course_id, user_id, payload, item=None, *, commit=True):
    current = None
    if item:
        current = task_json(db, item)
        check_version(payload.expected_version, current["version"])
        if current["archived"]:
            raise HTTPException(409, "Nhiệm vụ đã ẩn; tạo nhiệm vụ mới để giữ lịch sử.")
        if current["has_submissions"] and (
            payload.kind != current["kind"]
            or payload.points_possible != item.points_possible
            or [q.model_dump() for q in payload.questions] != current["questions"]
        ):
            raise HTTPException(409, "Đã có bài nộp: không đổi loại, thang điểm hoặc đáp án.")
        if (current["kind"] == "quiz") != (payload.kind == "quiz"):
            raise HTTPException(409, "Không chuyển qua lại quiz và bài tập; hãy tạo nhiệm vụ mới.")
    group_id = payload.group_id
    if payload.group_name:
        match = next(
            (
                row
                for row in db.scalars(select(AssignmentGroup).where(AssignmentGroup.course_id == course_id)).all()
                if row.name.casefold() == payload.group_name.casefold()
            ),
            None,
        )
        if match is None:
            raise HTTPException(422, "Tên nhóm điểm không thuộc môn học.")
        if group_id is not None and group_id != match.id:
            raise HTTPException(422, "Tên và ID nhóm điểm không khớp.")
        group_id = match.id
    if group_id is not None:
        group = db.get(AssignmentGroup, group_id)
        if not group or group.course_id != course_id:
            raise HTTPException(422, "Nhóm điểm không thuộc môn học.")
    check_resources(db, course_id, payload.resource_ids)
    if item is None:
        item = Assignment(course_id=course_id)
        db.add(item)
    item.title, item.description, item.due_at = payload.title, payload.description, payload.due_at
    item.points_possible, item.published = payload.points_possible, payload.published
    item.submission_types = "online_quiz" if payload.kind == "quiz" else "online_text_entry,online_upload"
    db.flush()
    map_chapter(db, course_id, payload.chapter, "assignment", item.id, item.title)
    meta = db.get(TeacherTaskMetadata, item.id) or TeacherTaskMetadata(assignment_id=item.id)
    meta.kind, meta.resource_ids_json = payload.kind, json.dumps(sorted(set(payload.resource_ids)))
    db.add(meta)
    config = db.scalar(
        select(AssignmentConfiguration).where(AssignmentConfiguration.assignment_id == item.id)
    ) or AssignmentConfiguration(assignment_id=item.id)
    config.assignment_group_id = group_id
    db.add(config)
    if payload.kind == "quiz":
        link = db.scalar(select(QuizAssignmentLink).where(QuizAssignmentLink.assignment_id == item.id))
        quiz = db.get(CourseContent, link.quiz_id) if link else CourseContent(course_id=course_id, kind="quiz")
        quiz.title, quiz.body, quiz.due_at = payload.title, payload.description, payload.due_at
        quiz.points_possible, quiz.published = payload.points_possible, payload.published
        db.add(quiz)
        db.flush()
        if not link:
            db.add(QuizAssignmentLink(quiz_id=quiz.id, assignment_id=item.id))
        if current is None or not current["has_submissions"]:
            for question in db.scalars(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id)).all():
                db.delete(question)
            db.flush()
            for index, question in enumerate(payload.questions):
                db.add(
                    QuizQuestion(
                        quiz_id=quiz.id,
                        prompt=question.prompt,
                        options_json=json.dumps(question.options),
                        correct_answer=question.correct_answer,
                        points=question.points,
                        position=index + 1,
                    )
                )
        db.flush()
        sync_quiz_assignment(db, quiz, user_id)
    record_change(
        db,
        actor_user_id=user_id,
        action="assignment.updated",
        entity_type="assignment",
        entity_id=item.id,
        course_id=course_id,
    )
    if commit:
        db.commit()
    return task_json(db, item)


@router.post("/courses/{course_id}/tasks", status_code=201)
def create_task(course_id: int, payload: TaskInput, user_id: int, db: Session = Depends(get_db)):
    teacher(db, course_id, user_id)
    return save_task(db, course_id, user_id, payload)


@router.put("/courses/{course_id}/tasks/{task_id}")
def update_task(course_id: int, task_id: int, payload: TaskInput, user_id: int, db: Session = Depends(get_db)):
    teacher(db, course_id, user_id)
    item = db.get(Assignment, task_id, with_for_update=True)
    if not item or item.course_id != course_id:
        raise HTTPException(404, "Không tìm thấy nhiệm vụ.")
    return save_task(db, course_id, user_id, payload, item)


@router.post("/courses/{course_id}/tasks/{task_id}/archive")
def archive_task(course_id: int, task_id: int, payload: VersionInput, user_id: int, db: Session = Depends(get_db)):
    teacher(db, course_id, user_id)
    item = db.get(Assignment, task_id, with_for_update=True)
    if not item or item.course_id != course_id:
        raise HTTPException(404, "Không tìm thấy nhiệm vụ.")
    check_version(payload.expected_version, task_json(db, item)["version"])
    item.published = False
    meta = db.get(TeacherTaskMetadata, item.id) or TeacherTaskMetadata(assignment_id=item.id)
    meta.kind = task_json(db, item)["kind"]
    meta.archived = True
    db.add(meta)
    link = db.scalar(select(QuizAssignmentLink).where(QuizAssignmentLink.assignment_id == item.id))
    if link:
        db.get(CourseContent, link.quiz_id).published = False
    record_change(
        db,
        actor_user_id=user_id,
        action="assignment.updated",
        entity_type="assignment",
        entity_id=item.id,
        course_id=course_id,
        metadata={"archived": True},
    )
    db.commit()
    return {"status": "archived"}


@router.put("/courses/{course_id}/weights")
def update_weights(course_id: int, payload: WeightsInput, user_id: int, db: Session = Depends(get_db)):
    return save_weights(db, course_id, user_id, payload)


def save_weights(db, course_id, user_id, payload, *, commit=True):
    teacher(db, course_id, user_id)
    rows = db.scalars(select(AssignmentGroup).where(AssignmentGroup.course_id == course_id).with_for_update()).all()
    check_version(payload.expected_version, weights_json(db, course_id)["version"])
    previous = {row.id: row for row in rows}
    included = {row.id for row in payload.groups if row.id is not None}
    if not included <= previous.keys():
        raise HTTPException(422, "Nhóm điểm không thuộc môn học.")
    for identifier in previous.keys() - included:
        if db.scalar(
            select(AssignmentConfiguration.id).where(AssignmentConfiguration.assignment_group_id == identifier).limit(1)
        ):
            raise HTTPException(409, "Nhóm đang có bài tập; chuyển bài sang nhóm khác trước khi xóa.")
        db.delete(previous[identifier])
    for position, value in enumerate(payload.groups):
        row = previous[value.id] if value.id else AssignmentGroup(course_id=course_id)
        row.name, row.group_weight, row.position = value.name, value.weight, position + 1
        db.add(row)
    record_change(
        db,
        actor_user_id=user_id,
        action="assignment_group.updated",
        entity_type="course",
        entity_id=course_id,
        course_id=course_id,
    )
    db.flush()
    if commit:
        db.commit()
    return weights_json(db, course_id)


@router.post("/courses/{course_id}/lessons", status_code=201)
def create_lesson(course_id: int, payload: LessonInput, user_id: int, db: Session = Depends(get_db)):
    return save_lessons(db, course_id, user_id, payload)


def save_lessons(db, course_id, user_id, payload, *, commit=True, series_key=None):
    teacher(db, course_id, user_id)
    check_resources(db, course_id, payload.resource_ids)
    members = db.scalars(select(Enrollment.user_id).where(Enrollment.course_id == course_id)).all()
    created = []
    now = datetime.now(UTC)
    series_key = series_key or (str(uuid4()) if payload.repeat_count > 1 else None)
    for index in range(payload.repeat_count):
        key = str(uuid4())
        for member in members:
            event = CalendarEvent(
                user_id=member,
                course_id=course_id,
                title=payload.title,
                starts_at=payload.starts_at + timedelta(weeks=index),
                ends_at=payload.ends_at + timedelta(weeks=index),
                description="course-activity-v1; "
                + json.dumps(
                    {
                        **payload.model_dump(exclude={"starts_at", "ends_at", "expected_version", "repeat_count"}),
                        "series_key": series_key,
                    }
                ),
                event_kind="class_session" if payload.mode == "online" else "class",
                join_url=payload.meeting_url if payload.mode == "online" else None,
                # Historical timetable imports carry no evidence of attendance.
                attendance_status=None if payload.ends_at + timedelta(weeks=index) <= now else "scheduled",
            )
            db.add(event)
            db.flush()
            db.add(TeachingEventLink(calendar_event_id=event.id, occurrence_key=key))
            if member == user_id:
                created.append(event.id)
    record_change(
        db,
        actor_user_id=user_id,
        action="calendar.created",
        entity_type="course",
        entity_id=course_id,
        course_id=course_id,
    )
    if commit:
        db.commit()
    return {"created": len(created), "ids": created}


def lesson_targets(db, course_id, user_id, lesson_id, expected, *, allowed_kinds=("class", "class_session")):
    event = db.get(CalendarEvent, lesson_id, with_for_update=True)
    if (
        not event
        or event.course_id != course_id
        or event.user_id != user_id
        or event.event_kind not in allowed_kinds
    ):
        raise HTTPException(404, "Không tìm thấy buổi học của giảng viên.")
    check_version(expected, lesson_json(event)["version"])
    link = db.get(TeachingEventLink, event.id)
    if link:
        targets = db.scalars(
            select(CalendarEvent)
            .join(TeachingEventLink)
            .where(TeachingEventLink.occurrence_key == link.occurrence_key, CalendarEvent.course_id == course_id,
                   CalendarEvent.event_kind == event.event_kind)
            .with_for_update()
        ).all()
    else:
        targets = db.scalars(
            select(CalendarEvent)
            .where(
                CalendarEvent.course_id == course_id,
                CalendarEvent.title == event.title,
                CalendarEvent.starts_at == event.starts_at,
                CalendarEvent.ends_at == event.ends_at,
                CalendarEvent.event_kind == event.event_kind,
                CalendarEvent.description == event.description,
            )
            .with_for_update()
        ).all()
        if len({row.user_id for row in targets}) != len(targets):
            raise HTTPException(409, "Buổi cũ bị trùng; không thể xác định bản sao để sửa an toàn.")
    return event, targets


@router.put("/courses/{course_id}/lessons/{lesson_id}")
def update_lesson(course_id: int, lesson_id: int, payload: LessonInput, user_id: int, db: Session = Depends(get_db)):
    teacher(db, course_id, user_id)
    event, targets = lesson_targets(db, course_id, user_id, lesson_id, payload.expected_version)
    if utc(event.starts_at) <= datetime.now(UTC) or payload.repeat_count != 1 or event.attendance_status == "cancelled":
        raise HTTPException(409, "Chỉ sửa buổi chưa diễn ra; chỉnh từng buổi của lịch lặp.")
    check_resources(db, course_id, payload.resource_ids)
    for target in targets:
        target.title, target.starts_at, target.ends_at = payload.title, payload.starts_at, payload.ends_at
        target.description = "course-activity-v1; " + json.dumps(
            {
                **payload.model_dump(exclude={"starts_at", "ends_at", "expected_version", "repeat_count"}),
                "series_key": lesson_metadata(event).get("series_key"),
            }
        )
        target.event_kind = "class_session" if payload.mode == "online" else "class"
        target.join_url = payload.meeting_url if payload.mode == "online" else None
    record_change(
        db,
        actor_user_id=user_id,
        action="calendar.updated",
        entity_type="calendar_event",
        entity_id=event.id,
        course_id=course_id,
    )
    db.commit()
    return lesson_json(event)


@router.post("/courses/{course_id}/lessons/{lesson_id}/cancel")
def cancel_lesson(course_id: int, lesson_id: int, payload: VersionInput, user_id: int, db: Session = Depends(get_db)):
    teacher(db, course_id, user_id)
    event, targets = lesson_targets(db, course_id, user_id, lesson_id, payload.expected_version)
    if utc(event.starts_at) <= datetime.now(UTC):
        raise HTTPException(409, "Không hủy buổi đã diễn ra; giữ lịch sử tham dự.")
    for target in targets:
        target.attendance_status = "cancelled"
    record_change(
        db,
        actor_user_id=user_id,
        action="calendar.deleted",
        entity_type="calendar_event",
        entity_id=event.id,
        course_id=course_id,
        metadata={"cancelled": True},
    )
    db.commit()
    return {"status": "cancelled"}


@router.get("/profile")
def read_profile(user_id: int, db: Session = Depends(get_db)):
    if not db.scalar(select(Enrollment.id).where(Enrollment.user_id == user_id, Enrollment.role == "instructor")):
        raise HTTPException(403, "Instructor enrollment required")
    user = db.get(User, user_id)
    profile = db.get(TeacherProfile, user_id)
    details = json.loads(profile.profile_json) if profile else ProfileInput().model_dump(exclude={"expected_version"})
    return {"name": user.full_name, "email": user.email, "details": details, "version": revision(details)}


@router.put("/profile")
def save_profile(payload: ProfileInput, user_id: int, db: Session = Depends(get_db)):
    current = read_profile(user_id, db)
    profile = db.get(TeacherProfile, user_id, with_for_update=True)
    if profile:
        current["version"] = revision(json.loads(profile.profile_json))
    check_version(payload.expected_version, current["version"])
    profile = profile or TeacherProfile(user_id=user_id)
    profile.profile_json = json.dumps(payload.model_dump(exclude={"expected_version"}))
    db.add(profile)
    record_change(
        db,
        actor_user_id=user_id,
        action="teacher.profile.updated",
        entity_type="user",
        entity_id=user_id,
        emit_event=False,
    )
    db.commit()
    return read_profile(user_id, db)


class PdfInput(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    data_base64: str = Field(max_length=7_000_000)
    chapter: str = Field(default="", max_length=255)


class MaterialInput(StrictModel):
    title: str = Field(min_length=1, max_length=255)
    chapter: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=20000)


def save_material(db, course_id, user_id, payload, *, commit=True):
    teacher(db, course_id, user_id)
    item = CourseContent(course_id=course_id, kind="page", title=payload.title, body=payload.content, published=True)
    db.add(item)
    db.flush()
    map_chapter(db, course_id, payload.chapter, "page", item.id, item.title)
    record_change(
        db, actor_user_id=user_id, action="content.created", entity_type="page", entity_id=item.id, course_id=course_id
    )
    if commit:
        db.commit()
    return {"id": item.id, "title": item.title}


@router.post("/courses/{course_id}/materials", status_code=201)
def create_material(course_id: int, payload: MaterialInput, user_id: int, db: Session = Depends(get_db)):
    return save_material(db, course_id, user_id, payload)


@router.post("/courses/{course_id}/pdf", status_code=201)
def upload_pdf(course_id: int, payload: PdfInput, user_id: int, db: Session = Depends(get_db)):
    teacher(db, course_id, user_id)
    from src.course_source.uploads import save_upload

    try:
        content = base64.b64decode(payload.data_base64, validate=True)
    except ValueError as exc:
        raise HTTPException(422, "PDF không hợp lệ.") from exc
    if (
        not payload.filename.lower().endswith(".pdf")
        or not content.startswith(b"%PDF-")
        or len(content) > 5 * 1024 * 1024
    ):
        raise HTTPException(422, "Chỉ nhận PDF tối đa 5 MB.")
    file = UploadFile(
        io.BytesIO(content), filename=payload.filename, headers=Headers({"content-type": "application/pdf"})
    )
    original, url = save_upload(file, f"course-{course_id}")
    resource = Resource(course_id=course_id, title=original, kind="file", source_url=url)
    db.add(resource)
    db.flush()
    map_chapter(db, course_id, payload.chapter, "resource", resource.id, resource.title)
    record_resource_version(
        db,
        resource,
        checksum=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        content_type="application/pdf",
    )
    record_change(
        db,
        actor_user_id=user_id,
        action="resource.created",
        entity_type="resource",
        entity_id=resource.id,
        course_id=course_id,
    )
    db.commit()
    return {"id": resource.id, "title": resource.title}
