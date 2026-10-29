import json
from datetime import UTC, date, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.agents.workflows.do import evaluate_completion
from src.config import get_settings
from src.db import Base
from src.persistence_models import (
    AgentReviewCase,
    KnowledgeStateSnapshot,
    LearnerMemory,
    LearningEvent,
    LearningEvidenceRecord,
    StudyTimerSession,
)
from src.security import SessionContext
from src.services.agent_memory import (
    load_learner_memory,
    load_planning_memory,
    persist_agent_outcome,
    resolve_review_case,
)
from src.services.learning_evidence import build_evidence_contract, persist_learning_evidence
from src.services.plan_intelligence import mastery_for_component
from src.services.planning import build_plan_draft
from src.services.replan_policy import plan_diff


def test_do_metrics_survive_checkpoint_and_reflect_does_not_edit_knowledge_or_plan():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = SessionContext(123, 456, (456,), "student", "Test", "test@example.edu", "x", "sid", 4102444800)
    settings = get_settings()
    with Session(engine) as db:
        do = evaluate_completion({
            "block_id": "b1",
            "task_id": "t1",
            "planned_minutes": 60,
            "actual_minutes": 100,
            "work_result": "needs_more_time",
            "remaining_minutes": 30,
        })["output"]["do_session"]
        persist_agent_outcome(db, session, settings, {"workflow": "do", "output": {"do_session": do}}, None)
        persist_agent_outcome(
            db, session, settings, {"workflow": "do", "output": {"do_session": {"action": "assess"}}}, None
        )
        reflection = {
            "workflow": "reflect",
            "status": "completed",
            "reflection_draft": {
                "scope": "activity",
                "week_start": "2026-10-05",
                "planning_signal": {"cause": "estimate_error", "task_id": "t1"},
                "mastery": 0.99,
            },
        }
        persist_agent_outcome(db, session, settings, reflection, None)
        profile = load_learner_memory(db, session, settings)
        assert profile["profile"]["last_do_session"] == do
        assert profile["mastery"] == {}
        assert reflection["output"]["replan_decision"]["action"] == "propose_draft"
        assert reflection["output"]["replan_decision"]["auto_apply"] is False
        assert len(profile["profile"]["do_history"]) == 1
        assert {event.event_type for event in db.scalars(select(LearningEvent))} == {
            "STUDY_SESSION_COMPLETED",
            "REFLECTION_SUBMITTED",
            "REPLAN_DECIDED",
        }
        assert db.scalars(select(LearnerMemory)).all()[0].course_id == 456
        repaired = build_plan_draft(
            {
                "weekStart": "2026-10-12",
                "horizonEnd": "2026-10-18",
                "tasks": [{"taskId": "t1", "remainingMin": 60}],
                "availability": [
                    {"weekday": day, "enabled": True, "start": "08:00", "end": "20:00"}
                    for day in range(7)
                ],
                "unavailable": [],
                "preferred": ["morning"],
            },
            [{"id": "t1", "title": "Task", "deadline": "2026-10-18T23:59:00+07:00"}],
            learner_profile=profile["profile"],
            today=date(2026, 10, 12),
        )
        assert repaired["planningTargets"][0]["targetMin"] == 130
        assert repaired["replanAdjustments"] == [
            {
                "taskId": "t1",
                "baselineRemainingMin": 60,
                "reconciledRemainingMin": 130,
                "addedMin": 70,
                "reason": "observed_unfinished_work",
                "sourceRef": "do:b1",
            }
        ]
    engine.dispose()


def test_planning_memory_carries_reflect_signal_across_courses_without_merging_mastery():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    settings = get_settings()
    course_one = SessionContext(123, 456, (456, 789), "student", "Test", "test@example.edu", "x", "sid", 4102444800)
    course_two = SessionContext(123, 789, (456, 789), "student", "Test", "test@example.edu", "x", "sid", 4102444800)
    do = {
        "action": "complete", "block_id": "b2", "task_id": "789:t2", "planned_minutes": 60,
        "actual_minutes": 90, "completion_percent": 50, "remaining_minutes": 30, "status": "needs_more_time",
    }
    reflection = {
        "workflow": "reflect",
        "status": "completed",
        "reflection_draft": {
            "scope": "activity",
            "week_start": "2026-10-05",
            "activity": {"block_id": "b2", "task_id": "789:t2"},
            "planning_signal": {"cause": "estimate_error", "task_id": "789:t2"},
        },
    }
    with Session(engine) as db:
        persist_agent_outcome(db, course_two, settings, {"workflow": "do", "output": {"do_session": do}}, None)
        persist_agent_outcome(db, course_two, settings, reflection, None)
        memory = load_planning_memory(db, course_one, settings)

    assert memory["profile"]["last_replan_proposal"]["repair_context"]["affected_task_ids"] == ["789:t2"]
    assert memory["profile"]["last_do_session"]["task_id"] == "789:t2"
    assert set(memory["mastery"]["__by_course__"]) == {"789"}
    engine.dispose()


def test_confirmed_weekly_reflection_changes_next_plan_draft_without_auto_applying_it():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = SessionContext(321, 654, (654,), "student", "Test", "test@example.edu", "x", "sid", 4102444800)
    settings = get_settings()
    plan_input = {
        "weekStart": "2026-10-12",
        "horizonEnd": "2026-10-18",
        "tasks": [{"taskId": "t1", "remainingMin": 60}],
        "availability": [
            {"weekday": weekday, "enabled": True, "start": "08:00", "end": "20:00"}
            for weekday in range(7)
        ],
        "unavailable": [],
        "preferred": ["morning"],
    }
    assignments = [{"id": "t1", "title": "Bài tập quan hệ", "deadline": "2026-10-18T23:59:00+07:00"}]

    baseline = build_plan_draft(plan_input, assignments, today=date(2026, 10, 12))
    reflection = {
        "workflow": "reflect",
        "status": "completed",
        "reflection_draft": {
            "scope": "weekly",
            "week_start": "2026-10-05",
            "effective_week_start": "2026-10-12",
            "planning_signal": {
                "cause": "knowledge_gap",
                "task_id": "t1",
                "follow_up_minutes": 45,
                "affected_kcs": ["binary-relations"],
            },
        },
    }
    with Session(engine) as db:
        assessment_result = {
            "workflow": "do",
            "status": "completed",
            "query": "attempt",
            "do_session": {"action": "assess", "block_id": "b-week"},
            "request": {
                "assessment_attempt": {
                    "event_key": "weekly-evidence-1",
                    "block_id": "b-week",
                    "response": "attempt",
                    "first_attempt": True,
                    "hint_level": 0,
                }
            },
            "_trusted_assessment": {
                "rubric_version": 1,
                "answer_type": "open",
                "knowledge_component_ids": ["binary-relations"],
                "kc_provisional": False,
            },
            "assessment_result": {
                "status": "misconception",
                "confidence": "high",
                "evaluator_version": "test",
                "evidence_quotes": ["attempt"],
                "dimensions": {
                    "conceptual": "passed",
                    "reasoning": "failed",
                    "application": "failed",
                },
            },
        }
        persist_agent_outcome(db, session, settings, assessment_result, "Q-weekly")
        assessment_decision = assessment_result["output"]["replan_decision"]
        evidence_id = assessment_result["output"]["learning_evidence"]["id"]
        record = db.get(LearningEvidenceRecord, evidence_id)
        assert record is not None
        # Keep this weekly-policy regression independent from the wall clock.
        record.created_at = datetime(2026, 10, 10, 12, tzinfo=UTC)
        db.commit()
        persist_agent_outcome(db, session, settings, reflection, None)
        memory = load_learner_memory(db, session, settings)

    replanned = build_plan_draft(
        plan_input,
        assignments,
        learner_profile=memory["profile"],
        today=date(2026, 10, 12),
    )

    assert assessment_decision["action"] == "propose_draft"
    assert "knowledge_gap_observed" in assessment_decision["reasons"]
    assert assessment_decision["auto_apply"] is False
    # The weekly reflection enriches the same pending proposal instead of
    # opening a duplicate proposal during the policy cooldown window.
    assert reflection["output"]["replan_decision"]["action"] == "keep"
    assert "last_confirmed_plan" not in memory["profile"]
    assert sum(block["workMinutes"] for block in baseline["blocks"]) == 60
    assert sum(block["workMinutes"] for block in replanned["blocks"]) == 105
    assert replanned["durationAdjustments"][0]["reviewAddedMin"] == 45
    diff = plan_diff(baseline["blocks"], replanned["blocks"])
    assert diff["added"] or diff["removed"] or diff["moved"]
    assert diff["stability"] < 1
    assert diff["requires_confirmation"] is True
    engine.dispose()


def test_accepted_assessment_gap_changes_next_plan_but_keeps_old_schedule_until_confirmation():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = SessionContext(654, 987, (987,), "student", "Test", "test@example.edu", "x", "sid", 4102444800)
    settings = get_settings()
    plan_input = {
        "weekStart": "2026-10-12",
        "horizonEnd": "2026-10-18",
        "tasks": [{"taskId": "task-1", "remainingMin": 60}],
        "availability": [
            {"weekday": weekday, "enabled": True, "start": "08:00", "end": "20:00"}
            for weekday in range(7)
        ],
        "unavailable": [],
        "preferred": ["morning"],
    }
    assignments = [{
        "id": "task-1",
        "title": "Bài tập quan hệ",
        "deadline": "2026-10-18T23:59:00+07:00",
        "knowledge_components": ["binary-relations"],
    }]
    baseline = build_plan_draft(plan_input, assignments, today=date(2026, 10, 12))
    block_id = baseline["blocks"][0]["id"]
    assessment = {
        "workflow": "do",
        "status": "completed",
        "query": "Em chưa vận dụng được tính bắc cầu vào ví dụ này.",
        "do_session": {"action": "assess"},
        "assessment_review": {"status": "accepted"},
        "request": {"assessment_attempt": {
            "event_key": "assessment-plan-impact",
            "block_id": block_id,
            "response": "Em chưa vận dụng được tính bắc cầu vào ví dụ này.",
            "first_attempt": True,
            "hint_level": 0,
        }},
        "_trusted_assessment": {
            "question": "Hãy vận dụng tính bắc cầu vào một quan hệ mới.",
            "rubric_version": 2,
            "answer_type": "open",
            "knowledge_component_ids": ["binary-relations"],
            "kc_provisional": False,
        },
        "assessment_result": {
            "status": "đang hình thành",
            "confidence": "Cao",
            "evaluator_version": "test",
            "evidence_quotes": ["Em chưa vận dụng được tính bắc cầu vào ví dụ này."],
            "dimensions": {
                "recall": "passed",
                "conceptual": "passed",
                "reasoning": "passed",
                "application": "failed",
                "transfer": "not_tested",
                "retention": "not_tested",
            },
            "criterion_scores": [
                {"criterion_id": "concept", "score": 3},
                {"criterion_id": "application", "score": 1},
            ],
        },
    }
    with Session(engine) as db:
        persist_agent_outcome(db, session, settings, {
            "workflow": "plan",
            "student_decision": {"action": "confirmed"},
            "output": {"confirmed_plan": baseline},
        }, None)
        persist_agent_outcome(db, session, settings, assessment, "Q-plan-impact")
        memory = load_learner_memory(db, session, settings)

    replanned = build_plan_draft(
        plan_input,
        assignments,
        learner_profile=memory["profile"],
        mastery_profile=memory["mastery"],
        today=date(2026, 10, 12),
    )
    decision = assessment["output"]["replan_decision"]
    assert decision["action"] == "propose_draft"
    assert decision["auto_apply"] is False
    assert decision["repair_context"]["affected_task_ids"] == ["task-1"]
    assert decision["repair_context"]["failed_dimensions"] == ["application"]
    assert memory["profile"]["last_confirmed_plan"]["createdAt"] == baseline["createdAt"]
    assert sum(block["workMinutes"] for block in baseline["blocks"]) == 60
    proposed_minutes = sum(block["workMinutes"] for block in replanned["blocks"])
    assert proposed_minutes >= 90
    assert replanned["durationAdjustments"][0]["reviewAddedMin"] == 30
    assert replanned["durationAdjustments"][0]["proposedTargetMin"] == proposed_minutes
    diff = plan_diff(baseline["blocks"], replanned["blocks"])
    assert diff["requires_confirmation"] is True
    assert diff["added"] or diff["removed"] or diff["moved"]
    engine.dispose()


def test_failed_observation_records_gap_without_erasing_historical_demonstration():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    learner = SessionContext(123, 456, (456,), "student", "Test", "test@example.edu", "x", "sid", 4102444800)
    settings = get_settings()
    trusted = {"rubric_version": 1, "answer_type": "open", "knowledge_component_ids": ["kc"], "kc_provisional": False}
    with Session(engine) as db:
        for index, passed in enumerate((True, False)):
            contract = build_evidence_contract(
                session=learner,
                settings=settings,
                assessment_id="Q-1",
                trusted_assessment=trusted,
                result={
                    "status": "completed",
                    "query": "answer",
                    "request": {"assessment_attempt": {"event_key": f"e{index}"}},
                    "assessment_result": {
                        "status": "demonstrated" if passed else "misconception",
                        "confidence": "high",
                        "evaluator_version": "test",
                        "evidence_quotes": ["answer"],
                        "dimensions": dict.fromkeys(
                            ("conceptual", "reasoning", "application"), "passed" if passed else "failed"
                        ),
                    },
                },
            )
            _, snapshots = persist_learning_evidence(db, learner, settings, contract)
            db.commit()
        snapshot = snapshots[0]
        assert snapshot["level"] == "application"
        assert snapshot["latest_observed_level"] == "no_evidence"
        assert "application" in snapshot["unresolved_dimensions"]
        assert mastery_for_component({"kc": snapshot}, "kc") == 0.25
    engine.dispose()


def test_assessment_before_do_completion_uses_durable_timer_task_for_replan():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    learner = SessionContext(123, 456, (456,), "student", "Test", "test@example.edu", "x", "sid", 4102444800)
    settings = get_settings()
    assessment = {
        "workflow": "do",
        "status": "completed",
        "do_session": {"action": "assess"},
        "request": {"assessment_attempt": {"block_id": "block-before-complete", "response": "wrong", "first_attempt": True}},
        "source_refs": [{"id": "Q-timer", "citation": "chapter.pdf"}],
        "_trusted_assessment": {
            "question": "Explain the model.", "rubric_version": 1, "answer_type": "open",
            "knowledge_component_ids": ["kc-model"], "kc_provisional": False,
        },
        "assessment_result": {
            "status": "đang hình thành", "confidence": "Cao", "evaluator_version": "test",
            "evidence_quotes": ["wrong"],
            "dimensions": {"conceptual": "failed"},
            "criterion_scores": [{"criterion_id": "concept", "score": 1, "evidence_quote": "wrong"}],
        },
    }
    with Session(engine) as db:
        db.add(StudyTimerSession(
            id="SS-before-complete", institution_id=settings.institution_id, user_id=learner.user_id,
            course_id=learner.course_id, block_id="block-before-complete", task_id="task-from-timer",
            active_scope="scope-before-complete", state_json="{}", chat_json="[]",
        ))
        db.commit()
        persist_agent_outcome(db, learner, settings, assessment, "Q-timer")
        decision = assessment["output"]["replan_decision"]

    assert decision["action"] == "propose_draft"
    assert decision["repair_context"]["affected_task_ids"] == ["task-from-timer"]
    engine.dispose()


def test_teacher_review_cannot_invent_transfer_from_empty_dimensions():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    settings = get_settings()
    with Session(engine) as db:
        review = AgentReviewCase(
            id="review1",
            institution_id=settings.institution_id,
            course_id=456,
            student_user_id=123,
            case_type="understanding_review",
            entity_id="Q-1",
            payload_json="{}",
        )
        review.payload_json = json.dumps(
            {
                "rubric_version": 1,
                "topic": "topic",
                "assessment_result": {
                    "status": "đã thể hiện được",
                    "evidence_quotes": ["answer"],
                    "dimensions": {},
                    "demonstrated_level": "retained",
                },
                "learning_evidence": {"id": "ev-original", "response": "answer", "hint_level": 0},
                "trusted_assessment": {
                    "rubric_version": 1,
                    "answer_type": "open",
                    "knowledge_component_ids": ["kc"],
                    "cognitive_level": "transfer",
                },
            }
        )
        db.add(review)
        resolve_review_case(db, review, {"status": "approved"}, settings)
        db.commit()
        assert db.scalars(select(KnowledgeStateSnapshot)).all() == []
    engine.dispose()
