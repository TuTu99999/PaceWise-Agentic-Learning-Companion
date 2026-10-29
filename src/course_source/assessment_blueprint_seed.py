"""Idempotently materialize teacher-reviewable demo Assessment anchors.

The seeded quizzes are private authoring records: they have no deadline, carry
no grade, and are not published to the course.  PaceWise exposes them only in
the instructor Assessment design screen until the instructor approves the
associated blueprint.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.course_source.models import Course, CourseContent, QuizQuestion
from src.services.demo_assessment_blueprints import DEMO_ASSESSMENT_BLUEPRINTS


def seed_assessment_blueprints(
    db: Session,
    *,
    blueprints: Iterable[dict[str, Any]] = DEMO_ASSESSMENT_BLUEPRINTS,
    apply: bool = False,
) -> dict[str, Any]:
    """Create missing private quiz anchors without overwriting teacher work."""

    courses = {course.code: course for course in db.scalars(select(Course)).all()}
    report: dict[str, Any] = {
        "apply": apply,
        "createdQuizzes": 0,
        "createdQuestions": 0,
        "unchanged": 0,
        "conflicts": [],
        "missingCourses": [],
        "items": [],
    }
    for blueprint in blueprints:
        course = courses.get(str(blueprint["course_code"]))
        if course is None:
            report["missingCourses"].append(blueprint["course_code"])
            continue
        quiz = db.scalar(
            select(CourseContent).where(
                CourseContent.course_id == course.id,
                CourseContent.kind == "quiz",
                CourseContent.title == blueprint["topic"],
            )
        )
        quiz_created = quiz is None
        if quiz is None:
            if not apply:
                report["items"].append({"key": blueprint["key"], "action": "create"})
                continue
            quiz = CourseContent(
                course_id=course.id,
                kind="quiz",
                title=blueprint["topic"],
                body=json.dumps(
                    {
                        "pacewiseAssessmentBlueprint": blueprint["key"],
                        "assignmentTitle": blueprint["assignment_title"],
                        "weekStart": blueprint["week_start"],
                        "weekEnd": blueprint["week_end"],
                    },
                    ensure_ascii=False,
                ),
                due_at=None,
                points_possible=0,
                published=False,
            )
            db.add(quiz)
            db.flush()
            report["createdQuizzes"] += 1

        questions = db.scalars(
            select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id).order_by(QuizQuestion.position)
        ).all()
        if questions:
            if questions[0].prompt == blueprint["question"]:
                report["unchanged"] += 1
                report["items"].append(
                    {"key": blueprint["key"], "action": "unchanged", "questionId": questions[0].id}
                )
            else:
                # A teacher may have edited the anchor in the source system.
                # Never overwrite it from a repeatable demo-content command.
                report["conflicts"].append(
                    {
                        "key": blueprint["key"],
                        "quizId": quiz.id,
                        "reason": "existing_question_differs",
                    }
                )
            continue
        if apply:
            question = QuizQuestion(
                quiz_id=quiz.id,
                prompt=blueprint["question"],
                options_json="[]",
                correct_answer="",
                points=0,
                position=1,
            )
            db.add(question)
            db.flush()
            report["createdQuestions"] += 1
            report["items"].append(
                {
                    "key": blueprint["key"],
                    "action": "created" if quiz_created else "question_created",
                    "questionId": question.id,
                }
            )
    report["missingCourses"] = sorted(set(report["missingCourses"]))
    if apply:
        db.commit()
    else:
        db.rollback()
    return report
