"""Small, enrollment-scoped course lifecycle for the single-web demo."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.course_source.db import Base, get_db
from src.course_source.integration_api import require_service_key
from src.course_source.models import Course, CourseLifecycle, Enrollment, GoogleIdentity, User
from src.course_source.teacher_management import StrictModel, VersionInput, check_version, revision
from src.course_source.telemetry import record_change

router = APIRouter(prefix="/api/pacewise/v1/teacher", dependencies=[Depends(require_service_key)])
_UNSET = object()


def instructor(db, user_id, *, for_update=True):
    user = db.get(User, user_id, with_for_update=for_update)
    if not user or user.role != "instructor":
        raise HTTPException(403, "Instructor account required")


def owned(db, user_id, course_id):
    db.get(User, user_id, with_for_update=True)
    if not db.scalar(
        select(Enrollment.id).where(
            Enrollment.user_id == user_id, Enrollment.course_id == course_id, Enrollment.role == "instructor"
        )
    ):
        raise HTTPException(403, "Instructor course enrollment required")
    course = db.get(Course, course_id, with_for_update=True)
    if not course:
        raise HTTPException(404, "Không tìm thấy môn học.")
    return course


def course_json(db, course, state=_UNSET):
    if state is _UNSET:
        state = db.get(CourseLifecycle, course.id)
    body = {
        "id": course.id,
        "code": course.code,
        "name": course.name,
        "term": course.term,
        "archived": bool(state and state.archived),
    }
    return {**body, "version": revision(body)}


class CourseInput(StrictModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[\w.-]+$")
    name: str = Field(min_length=1, max_length=255)
    term: str = Field(default="Demo", min_length=1, max_length=128)
    student_ids: list[int] = Field(default_factory=list, max_length=1000)
    invite_emails: list[str] = Field(default_factory=list, max_length=50)
    expected_version: str | None = Field(default=None, max_length=64)


@router.get("/courses")
def courses(user_id: int, db: Session = Depends(get_db)):
    instructor(db, user_id, for_update=False)
    rows = db.execute(
        select(Course, CourseLifecycle)
        .join(Enrollment)
        .outerjoin(CourseLifecycle, CourseLifecycle.course_id == Course.id)
        .where(Enrollment.user_id == user_id, Enrollment.role == "instructor")
        .order_by(Course.code)
    ).all()
    return [course_json(db, course, state) for course, state in rows]


@router.get("/roster")
def roster(user_id: int, db: Session = Depends(get_db)):
    instructor(db, user_id)
    # Demo directory: every student who completed Google sign-up can be
    # selected directly, even before joining a course. Preserve the existing
    # native/demo workflow for students already in one of this teacher's
    # courses, while keeping unrelated native accounts hidden.
    owned_ids = select(Enrollment.course_id).where(
        Enrollment.user_id == user_id,
        Enrollment.role == "instructor",
    )
    managed_student_ids = select(Enrollment.user_id).where(
        Enrollment.course_id.in_(owned_ids),
        Enrollment.role == "student",
    )
    google_student_ids = select(GoogleIdentity.user_id)
    members = db.scalars(
        select(User)
        .where(
            User.role == "student",
            or_(User.id.in_(google_student_ids), User.id.in_(managed_student_ids)),
        )
    ).all()
    # No emails, scores or evidence required by the enrollment picker.
    # Names are encrypted at rest, so database ordering would sort ciphertext.
    return [
        {"id": item.id, "name": item.full_name}
        for item in sorted(members, key=lambda item: (item.full_name.casefold(), item.id))
    ]


def check_code(db, code, except_id=None):
    from sqlalchemy import func

    query = select(Course.id).where(func.lower(Course.code) == code.lower())
    if except_id is not None:
        query = query.where(Course.id != except_id)
    if db.scalar(query):
        raise HTTPException(409, "Mã môn đã tồn tại. Chọn mã khác.")


@router.post("/courses", status_code=201)
def create_course(
    payload: CourseInput,
    user_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from src.course_source.membership import (
        auto_enroll_google_students,
        emails,
        invite_many,
        notify_membership,
        shared_catalog_teacher_id,
        throttle,
    )
    from src.course_source.models import User

    instructor(db, user_id)
    addresses = emails(payload.invite_emails)
    shared_catalog_owner = (
        settings.google_signup_auto_enroll_courses
        and shared_catalog_teacher_id(db, settings.google_signup_auto_enroll_teacher_email) == user_id
    )
    manual_invites = [] if shared_catalog_owner else addresses
    if manual_invites:
        throttle(db, user_id)
    db.get(User, user_id, with_for_update=True)
    check_code(db, payload.code)
    allowed = {item["id"] for item in roster(user_id, db)}
    if not set(payload.student_ids) <= allowed:
        raise HTTPException(
            403,
            "Chỉ thêm được sinh viên đã đăng ký bằng Google hoặc đang thuộc lớp bạn quản lý.",
        )
    row = Course(code=payload.code, name=payload.name, term=payload.term, color="#4169E1", published=True)
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Mã môn đã tồn tại. Tải lại danh sách và chọn mã khác.") from exc
    db.add(Enrollment(user_id=user_id, course_id=row.id, role="instructor"))
    db.add(CourseLifecycle(course_id=row.id, archived=False))
    db.flush()
    if shared_catalog_owner:
        auto_enroll_google_students(db, row.id, user_id, settings.google_signup_auto_enroll_teacher_email)
    for member in set(payload.student_ids):
        if not db.scalar(
            select(Enrollment.id).where(Enrollment.user_id == member, Enrollment.course_id == row.id)
        ):
            db.add(Enrollment(user_id=member, course_id=row.id, role="student"))
    db.flush()
    for member in set(payload.student_ids):
        notify_membership(db, row.id, member, user_id)
    if manual_invites:
        invite_many(db, row.id, user_id, manual_invites)
    record_change(
        db, actor_user_id=user_id, action="course.created", entity_type="course", entity_id=row.id, course_id=row.id
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Danh sách tham gia đã thay đổi; tải lại trước khi tạo môn.") from exc
    return course_json(db, row)


@router.put("/courses/{course_id}/info")
def update_course(course_id: int, payload: CourseInput, user_id: int, db: Session = Depends(get_db)):
    row = owned(db, user_id, course_id)
    check_version(payload.expected_version, course_json(db, row)["version"])
    if payload.student_ids or payload.invite_emails:
        raise HTTPException(422, "Chỉnh tên/mã môn không thay đổi danh sách sinh viên.")
    check_code(db, payload.code, row.id)
    row.code, row.name, row.term = payload.code, payload.name, payload.term
    record_change(
        db, actor_user_id=user_id, action="course.updated", entity_type="course", entity_id=row.id, course_id=row.id
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Mã môn đã được sử dụng; tải lại danh sách và chọn mã khác.") from exc
    return course_json(db, row)


@router.post("/courses/{course_id}/archive")
def archive(course_id: int, payload: VersionInput, user_id: int, db: Session = Depends(get_db)):
    row = owned(db, user_id, course_id)
    check_version(payload.expected_version, course_json(db, row)["version"])
    lifecycle = db.get(CourseLifecycle, row.id) or CourseLifecycle(course_id=row.id)
    lifecycle.archived = True
    db.add(lifecycle)
    record_change(
        db,
        actor_user_id=user_id,
        action="course.updated",
        entity_type="course",
        entity_id=row.id,
        course_id=row.id,
        metadata={"archived": True},
    )
    db.commit()
    return course_json(db, row)


@router.post("/courses/{course_id}/restore")
def restore(
    course_id: int,
    payload: VersionInput,
    user_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    row = owned(db, user_id, course_id)
    check_version(payload.expected_version, course_json(db, row)["version"])
    lifecycle = db.get(CourseLifecycle, row.id)
    if lifecycle:
        lifecycle.archived = False
    db.flush()
    if settings.google_signup_auto_enroll_courses:
        from src.course_source.membership import auto_enroll_google_students

        auto_enroll_google_students(db, row.id, user_id, settings.google_signup_auto_enroll_teacher_email)
    record_change(
        db,
        actor_user_id=user_id,
        action="course.updated",
        entity_type="course",
        entity_id=row.id,
        course_id=row.id,
        metadata={"archived": False},
    )
    db.commit()
    return course_json(db, row)


@router.post("/courses/{course_id}/delete-empty")
def delete_empty(course_id: int, payload: VersionInput, user_id: int, db: Session = Depends(get_db)):
    row = owned(db, user_id, course_id)
    check_version(payload.expected_version, course_json(db, row)["version"])
    if len(courses(user_id, db)) <= 1:
        raise HTTPException(409, "Không xóa môn cuối cùng.")
    # Check every course-linked domain table, not just visible tasks/lessons.
    for table in Base.metadata.sorted_tables:
        if "course_id" in table.c and table.name not in {
            "course_lifecycle",
            "enrollments",
            "audit_logs",
            "integration_events",
        }:
            if db.execute(select(table.c.course_id).where(table.c.course_id == course_id).limit(1)).first():
                raise HTTPException(409, "Môn đã có dữ liệu. Hãy lưu trữ để giữ lịch sử.")
    enrollments = db.scalars(select(Enrollment).where(Enrollment.course_id == course_id)).all()
    if len(enrollments) != 1 or enrollments[0].user_id != user_id or enrollments[0].progress:
        raise HTTPException(409, "Môn đã có người học. Hãy lưu trữ thay vì xóa.")
    record_change(
        db, actor_user_id=user_id, action="course.deleted", entity_type="course", entity_id=row.id, course_id=row.id
    )
    for item in enrollments:
        db.delete(item)
    lifecycle = db.get(CourseLifecycle, row.id)
    if lifecycle:
        db.delete(lifecycle)
    db.flush()
    db.delete(row)
    db.commit()
    return {"status": "deleted"}
