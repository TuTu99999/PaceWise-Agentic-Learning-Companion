import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AppointmentGroup,
    Assignment,
    AssignmentConfiguration,
    AssignmentGroup,
    AssignmentRubric,
    Course,
    CourseGroup,
    CourseModule,
    CourseSection,
    Enrollment,
    GroupCategory,
    GroupMembership,
    LearningActivity,
    ModuleItem,
    ModuleItemProgress,
    ModulePolicy,
    ModulePrerequisite,
    ModuleRequirement,
    PlannerItem,
    Resource,
    ResourceAccess,
    ResourceVersion,
    Rubric,
    RubricCriterion,
    RubricRating,
    SectionMembership,
    Submission,
    SubmissionAttempt,
    SubmissionComment,
    SubmissionWorkflow,
    User,
)


def _get_or_create_assignment_groups(db: Session, course: Course) -> list[AssignmentGroup]:
    existing = db.scalars(
        select(AssignmentGroup)
        .where(AssignmentGroup.course_id == course.id)
        .order_by(AssignmentGroup.position)
    ).all()
    templates = {
        "CS101": [("Bài tập", 25), ("Quiz", 20), ("Project", 55)],
        "DS201": [("Thực hành dữ liệu", 35), ("Quiz", 20), ("Project", 45)],
        "PM102": [("Bài cá nhân", 25), ("Hoạt động nhóm", 35), ("Project", 40)],
    }.get(course.code, [("Bài tập", 40), ("Quiz", 20), ("Project", 40)])
    by_position = {group.position: group for group in existing}
    groups: list[AssignmentGroup] = []
    for position, (name, weight) in enumerate(templates, 1):
        group = by_position.get(position)
        if group:
            group.name = name
            group.group_weight = weight
        else:
            group = AssignmentGroup(
                course_id=course.id,
                name=name,
                position=position,
                group_weight=weight,
            )
            db.add(group)
        group.drop_lowest = 1 if name == "Quiz" else 0
        groups.append(group)
    db.flush()
    return groups


def _seed_assignment_structure(db: Session, course: Course) -> None:
    groups = _get_or_create_assignment_groups(db, course)
    assignments = db.scalars(
        select(Assignment)
        .where(Assignment.course_id == course.id)
        .order_by(Assignment.due_at)
    ).all()
    for index, assignment in enumerate(assignments):
        config = db.scalar(
            select(AssignmentConfiguration).where(
                AssignmentConfiguration.assignment_id == assignment.id
            )
        )
        group = groups[index % len(groups)]
        if not config:
            db.add(
                AssignmentConfiguration(
                    assignment_id=assignment.id,
                    assignment_group_id=group.id,
                    unlock_at=assignment.due_at - timedelta(days=14),
                    lock_at=assignment.due_at + timedelta(days=2),
                    grading_type="points",
                    peer_reviews=index % 4 == 0,
                )
            )
        else:
            # Keep demo data idempotent while allowing improved academic
            # weights to appear after an ordinary service restart.
            config.assignment_group_id = group.id


def _seed_sections_and_groups(db: Session, course: Course, students: list[User]) -> None:
    sections = db.scalars(select(CourseSection).where(CourseSection.course_id == course.id)).all()
    if not sections:
        sections = [
            CourseSection(course_id=course.id, name="Section A"),
            CourseSection(course_id=course.id, name="Section B"),
        ]
        db.add_all(sections)
        db.flush()
    for index, student in enumerate(students):
        section = sections[index % len(sections)]
        exists = db.scalar(
            select(SectionMembership).where(
                SectionMembership.section_id == section.id,
                SectionMembership.user_id == student.id,
            )
        )
        if not exists:
            db.add(SectionMembership(section_id=section.id, user_id=student.id))

    category = db.scalar(select(GroupCategory).where(GroupCategory.course_id == course.id))
    if not category:
        category = GroupCategory(course_id=course.id, name="Project teams", self_signup=False)
        db.add(category)
        db.flush()
    groups = db.scalars(select(CourseGroup).where(CourseGroup.category_id == category.id)).all()
    if not groups:
        groups = [
            CourseGroup(category_id=category.id, name="Team 1"),
            CourseGroup(category_id=category.id, name="Team 2"),
        ]
        db.add_all(groups)
        db.flush()
    for index, student in enumerate(students):
        group = groups[index % len(groups)]
        exists = db.scalar(
            select(GroupMembership).where(
                GroupMembership.group_id == group.id,
                GroupMembership.user_id == student.id,
            )
        )
        if not exists:
            db.add(GroupMembership(group_id=group.id, user_id=student.id))


def _seed_module_progress(db: Session, course: Course, students: list[User]) -> None:
    modules = db.scalars(
        select(CourseModule)
        .where(CourseModule.course_id == course.id)
        .order_by(CourseModule.position)
    ).all()
    for index, module in enumerate(modules):
        if not db.scalar(select(ModulePolicy).where(ModulePolicy.module_id == module.id)):
            db.add(ModulePolicy(module_id=module.id, sequential_progress=True))
        if index and not db.scalar(
            select(ModulePrerequisite).where(ModulePrerequisite.module_id == module.id)
        ):
            db.add(
                ModulePrerequisite(
                    module_id=module.id,
                    prerequisite_module_id=modules[index - 1].id,
                )
            )
        items = db.scalars(
            select(ModuleItem)
            .where(ModuleItem.module_id == module.id)
            .order_by(ModuleItem.position)
        ).all()
        for item in items:
            if not db.scalar(
                select(ModuleRequirement).where(ModuleRequirement.module_item_id == item.id)
            ):
                db.add(
                    ModuleRequirement(
                        module_item_id=item.id,
                        requirement_type="must_view",
                    )
                )
            for student_index, student in enumerate(students[:4]):
                if db.scalar(
                    select(ModuleItemProgress).where(
                        ModuleItemProgress.module_item_id == item.id,
                        ModuleItemProgress.user_id == student.id,
                    )
                ):
                    continue
                completed = student_index % 3 != 2 and index == 0
                db.add(
                    ModuleItemProgress(
                        module_item_id=item.id,
                        user_id=student.id,
                        status="completed" if completed else "unlocked",
                        completed_at=datetime.now(UTC) if completed else None,
                    )
                )


def _seed_rubric(db: Session, course: Course) -> None:
    rubric = db.scalar(select(Rubric).where(Rubric.course_id == course.id))
    if not rubric:
        rubric = Rubric(course_id=course.id, title="Learning evidence rubric", points_possible=10)
        db.add(rubric)
        db.flush()
        criteria_data = [
            ("Conceptual understanding", 4.0),
            ("Reasoning and process", 3.0),
            ("Accuracy and communication", 3.0),
        ]
        for position, (description, points) in enumerate(criteria_data, 1):
            criterion = RubricCriterion(
                rubric_id=rubric.id,
                description=description,
                points=points,
                position=position,
            )
            db.add(criterion)
            db.flush()
            db.add_all(
                [
                    RubricRating(criterion_id=criterion.id, description="Meets", points=points),
                    RubricRating(
                        criterion_id=criterion.id,
                        description="Developing",
                        points=round(points * 0.6, 1),
                    ),
                    RubricRating(criterion_id=criterion.id, description="Missing", points=0),
                ]
            )
    assignment = db.scalar(
        select(Assignment).where(Assignment.course_id == course.id).order_by(Assignment.id)
    )
    if assignment and not db.scalar(
        select(AssignmentRubric).where(AssignmentRubric.assignment_id == assignment.id)
    ):
        db.add(AssignmentRubric(assignment_id=assignment.id, rubric_id=rubric.id))


def _seed_resource_versions(db: Session, course: Course) -> None:
    resources = db.scalars(select(Resource).where(Resource.course_id == course.id)).all()
    for resource in resources:
        if not db.scalar(
            select(ResourceVersion).where(ResourceVersion.resource_id == resource.id)
        ):
            db.add(
                ResourceVersion(
                    resource_id=resource.id,
                    version=1,
                    checksum_sha256=hashlib.sha256(resource.source_url.encode()).hexdigest(),
                    source_url=resource.source_url,
                    content_type="text/html" if resource.kind == "link" else "application/octet-stream",
                )
            )
        if not db.scalar(select(ResourceAccess).where(ResourceAccess.resource_id == resource.id)):
            db.add(
                ResourceAccess(
                    resource_id=resource.id,
                    scope_type="course",
                    scope_id=course.id,
                )
            )


def _seed_submission_history(db: Session, course: Course, teacher: User | None) -> None:
    submissions = db.scalars(
        select(Submission)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .where(Assignment.course_id == course.id)
    ).all()
    for submission in submissions:
        if not db.scalar(
            select(SubmissionAttempt).where(SubmissionAttempt.submission_id == submission.id)
        ):
            db.add(
                SubmissionAttempt(
                    submission_id=submission.id,
                    attempt_number=1,
                    submitted_at=submission.submitted_at or datetime.now(UTC),
                )
            )
        if not db.scalar(
            select(SubmissionWorkflow).where(SubmissionWorkflow.submission_id == submission.id)
        ):
            db.add(SubmissionWorkflow(submission_id=submission.id))
        if teacher and submission.score is not None and not db.scalar(
            select(SubmissionComment).where(SubmissionComment.submission_id == submission.id)
        ):
            db.add(
                SubmissionComment(
                    submission_id=submission.id,
                    author_id=teacher.id,
                    body="Review the rubric feedback before the next attempt.",
                )
            )


def _seed_planner_and_analytics(db: Session, course: Course, students: list[User]) -> None:
    now = datetime.now(UTC)
    assignments = db.scalars(
        select(Assignment)
        .where(Assignment.course_id == course.id)
        .order_by(Assignment.due_at)
    ).all()
    for student in students[:4]:
        if assignments and not db.scalar(
            select(PlannerItem).where(
                PlannerItem.user_id == student.id,
                PlannerItem.course_id == course.id,
            )
        ):
            assignment = assignments[student.id % len(assignments)]
            db.add(
                PlannerItem(
                    user_id=student.id,
                    course_id=course.id,
                    assignment_id=assignment.id,
                    title=f"Prepare: {assignment.title}",
                    due_at=assignment.due_at - timedelta(days=1),
                )
            )
    if not db.scalar(
        select(func.count(LearningActivity.id)).where(LearningActivity.course_id == course.id)
    ):
        activity_types = ["page_view", "module_view", "assignment_view", "participation"]
        for index in range(30):
            student = students[index % len(students)]
            db.add(
                LearningActivity(
                    user_id=student.id,
                    course_id=course.id,
                    activity_type=activity_types[index % len(activity_types)],
                    object_type="course",
                    object_id=str(course.id),
                    duration_seconds=60 + (index % 8) * 45,
                    occurred_at=now - timedelta(hours=index * 3),
                )
            )
    if not db.scalar(select(AppointmentGroup).where(AppointmentGroup.course_id == course.id)):
        db.add(
            AppointmentGroup(
                course_id=course.id,
                title="Weekly office hours",
                starts_at=now + timedelta(days=2),
                ends_at=now + timedelta(days=2, hours=2),
                slot_minutes=30,
                participants_per_slot=2,
            )
        )


def seed_learning_extensions(db: Session) -> None:
    from app.demo_seed_policy import demo_courses

    courses = demo_courses(db)
    teacher = db.scalar(select(User).where(User.role == "instructor").order_by(User.id))
    for course in courses:
        students = [
            enrollment.user
            for enrollment in db.scalars(
                select(Enrollment).where(
                    Enrollment.course_id == course.id,
                    Enrollment.role == "student",
                )
            ).all()
        ]
        if not students:
            continue
        _seed_assignment_structure(db, course)
        _seed_sections_and_groups(db, course, students)
        _seed_module_progress(db, course, students)
        _seed_rubric(db, course)
        _seed_resource_versions(db, course)
        _seed_submission_history(db, course, teacher)
        _seed_planner_and_analytics(db, course, students)
    db.commit()
