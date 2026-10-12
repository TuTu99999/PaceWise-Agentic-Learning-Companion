import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.demo_seed_policy import demo_courses
from app.extension_seed import seed_learning_extensions
from app.models import (
    Assignment,
    CalendarEvent,
    Conversation,
    ConversationMessage,
    ConversationParticipant,
    ConversationState,
    Course,
    CourseContent,
    CourseModule,
    Enrollment,
    GradeHistory,
    LearningEvidence,
    ModuleItem,
    OutcomeAlignment,
    QuizAttempt,
    QuizQuestion,
    Resource,
    Submission,
    User,
)
from app.security import hash_password
from app.year_schedule_seed import seed_2026_demo_calendars


def seed_demo_data(db: Session) -> None:
    if db.scalar(select(func.count(User.id))):
        seed_canvas_features(db)
        seed_pacewise_data(db)
        seed_2026_demo_calendars(db)
        seed_learning_extensions(db)
        return

    demo_password = hash_password("demo123")
    teacher = User(
        email="teacher@canvas.local",
        full_name="Nguyễn Minh Anh",
        password_hash=demo_password,
        role="instructor",
        avatar_color="#7c3aed",
    )
    students = [
        User(
            email="student@canvas.local",
            full_name="Trần Gia An",
            password_hash=demo_password,
            role="student",
            avatar_color="#2563eb",
        ),
        User(
            email="minh@canvas.local",
            full_name="Lê Hoàng Minh",
            password_hash=demo_password,
            role="student",
            avatar_color="#059669",
        ),
        User(
            email="linh@canvas.local",
            full_name="Phạm Ngọc Linh",
            password_hash=demo_password,
            role="student",
            avatar_color="#db2777",
        ),
        User(
            email="nam@canvas.local",
            full_name="Vũ Hải Nam",
            password_hash=demo_password,
            role="student",
            avatar_color="#ea580c",
        ),
    ]
    db.add_all([teacher, *students])

    courses = [
        Course(
            code="CS101",
            name="Nhập môn lập trình Python",
            term="Học kỳ 1 · 2026–2027",
            color="#2563eb",
        ),
        Course(
            code="DS201",
            name="Toán rời rạc",
            term="Học kỳ 1 · 2026–2027",
            color="#7c3aed",
        ),
        Course(
            code="PM102",
            name="Quản lý dự án công nghệ",
            term="Học kỳ 1 · 2026–2027",
            color="#ea580c",
        ),
    ]
    db.add_all(courses)
    db.flush()

    progress_by_student = [72, 64, 48, 35]
    for course in courses:
        db.add(Enrollment(user=teacher, course=course, role="instructor", progress=100))
        for index, student in enumerate(students):
            adjustment = 0 if course.code == "CS101" else (-5 if course.code == "DS201" else 4)
            db.add(
                Enrollment(
                    user=student,
                    course=course,
                    role="student",
                    progress=max(10, progress_by_student[index] + adjustment),
                )
            )

    now = datetime.now(UTC)
    assignment_specs = {
        "CS101": [
            ("Bài 1: Biến và kiểu dữ liệu", -5, 10),
            ("Bài 2: Hàm và vòng lặp", 1, 15),
            ("Mini project: Quản lý thư viện", 5, 30),
        ],
        "DS201": [
            ("Bài tập: Tập hợp và ánh xạ", -2, 15),
            ("Bài tập Chương 3: Quan hệ tương đương", 2, 25),
            ("Bài tập Chương 3: Quan hệ thứ tự", 7, 30),
        ],
        "PM102": [
            ("Project charter", -4, 10),
            ("Risk register", 3, 20),
            ("Sprint retrospective", 8, 15),
        ],
    }
    assignments: list[Assignment] = []
    for course in courses:
        for title, due_offset, points in assignment_specs[course.code]:
            assignment = Assignment(
                course=course,
                title=title,
                description=(
                    "Đọc yêu cầu, chuẩn bị bản nháp và nộp sản phẩm trước hạn. "
                    "Tài liệu tham khảo nằm trong module của môn học."
                ),
                due_at=now + timedelta(days=due_offset, hours=20),
                points_possible=points,
            )
            db.add(assignment)
            assignments.append(assignment)

        db.add_all(
            [
                Resource(
                    course=course,
                    title=f"Syllabus · {course.code}",
                    kind="syllabus",
                    source_url=f"/mock-files/{course.code.lower()}-syllabus.pdf",
                ),
                Resource(
                    course=course,
                    title=(
                        "Slide Chương 3: Quan hệ hai ngôi"
                        if course.code == "DS201"
                        else "Slide bài giảng tuần này"
                    ),
                    kind="slides",
                    source_url=(
                        "/static/mock-files/TRR_Full_P4.pdf"
                        if course.code == "DS201"
                        else f"/mock-files/{course.code.lower()}-week.pdf"
                    ),
                ),
            ]
        )

    db.flush()

    # Seed ordinary Canvas submission states for the student and gradebook views.
    for student_index, student in enumerate(students):
        for assignment_index, assignment in enumerate(assignments):
            due = assignment.due_at
            should_submit = (assignment_index + student_index) % 3 != 1
            if due < now and should_submit:
                late = student_index == 3 and assignment_index % 2 == 0
                submitted_at = due + timedelta(hours=5) if late else due - timedelta(hours=8)
                db.add(
                    Submission(
                        assignment=assignment,
                        user_id=student.id,
                        submitted_at=submitted_at,
                        workflow_state="submitted",
                        score=max(5, assignment.points_possible - student_index * 1.5),
                        late=late,
                    )
                )

    db.commit()
    seed_canvas_features(db)
    seed_pacewise_data(db)
    seed_2026_demo_calendars(db)
    seed_learning_extensions(db)


def seed_canvas_features(db: Session) -> None:
    """Add Canvas-native demo content without replacing existing demo records."""
    courses = demo_courses(db)
    teacher = db.scalar(select(User).where(User.role == "instructor").order_by(User.id))
    student = db.scalar(select(User).where(User.role == "student").order_by(User.id))
    if not courses or not teacher or not student:
        return

    now = datetime.now(UTC)
    if not db.scalar(select(func.count(CourseContent.id))):
        first_course = courses[0]
        db.add_all(
            [
                CourseContent(
                    course_id=first_course.id,
                    kind="announcement",
                    title="Welcome to the course",
                    body="Please review the syllabus and the first module before beginning the assignments.",
                    published=True,
                ),
                CourseContent(
                    course_id=first_course.id,
                    kind="syllabus",
                    title="Course Syllabus",
                    body="Course description, learning objectives, assessment policy, and weekly schedule.",
                    published=True,
                ),
                CourseContent(
                    course_id=first_course.id,
                    kind="discussion",
                    title="Introduce yourself",
                    body="Share your learning goals and one topic you would like to understand better.",
                    published=True,
                ),
                CourseContent(
                    course_id=first_course.id,
                    kind="page",
                    title="Course Overview",
                    body="This page contains the course overview, learning objectives, and weekly structure.",
                    published=True,
                ),
                CourseContent(
                    course_id=first_course.id,
                    kind="outcome",
                    title="Apply core programming concepts",
                    body="Students can select and apply variables, control flow, functions, and data structures.",
                    points_possible=5,
                    published=True,
                ),
                CourseContent(
                    course_id=first_course.id,
                    kind="quiz",
                    title="Week 1 Knowledge Check",
                    body="A short quiz covering variables and basic data types.",
                    due_at=now + timedelta(days=4, hours=20),
                    points_possible=10,
                    published=True,
                ),
            ]
        )

    if not db.scalar(
        select(CourseContent).where(
            CourseContent.course_id == courses[0].id,
            CourseContent.kind == "syllabus",
        )
    ):
        db.add(
            CourseContent(
                course_id=courses[0].id,
                kind="syllabus",
                title="Course Syllabus",
                body="Course description, learning objectives, assessment policy, and weekly schedule.",
                published=True,
            )
        )

    if not db.scalar(select(func.count(CourseModule.id))):
        module = CourseModule(
            course_id=courses[0].id,
            name="Module 1: Getting Started",
            position=1,
            published=True,
        )
        db.add(module)
        db.flush()
        first_assignment = db.scalar(
            select(Assignment).where(Assignment.course_id == courses[0].id).order_by(Assignment.id)
        )
        db.add_all(
            [
                ModuleItem(
                    module_id=module.id,
                    title="Course Overview",
                    item_type="page",
                    position=1,
                    published=True,
                ),
                ModuleItem(
                    module_id=module.id,
                    title=first_assignment.title if first_assignment else "First Assignment",
                    item_type="assignment",
                    content_id=first_assignment.id if first_assignment else None,
                    position=2,
                    published=True,
                ),
            ]
        )

    if not db.scalar(select(func.count(QuizQuestion.id))):
        quiz = db.scalar(select(CourseContent).where(CourseContent.kind == "quiz").order_by(CourseContent.id))
        if quiz:
            db.add_all(
                [
                    QuizQuestion(
                        quiz_id=quiz.id,
                        prompt="Which Python value is immutable?",
                        options_json='["list", "dictionary", "tuple", "set"]',
                        correct_answer="tuple",
                        points=1,
                        position=1,
                    ),
                    QuizQuestion(
                        quiz_id=quiz.id,
                        prompt="Which keyword defines a function in Python?",
                        options_json='["func", "define", "def", "lambda-only"]',
                        correct_answer="def",
                        points=1,
                        position=2,
                    ),
                ]
            )

    if not db.scalar(select(func.count(CalendarEvent.id))):
        db.add(
            CalendarEvent(
                user_id=student.id,
                course_id=courses[0].id,
                title="Study group",
                description="Review the first module with classmates.",
                starts_at=now + timedelta(days=2, hours=18),
                ends_at=now + timedelta(days=2, hours=19),
            )
        )

    if not db.scalar(select(func.count(Conversation.id))):
        conversation = Conversation(subject="Welcome to the course")
        db.add(conversation)
        db.flush()
        db.add_all(
            [
                ConversationParticipant(conversation_id=conversation.id, user_id=teacher.id),
                ConversationParticipant(conversation_id=conversation.id, user_id=student.id),
                ConversationState(
                    conversation_id=conversation.id,
                    user_id=teacher.id,
                    unread=False,
                ),
                ConversationState(
                    conversation_id=conversation.id,
                    user_id=student.id,
                    unread=True,
                ),
                ConversationMessage(
                    conversation_id=conversation.id,
                    sender_id=teacher.id,
                    body="Welcome! Let me know if you have any questions about the first module.",
                ),
            ]
        )

    if not db.scalar(select(func.count(ConversationState.id))):
        conversations = db.scalars(select(Conversation)).all()
        for conversation in conversations:
            participants = db.scalars(
                select(ConversationParticipant).where(ConversationParticipant.conversation_id == conversation.id)
            ).all()
            db.add_all(
                [
                    ConversationState(
                        conversation_id=conversation.id,
                        user_id=participant.user_id,
                        unread=participant.user_id != teacher.id,
                    )
                    for participant in participants
                ]
            )

    db.commit()


def seed_pacewise_data(db: Session) -> None:
    """Create a deterministic evaluation cohort with more than 100 evidence samples."""
    courses = demo_courses(db)
    assignments = db.scalars(select(Assignment).where(Assignment.course_id.in_([course.id for course in courses])).order_by(Assignment.id)).all()
    teacher = db.scalar(select(User).where(User.role == "instructor").order_by(User.id))
    if not courses or not assignments or not teacher:
        return

    demo_password = hash_password("demo123")
    synthetic_students = db.scalars(
        select(User).where(User.email.like("evaluation%")).order_by(User.id)
    ).all()
    if len(synthetic_students) < 24:
        existing_emails = {user.email for user in synthetic_students}
        for index in range(1, 25):
            email = f"evaluation{index:03d}@canvas.local"
            if email in existing_emails:
                continue
            student = User(
                email=email,
                full_name=f"Evaluation Student {index:03d}",
                password_hash=demo_password,
                role="student",
                avatar_color=["#2563eb", "#059669", "#db2777", "#ea580c"][index % 4],
            )
            db.add(student)
        db.flush()
        synthetic_students = db.scalars(
            select(User).where(User.email.like("evaluation%")).order_by(User.id)
        ).all()

    existing_enrollments = {
        (item.user_id, item.course_id)
        for item in db.scalars(
            select(Enrollment).where(Enrollment.user_id.in_([user.id for user in synthetic_students]))
        ).all()
    }
    for student_index, student in enumerate(synthetic_students):
        for course_index, course in enumerate(courses):
            if (student.id, course.id) not in existing_enrollments:
                db.add(
                    Enrollment(
                        user_id=student.id,
                        course_id=course.id,
                        role="student",
                        progress=float(30 + ((student_index * 7 + course_index * 11) % 66)),
                    )
                )
    db.flush()

    outcome = db.scalar(
        select(CourseContent).where(CourseContent.kind == "outcome").order_by(CourseContent.id)
    )
    first_course_assignment = next(
        (assignment for assignment in assignments if outcome and assignment.course_id == outcome.course_id),
        None,
    )
    if outcome and first_course_assignment and not db.scalar(
        select(OutcomeAlignment).where(
            OutcomeAlignment.outcome_id == outcome.id,
            OutcomeAlignment.assignment_id == first_course_assignment.id,
        )
    ):
        db.add(OutcomeAlignment(outcome_id=outcome.id, assignment_id=first_course_assignment.id))

    now = datetime.now(UTC)
    for student_index, student in enumerate(synthetic_students):
        for assignment_index, assignment in enumerate(assignments):
            submission = db.scalar(
                select(Submission).where(
                    Submission.assignment_id == assignment.id,
                    Submission.user_id == student.id,
                )
            )
            if submission:
                continue
            missed = (student_index + assignment_index) % 7 == 0
            if missed:
                continue
            late = (student_index * 2 + assignment_index) % 5 == 0
            due_at = assignment.due_at
            if due_at.tzinfo is None:  # SQLite does not preserve timezone metadata.
                due_at = due_at.replace(tzinfo=UTC)
            submitted_at = due_at + timedelta(hours=6) if late else due_at - timedelta(hours=10)
            score_ratio = 0.55 + ((student_index * 13 + assignment_index * 7) % 41) / 100
            score = round(min(assignment.points_possible, assignment.points_possible * score_ratio), 2)
            submission = Submission(
                assignment_id=assignment.id,
                user_id=student.id,
                submitted_at=submitted_at,
                workflow_state="submitted",
                score=score,
                late=late,
            )
            db.add(submission)
            db.flush()
            rubric = {
                "understanding": round(4 * score_ratio),
                "accuracy": round(4 * max(0.5, score_ratio - 0.05)),
                "process": round(4 * min(1, score_ratio + 0.05)),
            }
            comment = "Needs targeted review." if score_ratio < 0.7 else "Meets the expected learning outcome."
            db.add(
                GradeHistory(
                    submission_id=submission.id,
                    assignment_id=assignment.id,
                    user_id=student.id,
                    grader_id=teacher.id,
                    score=score,
                    comment=comment,
                    rubric_json=json.dumps(rubric),
                    graded_at=min(now, submitted_at + timedelta(days=1)),
                )
            )
            competency = (
                f"outcome:{outcome.id}"
                if outcome and assignment.course_id == outcome.course_id
                else f"course:{assignment.course_id}:assignment-performance"
            )
            db.add(
                LearningEvidence(
                    user_id=student.id,
                    course_id=assignment.course_id,
                    evidence_type="graded_assignment",
                    source_type="submission",
                    source_id=str(submission.id),
                    competency_key=competency,
                    score=score,
                    max_score=assignment.points_possible,
                    details_json=json.dumps(
                        {"late": late, "rubric": rubric, "comment": comment},
                        ensure_ascii=False,
                    ),
                    observed_at=min(now, submitted_at + timedelta(days=1)),
                )
            )

    quiz = db.scalar(select(CourseContent).where(CourseContent.kind == "quiz").order_by(CourseContent.id))
    if quiz:
        questions = db.scalars(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id)).all()
        for student_index, student in enumerate(synthetic_students):
            if db.scalar(
                select(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id, QuizAttempt.user_id == student.id)
            ):
                continue
            answers = {}
            score = 0.0
            for question_index, question in enumerate(questions):
                correct = (student_index + question_index) % 4 != 0
                answer = question.correct_answer if correct else "incorrect"
                answers[str(question.id)] = answer
                if correct:
                    score += question.points
                db.add(
                    LearningEvidence(
                        user_id=student.id,
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
            db.add(
                QuizAttempt(
                    quiz_id=quiz.id,
                    user_id=student.id,
                    answers_json=json.dumps(answers),
                    score=score,
                )
            )

    db.commit()
