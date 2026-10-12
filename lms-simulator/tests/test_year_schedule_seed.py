from datetime import UTC, datetime

from app.db import Base
from app.extended_api import CourseActivityRequest, create_course_activity
from app.models import (
    Assignment,
    CalendarEvent,
    Course,
    CourseContent,
    CourseModule,
    Enrollment,
    ModuleItem,
    QuizQuestion,
    Resource,
    User,
)
from app.security import hash_password
from app.year_schedule_seed import COURSE_SCHEDULES, seed_2026_demo_calendars
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


def _database() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, autoflush=False)
    student = User(
        email="student@canvas.local",
        full_name="Demo Student",
        password_hash=hash_password("demo123"),
        role="student",
        avatar_color="#2563eb",
    )
    teacher = User(
        email="teacher@canvas.local",
        full_name="Demo Teacher",
        password_hash=hash_password("demo123"),
        role="instructor",
        avatar_color="#7c3aed",
    )
    db.add_all([student, teacher])
    for schedule in COURSE_SCHEDULES:
        course = Course(code=schedule.code, name=schedule.code, term="2026", color="#2563eb")
        db.add(course)
        db.flush()
        db.add(Enrollment(user_id=student.id, course_id=course.id, role="student", progress=0))
        db.add(Enrollment(user_id=teacher.id, course_id=course.id, role="instructor", progress=100))
    db.commit()
    return db


def test_year_schedule_covers_2026_and_is_idempotent() -> None:
    with _database() as db:
        seed_2026_demo_calendars(db)
        counts = {
            "events": db.scalar(select(func.count(CalendarEvent.id))),
            "assignments": db.scalar(select(func.count(Assignment.id))),
            "videos": db.scalar(select(func.count(Resource.id)).where(Resource.kind == "video")),
            "quizzes": db.scalar(select(func.count(CourseContent.id)).where(CourseContent.kind == "quiz")),
        }
        starts = db.scalars(select(CalendarEvent.starts_at).order_by(CalendarEvent.starts_at)).all()

        assert counts["events"] == 498
        assert counts["assignments"] == 36
        assert counts["videos"] == 36
        assert counts["quizzes"] == 48
        assert starts[0].replace(tzinfo=UTC).year == 2026
        assert starts[-1].replace(tzinfo=UTC).year == 2026
        assert {value.month for value in starts} == set(range(1, 13))
        assert any("Thi giữa kỳ" in item for item in db.scalars(select(CalendarEvent.title)))
        assert any("Thi cuối kỳ" in item for item in db.scalars(select(CalendarEvent.title)))
        assignment_counts = {
            code: db.scalar(
                select(func.count(Assignment.id))
                .join(Course, Course.id == Assignment.course_id)
                .where(Course.code == code)
            )
            for code in ("CS101", "DS201", "PM102")
        }
        assert assignment_counts == {"CS101": 11, "DS201": 12, "PM102": 13}

        discrete_math = db.scalar(select(Course).where(Course.code == "DS201"))
        assert discrete_math is not None
        assert discrete_math.name == "Toán rời rạc — Chương 3: Quan hệ hai ngôi"
        discrete_math_assignments = db.scalars(
            select(Assignment.title).where(Assignment.course_id == discrete_math.id)
        ).all()
        assert "BTVN 2026 T10.1: 3.1 Khái niệm quan hệ hai ngôi và tính chất" in discrete_math_assignments
        assert not any(
            legacy.casefold() in title.casefold()
            for title in discrete_math_assignments
            for legacy in ("làm sạch dữ liệu", "trực quan hóa", "dashboard", "phân tích mô tả")
        )
        chapter_module = db.scalar(
            select(CourseModule).where(
                CourseModule.course_id == discrete_math.id,
                CourseModule.name == "Chương 3: Quan hệ hai ngôi",
            )
        )
        assert chapter_module is not None
        chapter_items = db.scalars(
            select(ModuleItem)
            .where(ModuleItem.module_id == chapter_module.id)
            .order_by(ModuleItem.position)
        ).all()
        assert [item.title for item in chapter_items[:3]] == [
            "3.1 Khái niệm quan hệ hai ngôi và tính chất",
            "3.2 Quan hệ tương đương",
            "3.3 Quan hệ thứ tự",
        ]
        assert chapter_items[0].item_type == "file"
        assert chapter_items[0].external_url == "/static/mock-files/TRR_Full_P4.pdf"
        assert all(item.item_type == "page" and not item.external_url for item in chapter_items[1:3])
        linked_assignments = {item.content_id for item in chapter_items if item.item_type == "assignment"}
        chapter_assignments = db.scalars(select(Assignment).where(Assignment.course_id == discrete_math.id)).all()
        expected = {item.id for item in chapter_assignments if "3.1" in item.title or "Chương 3" in item.title}
        assert expected <= linked_assignments
        assert any(item.item_type == "file" and item.content_id is not None for item in chapter_items)
        chapter_quiz = db.scalar(
            select(CourseContent).where(
                CourseContent.course_id == discrete_math.id,
                CourseContent.title == "Quiz Chương 3: Quan hệ hai ngôi",
            )
        )
        assert chapter_quiz is not None
        assert db.scalar(
            select(func.count(QuizQuestion.id)).where(QuizQuestion.quiz_id == chapter_quiz.id)
        ) == 5
        assert db.scalar(
            select(func.count(Resource.id)).where(
                Resource.course_id == discrete_math.id,
                Resource.source_url == "/static/mock-files/TRR_Full_P4.pdf",
            )
        ) == 1
        discrete_math_events = db.scalars(
            select(CalendarEvent).where(CalendarEvent.course_id == discrete_math.id)
        ).all()
        demo_online = [
            item
            for item in discrete_math_events
            if item.title == "[DS201] Học online · Chương 3: Quan hệ hai ngôi (3.1–3.3) · 120 phút"
        ]
        demo_offline = [
            item
            for item in discrete_math_events
            if item.title == "[DS201] Học tại lớp · Chương 3: Quan hệ hai ngôi (3.1–3.3) · 90 phút"
        ]
        assert len(demo_online) == 2
        assert len(demo_offline) == 2
        assert not any(
            legacy.casefold() in item.title.casefold()
            for item in discrete_math_events
            for legacy in ("làm sạch dữ liệu", "trực quan hóa", "dashboard", "phân tích mô tả")
        )
        online_classes = db.scalars(
            select(CalendarEvent).where(CalendarEvent.event_kind == "class_session")
        ).all()
        assert online_classes
        assert all(item.join_url for item in online_classes)
        assert all(item.attendance_status == "scheduled" for item in online_classes)
        offline_classes = db.scalars(
            select(CalendarEvent).where(CalendarEvent.event_kind == "class")
        ).all()
        assert len(offline_classes) == 6
        assert all(item.join_url is None for item in offline_classes)

        teacher = db.scalar(select(User).where(User.email == "teacher@canvas.local"))
        assert teacher is not None
        q4_titles = db.scalars(
            select(CalendarEvent.title).where(
                CalendarEvent.user_id == teacher.id,
                CalendarEvent.starts_at >= datetime(2026, 10, 1, tzinfo=UTC),
                CalendarEvent.starts_at < datetime(2027, 1, 1, tzinfo=UTC),
            )
        ).all()
        assert any("Ca học online" in title for title in q4_titles)
        assert any("Video tháng" in title for title in q4_titles)
        assert any("Quiz tháng" in title for title in q4_titles)
        assert any("Thi giữa kỳ học kỳ 1" in title for title in q4_titles)
        assert any("Thi cuối kỳ" in title for title in q4_titles)
        assert any("Học tại lớp" in title for title in q4_titles)
        assert any("Quiz tuần 05/10" in title for title in q4_titles)

        link_count = db.scalar(select(func.count(ModuleItem.id)))
        seed_2026_demo_calendars(db)
        assert db.scalar(select(func.count(ModuleItem.id))) == link_count

        assert db.scalar(select(func.count(CalendarEvent.id))) == counts["events"]
        assert db.scalar(select(func.count(Assignment.id))) == counts["assignments"]
        assert db.scalar(select(func.count(Resource.id)).where(Resource.kind == "video")) == counts["videos"]
        assert db.scalar(select(func.count(CourseContent.id)).where(CourseContent.kind == "quiz")) == counts["quizzes"]
        assert db.scalar(
            select(func.count(Resource.id)).where(
                Resource.course_id == discrete_math.id,
                Resource.source_url == "/static/mock-files/TRR_Full_P4.pdf",
            )
        ) == 1


def test_instructor_can_add_full_activity_set_to_an_existing_course() -> None:
    with _database() as db:
        teacher = db.scalar(select(User).where(User.email == "teacher@canvas.local"))
        course = db.scalar(select(Course).where(Course.code == "CS101"))
        assert teacher is not None and course is not None
        base = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)

        activity_specs = (
            ("class_session", "Online class", 2),
            ("lecture_video", "Lecture video", 1),
            ("quiz", "Weekly quiz", 1),
            ("assignment", "Homework", 1),
            ("midterm", "Midterm exam", 1),
            ("final_exam", "Final exam", 1),
        )
        for index, (activity_type, title, repeat_count) in enumerate(activity_specs):
            starts_at = base.replace(day=base.day + index)
            create_course_activity(
                course.id,
                CourseActivityRequest(
                    user_id=teacher.id,
                    activity_type=activity_type,
                    title=title,
                    starts_at=starts_at,
                    ends_at=(
                        None
                        if activity_type == "assignment"
                        else starts_at.replace(hour=11)
                    ),
                    repeat_count=repeat_count,
                    source_url="https://example.test/video" if activity_type == "lecture_video" else "",
                    points_possible=20,
                ),
                db,
            )

        assert db.scalar(select(func.count(CalendarEvent.id))) == 12
        assert db.scalar(select(func.count(Resource.id)).where(Resource.kind == "video")) == 1
        # Homework plus the quiz-backed quiz/midterm/final assignments.
        assert db.scalar(select(func.count(Assignment.id))) == 4
        assert db.scalar(select(func.count(CourseContent.id)).where(CourseContent.kind == "quiz")) == 3
        online = db.scalars(
            select(CalendarEvent).where(CalendarEvent.event_kind == "class_session")
        ).all()
        assert len(online) == 4
        assert all(item.join_url for item in online)
