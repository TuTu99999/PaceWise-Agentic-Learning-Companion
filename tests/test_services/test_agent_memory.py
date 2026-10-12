import json

from sqlalchemy import select

from src.config import get_settings
from src.db import SessionLocal
from src.persistence_models import AgentReviewCase, LearnerMemory
from src.security import SessionContext
from src.services.agent_memory import (
    load_learner_memory,
    persist_agent_outcome,
    resolve_review_case,
)


def _session() -> SessionContext:
    return SessionContext(
        user_id=98701,
        course_id=87601,
        course_ids=(87601,),
        role="student",
        name="Memory Test",
        email="memory@example.edu",
        csrf_hash="test",
        sid="memory-test-session",
        exp=4_102_444_800,
    )


def test_low_confidence_outcome_waits_for_teacher_before_updating_mastery():
    session = _session()
    settings = get_settings()
    result = {
        "workflow": "understanding",
        "status": "awaiting_teacher",
        "assessment_result": {
            "status": "còn nhầm lẫn",
            "confidence": "Thấp",
            "evidence_quotes": ["p-value là xác suất H0 đúng"],
        },
        "pending_action": {"type": "instructor_review"},
        "request": {"topic": "Kiểm định giả thuyết"},
    }

    with SessionLocal() as db:
        db.query(AgentReviewCase).filter(AgentReviewCase.student_user_id == session.user_id).delete()
        db.query(LearnerMemory).filter(LearnerMemory.user_id == session.user_id).delete()
        db.commit()
        persist_agent_outcome(db, session, settings, result, "Q-42")
        memory = load_learner_memory(db, session, settings)
        cases = db.scalars(
            select(AgentReviewCase).where(AgentReviewCase.student_user_id == session.user_id)
        ).all()

    assert memory["mastery"] == {}
    assert memory["misconceptions"] == []
    assert len(cases) == 1
    assert cases[0].case_type == "understanding_review"
    assert json.loads(cases[0].payload_json)["assessment_result"]["confidence"] == "Thấp"

    with SessionLocal() as db:
        review_case = db.get(AgentReviewCase, cases[0].id)
        resolve_review_case(
            db,
            review_case,
            {
                "status": "edited",
                "edited_result": {"status": "còn nhầm lẫn"},
            },
            settings,
        )
        review_case.status = "edited"
        db.commit()
        memory = load_learner_memory(db, session, settings)

    assert memory["mastery"]["Kiểm định giả thuyết"]["assessment_id"] == "Q-42"
    assert memory["mastery"]["Kiểm định giả thuyết"]["confidence"] == "teacher_confirmed"
    assert memory["misconceptions"][0]["assessment_id"] == "Q-42"


def test_persist_agent_outcome_deduplicates_pending_citation_case():
    session = _session()
    settings = get_settings()
    dispute = {
        "dispute_id": "disp-stable",
        "citation": "[Nguồn, Trang 1]",
        "status": "flagged_for_review",
    }
    result = {
        "workflow": "qa",
        "status": "completed",
        "output": {"citation_dispute": dispute},
    }

    with SessionLocal() as db:
        db.query(AgentReviewCase).filter(AgentReviewCase.student_user_id == session.user_id).delete()
        db.commit()
        persist_agent_outcome(db, session, settings, result, None)
        persist_agent_outcome(db, session, settings, result, None)
        cases = db.scalars(
            select(AgentReviewCase).where(
                AgentReviewCase.student_user_id == session.user_id,
                AgentReviewCase.entity_id == "disp-stable",
            )
        ).all()

    assert len(cases) == 1


def test_reflection_updates_next_week_memory_only_after_student_confirmation():
    session = _session()
    settings = get_settings()
    draft = {
        "week_start": "2026-09-28",
        "week_end": "2026-10-04",
        "effective_week_start": "2026-10-05",
        "adjustment": "Tăng 15 phút cho mỗi study block.",
    }

    with SessionLocal() as db:
        db.query(LearnerMemory).filter(LearnerMemory.user_id == session.user_id).delete()
        db.commit()
        persist_agent_outcome(
            db,
            session,
            settings,
            {"workflow": "reflect", "status": "awaiting_student", "reflection_draft": draft},
            None,
        )
        pending_memory = load_learner_memory(db, session, settings)
        persist_agent_outcome(
            db,
            session,
            settings,
            {"workflow": "reflect", "status": "completed", "reflection_draft": draft},
            None,
        )
        confirmed_memory = load_learner_memory(db, session, settings)

    assert "last_reflection" not in pending_memory["profile"]
    assert confirmed_memory["profile"]["last_reflection"] == draft
    next_adjustment = confirmed_memory["profile"]["next_week_adjustment"]
    assert next_adjustment["effective_week_start"] == "2026-10-05"
    assert next_adjustment["adjustment"] == "Tăng 15 phút cho mỗi study block."
    assert next_adjustment["confirmed_at"]


def test_activity_reflection_is_history_and_never_overwrites_weekly_adjustment():
    session = _session()
    settings = get_settings()
    weekly = {
        "scope": "weekly",
        "effective_week_start": "2026-10-05",
        "adjustment": "Chia block còn 45 phút.",
    }
    activity = {
        "scope": "activity",
        "activity": {"id": "study:b1", "title": "Ôn vòng lặp"},
        "next_step": "Đọc lại slide 3.",
    }

    with SessionLocal() as db:
        db.query(LearnerMemory).filter(LearnerMemory.user_id == session.user_id).delete()
        db.commit()
        persist_agent_outcome(
            db, session, settings,
            {"workflow": "reflect", "status": "completed", "reflection_draft": weekly},
            None,
        )
        persist_agent_outcome(
            db, session, settings,
            {"workflow": "reflect", "status": "completed", "reflection_draft": activity},
            None,
        )
        memory = load_learner_memory(db, session, settings)

    assert memory["profile"]["next_week_adjustment"]["adjustment"] == "Chia block còn 45 phút."
    assert memory["profile"]["activity_reflections"][-1]["activity"]["id"] == "study:b1"
