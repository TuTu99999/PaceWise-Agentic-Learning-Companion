"""Preview/confirm transactions. Never accept a browser-authored list of IDs to delete."""

import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, ValidationError, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.course_source.course_management import course_json, owned
from src.course_source.db import get_db
from src.course_source.integration_api import require_service_key
from src.course_source.models import (
    CalendarEvent,
    Course,
    CourseLifecycle,
    Enrollment,
    TeacherScheduleBatch,
    User,
)
from src.course_source.schedule_policy import LESSON_KINDS, SCHEDULE_KINDS, remove_calendar_kind
from src.course_source.teacher_management import (
    LessonInput,
    MaterialInput,
    StrictModel,
    TaskInput,
    WeightsInput,
    check_version,
    lesson_json,
    lesson_metadata,
    lesson_targets,
    revision,
    save_lessons,
    save_material,
    save_task,
    save_weights,
    snapshot,
    utc,
)
from src.course_source.telemetry import record_change

router = APIRouter(prefix="/api/pacewise/v1/teacher/schedule", dependencies=[Depends(require_service_key)])


class ImportRow(StrictModel):
    course_id: int
    course_code: str = Field(default="", max_length=64)
    sheet: Literal["Lessons", "Tasks", "Weights", "Materials"]
    row: int = Field(ge=2)
    data: dict


class CourseDraft(StrictModel):
    temp_id: int = Field(lt=0)
    code: str = Field(min_length=1, max_length=64, pattern=r"^[\w.-]+$")
    name: str = Field(min_length=1, max_length=255)
    term: str = Field(default="Demo", min_length=1, max_length=128)
    row: int = Field(ge=2)


class PreviewInput(StrictModel):
    mode: Literal["append", "replace_future", "cleanup", "replace_series", "remove"] = "append"
    rows: list[ImportRow] = Field(default_factory=list, max_length=500)
    course_ids: list[int] = Field(default_factory=list, max_length=100)
    new_courses: list[CourseDraft] = Field(default_factory=list, max_length=100)
    from_at: datetime | None = None
    until_at: datetime | None = None
    series_lesson_id: int | None = None
    lesson_ids: list[int] | None = Field(default=None, min_length=1, max_length=500)
    period: Literal["all", "past", "future"] = "all"

    @model_validator(mode="after")
    def timezones(self):
        if not self.course_ids and not self.new_courses:
            raise ValueError("At least one existing or new course is required")
        if any(identifier <= 0 for identifier in self.course_ids) or len(self.course_ids) != len(set(self.course_ids)):
            raise ValueError("Existing course IDs must be unique positive integers")
        temporary_ids = [item.temp_id for item in self.new_courses]
        codes = [item.code.casefold() for item in self.new_courses]
        if len(temporary_ids) != len(set(temporary_ids)) or len(codes) != len(set(codes)):
            raise ValueError("New course codes and temporary IDs must be unique")
        for value in [self.from_at, self.until_at]:
            if value and value.tzinfo is None:
                raise ValueError("Timezone required")
        if self.from_at and self.until_at and self.until_at <= self.from_at:
            raise ValueError("End must follow start")
        if self.series_lesson_id is not None and (
            self.mode not in {"cleanup", "replace_series"} or len(self.course_ids) != 1
        ):
            raise ValueError("Series changes require exactly one course")
        if self.mode == "replace_series" and (self.series_lesson_id is None or self.from_at or self.until_at):
            raise ValueError("Series replacement needs its source lesson, without a date filter")
        if self.mode == "remove" and (self.rows or self.series_lesson_id is not None):
            raise ValueError("Removal cannot import content or replace a series")
        if self.lesson_ids is not None and (
            self.mode != "remove" or any(identifier <= 0 for identifier in self.lesson_ids)
        ):
            raise ValueError("Lesson selection requires removal and positive identifiers")
        if self.mode != "remove" and self.period != "all":
            raise ValueError("Period selection requires removal")
        return self


class ConfirmInput(StrictModel):
    ticket: str = Field(min_length=36, max_length=36)


def course_state(db, user_id, course_id):
    course = owned(db, user_id, course_id)
    body = course_json(db, course)
    if body["archived"]:
        raise HTTPException(409, "Khôi phục môn trước khi thay đổi lịch.")
    return revision({"course": body, "content": snapshot(course_id, user_id, db)})


def cancelled_candidates(db, user_id, payload, now):
    if payload.mode == "append":
        return []
    ids = set(payload.course_ids)
    # Replacing only affects courses with lesson rows; task-only files cannot erase classes.
    if payload.mode == "replace_future":
        ids &= {row.course_id for row in payload.rows if row.sheet == "Lessons"}
    query = (
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.course_id.in_(ids),
            CalendarEvent.event_kind.in_(SCHEDULE_KINDS if payload.mode == "remove" else LESSON_KINDS),
        )
        .order_by(CalendarEvent.starts_at)
    )
    if payload.mode != "remove":
        query = query.where(
            CalendarEvent.starts_at > now,
            or_(CalendarEvent.attendance_status.is_(None), CalendarEvent.attendance_status != "cancelled"),
        )
    elif payload.period == "past":
        query = query.where(CalendarEvent.ends_at <= now)
    elif payload.period == "future":
        query = query.where(CalendarEvent.starts_at > now)
    if payload.lesson_ids is not None:
        query = query.where(CalendarEvent.id.in_(payload.lesson_ids))
    if payload.from_at:
        query = query.where(CalendarEvent.starts_at >= payload.from_at)
    if payload.until_at:
        query = query.where(CalendarEvent.starts_at < payload.until_at)
    candidates = db.scalars(query).all()
    if payload.lesson_ids is not None and {item.id for item in candidates} != set(payload.lesson_ids):
        raise HTTPException(404, "Buổi học không còn tồn tại hoặc nằm ngoài phạm vi đã chọn.")
    if payload.series_lesson_id is not None:
        item = db.get(CalendarEvent, payload.series_lesson_id)
        if not item or item.course_id not in ids or item.user_id != user_id:
            raise HTTPException(404, "Không tìm thấy chuỗi buổi học.")
        key = lesson_metadata(item).get("series_key")
        if not key:
            raise HTTPException(409, "Buổi cũ chưa có liên kết chuỗi; dùng dọn lịch theo môn/ngày.")
        candidates = [item for item in candidates if lesson_metadata(item).get("series_key") == key]
    return candidates


def make_preview(db, user_id, payload):
    now = datetime.now(UTC)
    states = {str(identifier): course_state(db, user_id, identifier) for identifier in sorted(set(payload.course_ids))}
    pending = {item.temp_id: item for item in payload.new_courses}
    errors, validated, seen = [], [], set()
    for item in payload.new_courses:
        if db.scalar(select(Course.id).where(func.lower(Course.code) == item.code.casefold())):
            errors.append(
                {
                    "source": f"Courses dòng {item.row}",
                    "message": "Mã môn đã tồn tại nhưng không thuộc danh sách môn đang quản lý. Đổi mã hoặc tải lại danh sách môn.",
                }
            )
    cancellations = cancelled_candidates(db, user_id, payload, now)
    series_key = None
    if payload.mode == "replace_series":
        origin = db.get(CalendarEvent, payload.series_lesson_id)
        series_key = lesson_metadata(origin).get("series_key")
        if not cancellations or len(payload.rows) != len(cancellations):
            errors.append({"source": "Chuỗi", "message": "Số buổi mới phải khớp các buổi tương lai của chuỗi."})
    excluded = {event.id for event in cancellations}
    # Archived courses remain in the database for audit/restore, but their
    # timetable must not reserve capacity for a new active course.  The outer
    # join keeps legacy courses that predate CourseLifecycle records active.
    intervals = [
        (event.course_id, utc(event.starts_at), utc(event.ends_at))
        for event in db.scalars(
            select(CalendarEvent)
            .outerjoin(CourseLifecycle, CourseLifecycle.course_id == CalendarEvent.course_id)
            .where(
                CalendarEvent.user_id == user_id,
                CalendarEvent.event_kind.in_(["class", "class_session"]),
                or_(CourseLifecycle.archived.is_(False), CourseLifecycle.archived.is_(None)),
                or_(CalendarEvent.attendance_status.is_(None), CalendarEvent.attendance_status != "cancelled"),
            )
        ).all()
        if event.id not in excluded and event.ends_at
    ]
    counts = {"courses": len(payload.new_courses), "lessons": 0, "historical_lessons": 0,
              "tasks": 0, "weights": 0, "materials": 0,
              "cancelled_lessons": 0 if payload.mode == "remove" else len(cancellations),
              "removed_lessons": len(cancellations) if payload.mode == "remove" else 0}
    if payload.mode == "remove" and not cancellations:
        errors.append({"source": "Lịch", "message": "Không có buổi học nào trong phạm vi đã chọn để xóa."})
    weights_seen = set()
    imported_group_names = {
        row.course_id: {
            str(group.get("name") or "").strip().casefold()
            for group in row.data.get("groups", [])
            if str(group.get("name") or "").strip()
        }
        for row in payload.rows
        if row.sheet == "Weights"
    }
    from src.course_source.models import AssignmentGroup

    existing_group_names = {}
    for group in db.scalars(select(AssignmentGroup).where(AssignmentGroup.course_id.in_(payload.course_ids))).all():
        existing_group_names.setdefault(group.course_id, set()).add(group.name.casefold())
    for row in payload.rows:
        label = f"{row.sheet} dòng {row.row}"
        try:
            is_pending = row.course_id in pending
            if row.course_id not in payload.course_ids and not is_pending:
                raise ValueError("Môn nằm ngoài phạm vi nhập.")
            model = {"Lessons": LessonInput, "Tasks": TaskInput, "Weights": WeightsInput, "Materials": MaterialInput}[
                row.sheet
            ]
            data = dict(row.data)
            if row.sheet == "Weights":
                if row.course_id in weights_seen:
                    raise ValueError("Mỗi môn chỉ có một bộ trọng số.")
                weights_seen.add(row.course_id)
                current_weights = (
                    {"version": "0" * 64, "groups": []}
                    if is_pending
                    else snapshot(row.course_id, user_id, db)["weights"]
                )
                data["expected_version"] = current_weights["version"]
                previous_groups = current_weights["groups"]
                by_name = {group["name"].casefold(): group["id"] for group in previous_groups}
                data["groups"] = [
                    {**group, "id": by_name.get(str(group["name"]).casefold())} for group in data.get("groups", [])
                ]
                from src.course_source.models import AssignmentConfiguration, AssignmentGroup

                included = {group.get("id") for group in data["groups"]}
                referenced = (
                    set()
                    if is_pending
                    else set(
                        db.scalars(
                            select(AssignmentConfiguration.assignment_group_id)
                            .join(AssignmentGroup)
                            .where(AssignmentGroup.course_id == row.course_id)
                        ).all()
                    )
                )
                if not referenced <= included:
                    raise ValueError(
                        "Nhóm điểm cũ đang có bài tập; giữ tên nhóm trong file hoặc chuyển bài sang nhóm khác trước"
                    )
            item = model.model_validate(data)
            if payload.mode == "replace_series" and (row.sheet != "Lessons" or item.repeat_count != 1):
                raise ValueError("Sửa chuỗi chỉ thay từng buổi tương lai, không thêm nhiệm vụ hoặc buổi lặp mới.")
            key = revision({"course": row.course_id, "sheet": row.sheet, "data": item.model_dump(mode="json")})
            if key in seen:
                raise ValueError("Dòng trùng lặp trong file.")
            seen.add(key)
            if row.sheet == "Lessons":
                historical_lessons = 0
                for index in range(item.repeat_count):
                    start, end = item.starts_at + timedelta(weeks=index), item.ends_at + timedelta(weeks=index)
                    if start <= now < end:
                        raise ValueError("Không nhập buổi đang diễn ra; chọn buổi đã kết thúc hoặc chưa bắt đầu.")
                    if payload.mode == "replace_series" and start <= now:
                        raise ValueError("Sửa chuỗi chỉ thay các buổi chưa bắt đầu.")
                    if any(start < right and end > left for _, left, right in intervals):
                        raise ValueError("Trùng buổi học hiện có hoặc dòng khác; đổi giờ hoặc chọn thay lịch.")
                    intervals.append((row.course_id, start, end))
                    historical_lessons += int(end <= now)
                counts["lessons"] += item.repeat_count
                counts["historical_lessons"] += historical_lessons
            elif row.sheet == "Tasks":
                if item.due_at <= now:
                    raise ValueError("Deadline phải ở tương lai.")
                allowed_names = imported_group_names.get(row.course_id, existing_group_names.get(row.course_id, set()))
                if item.group_name and item.group_name.casefold() not in allowed_names:
                    raise ValueError("Tên nhóm điểm không có trong sheet Weights hoặc môn hiện tại.")
                counts["tasks"] += 1
            elif row.sheet == "Weights":
                counts["weights"] += 1
            else:
                counts["materials"] += 1
            # Creation-only import: versions/resources/groups must be validated by domain too.
            if row.sheet in {"Lessons", "Tasks"}:
                from src.course_source.teacher_management import check_resources

                if is_pending and item.resource_ids:
                    raise ValueError("Môn mới chưa có học liệu để liên kết bằng ID.")
                if not is_pending:
                    check_resources(db, row.course_id, item.resource_ids)
            if row.sheet == "Tasks" and item.group_id is not None:
                if is_pending:
                    raise ValueError("Môn mới chưa có nhóm điểm để liên kết bằng ID.")
                from src.course_source.models import AssignmentGroup

                group = db.get(AssignmentGroup, item.group_id)
                if not group or group.course_id != row.course_id:
                    raise ValueError("Nhóm điểm không thuộc môn.")
            validated.append(
                {
                    "course_id": row.course_id,
                    "course_code": row.course_code or (pending[row.course_id].code if is_pending else ""),
                    "sheet": row.sheet,
                    "row": row.row,
                    "data": item.model_dump(mode="json"),
                }
            )
        except (ValidationError, ValueError, HTTPException) as exc:
            message = exc.detail if isinstance(exc, HTTPException) else str(exc)
            errors.append({"source": label, "message": message[:1000]})
    if not payload.rows and payload.mode not in {"cleanup", "remove"}:
        errors.append({"source": "File", "message": "File không có dòng dữ liệu."})
    if payload.mode == "cleanup" and payload.rows:
        errors.append({"source": "Phạm vi", "message": "Dọn lịch không được kèm dữ liệu nhập."})
    return {
        "counts": counts,
        "errors": errors,
        "states": states,
        "new_courses": [item.model_dump(mode="json") for item in payload.new_courses],
        "rows": validated,
        "cancellations": [{"course_id": e.course_id, **lesson_json(e)} for e in cancellations],
        "series_key": series_key,
    }


@router.post("/preview")
def preview(payload: PreviewInput, user_id: int, db: Session = Depends(get_db)):
    # Serializes competing previews/commits for an actor across processes.
    db.get(User, user_id, with_for_update=True)
    value = None
    fingerprint_body = payload.model_dump(mode="json")
    if payload.mode in {"cleanup", "remove"}:
        # The same filters must select newly added lessons on the next cleanup.
        # Ticket confirmation remains idempotent; filters are not an import ID.
        value = make_preview(db, user_id, payload)
        fingerprint_body = {"request": fingerprint_body, "states": value["states"],
                            "cancellations": value["cancellations"]}
    fingerprint = revision(fingerprint_body)
    previous = db.scalar(
        select(TeacherScheduleBatch)
        .where(TeacherScheduleBatch.user_id == user_id, TeacherScheduleBatch.fingerprint == fingerprint)
        .with_for_update()
    )
    if previous and previous.restored_at and payload.mode in {"cleanup", "remove"}:
        previous.fingerprint = revision({"old_fingerprint": fingerprint, "batch": previous.id})
        db.flush()
        previous = None
    if previous and previous.applied_at:
        return public_preview(previous)
    value = value or make_preview(db, user_id, payload)
    batch = previous or TeacherScheduleBatch(id=str(uuid4()), user_id=user_id, fingerprint=fingerprint)
    batch.payload_json = payload.model_dump_json()
    batch.preview_json = json.dumps(value)
    batch.expires_at = datetime.now(UTC) + timedelta(minutes=30)
    db.add(batch)
    db.commit()
    return public_preview(batch)


def public_preview(batch):
    body = json.loads(batch.preview_json)
    pending_codes = {item["temp_id"]: item["code"] for item in body.get("new_courses", [])}
    return {
        "ticket": batch.id,
        "counts": body["counts"],
        "errors": body["errors"],
        "applied": bool(batch.applied_at),
        "restored": bool(batch.restored_at),
        "mode": json.loads(batch.payload_json)["mode"],
        "courses": list(body["states"]) + [str(item["id"]) for item in body.get("created_courses", [])],
        "created_courses": body.get("created_courses", []),
        "items": [
            {
                "sheet": row["sheet"],
                "row": row["row"],
                "course_id": row["course_id"],
                "course_code": row.get("course_code") or pending_codes.get(row["course_id"], ""),
                "title": row["data"].get("title", "Trọng số điểm"),
                "details": {
                    key: value
                    for key, value in row["data"].items()
                    if key
                    in {
                        "starts_at",
                        "ends_at",
                        "repeat_count",
                        "due_at",
                        "points_possible",
                        "published",
                        "chapter",
                        "groups",
                    }
                },
            }
            for row in body["rows"]
        ],
        "cancellations": [
            {"id": item["id"], "course_id": item["course_id"], "title": item["title"], "starts_at": item["starts_at"]}
            for item in body["cancellations"]
        ],
    }


def find_batch(db, user_id, ticket):
    db.get(User, user_id, with_for_update=True)
    batch = db.get(TeacherScheduleBatch, ticket, with_for_update=True)
    if not batch or batch.user_id != user_id:
        raise HTTPException(404, "Không tìm thấy bản xem trước.")
    return batch


@router.post("/confirm")
def confirm(payload: ConfirmInput, user_id: int, db: Session = Depends(get_db)):
    batch = find_batch(db, user_id, payload.ticket)
    original = json.loads(batch.preview_json)
    for identifier in original["states"]:
        owned(db, user_id, int(identifier))
    if batch.applied_at:
        return public_preview(batch)
    if utc(batch.expires_at) <= datetime.now(UTC) or original["errors"]:
        raise HTTPException(409, "Bản xem trước hết hạn hoặc có lỗi. Tải lại xem trước.")
    request = PreviewInput.model_validate_json(batch.payload_json)
    current = make_preview(db, user_id, request)
    if (
        current["errors"]
        or current["states"] != original["states"]
        or current["new_courses"] != original.get("new_courses", [])
        or current["cancellations"] != original["cancellations"]
    ):
        raise HTTPException(409, "Dữ liệu hoặc thời gian đã thay đổi; xem trước lại trước khi xác nhận.")
    restored_targets = []
    try:
        course_ids = {}
        created_courses = []
        for item in original.get("new_courses", []):
            if db.scalar(select(Course.id).where(func.lower(Course.code) == item["code"].casefold())):
                raise HTTPException(409, "Mã môn vừa được sử dụng. Xem trước lại file trước khi xác nhận.")
            course = Course(
                code=item["code"],
                name=item["name"],
                term=item["term"],
                color="#4169E1",
                published=True,
            )
            db.add(course)
            db.flush()
            db.add(Enrollment(user_id=user_id, course_id=course.id, role="instructor"))
            db.add(CourseLifecycle(course_id=course.id, archived=False))
            record_change(
                db,
                actor_user_id=user_id,
                action="course.created",
                entity_type="course",
                entity_id=course.id,
                course_id=course.id,
                metadata={"schedule_batch": batch.id},
            )
            course_ids[int(item["temp_id"])] = course.id
            created_courses.append({"id": course.id, "code": course.code, "name": course.name, "term": course.term})
        db.flush()
        for item in original["cancellations"]:
            _, targets = lesson_targets(
                db, item["course_id"], user_id, item["id"], item["version"],
                allowed_kinds=SCHEDULE_KINDS if request.mode == "remove" else LESSON_KINDS,
            )
            for target in targets:
                old = target.attendance_status
                old_kind = target.event_kind
                if request.mode == "remove":
                    target.event_kind = remove_calendar_kind(old_kind)
                else:
                    target.attendance_status = "cancelled"
                restored_targets.append(
                    {
                        "id": target.id,
                        "course_id": target.course_id,
                        "status": old,
                        "event_kind": old_kind,
                        "cancelled_version": lesson_json(target)["version"],
                    }
                )
            record_change(
                db,
                actor_user_id=user_id,
                action="calendar.deleted",
                entity_type="calendar_event",
                entity_id=item["id"],
                course_id=item["course_id"],
                metadata={"batch": batch.id, "cancelled": request.mode != "remove",
                          "removed": request.mode == "remove"},
            )
        ordered_rows = sorted(original["rows"], key=lambda row: 0 if row["sheet"] == "Weights" else 1)
        for row in ordered_rows:
            course_id = course_ids.get(row["course_id"], row["course_id"])
            data = dict(row["data"])
            if row["sheet"] == "Weights" and row["course_id"] in course_ids:
                data["expected_version"] = snapshot(course_id, user_id, db)["weights"]["version"]
            if row["sheet"] == "Lessons":
                save_lessons(
                    db,
                    course_id,
                    user_id,
                    LessonInput.model_validate(data),
                    commit=False,
                    series_key=original.get("series_key"),
                )
            elif row["sheet"] == "Tasks":
                save_task(db, course_id, user_id, TaskInput.model_validate(data), commit=False)
            elif row["sheet"] == "Materials":
                save_material(db, course_id, user_id, MaterialInput.model_validate(data), commit=False)
            else:
                save_weights(db, course_id, user_id, WeightsInput.model_validate(data), commit=False)
            row["course_id"] = course_id
            row["data"] = data
        original["restore_targets"] = restored_targets
        original["created_courses"] = created_courses
        batch.preview_json = json.dumps(original)
        batch.applied_at = datetime.now(UTC)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return public_preview(batch)


class SeriesPreviewInput(LessonInput):
    course_ids: list[int] = Field(min_length=1, max_length=1)
    series_lesson_id: int


@router.post("/series-preview")
def series_preview(payload: SeriesPreviewInput, user_id: int, db: Session = Depends(get_db)):
    course_id = payload.course_ids[0]
    course_state(db, user_id, course_id)
    origin, _ = lesson_targets(db, course_id, user_id, payload.series_lesson_id, payload.expected_version)
    if utc(origin.starts_at) <= datetime.now(UTC) or origin.attendance_status == "cancelled":
        raise HTTPException(409, "Chọn một buổi chưa bắt đầu và chưa hủy để sửa chuỗi.")
    if payload.repeat_count != 1:
        raise HTTPException(422, "Sửa chuỗi giữ nguyên số buổi còn lại.")
    request = PreviewInput(mode="replace_series", course_ids=[course_id], series_lesson_id=origin.id)
    targets = cancelled_candidates(db, user_id, request, datetime.now(UTC))
    # Apply one relative date/time shift and duration, retaining each remaining occurrence.
    shift = payload.starts_at - utc(origin.starts_at)
    duration = payload.ends_at - payload.starts_at
    shared = payload.model_dump(mode="json", exclude={"course_ids", "series_lesson_id", "expected_version"})
    for index, event in enumerate(targets, 2):
        start = utc(event.starts_at) + shift
        request.rows.append(
            ImportRow(
                course_id=course_id,
                sheet="Lessons",
                row=index,
                data={**shared, "starts_at": start.isoformat(), "ends_at": (start + duration).isoformat()},
            )
        )
    return preview(request, user_id, db)


class DemoInput(StrictModel):
    course_ids: list[int] = Field(min_length=1, max_length=1)

    @property
    def course_id(self):
        return self.course_ids[0]


@router.post("/demo-preview")
def demo_preview(payload: DemoInput, user_id: int, db: Session = Depends(get_db)):
    from zoneinfo import ZoneInfo

    local = ZoneInfo("Asia/Ho_Chi_Minh")
    chapter = "Demo · Lập kế hoạch và tự kiểm tra"
    tomorrow = (datetime.now(local) + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    # Dates are current; labels explicitly say demo. Nothing is seeded before confirmation.
    value = PreviewInput(
        course_ids=[payload.course_id],
        rows=[
            ImportRow(
                course_id=payload.course_id,
                sheet="Lessons",
                row=2,
                data={
                    "title": "Demo · Buổi hướng dẫn",
                    "starts_at": tomorrow.isoformat(),
                    "ends_at": (tomorrow + timedelta(minutes=60)).isoformat(),
                },
            ),
            ImportRow(
                course_id=payload.course_id,
                sheet="Tasks",
                row=2,
                data={
                    "title": "Demo · Tự lập kế hoạch tuần",
                    "chapter": chapter,
                    "description": "Đọc hướng dẫn trong chương Demo, lập kế hoạch và tự giải thích lựa chọn.",
                    "due_at": (tomorrow + timedelta(days=3, hours=8)).isoformat(),
                    "points_possible": 10,
                    "published": True,
                },
            ),
            ImportRow(
                course_id=payload.course_id,
                sheet="Materials",
                row=2,
                data={
                    "title": "Demo · Hướng dẫn học và tự kiểm tra",
                    "chapter": chapter,
                    "content": "Tài liệu demo: liệt kê các nhiệm vụ, kiểm tra deadline và thời gian rảnh. "
                    "Chia nhiệm vụ thành bước nhỏ, dành thời gian nghỉ và tự giải thích vì sao chọn thứ tự đó. "
                    "Sau một phiên, đối chiếu tiến độ thực tế với kế hoạch; nếu gián đoạn do việc đột xuất, ghi nhận nguyên nhân. "
                    "Thời gian học không tự chứng minh mức hiểu. Tự kiểm tra bằng giải thích hoặc vận dụng trong tình huống mới.",
                },
            ),
        ],
    )
    return preview(value, user_id, db)


@router.get("/history")
def history(user_id: int, db: Session = Depends(get_db)):
    from src.course_source.course_management import instructor

    instructor(db, user_id)
    batches = db.scalars(
        select(TeacherScheduleBatch)
        .where(TeacherScheduleBatch.user_id == user_id, TeacherScheduleBatch.applied_at.is_not(None))
        .order_by(TeacherScheduleBatch.applied_at.desc())
        .limit(20)
    ).all()
    return [public_preview(batch) for batch in batches]


@router.post("/restore")
def restore(payload: ConfirmInput, user_id: int, db: Session = Depends(get_db)):
    batch = find_batch(db, user_id, payload.ticket)
    if not batch.applied_at:
        raise HTTPException(409, "Chưa có thay đổi để khôi phục.")
    if batch.restored_at:
        return public_preview(batch)
    data = json.loads(batch.preview_json)
    removing = json.loads(batch.payload_json)["mode"] == "remove"
    targets = []
    for value in data.get("restore_targets", []):
        owned(db, user_id, value["course_id"])
        event = db.get(CalendarEvent, value["id"], with_for_update=True)
        if not event or (not removing and utc(event.starts_at) <= datetime.now(UTC)):
            raise HTTPException(409, "Buổi đã bắt đầu; không khôi phục thay đổi lịch sử.")
        check_version(value["cancelled_version"], lesson_json(event)["version"])
        conflict = db.scalar(
            select(CalendarEvent.id)
            .where(
                CalendarEvent.user_id == event.user_id,
                CalendarEvent.event_kind.in_(SCHEDULE_KINDS if removing else LESSON_KINDS),
                or_(CalendarEvent.attendance_status.is_(None), CalendarEvent.attendance_status != "cancelled"),
                CalendarEvent.starts_at < event.ends_at,
                CalendarEvent.ends_at > event.starts_at,
            )
            .limit(1)
        )
        restored_status = event.attendance_status if removing else value["status"]
        if conflict and restored_status != "cancelled" and (
            not removing or utc(event.ends_at or event.starts_at) > datetime.now(UTC)
        ):
            raise HTTPException(409, "Khôi phục sẽ trùng buổi mới. Sửa lịch mới trước.")
        targets.append((event, value["status"], value.get("event_kind", event.event_kind)))
    for event, status, kind in targets:
        if not removing:
            event.attendance_status = status
        event.event_kind = kind
        record_change(
            db,
            actor_user_id=user_id,
            action="calendar.updated",
            entity_type="calendar_event",
            entity_id=event.id,
            course_id=event.course_id,
            metadata={"restored_batch": batch.id},
        )
    batch.restored_at = datetime.now(UTC)
    db.commit()
    return public_preview(batch)
