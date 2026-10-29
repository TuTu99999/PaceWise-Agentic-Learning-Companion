import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from src.config import get_settings
from src.db import SessionLocal
from src.persistence_models import AgentReviewCase, InstructorAction, LearnerMemory, LearningEvent
from src.security import SessionContext
from src.services.agent_memory import (
    load_approved_assessment,
    load_learner_memory,
    load_plan_confirmation,
    load_planning_memory,
    persist_agent_outcome,
)
from src.services.plan_intelligence import normalize_reflection_feedback


@pytest.mark.asyncio
async def test_self_contained_approved_assessment_needs_no_quiz_provider():
    session = _session()
    settings = get_settings()
    entity_id = "assessment-authored-source"
    with SessionLocal() as db:
        db.query(InstructorAction).filter(InstructorAction.entity_id == entity_id).delete()
        db.add(
            InstructorAction(
                id="action-authored-source",
                course_id=session.course_id,
                actor_user_id=700,
                action_type="assessment",
                entity_id=entity_id,
                payload_json=json.dumps(
                    {
                        "status": "approved",
                        "version": 1,
                        "topic": "Kỹ thuật tìm kiếm",
                        "question": "Giải thích vì sao tìm kiếm nhị phân cần mảng đã sắp xếp.",
                        "source": "Buoi02_Ky_thuat_tim_kiem.pdf · Trang 2",
                        "answerType": "open",
                        "rubric": ["Nêu đúng điều kiện", "Giải thích việc loại bỏ một nửa"],
                        "knowledgeComponentIds": ["search.binary"],
                    }
                ),
            )
        )
        db.commit()
        result = await load_approved_assessment(db, session, settings, entity_id)
        db.query(InstructorAction).filter(InstructorAction.entity_id == entity_id).delete()
        db.commit()

    assert result["question"].startswith("Giải thích vì sao")
    assert result["source"] == "Buoi02_Ky_thuat_tim_kiem.pdf · Trang 2"
    assert result["knowledge_component_ids"] == ["search.binary"]


@pytest.mark.asyncio
async def test_legacy_quiz_approval_without_question_snapshot_is_rejected():
    session = _session()
    settings = get_settings()
    entity_id = "Q-legacy-quiz"
    with SessionLocal() as db:
        db.query(InstructorAction).filter(InstructorAction.entity_id == entity_id).delete()
        db.add(
            InstructorAction(
                id="action-legacy-quiz",
                course_id=session.course_id,
                actor_user_id=700,
                action_type="assessment",
                entity_id=entity_id,
                payload_json=json.dumps({"status": "approved", "source": "Canvas quiz"}),
            )
        )
        db.commit()
        with pytest.raises(HTTPException) as failure:
            await load_approved_assessment(db, session, settings, entity_id)
        db.query(InstructorAction).filter(InstructorAction.entity_id == entity_id).delete()
        db.commit()

    assert failure.value.status_code == 409


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


def test_low_confidence_outcome_stays_unknown_without_creating_teacher_work():
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
    assert cases == []
    assert memory["profile"].get("last_replan_proposal") is None


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


def test_latest_weekly_reflection_drives_plan_while_all_versions_remain_auditable():
    session = _session()
    settings = get_settings()
    first = {
        "scope": "weekly",
        "week_start": "2026-10-12",
        "week_end": "2026-10-18",
        "adjustment": "Ôn thêm 45 phút.",
        "planning_signal": {
            "cause": "knowledge_gap",
            "task_id": "t1",
            "follow_up_minutes": 45,
            "affected_kcs": ["database-model"],
        },
    }
    latest = {
        "scope": "weekly",
        "week_start": "2026-10-12",
        "week_end": "2026-10-18",
        "adjustment": "Đã hiểu hơn, chỉ ôn thêm 15 phút.",
        "planning_signal": {
            "cause": "knowledge_gap",
            "task_id": "t1",
            "follow_up_minutes": 15,
            "affected_kcs": ["database-model"],
        },
    }

    with SessionLocal() as db:
        db.query(LearningEvent).filter(LearningEvent.student_user_id == session.user_id).delete()
        db.query(LearnerMemory).filter(LearnerMemory.user_id == session.user_id).delete()
        db.commit()
        persist_agent_outcome(db, session, settings, {
            "workflow": "reflect", "status": "completed", "reflection_draft": first,
        }, None)
        persist_agent_outcome(db, session, settings, {
            "workflow": "reflect", "status": "completed", "reflection_draft": latest,
        }, None)
        memory = load_learner_memory(db, session, settings)
        versions = db.scalars(select(LearningEvent).where(
            LearningEvent.student_user_id == session.user_id,
            LearningEvent.event_type == "REFLECTION_SUBMITTED",
            LearningEvent.entity_id == "2026-10-12",
        )).all()

    feedback = normalize_reflection_feedback(memory["profile"], task_id="t1")
    assert memory["profile"]["last_reflection"] == latest
    assert feedback["followUpMinutes"] == 15
    assert len(versions) == 2
    snapshots = [json.loads(version.payload_json)["reflection"] for version in versions]
    assert {snapshot["adjustment"] for snapshot in snapshots} == {
        "Ôn thêm 45 phút.",
        "Đã hiểu hơn, chỉ ôn thêm 15 phút.",
    }


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


def test_plan_confirmation_survives_active_course_switch_and_clears_owner_draft():
    settings = get_settings()
    first = SessionContext(98702, 87611, (87611, 87612), "student", "Memory Test", "", "x", "sid", 4_102_444_800)
    second = SessionContext(98702, 87612, (87611, 87612), "student", "Memory Test", "", "x", "sid", 4_102_444_800)
    draft = {"createdAt": "2026-10-16T19:00:00+07:00", "blocks": []}

    with SessionLocal() as db:
        db.query(LearnerMemory).filter(LearnerMemory.user_id == first.user_id).delete()
        db.commit()
        persist_agent_outcome(db, first, settings, {
            "workflow": "plan", "status": "awaiting_student", "output": {"plan_draft": draft},
        }, None)
        loaded, replay = load_plan_confirmation(db, second, settings, draft["createdAt"])
        assert loaded == draft
        assert replay is False

        planning = load_planning_memory(db, second, settings)
        # Before confirmation there is no confirmed plan to leak into re-plan.
        assert "last_confirmed_plan" not in planning["profile"]

        persist_agent_outcome(db, second, settings, {
            "workflow": "plan",
            "status": "completed",
            "student_decision": {"action": "confirmed"},
            "output": {"confirmed_plan": draft},
        }, None)
        owner = db.get(LearnerMemory, f"{settings.institution_id}:{first.user_id}:{first.course_id}")
        assert "pending_plan_draft" not in json.loads(owner.profile_json)
        replayed, replay = load_plan_confirmation(db, first, settings, draft["createdAt"])
        assert replayed["createdAt"] == draft["createdAt"]
        assert replay is True
        assert load_planning_memory(db, first, settings)["profile"]["last_confirmed_plan"]["createdAt"] == draft["createdAt"]


def test_empty_confirmed_payload_does_not_destroy_pending_plan():
    session = _session()
    settings = get_settings()
    draft = {"createdAt": "2026-10-16T20:00:00+07:00", "blocks": []}
    with SessionLocal() as db:
        db.query(LearnerMemory).filter(LearnerMemory.user_id == session.user_id).delete()
        db.commit()
        persist_agent_outcome(db, session, settings, {
            "workflow": "plan", "status": "awaiting_student", "output": {"plan_draft": draft},
        }, None)
        persist_agent_outcome(db, session, settings, {
            "workflow": "plan", "status": "completed",
            "student_decision": {"action": "confirmed"}, "output": {"confirmed_plan": {}},
        }, None)
        assert load_learner_memory(db, session, settings)["profile"]["pending_plan_draft"] == draft
