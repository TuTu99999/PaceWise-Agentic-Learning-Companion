"""Course-scoped membership. Invitations never assert ownership of an email."""

import hashlib
import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select

from src.course_source.course_management import owned, roster
from src.course_source.models import (
    CalendarEvent,
    Course,
    CourseInvitation,
    CourseLifecycle,
    Enrollment,
    GoogleIdentity,
    IntegrationEvent,
    MembershipThrottle,
    TeachingEventLink,
    User,
)
from src.course_source.teacher_management import utc
from src.course_source.telemetry import record_change

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def emails(values):
    result = sorted({value.strip().lower() for value in values})
    if len(result) > 50 or any(len(value) > 254 or not EMAIL.fullmatch(value) for value in result):
        raise HTTPException(422, "Nhập tối đa 50 email hợp lệ.")
    return result


def throttle(db, user_id):
    # Actor lock makes the persistent per-user limit atomic across replicas.
    if not db.get(User, user_id, with_for_update=True):
        raise HTTPException(401, "Authentication required")
    now = datetime.now(UTC)
    row = db.get(MembershipThrottle, user_id)
    if not row:
        row = MembershipThrottle(user_id=user_id, window_start=now, requests=0)
        db.add(row)
    if utc(row.window_start) <= now - timedelta(minutes=10):
        row.window_start, row.requests = now, 0
    if row.requests >= 30:
        raise HTTPException(429, "Thao tác quá nhanh. Vui lòng thử lại sau.", headers={"Retry-After": "600"})
    row.requests += 1
    db.commit()  # Charge invalid attempts too; caller begins its own write transaction.


def active_course(db, course_id, teacher_id):
    course = owned(db, teacher_id, course_id)
    lifecycle = db.get(CourseLifecycle, course_id)
    if lifecycle and lifecycle.archived:
        raise HTTPException(409, "Khôi phục môn trước khi quản lý sinh viên.")
    return course


def invitation_status(invite):
    if invite.revoked_at:
        return "revoked"
    if invite.accepted_at:
        return "accepted"
    return "expired" if utc(invite.expires_at) <= datetime.now(UTC) else "pending"


def invite_json(invite):
    """Teacher-facing invitation state.

    The acceptance secret is deliberately server-only.  Returning it here turns
    an ordinary roster action into a bearer-link workflow and leaks the secret
    into browser history, clipboard managers and frontend logs.
    """
    return {
        "id": invite.id,
        "email": invite.email,
        "status": invitation_status(invite),
        "expiresAt": utc(invite.expires_at).isoformat(),
    }


def members(db, course_id, teacher_id):
    active_course(db, course_id, teacher_id)
    students = db.scalars(
        select(User).join(Enrollment).where(Enrollment.course_id == course_id, Enrollment.role == "student")
    ).all()
    invitations = db.scalars(
        select(CourseInvitation)
        .where(CourseInvitation.course_id == course_id)
        .order_by(CourseInvitation.created_at.desc())
        .limit(500)
    ).all()
    return {
        "students": sorted([{"id": user.id, "name": user.full_name} for user in students], key=lambda row: row["name"]),
        "invitations": [invite_json(invite) for invite in invitations],
    }


def invite_many(db, course_id, teacher_id, addresses):
    active_course(db, course_id, teacher_id)  # Serializes create/revoke/accept for this course.
    active = db.scalar(
        select(func.count())
        .select_from(CourseInvitation)
        .where(
            CourseInvitation.course_id == course_id,
            CourseInvitation.revoked_at.is_(None),
            CourseInvitation.accepted_at.is_(None),
            CourseInvitation.expires_at > datetime.now(UTC),
        )
    )
    new_count = 0
    result = []
    for email in emails(addresses):
        pending = db.scalar(
            select(CourseInvitation).where(
                CourseInvitation.course_id == course_id,
                CourseInvitation.email == email,
                CourseInvitation.revoked_at.is_(None),
                CourseInvitation.accepted_at.is_(None),
                CourseInvitation.expires_at > datetime.now(UTC),
            )
        )
        if pending:
            result.append(invite_json(pending))
            continue
        if active + new_count >= 500:
            raise HTTPException(409, "Môn đã có 500 lời mời đang chờ. Hủy lời mời không dùng trước khi tạo thêm.")
        new_count += 1
        token = secrets.token_urlsafe(32)
        invite = CourseInvitation(
            id=str(uuid4()),
            course_id=course_id,
            inviter_id=teacher_id,
            email=email,
            token=token,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        db.add(invite)
        db.flush()
        result.append(invite_json(invite))
        record_change(
            db,
            actor_user_id=teacher_id,
            action="invitation.created",
            entity_type="invitation",
            entity_id=invite.id,
            course_id=course_id,
            emit_event=False,
        )
        target_user_id = db.scalar(
            select(User.id)
            .join(GoogleIdentity, GoogleIdentity.user_id == User.id)
            .where(User.email == email, User.role == "student")
        )
        if target_user_id is not None:
            db.add(
                IntegrationEvent(
                    event_type="invitation.changed",
                    aggregate_type="invitation",
                    aggregate_id=invite.id,
                    course_id=None,
                    actor_user_id=teacher_id,
                    payload_json=json.dumps({"target_user_id": target_user_id}),
                )
            )
    # The response never discloses whether the invited email has an account.
    return result


def notify_membership(db, course_id, user_id, actor_id):
    record_change(
        db,
        actor_user_id=actor_id,
        action="enrollment.changed",
        entity_type="enrollment",
        entity_id=user_id,
        course_id=course_id,
        emit_event=False,
    )
    # Course-less targeted invalidation also reaches a subscriber with no courses yet.
    db.add(
        IntegrationEvent(
            event_type="enrollment.changed",
            aggregate_type="enrollment",
            aggregate_id=str(user_id),
            course_id=None,
            actor_user_id=actor_id,
            payload_json=json.dumps({"target_user_id": user_id}),
        )
    )


def copy_lessons(db, course_id, user_id):
    existing = set(
        db.scalars(
            select(TeachingEventLink.occurrence_key)
            .join(CalendarEvent)
            .where(CalendarEvent.course_id == course_id, CalendarEvent.user_id == user_id)
        )
    )
    teachers = select(Enrollment.user_id).where(Enrollment.course_id == course_id, Enrollment.role == "instructor")
    rows = db.execute(
        select(CalendarEvent, TeachingEventLink.occurrence_key)
        .join(TeachingEventLink)
        .where(CalendarEvent.course_id == course_id, CalendarEvent.user_id.in_(teachers))
        .order_by(CalendarEvent.id)
    ).all()
    for event, key in rows:
        if key in existing:
            continue
        copied = CalendarEvent(
            user_id=user_id,
            course_id=course_id,
            title=event.title,
            description=event.description,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            event_kind=event.event_kind,
            join_url=event.join_url,
            attendance_status=None,
        )
        db.add(copied)
        db.flush()
        db.add(TeachingEventLink(calendar_event_id=copied.id, occurrence_key=key))
        existing.add(key)


def remove_member(db, course_id, teacher_id, student_id):
    active_course(db, course_id, teacher_id)
    enrolled = db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == student_id, Enrollment.role == "student"
        )
    )
    if enrolled:
        db.delete(enrolled)
        # Removing someone also invalidates old accepted/pending links to this course.
        user = db.get(User, student_id)
        now = datetime.now(UTC)
        for invite in db.scalars(select(CourseInvitation).where(CourseInvitation.course_id == course_id)).all():
            if invite.accepted_by == student_id or (user and invite.email == user.email.lower()):
                invite.revoked_at = now
        notify_membership(db, course_id, student_id, teacher_id)
    # Preserve calendar/evidence/history; live membership hides course-owned content.


def add_members(db, course_id, teacher_id, student_ids):
    active_course(db, course_id, teacher_id)
    selected = set(student_ids)
    allowed = {student["id"] for student in roster(teacher_id, db)}
    if not selected <= allowed:
        raise HTTPException(403, "Chỉ chọn sinh viên đang thuộc lớp bạn quản lý; người mới cần lời mời email.")
    current = set(db.scalars(select(Enrollment.user_id).where(Enrollment.course_id == course_id)))
    for student_id in selected - current:
        db.add(Enrollment(course_id=course_id, user_id=student_id, role="student"))
        db.flush()
        copy_lessons(db, course_id, student_id)
        notify_membership(db, course_id, student_id, teacher_id)
    return sorted(selected - current)


def revoke(db, course_id, teacher_id, invite_id):
    active_course(db, course_id, teacher_id)
    invite = db.get(CourseInvitation, invite_id)
    if not invite or invite.course_id != course_id:
        raise HTTPException(404, "Không tìm thấy lời mời.")
    if invite.accepted_at:
        raise HTTPException(409, "Sinh viên đã tham gia. Dùng Gỡ khỏi môn để ngừng cấp quyền.")
    invite.revoked_at = datetime.now(UTC)


def _verified_invite_for_user(db, user_id, invite):
    user = db.get(User, user_id, with_for_update=True)
    if not user or user.role != "student":
        raise HTTPException(403, "Chỉ tài khoản sinh viên được tham gia môn.")
    if not db.scalar(select(GoogleIdentity.user_id).where(GoogleIdentity.user_id == user_id)):
        raise HTTPException(403, "Cần đăng nhập bằng tài khoản Google đã xác minh để nhận lời mời email.")
    if not invite:
        raise HTTPException(404, "Lời mời không khả dụng cho tài khoản này.")
    db.get(Course, invite.course_id, with_for_update=True)
    db.refresh(invite)
    state = db.get(CourseLifecycle, invite.course_id)
    if (
        invite.email != user.email.lower()
        or invite.revoked_at
        or utc(invite.expires_at) <= datetime.now(UTC)
        or (state and state.archived)
        or (invite.accepted_by is not None and invite.accepted_by != user_id)
    ):
        raise HTTPException(404, "Lời mời không khả dụng cho tài khoản này.")
    return user, invite


def my_invites(db, user_id):
    """Return only invitations addressed to the verified signed-in identity."""
    user = db.get(User, user_id)
    if not user or user.role != "student":
        raise HTTPException(403, "Chỉ tài khoản sinh viên được xem lời mời môn học.")
    if not db.scalar(select(GoogleIdentity.user_id).where(GoogleIdentity.user_id == user_id)):
        return []
    now = datetime.now(UTC)
    rows = db.scalars(
        select(CourseInvitation)
        .where(
            CourseInvitation.email == user.email.lower(),
            CourseInvitation.revoked_at.is_(None),
            CourseInvitation.accepted_at.is_(None),
            CourseInvitation.expires_at > now,
        )
        .order_by(CourseInvitation.created_at.desc())
        .limit(100)
    ).all()
    result = []
    for invite in rows:
        course = db.get(Course, invite.course_id)
        lifecycle = db.get(CourseLifecycle, invite.course_id)
        if not course or (lifecycle and lifecycle.archived):
            continue
        teacher = db.get(User, invite.inviter_id)
        result.append(
            {
                "id": invite.id,
                "courseId": course.id,
                "code": course.code,
                "name": course.name,
                "term": course.term,
                "teacher": teacher.full_name if teacher else "Giảng viên",
                "expiresAt": utc(invite.expires_at).isoformat(),
            }
        )
    return result


def accept_my_invite(db, user_id, invite_id):
    user, invite = _verified_invite_for_user(db, user_id, db.get(CourseInvitation, invite_id))
    if not db.scalar(
        select(Enrollment.id).where(Enrollment.course_id == invite.course_id, Enrollment.user_id == user_id)
    ):
        db.add(Enrollment(user_id=user_id, course_id=invite.course_id, role="student"))
        db.flush()
        # Copying uses a stable occurrence key, so retries cannot duplicate lessons.
        copy_lessons(db, invite.course_id, user_id)
        notify_membership(db, invite.course_id, user_id, user_id)
    invite.accepted_at = invite.accepted_at or datetime.now(UTC)
    invite.accepted_by = user.id
    return {"courseId": invite.course_id, "joined": True}


