"""Demo fixtures must never populate courses managed by the teacher."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.course_source.models import (
    Assignment,
    CalendarEvent,
    Course,
    CourseLifecycle,
    TeacherTaskMetadata,
    TeachingEventLink,
)

DEMO_COURSE_CODES = ("CS101", "DS201", "PM102")


def mark_teacher_managed(db: Session, course_id: int) -> None:
    # Lifecycle presence opts out of future fixture seeding, even while active.
    if db.get(CourseLifecycle, course_id) is None and not any(
        isinstance(row, CourseLifecycle) and row.course_id == course_id for row in db.new
    ):
        db.add(CourseLifecycle(course_id=course_id, archived=False))


def demo_courses(db: Session) -> Sequence[Course]:
    # Existing volumes may contain authoring records from before lifecycle markers.
    authored_tasks = select(Assignment.course_id).join(TeacherTaskMetadata)
    authored_lessons = (
        select(CalendarEvent.course_id).join(TeachingEventLink).where(CalendarEvent.course_id.is_not(None))
    )
    return db.scalars(
        select(Course)
        .where(
            Course.code.in_(DEMO_COURSE_CODES),
            Course.id.not_in(select(CourseLifecycle.course_id)),
            Course.id.not_in(authored_tasks),
            Course.id.not_in(authored_lessons),
        )
        .order_by(Course.id)
    ).all()
