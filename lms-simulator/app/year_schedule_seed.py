"""Deterministic 2026 learning calendars for demo learners and instructors.

The calendar deliberately keeps each visible entry to a concise title. Detailed
duration and source metadata remain in the LMS records so PaceWise can build a
multi-course plan without turning the calendar into a wall of text.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    ResourceVersion,
    Submission,
    User,
)

LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PRIMARY_STUDENT_EMAIL = "student@canvas.local"
CALENDAR_USER_EMAILS = (PRIMARY_STUDENT_EMAIL, "teacher@canvas.local")
SEED_MARKER = "pacewise-2026-v1"
DISCRETE_MATH_COURSE_NAME = "Toán rời rạc — Chương 3: Quan hệ hai ngôi"
DISCRETE_MATH_MODULE_NAME = "Chương 3: Quan hệ hai ngôi"
DISCRETE_MATH_PDF_URL = "/static/mock-files/TRR_Full_P4.pdf"
DISCRETE_MATH_TOPICS = (
    "3.1 Khái niệm quan hệ hai ngôi và tính chất",
    "3.2 Quan hệ tương đương",
    "3.3 Quan hệ thứ tự",
    "Bài tập tổng hợp Chương 3",
)
DISCRETE_MATH_DEMO_ONLINE_TITLE = (
    "[DS201] Học online · Chương 3: Quan hệ hai ngôi (3.1–3.3) · 120 phút"
)
DISCRETE_MATH_DEMO_OFFLINE_TITLE = (
    "[DS201] Học tại lớp · Chương 3: Quan hệ hai ngôi (3.1–3.3) · 90 phút"
)

DISCRETE_MATH_QUIZ_QUESTIONS = (
    (
        "Cho hai tập A, B khác rỗng. Một quan hệ hai ngôi từ A đến B là gì?",
        '["Một phần tử của A", "Một tập con của A × B", "Một hàm từ B đến A", "Một tập con của A ∪ B"]',
        "Một tập con của A × B",
    ),
    (
        "Điều kiện nào mô tả tính phản xạ của quan hệ R trên A?",
        '["Mọi a ∈ A đều có aRa", "aRb thì bRa", "aRb và bRa thì a = b", "aRb và bRc thì aRc"]',
        "Mọi a ∈ A đều có aRa",
    ),
    (
        "Một quan hệ tương đương phải đồng thời có những tính chất nào?",
        '["Phản xạ, đối xứng, bắc cầu", "Phản xạ, phản đối xứng, bắc cầu", "Đối xứng, phản đối xứng", "Chỉ cần bắc cầu"]',
        "Phản xạ, đối xứng, bắc cầu",
    ),
    (
        "Một quan hệ thứ tự bộ phận phải đồng thời có những tính chất nào?",
        '["Phản xạ, đối xứng, bắc cầu", "Phản xạ, phản đối xứng, bắc cầu", "Đối xứng, bắc cầu", "Chỉ cần phản đối xứng"]',
        "Phản xạ, phản đối xứng, bắc cầu",
    ),
    (
        "Nếu aRb và bRc luôn kéo theo aRc thì R có tính chất gì?",
        '["Phản xạ", "Đối xứng", "Phản đối xứng", "Bắc cầu"]',
        "Bắc cầu",
    ),
)


@dataclass(frozen=True)
class CourseSchedule:
    code: str
    class_weekday: int
    class_start: time
    class_minutes: int
    video_minutes: int
    quiz_minutes: int
    midterm_minutes: int
    final_minutes: int
    topics: tuple[str, ...]


COURSE_SCHEDULES = (
    CourseSchedule(
        code="CS101",
        class_weekday=0,
        class_start=time(8, 0),
        class_minutes=90,
        video_minutes=40,
        quiz_minutes=20,
        midterm_minutes=90,
        final_minutes=120,
        topics=("Biến và kiểu dữ liệu", "Hàm", "Vòng lặp", "Cấu trúc dữ liệu"),
    ),
    CourseSchedule(
        code="DS201",
        class_weekday=2,
        class_start=time(13, 30),
        class_minutes=120,
        video_minutes=50,
        quiz_minutes=25,
        midterm_minutes=90,
        final_minutes=120,
        topics=DISCRETE_MATH_TOPICS,
    ),
    CourseSchedule(
        code="PM102",
        class_weekday=4,
        class_start=time(9, 0),
        class_minutes=90,
        video_minutes=35,
        quiz_minutes=15,
        midterm_minutes=75,
        final_minutes=90,
        topics=("Project charter", "Quản trị rủi ro", "Lập kế hoạch sprint", "Retrospective"),
    ),
)


def _local_datetime(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=LOCAL_TZ).astimezone(UTC)


def _weekly_dates(weekday: int) -> list[date]:
    current = date(2026, 1, 1)
    current += timedelta(days=(weekday - current.weekday()) % 7)
    result: list[date] = []
    while current <= date(2026, 12, 31):
        result.append(current)
        current += timedelta(days=7)
    return result


def _event_key(event: CalendarEvent) -> tuple[int | None, str, datetime]:
    starts_at = event.starts_at
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)
    return event.course_id, event.title, starts_at.astimezone(UTC).replace(microsecond=0)


def _add_event(
    db: Session,
    existing: set[tuple[int | None, str, datetime]],
    *,
    user_id: int,
    course_id: int,
    title: str,
    starts_at: datetime,
    minutes: int,
    kind: str,
) -> None:
    starts_at = starts_at.astimezone(UTC).replace(microsecond=0)
    key = course_id, title, starts_at
    if key in existing:
        return
    event = CalendarEvent(
        user_id=user_id,
        course_id=course_id,
        title=title,
        description=f"{SEED_MARKER}; kind={kind}; duration_minutes={minutes}",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=minutes),
        event_kind=kind,
        attendance_status="scheduled" if kind == "class_session" else None,
    )
    db.add(event)
    db.flush()
    if kind == "class_session":
        event.join_url = f"/api/calendar/events/{event.id}/join"
    existing.add(key)


def _seed_classes(
    db: Session,
    existing_events: set[tuple[int | None, str, datetime]],
    student: User,
    course: Course,
    schedule: CourseSchedule,
) -> None:
    for week_index, day in enumerate(_weekly_dates(schedule.class_weekday)):
        topic = schedule.topics[week_index % len(schedule.topics)]
        title = f"[{course.code}] Ca học online: {topic} · {schedule.class_minutes} phút"
        if course.code == "DS201" and day == date(2026, 10, 7):
            title = DISCRETE_MATH_DEMO_ONLINE_TITLE
        _add_event(
            db,
            existing_events,
            user_id=student.id,
            course_id=course.id,
            title=title,
            starts_at=_local_datetime(day, schedule.class_start),
            minutes=schedule.class_minutes,
            kind="class_session",
        )


def _seed_monthly_videos_and_quizzes(
    db: Session,
    existing_events: set[tuple[int | None, str, datetime]],
    student: User,
    course: Course,
    schedule: CourseSchedule,
) -> None:
    resources = {
        item.title
        for item in db.scalars(select(Resource).where(Resource.course_id == course.id)).all()
    }
    quiz_titles = {
        item.title
        for item in db.scalars(
            select(CourseContent).where(
                CourseContent.course_id == course.id,
                CourseContent.kind == "quiz",
            )
        ).all()
    }

    for month in range(1, 13):
        topic = schedule.topics[(month - 1) % len(schedule.topics)]
        video_title = f"Video tháng {month:02d}: {topic} · {schedule.video_minutes} phút"
        if video_title not in resources:
            db.add(
                Resource(
                    course_id=course.id,
                    title=video_title,
                    kind="video",
                    source_url=f"/mock-videos/{course.code.lower()}-2026-{month:02d}.mp4",
                )
            )
            resources.add(video_title)
        video_day = date(2026, month, 5)
        _add_event(
            db,
            existing_events,
            user_id=student.id,
            course_id=course.id,
            title=f"[{course.code}] {video_title}",
            starts_at=_local_datetime(video_day, time(19, 0)),
            minutes=schedule.video_minutes,
            kind="lecture_video",
        )

        quiz_title = f"Quiz tháng {month:02d} · {schedule.quiz_minutes} phút"
        quiz_start = _local_datetime(date(2026, month, 20), time(20, 0))
        if quiz_title not in quiz_titles:
            quiz = CourseContent(
                course_id=course.id,
                kind="quiz",
                title=quiz_title,
                body=f"Kiểm tra ngắn về {topic}. Thời lượng {schedule.quiz_minutes} phút.",
                due_at=quiz_start + timedelta(minutes=schedule.quiz_minutes),
                points_possible=10,
                published=True,
            )
            db.add(quiz)
            db.flush()
            db.add(
                QuizQuestion(
                    quiz_id=quiz.id,
                    prompt=f"Khái niệm nào phù hợp nhất với chủ đề {topic}?",
                    options_json='["A", "B", "C", "D"]',
                    correct_answer="A",
                    points=1,
                    position=1,
                )
            )
            quiz_titles.add(quiz_title)
        _add_event(
            db,
            existing_events,
            user_id=student.id,
            course_id=course.id,
            title=f"[{course.code}] {quiz_title}",
            starts_at=quiz_start,
            minutes=schedule.quiz_minutes,
            kind="quiz",
        )


def _seed_homework(
    db: Session,
    student: User | None,
    course: Course,
    schedule: CourseSchedule,
) -> None:
    existing = {
        item.title: item
        for item in db.scalars(select(Assignment).where(Assignment.course_id == course.id)).all()
    }
    specs = (
        (1, date(2026, 3, 29), 10.0),
        (2, date(2026, 6, 28), 12.0),
        (3, date(2026, 9, 27), 15.0),
        (4, date(2026, 12, 27), 20.0),
    )
    for quarter, due_day, points in specs:
        topic = schedule.topics[(quarter - 1) % len(schedule.topics)]
        title = f"BTVN 2026 Q{quarter}: {topic}"
        assignment = existing.get(title)
        if assignment is None:
            due_at = _local_datetime(due_day, time(23, 59))
            assignment = Assignment(
                course_id=course.id,
                title=title,
                description=(
                    f"Bài tập về nhà chủ đề {topic}. Hạn nộp {due_day:%d/%m/%Y} lúc 23:59. "
                    f"Thời gian dự kiến {int(points * 12)} phút."
                ),
                due_at=due_at,
                points_possible=points,
                published=True,
            )
            db.add(assignment)
            db.flush()
            existing[title] = assignment

        # Keep the demo workspace useful in October: Q1/Q2 are completed,
        # Q3 is visibly overdue, and Q4 remains upcoming for planning.
        if student is not None and quarter <= 2 and not db.scalar(
            select(Submission).where(
                Submission.assignment_id == assignment.id,
                Submission.user_id == student.id,
            )
        ):
            db.add(
                Submission(
                    assignment_id=assignment.id,
                    user_id=student.id,
                    submitted_at=assignment.due_at - timedelta(hours=4),
                    workflow_state="submitted",
                    score=round(points * 0.85, 2),
                    late=False,
                )
            )

    # A dense Q4 term makes the October-to-December planning and recovery
    # workflow realistic without flooding the rest of the demo year.
    q4_specs = (
        ("T10.1", date(2026, 10, 11), 12.0, 0),
        ("T10.2", date(2026, 10, 25), 15.0, 1),
        ("T11.1", date(2026, 11, 8), 15.0, 2),
        ("T11.2", date(2026, 11, 22), 18.0, 3),
        ("T12.1", date(2026, 12, 6), 18.0, 0),
        ("T12.2", date(2026, 12, 27), 20.0, 1),
    )
    for label, due_day, points, topic_index in q4_specs:
        topic = schedule.topics[topic_index]
        title = f"BTVN 2026 {label}: {topic}"
        if title in existing:
            continue
        assignment = Assignment(
            course_id=course.id,
            title=title,
            description=(
                f"Bài tập về nhà chủ đề {topic}. Hạn nộp {due_day:%d/%m/%Y} lúc 23:59. "
                f"Thời gian dự kiến {int(points * 12)} phút."
            ),
            due_at=_local_datetime(due_day, time(23, 59)),
            points_possible=points,
            published=True,
        )
        db.add(assignment)
        existing[title] = assignment

    # Keep each demo course measurably different so switching courses in
    # PaceWise can be verified from task totals and completion metrics.
    course_specific_specs = {
        "DS201": (
            ("Bài tập mở rộng: Phân loại quan hệ", date(2026, 11, 29), 24.0, False),
        ),
        "PM102": (
            ("Workshop: Risk response", date(2026, 9, 30), 10.0, True),
            ("Đồ án: Sprint review", date(2026, 12, 20), 25.0, False),
        ),
    }
    for title, due_day, points, completed in course_specific_specs.get(course.code, ()):
        assignment = existing.get(title)
        if assignment is None:
            assignment = Assignment(
                course_id=course.id,
                title=title,
                description=(
                    f"Hoạt động riêng của môn {course.code}. Hạn nộp {due_day:%d/%m/%Y} lúc 23:59. "
                    f"Thời gian dự kiến {int(points * 12)} phút."
                ),
                due_at=_local_datetime(due_day, time(23, 59)),
                points_possible=points,
                published=True,
            )
            db.add(assignment)
            db.flush()
            existing[title] = assignment
        if completed and student is not None and not db.scalar(
            select(Submission).where(
                Submission.assignment_id == assignment.id,
                Submission.user_id == student.id,
            )
        ):
            db.add(
                Submission(
                    assignment_id=assignment.id,
                    user_id=student.id,
                    submitted_at=assignment.due_at - timedelta(hours=6),
                    workflow_state="submitted",
                    score=round(points * 0.9, 2),
                    late=False,
                )
            )


def _seed_exams(
    db: Session,
    existing_events: set[tuple[int | None, str, datetime]],
    calendar_user: User,
    course: Course,
    schedule: CourseSchedule,
    course_index: int,
) -> None:
    exams = (
        (
            "Thi giữa kỳ",
            date(2026, 6, 15 + course_index * 2),
            time(8, 0),
            schedule.midterm_minutes,
            30.0,
        ),
        (
            "Thi cuối kỳ",
            date(2026, 12, 14 + course_index * 2),
            time(8, 0),
            schedule.final_minutes,
            50.0,
        ),
    )
    existing_quizzes = {
        item.title
        for item in db.scalars(
            select(CourseContent).where(
                CourseContent.course_id == course.id,
                CourseContent.kind == "quiz",
            )
        ).all()
    }
    for label, exam_day, starts, minutes, points in exams:
        title = f"{label} 2026 · {minutes} phút"
        exam_start = _local_datetime(exam_day, starts)
        if title not in existing_quizzes:
            exam = CourseContent(
                course_id=course.id,
                kind="quiz",
                title=title,
                body=f"{label} môn {course.code}. Thời lượng {minutes} phút.",
                due_at=exam_start + timedelta(minutes=minutes),
                points_possible=points,
                published=True,
            )
            db.add(exam)
            db.flush()
            db.add(
                QuizQuestion(
                    quiz_id=exam.id,
                    prompt=f"Câu hỏi tổng hợp {label.lower()} môn {course.code}.",
                    options_json='["A", "B", "C", "D"]',
                    correct_answer="A",
                    points=points,
                    position=1,
                )
            )
            existing_quizzes.add(title)
        _add_event(
            db,
            existing_events,
            user_id=calendar_user.id,
            course_id=course.id,
            title=f"[{course.code}] {title}",
            starts_at=exam_start,
            minutes=minutes,
            kind="midterm" if label == "Thi giữa kỳ" else "final_exam",
        )


def _seed_q4_term_events(
    db: Session,
    existing_events: set[tuple[int | None, str, datetime]],
    calendar_user: User,
    course: Course,
    schedule: CourseSchedule,
    course_index: int,
) -> None:
    kickoff_times = (time(8, 0), time(10, 0), time(13, 30))
    _add_event(
        db,
        existing_events,
        user_id=calendar_user.id,
        course_id=course.id,
        title=f"[{course.code}] Ca học online mở đầu học kỳ · {schedule.class_minutes} phút",
        starts_at=_local_datetime(date(2026, 10, 1), kickoff_times[course_index]),
        minutes=schedule.class_minutes,
        kind="class_session",
    )
    _add_event(
        db,
        existing_events,
        user_id=calendar_user.id,
        course_id=course.id,
        title=f"[{course.code}] Ca học online tổng kết năm 2026 · {schedule.class_minutes} phút",
        starts_at=_local_datetime(date(2026, 12, 31), kickoff_times[course_index]),
        minutes=schedule.class_minutes,
        kind="class_session",
    )

    exam_day = date(2026, 11, 9 + course_index * 2)
    exam_start = _local_datetime(exam_day, time(8, 0))
    title = f"Thi giữa kỳ học kỳ 1 năm 2026 · {schedule.midterm_minutes} phút"
    existing_quiz = db.scalar(
        select(CourseContent).where(
            CourseContent.course_id == course.id,
            CourseContent.kind == "quiz",
            CourseContent.title == title,
        )
    )
    if existing_quiz is None:
        exam = CourseContent(
            course_id=course.id,
            kind="quiz",
            title=title,
            body=(
                f"Thi giữa kỳ học kỳ 1 môn {course.code}. "
                f"Thời lượng {schedule.midterm_minutes} phút."
            ),
            due_at=exam_start + timedelta(minutes=schedule.midterm_minutes),
            points_possible=30,
            published=True,
        )
        db.add(exam)
        db.flush()
        db.add(
            QuizQuestion(
                quiz_id=exam.id,
                prompt=f"Câu hỏi tổng hợp giữa kỳ học kỳ 1 môn {course.code}.",
                options_json='["A", "B", "C", "D"]',
                correct_answer="A",
                points=30,
                position=1,
            )
        )
    _add_event(
        db,
        existing_events,
        user_id=calendar_user.id,
        course_id=course.id,
        title=f"[{course.code}] {title}",
        starts_at=exam_start,
        minutes=schedule.midterm_minutes,
        kind="midterm",
    )


def _replace_discrete_math_text(value: str) -> str:
    replacements = (
        ("Làm sạch dữ liệu", "3.1 Khái niệm quan hệ hai ngôi và tính chất"),
        ("Tập hợp và logic", "3.1 Khái niệm quan hệ hai ngôi và tính chất"),
        ("Phân tích mô tả", "3.2 Quan hệ tương đương"),
        ("Logic mệnh đề", "3.2 Quan hệ tương đương"),
        ("Trực quan hóa", "3.3 Quan hệ thứ tự"),
        ("Phép đếm", "3.3 Quan hệ thứ tự"),
        ("Dashboard", "Bài tập tổng hợp Chương 3"),
        ("Dữ liệu và trực quan hóa", DISCRETE_MATH_COURSE_NAME),
    )
    for old, new in replacements:
        value = value.replace(old, new)
    return value


def _sync_discrete_math_quiz_questions(db: Session, quiz: CourseContent) -> None:
    existing_by_position: dict[int, list[QuizQuestion]] = {}
    for item in db.scalars(
        select(QuizQuestion)
        .where(QuizQuestion.quiz_id == quiz.id)
        .order_by(QuizQuestion.position, QuizQuestion.id)
    ).all():
        existing_by_position.setdefault(item.position, []).append(item)
    for position, (prompt, options_json, correct_answer) in enumerate(
        DISCRETE_MATH_QUIZ_QUESTIONS,
        1,
    ):
        candidates = existing_by_position.pop(position, [])
        question = candidates.pop(0) if candidates else None
        if question is None:
            question = QuizQuestion(quiz_id=quiz.id, position=position)
            db.add(question)
        question.prompt = prompt
        question.options_json = options_json
        question.correct_answer = correct_answer
        question.points = 2
        for duplicate in candidates:
            db.delete(duplicate)
    for obsolete_items in existing_by_position.values():
        for obsolete in obsolete_items:
            db.delete(obsolete)
    # The demo week is seeded once per calendar owner. Flush here so the next
    # owner sees the synchronized set even when the session disables autoflush.
    db.flush()


def _ensure_discrete_math_learning_data(db: Session, course: Course) -> None:
    """Migrate the former DS201 demo into a grounded discrete-math course."""

    course.name = DISCRETE_MATH_COURSE_NAME

    assignment_renames = {
        "Khám phá bộ dữ liệu bán hàng": "Bài tập: Tập hợp và ánh xạ",
        "Thiết kế dashboard trực quan": "Bài tập Chương 3: Quan hệ tương đương",
        "Phân tích xu hướng": "Bài tập Chương 3: Quan hệ thứ tự",
        "Bài tập: Làm sạch dữ liệu bán hàng": "Bài tập Chương 3: Phân loại quan hệ hai ngôi",
        "Case study: Phân tích dữ liệu bán hàng": "Bài tập mở rộng: Phân loại quan hệ",
        "BTVN 2026 T11.2: Quan hệ hai ngôi": "BTVN 2026 T11.2: Bài tập tổng hợp Chương 3",
        "BTVN 2026 Q4: Quan hệ hai ngôi": "BTVN 2026 Q4: Bài tập tổng hợp Chương 3",
    }
    for assignment in db.scalars(
        select(Assignment).where(Assignment.course_id == course.id)
    ).all():
        assignment.title = assignment_renames.get(
            assignment.title,
            _replace_discrete_math_text(assignment.title),
        )
        assignment.description = _replace_discrete_math_text(assignment.description or "")

    resources = db.scalars(
        select(Resource).where(Resource.course_id == course.id)
    ).all()
    seen_seed_resources: dict[tuple[str, str], Resource] = {}
    for resource in resources:
        if resource.kind == "slides" and resource.title == "Slide bài giảng tuần này":
            resource.title = "Slide Chương 3: Quan hệ hai ngôi"
            resource.source_url = DISCRETE_MATH_PDF_URL
        else:
            resource.title = _replace_discrete_math_text(resource.title)
        if resource.kind == "video" and resource.source_url.startswith("/mock-videos/ds201-2026-"):
            try:
                month = int(resource.source_url.rsplit("-", 1)[1].split(".", 1)[0])
            except (IndexError, ValueError):
                month = 0
            if 1 <= month <= 12:
                topic = DISCRETE_MATH_TOPICS[(month - 1) % len(DISCRETE_MATH_TOPICS)]
                resource.title = f"Video tháng {month:02d}: {topic} · 50 phút"
        resource_key = (resource.kind, resource.source_url)
        is_seed_resource = (
            resource.source_url == DISCRETE_MATH_PDF_URL
            or resource.source_url.startswith("/mock-videos/ds201-2026-")
        )
        if is_seed_resource and resource_key in seen_seed_resources:
            db.delete(resource)
        elif is_seed_resource:
            seen_seed_resources[resource_key] = resource

    chapter_resource = db.scalar(
        select(Resource).where(
            Resource.course_id == course.id,
            Resource.source_url == DISCRETE_MATH_PDF_URL,
        )
    )
    if chapter_resource is None:
        db.add(
            Resource(
                course_id=course.id,
                title="Slide Chương 3: Quan hệ hai ngôi",
                kind="slides",
                source_url=DISCRETE_MATH_PDF_URL,
            )
        )

    for content in db.scalars(
        select(CourseContent).where(CourseContent.course_id == course.id)
    ).all():
        if content.title == "Quiz tuần 05/10: Làm sạch dữ liệu":
            content.title = "Quiz Chương 3: Quan hệ hai ngôi"
        else:
            content.title = _replace_discrete_math_text(content.title)
        content.body = _replace_discrete_math_text(content.body or "")

    events = db.scalars(
        select(CalendarEvent).where(CalendarEvent.course_id == course.id)
    ).all()
    for event in events:
        event.title = event.title.replace(
            "Thực hành làm sạch dữ liệu",
            "Thực hành Chương 3: Quan hệ hai ngôi",
        ).replace(
            "Quiz tuần 05/10: Làm sạch dữ liệu",
            "Quiz Chương 3: Quan hệ hai ngôi",
        )
        event.title = _replace_discrete_math_text(event.title)
        starts_at = event.starts_at
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=UTC)
        local_day = starts_at.astimezone(LOCAL_TZ).date()
        if event.event_kind == "class_session" and local_day == date(2026, 10, 7):
            event.title = DISCRETE_MATH_DEMO_ONLINE_TITLE
        elif event.event_kind == "class" and local_day == date(2026, 10, 8):
            event.title = DISCRETE_MATH_DEMO_OFFLINE_TITLE

    # Older seed versions used the title as part of their idempotency key.
    # Renaming a topic could therefore leave two copies at the same time for
    # one learner. Keep one deterministic seed event per kind and start time.
    seen_seed_events: dict[tuple[int, str, datetime], CalendarEvent] = {}
    for event in sorted(events, key=lambda item: item.id):
        if not (event.description or "").startswith(SEED_MARKER):
            continue
        starts_at = event.starts_at
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=UTC)
        event_key = (
            event.user_id,
            event.event_kind,
            starts_at.astimezone(UTC).replace(microsecond=0),
        )
        if event_key in seen_seed_events:
            db.delete(event)
        else:
            seen_seed_events[event_key] = event

    # The session is configured with autoflush disabled. Flush migrations and
    # de-duplication before the idempotent seed pass calculates existing keys.
    db.flush()

    module = db.scalar(
        select(CourseModule).where(
            CourseModule.course_id == course.id,
            CourseModule.name == DISCRETE_MATH_MODULE_NAME,
        )
    )
    if module is None:
        module = CourseModule(
            course_id=course.id,
            name=DISCRETE_MATH_MODULE_NAME,
            position=3,
            published=True,
        )
        db.add(module)
        db.flush()

    item_specs = (
        (
            "3.1 Khái niệm quan hệ hai ngôi và tính chất",
            "file",
            DISCRETE_MATH_PDF_URL,
        ),
        ("3.2 Quan hệ tương đương", "page", ""),
        ("3.3 Quan hệ thứ tự", "page", ""),
    )
    existing_items = {
        item.title: item
        for item in db.scalars(
            select(ModuleItem).where(ModuleItem.module_id == module.id)
        ).all()
    }
    for position, (title, item_type, external_url) in enumerate(item_specs, 1):
        item = existing_items.get(title)
        if item is None:
            item = ModuleItem(module_id=module.id, title=title)
            db.add(item)
        item.item_type = item_type
        item.external_url = external_url
        item.position = position
        item.published = True


def _seed_demo_week(
    db: Session,
    existing_events: set[tuple[int | None, str, datetime]],
    calendar_user: User,
    course: Course,
) -> None:
    """Add a compact 05/10 demo week with offline classes, tasks, and quizzes."""

    demo_specs = {
        "CS101": {
            "offline": (date(2026, 10, 6), time(13, 30), 90, "Thực hành hàm và vòng lặp"),
            "assignment": ("Bài thực hành: Hàm và vòng lặp", date(2026, 10, 7), 8.0),
            "quiz": ("Quiz tuần 05/10: Vòng lặp", date(2026, 10, 6), time(19, 0), 20),
        },
        "DS201": {
            "offline": (date(2026, 10, 8), time(9, 0), 90, "Chương 3: Quan hệ hai ngôi (3.1–3.3)"),
            "assignment": ("Bài tập Chương 3: Phân loại quan hệ hai ngôi", date(2026, 10, 9), 10.0),
            "quiz": ("Quiz Chương 3: Quan hệ hai ngôi", date(2026, 10, 8), time(19, 30), 25),
        },
        "PM102": {
            "offline": (date(2026, 10, 10), time(8, 30), 90, "Workshop project charter"),
            "assignment": ("Bài tập: Project charter", date(2026, 10, 11), 12.0),
            "quiz": ("Quiz tuần 05/10: Project charter", date(2026, 10, 10), time(10, 30), 15),
        },
    }
    spec = demo_specs.get(course.code)
    if spec is None:
        return

    offline_day, offline_start, offline_minutes, offline_topic = spec["offline"]
    offline_title = f"[{course.code}] Học tại lớp: {offline_topic} · {offline_minutes} phút"
    if course.code == "DS201":
        offline_title = DISCRETE_MATH_DEMO_OFFLINE_TITLE
    _add_event(
        db,
        existing_events,
        user_id=calendar_user.id,
        course_id=course.id,
        title=offline_title,
        starts_at=_local_datetime(offline_day, offline_start),
        minutes=offline_minutes,
        kind="class",
    )

    assignment_title, assignment_due, assignment_points = spec["assignment"]
    assignment = db.scalar(
        select(Assignment).where(
            Assignment.course_id == course.id,
            Assignment.title == assignment_title,
        )
    )
    if assignment is None:
        db.add(
            Assignment(
                course_id=course.id,
                title=assignment_title,
                description=(
                    f"Nhiệm vụ demo tuần 05/10 của môn {course.code}. "
                    f"Hạn nộp {assignment_due:%d/%m/%Y} lúc 23:59."
                ),
                due_at=_local_datetime(assignment_due, time(23, 59)),
                points_possible=assignment_points,
                published=True,
            )
        )

    quiz_title, quiz_day, quiz_clock, quiz_minutes = spec["quiz"]
    quiz_start = _local_datetime(quiz_day, quiz_clock)
    quiz = db.scalar(
        select(CourseContent).where(
            CourseContent.course_id == course.id,
            CourseContent.kind == "quiz",
            CourseContent.title == quiz_title,
        )
    )
    if quiz is None:
        quiz = CourseContent(
            course_id=course.id,
            kind="quiz",
            title=quiz_title,
            body=f"Quiz ngắn phục vụ demo tuần 05/10. Thời lượng {quiz_minutes} phút.",
            due_at=quiz_start + timedelta(minutes=quiz_minutes),
            points_possible=10,
            published=True,
        )
        db.add(quiz)
        db.flush()
    if course.code == "DS201":
        quiz.body = (
            "Kiểm tra Chương 3 về quan hệ hai ngôi, quan hệ tương đương và quan hệ thứ tự. "
            f"Thời lượng {quiz_minutes} phút."
        )
        quiz.points_possible = 10
        _sync_discrete_math_quiz_questions(db, quiz)
    elif not db.scalar(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id)):
        db.add(
            QuizQuestion(
                quiz_id=quiz.id,
                prompt=f"Câu hỏi kiểm tra nhanh kiến thức tuần của môn {course.code}.",
                options_json='["A", "B", "C", "D"]',
                correct_answer="A",
                points=1,
                position=1,
            )
        )
    _add_event(
        db,
        existing_events,
        user_id=calendar_user.id,
        course_id=course.id,
        title=f"[{course.code}] {quiz_title} · {quiz_minutes} phút",
        starts_at=quiz_start,
        minutes=quiz_minutes,
        kind="quiz",
    )


def _normalize_seeded_events(events: list[CalendarEvent]) -> None:
    """Migrate existing v1 events without creating duplicate calendar rows."""

    for event in events:
        if not event.description.startswith(SEED_MARKER):
            continue
        kind = next(
            (
                token.split("=", 1)[1].strip()
                for token in event.description.split(";")
                if token.strip().startswith("kind=")
            ),
            "institutional",
        )
        event.event_kind = kind
        if kind == "class_session":
            if "Ca học:" in event.title:
                event.title = event.title.replace("Ca học:", "Ca học online:", 1)
            event.join_url = event.join_url or f"/api/calendar/events/{event.id}/join"
            event.attendance_status = event.attendance_status or "scheduled"


def seed_2026_demo_calendars(db: Session) -> None:
    """Seed repeatable 2026 calendars for the demo student and instructor."""
    from app.demo_seed_policy import demo_courses

    student = db.scalar(select(User).where(User.email == PRIMARY_STUDENT_EMAIL))
    calendar_users = db.scalars(select(User).where(User.email.in_(CALENDAR_USER_EMAILS))).all()
    if not calendar_users:
        return
    courses = {item.code: item for item in demo_courses(db)}
    eligible_course_ids = {item.id for item in courses.values()}

    for course_index, schedule in enumerate(COURSE_SCHEDULES):
        course = courses.get(schedule.code)
        if course is None:
            continue
        course.term = "Lịch học demo toàn năm 2026"
        if course.code == "DS201":
            _ensure_discrete_math_learning_data(db, course)
        _seed_homework(db, student, course, schedule)

    for calendar_user in calendar_users:
        enrolled_course_ids = set(
            db.scalars(
                select(Enrollment.course_id).where(Enrollment.user_id == calendar_user.id)
            ).all()
        )
        user_events = db.scalars(
            select(CalendarEvent).where(CalendarEvent.user_id == calendar_user.id)
        ).all()
        _normalize_seeded_events([item for item in user_events if item.course_id is None or item.course_id in eligible_course_ids])
        existing_events = {_event_key(item) for item in user_events}

        for course_index, schedule in enumerate(COURSE_SCHEDULES):
            course = courses.get(schedule.code)
            if course is None or course.id not in enrolled_course_ids:
                continue
            _seed_classes(db, existing_events, calendar_user, course, schedule)
            _seed_monthly_videos_and_quizzes(
                db,
                existing_events,
                calendar_user,
                course,
                schedule,
            )
            _seed_exams(
                db,
                existing_events,
                calendar_user,
                course,
                schedule,
                course_index,
            )
            _seed_q4_term_events(
                db,
                existing_events,
                calendar_user,
                course,
                schedule,
                course_index,
            )
            _seed_demo_week(
                db,
                existing_events,
                calendar_user,
                course,
            )

    db.flush()
    for schedule in COURSE_SCHEDULES:
        course = courses.get(schedule.code)
        if course:
            _seed_demo_scope_links(db, course, schedule)
    db.commit()


def _seed_demo_scope_links(db: Session, course: Course, schedule: CourseSchedule) -> None:
    """Explicit seed-authored chapter links; never used to guess scope at runtime.

    New teacher content still needs module membership. This idempotent migration
    only links the known demo curriculum and does not change task deadlines.
    """
    assignments = db.scalars(select(Assignment).where(Assignment.course_id == course.id)).all()
    resources = db.scalars(select(Resource).where(Resource.course_id == course.id)).all()
    # Docker bundles this immutable demo asset. Version its actual content, not
    # just its URL, so indexing and authenticated download agree on the hash.
    slide_path = Path(__file__).resolve().parent.parent / "static" / "mock-files" / "TRR_Full_P4.pdf"
    if slide_path.is_file():
        from app.learning_api import record_resource_version
        checksum = hashlib.sha256(slide_path.read_bytes()).hexdigest()
        for resource in resources:
            if resource.source_url != DISCRETE_MATH_PDF_URL:
                continue
            latest = db.scalar(select(ResourceVersion).where(ResourceVersion.resource_id == resource.id)
                .order_by(ResourceVersion.version.desc()))
            if not latest or latest.checksum_sha256 != checksum:
                record_resource_version(db, resource, checksum=checksum, size_bytes=slide_path.stat().st_size,
                    content_type="application/pdf", ensure_course_access=False)
    for position, topic in enumerate(schedule.topics, 1):
        name = DISCRETE_MATH_MODULE_NAME if course.code == "DS201" else topic
        module = db.scalar(select(CourseModule).where(CourseModule.course_id == course.id, CourseModule.name == name))
        if not module:
            module = CourseModule(course_id=course.id, name=name, position=position, published=True)
            db.add(module)
            db.flush()
        existing = {(item.item_type, item.content_id) for item in db.scalars(
            select(ModuleItem).where(ModuleItem.module_id == module.id)).all()}
        targets = [("assignment", assignment) for assignment in assignments if topic.casefold() in assignment.title.casefold()
            or (course.code == "DS201" and ("Chương 3" in assignment.title or "Quan hệ" in assignment.title))]
        targets += [("file", resource) for resource in resources if topic.casefold() in resource.title.casefold()
            or (course.code == "DS201" and resource.source_url == DISCRETE_MATH_PDF_URL)]
        for kind, target in targets:
            if (kind, target.id) not in existing:
                db.add(ModuleItem(module_id=module.id, title=target.title, item_type=kind,
                    content_id=target.id, position=len(existing) + 1, published=True))
                existing.add((kind, target.id))
        db.flush()
