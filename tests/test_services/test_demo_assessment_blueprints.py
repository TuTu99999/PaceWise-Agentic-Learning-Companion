from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.course_source.assessment_blueprint_seed import seed_assessment_blueprints
from src.course_source.db import Base
from src.course_source.models import Course, CourseContent, QuizQuestion
from src.services.demo_assessment_blueprints import (
    ADAPTIVE_SEQUENCE_STAGES,
    DEMO_ASSESSMENT_BLUEPRINTS,
    blueprint_by_topic,
    blueprint_payload,
    blueprints_for_window,
)
from src.services.replan_policy import decide_replan


def _database() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    for index, code in enumerate(("DB201", "DSA201", "OOPCPP201", "WEB201"), start=1):
        db.add(Course(id=index, code=code, name=code, term="2026", color="#2563eb"))
    db.commit()
    return db


def test_four_course_blueprints_cover_current_and_next_week():
    current = blueprints_for_window(
        date(2026, 10, 12),
        date(2026, 10, 18),
    )
    following = blueprints_for_window(
        date(2026, 10, 19),
        date(2026, 10, 25),
    )

    assert len(DEMO_ASSESSMENT_BLUEPRINTS) == 24
    assert {item["course_code"] for item in current} == {"DB201", "DSA201", "OOPCPP201", "WEB201"}
    assert {item["course_code"] for item in following} == {"DB201", "DSA201", "OOPCPP201", "WEB201"}
    assert len(current) == 4
    assert len(following) == 20
    assert all(len(item["rubric"]) == 3 for item in DEMO_ASSESSMENT_BLUEPRINTS)
    assert all(item["source"].endswith((".pdf", ".docx")) for item in DEMO_ASSESSMENT_BLUEPRINTS)


def test_blueprints_are_teacher_review_drafts_not_auto_published():
    blueprint = DEMO_ASSESSMENT_BLUEPRINTS[0]
    payload = blueprint_payload(blueprint)

    assert blueprint_by_topic(blueprint["topic"]) == blueprint
    assert payload["status"] == "review"
    assert payload["kcProvisional"] is False
    assert payload["knowledgeComponentIds"]
    assert "approved" not in payload


def test_blueprint_payload_is_a_self_contained_ai_proposal():
    blueprint = DEMO_ASSESSMENT_BLUEPRINTS[0]
    item = blueprint_payload(blueprint)

    assert item["status"] == "review"
    assert item["aiGenerated"] is True
    assert item["topic"] == blueprint["topic"]
    assert item["question"] == blueprint["question"]
    assert item["rubric"] == blueprint["rubric"]
    assert item["knowledgeComponentIds"] == blueprint["knowledge_component_ids"]
    assert item["source"] == blueprint["source"]


def test_seed_materializes_private_ungraded_quiz_anchors_idempotently():
    db = _database()
    try:
        first = seed_assessment_blueprints(db, apply=True)
        second = seed_assessment_blueprints(db, apply=True)

        quizzes = db.scalars(select(CourseContent).where(CourseContent.kind == "quiz")).all()
        questions = db.scalars(select(QuizQuestion)).all()
        assert first["createdQuizzes"] == 24
        assert first["createdQuestions"] == 24
        assert not first["conflicts"]
        assert len(quizzes) == len(questions) == 24
        assert all(not quiz.published and quiz.due_at is None and quiz.points_possible == 0 for quiz in quizzes)
        assert second["createdQuizzes"] == second["createdQuestions"] == 0
        assert second["unchanged"] == 24
    finally:
        db.close()


def test_each_next_week_course_has_a_complete_adaptive_stage_bank_for_teacher_review():
    next_week = blueprints_for_window(date(2026, 10, 19), date(2026, 10, 25))
    for code in ("DB201", "DSA201", "OOPCPP201", "WEB201"):
        course_items = [item for item in next_week if item["course_code"] == code]
        assert {item["assessment_stage"] for item in course_items} == {
            "recall", "explain", "why", "application", "transfer"
        }
        kc_ids = {tuple(item["knowledge_component_ids"]) for item in course_items}
        assert len(kc_ids) == 1
        assert all(blueprint_payload(item)["status"] == "review" for item in course_items)
        assert all(
            blueprint_payload(item)["questionDesign"]["stages"] == ADAPTIVE_SEQUENCE_STAGES
            for item in course_items
        )


def test_verified_assessment_gap_only_proposes_replan_draft():
    blueprint = DEMO_ASSESSMENT_BLUEPRINTS[-1]
    evidence = {
        "id": "evidence-web201",
        "valid": True,
        "confidence": "high",
        "review_status": "accepted",
        "provisional": False,
        "can_update_knowledge": True,
        "dimensions": {blueprint["assessment_stage"]: "failed"},
        "knowledge_component_ids": blueprint["knowledge_component_ids"],
        "task_id": "WEB201:chapter-1",
    }

    decision = decide_replan(signal={}, last_do={}, latest_evidence=evidence)

    assert decision["action"] == "propose_draft"
    assert decision["reasons"] == ["knowledge_gap_observed"]
    assert decision["requires_confirmation"] is True
    assert decision["auto_apply"] is False
    assert decision["mutable_scope"] == "future_uncompleted_student_blocks"
    assert decision["repair_context"]["affected_knowledge_component_ids"] == blueprint[
        "knowledge_component_ids"
    ]
    assert decision["repair_context"]["failed_dimensions"] == ["transfer"]


def test_unconfirmed_assessment_never_changes_the_plan():
    blueprint = DEMO_ASSESSMENT_BLUEPRINTS[-1]
    evidence = {
        "valid": True,
        "confidence": "high",
        "review_status": "verifying",
        "provisional": True,
        "dimensions": {blueprint["assessment_stage"]: "failed"},
        "knowledge_component_ids": blueprint["knowledge_component_ids"],
    }

    decision = decide_replan(signal={}, last_do={}, latest_evidence=evidence)

    assert decision["action"] == "keep"
    assert decision["auto_apply"] is False
