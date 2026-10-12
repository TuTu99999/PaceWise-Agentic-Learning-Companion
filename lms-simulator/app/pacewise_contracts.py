"""Small authoritative contracts shared by simulator UI and PaceWise API.

Ported behavior, not Canvas Ruby implementation: enrollment visibility and a
graded quiz's assignment linkage. Do not infer mastery from these LMS scores.
"""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dates import as_utc
from app.models import (
    Assignment,
    Course,
    CourseContent,
    CourseLifecycle,
    Enrollment,
    ModuleItem,
    PlannerItem,
    QuizAssignmentLink,
    QuizQuestion,
    Resource,
    RubricAssessment,
    Submission,
    SubmissionWorkflow,
)
from app.telemetry import record_change


def course_actor(db: Session, course_id: int, user_id: int | None):
    if user_id is None:
        return None  # Privileged worker/service snapshot, not a student view.
    enrollment = db.scalar(select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.user_id == user_id))
    if enrollment is None:
        raise HTTPException(403, "Course enrollment required")
    course = db.get(Course, course_id)
    lifecycle = db.get(CourseLifecycle, course_id)
    if lifecycle and lifecycle.archived:
        raise HTTPException(403, "Course is archived")
    if not course or (enrollment.role != "instructor" and not course.published):
        raise HTTPException(403, "Course is not published for students")
    return enrollment


def visible_module_item(db: Session, item: ModuleItem, course_id: int, user_id: int) -> bool:
    """A published module cannot grant access to a hidden/cross-course target."""
    from app.learning_api import can_access_resource

    if not item.published:
        return False
    kind = item.item_type.lower()
    model = Resource if kind in {"resource", "file"} else Assignment if kind == "assignment" else CourseContent
    if item.content_id is None:
        return kind in {"external_url", "externalurl", "subheader"}
    target = db.get(model, item.content_id)
    if not target or target.course_id != course_id or not getattr(target, "published", True):
        return False
    return model is not Resource or can_access_resource(db, target, user_id)


def planner_payload(db: Session, item: PlannerItem) -> dict | None:
    """Assignment dates/completion come from LMS, never the editable planner note."""
    from app.learning_api import effective_assignment_window

    due_at, completed, title = item.due_at, item.completed, item.title
    course_id = item.course_id
    if course_id is not None:
        try:
            course_actor(db, course_id, item.user_id)
        except HTTPException:
            return None
    if item.assignment_id is not None:
        assignment = db.get(Assignment, item.assignment_id)
        if not assignment or not assignment.published or course_id != assignment.course_id:
            return None
        if not db.scalar(
            select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.user_id == item.user_id)
        ):
            return None
        due_at, _, _, _ = effective_assignment_window(db, assignment, item.user_id)
        submission = db.scalar(
            select(Submission).where(Submission.assignment_id == assignment.id, Submission.user_id == item.user_id)
        )
        completed = bool(
            submission
            and submission_contract(db, submission)["workflow_state"]
            in {"submitted", "graded", "pending_review", "excused"}
        )
        title = assignment.title
    elif course_id is not None and not db.scalar(
        select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.user_id == item.user_id)
    ):
        return None
    return {
        "id": item.id,
        "course_id": course_id,
        "assignment_id": item.assignment_id,
        "title": title,
        "due_at": as_utc(due_at).isoformat() if due_at else None,
        "completed": completed,
    }


def submission_contract(db: Session, submission: Submission) -> dict:
    workflow = db.scalar(select(SubmissionWorkflow).where(SubmissionWorkflow.submission_id == submission.id))
    excused, reassigned = bool(workflow and workflow.excused), bool(workflow and workflow.reassigned)
    state = "excused" if excused else "reassigned" if reassigned else submission.workflow_state
    return {
        "workflow_state": state,
        "source_workflow_state": submission.workflow_state,
        "excused": excused,
        "reassigned": reassigned,
    }


def submission_rubric(db: Session, submission_id: int, legacy: dict) -> dict:
    assessments = db.scalars(select(RubricAssessment).where(RubricAssessment.submission_id == submission_id)).all()
    return {
        **legacy,
        **{
            str(row.criterion_id): {"points": row.points, "comments": row.comments, "assessor_id": row.assessor_id}
            for row in assessments
        },
    }


def sync_quiz_assignment(db: Session, quiz: CourseContent, actor_id: int | None = None) -> Assignment | None:
    if quiz.kind != "quiz":
        return None
    link = db.get(QuizAssignmentLink, quiz.id)
    assignment = db.get(Assignment, link.assignment_id) if link else None
    previous = (
        None
        if assignment is None
        else (
            assignment.title,
            assignment.description,
            assignment.due_at,
            assignment.published,
            assignment.points_possible,
            assignment.submission_types,
        )
    )
    if quiz.due_at is None:
        if assignment and assignment.published:
            assignment.published = False
            record_change(
                db,
                actor_user_id=actor_id,
                action="assignment.updated",
                entity_type="assignment",
                entity_id=assignment.id,
                course_id=quiz.course_id,
                metadata={"quiz_id": quiz.id, "undated": True},
            )
        return None  # Never fabricate a deadline for an undated quiz.
    if assignment is None:
        # Link existing equivalent demo assignments rather than creating a duplicate.
        assignment = db.scalar(
            select(Assignment).where(
                Assignment.course_id == quiz.course_id,
                Assignment.title == quiz.title,
                Assignment.due_at == quiz.due_at,
                Assignment.id.not_in(select(QuizAssignmentLink.assignment_id)),
            )
        )
        if assignment is None:
            assignment = Assignment(
                course_id=quiz.course_id,
                title=quiz.title,
                description=quiz.body,
                due_at=quiz.due_at,
                points_possible=quiz.points_possible or 0,
                submission_types="online_quiz",
                published=quiz.published,
            )
            db.add(assignment)
            db.flush()
        db.add(QuizAssignmentLink(quiz_id=quiz.id, assignment_id=assignment.id))
    assignment.title, assignment.description = quiz.title, quiz.body
    assignment.due_at, assignment.published = quiz.due_at, quiz.published
    total = db.scalar(select(func.sum(QuizQuestion.points)).where(QuizQuestion.quiz_id == quiz.id))
    assignment.points_possible, assignment.submission_types = (
        total if total is not None else quiz.points_possible or 0,
        "online_quiz",
    )
    db.flush()
    current = (
        assignment.title,
        assignment.description,
        assignment.due_at,
        assignment.published,
        assignment.points_possible,
        assignment.submission_types,
    )
    if previous != current:
        record_change(
            db,
            actor_user_id=actor_id,
            action="assignment.updated",
            entity_type="assignment",
            entity_id=assignment.id,
            course_id=quiz.course_id,
            metadata={"quiz_id": quiz.id},
        )
    return assignment


def remove_quiz_assignment(db: Session, quiz_id: int, actor_id: int) -> None:
    link = db.get(QuizAssignmentLink, quiz_id)
    if link:
        assignment = db.get(Assignment, link.assignment_id)
        db.delete(link)
        if assignment:
            # Keep historical submissions; unpublish instead of deleting evidence.
            assignment.published = False
            record_change(
                db,
                actor_user_id=actor_id,
                action="assignment.updated",
                entity_type="assignment",
                entity_id=assignment.id,
                course_id=assignment.course_id,
                metadata={"quiz_deleted": True},
            )


def sync_quiz_submission(db: Session, quiz: CourseContent, user_id: int, score: float, submitted_at: datetime) -> None:
    from app.learning_api import effective_assignment_window, record_submission_attempt

    assignment = sync_quiz_assignment(db, quiz, user_id)
    if assignment is None:
        return
    submission = db.scalar(
        select(Submission).where(Submission.assignment_id == assignment.id, Submission.user_id == user_id)
    )
    if submission is None:
        submission = Submission(assignment_id=assignment.id, user_id=user_id)
        db.add(submission)
    due_at, _, _, _ = effective_assignment_window(db, assignment, user_id)
    due_at = due_at.replace(tzinfo=UTC) if due_at.tzinfo is None else due_at
    submission.submitted_at, submission.score = submitted_at, score
    submission.workflow_state, submission.late = "graded", submitted_at > due_at
    db.flush()
    record_submission_attempt(db, submission)
    record_change(
        db,
        actor_user_id=user_id,
        action="submission.submitted",
        entity_type="submission",
        entity_id=submission.id,
        course_id=quiz.course_id,
        metadata={"assignment_id": assignment.id, "quiz_id": quiz.id},
    )
