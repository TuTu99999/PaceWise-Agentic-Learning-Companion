import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.agents.workflows.reflect import reflect_node
from src.config import get_settings
from src.db import Base
from src.persistence_models import LearnerMemory, LearningEvent
from src.security import SessionContext
from src.services.agent_memory import persist_agent_outcome
from src.services.plan_intelligence import normalize_reflection_feedback
from src.services.planning_signals import CAUSES, normalize_planning_signal
from src.services.reflection_observations import load_reflection_observations, reflection_context
from src.services.replan_policy import decide_weekly_replan

NOW = datetime(2026, 10, 8, 10, tzinfo=UTC)


@pytest.mark.parametrize("cause", sorted(CAUSES))
def test_every_reflect_cause_survives_plan_adapter(cause):
    signal = normalize_planning_signal(
        {
            "cause": cause,
            "duration_factor": 1.2,
            "follow_up_minutes": 30,
            "task_id": "t",
        }
    )
    feedback = normalize_reflection_feedback({"last_reflection": {"planning_signal": signal}}, task_id="t")
    assert feedback["cause"] == cause
    assert feedback["durationFactor"] == 1.0  # A cause alone is not a duration calibration dataset.
    assert feedback["followUpMinutes"] == (0 if cause in {"capacity_changed", "insufficient_time", "interruption", "missed_block", "schedule_conflict", "unknown"} else 30)


@pytest.mark.parametrize("legacy,expected", [("underestimated", "estimate_error"), ("distraction", "interruption")])
def test_legacy_aliases(legacy, expected):
    assert normalize_planning_signal({"cause": legacy})["cause"] == expected


def test_unknown_nonfinite_and_malformed_signal_are_safe_and_auditable():
    signal = normalize_planning_signal(
        {
            "cause": "invented",
            "duration_factor": float("nan"),
            "follow_up_minutes": float("inf"),
            "affected_kcs": 42,
        }
    )
    assert signal["cause"] == "unknown"
    assert signal["unrecognized_cause"] == "invented"
    assert signal["duration_factor"] == 1
    assert signal["follow_up_minutes"] == 0
    assert signal["affected_kcs"] == []
    assert normalize_reflection_feedback({"last_reflection": {"planning_signal": signal}})["cause"] == "unknown"


@pytest.mark.parametrize(
    "forged",
    [
        {"planned_minutes": 999},
        {"activity": {"actual_minutes": 999}},
        {"invented_fact": 1},
        {"assessment_evidence": [{"valid": True}]},
    ],
)
def test_model_cannot_overwrite_evidence_or_display_conflicting_advice(monkeypatch, forged):
    metrics = {"reflection_scope": "activity", "planned_minutes": 60, "activity": {"actual_minutes": 100}}
    text = (
        "You studied 999 minutes.\n```json\n"
        + json.dumps(
            {
                "effective": "999 minutes",
                "evidence": forged,
                "planning_signal": {"cause": "estimate_error", "duration_factor": 1.5},
            }
        )
        + "\n```"
    )
    monkeypatch.setattr(
        "src.agents.workflows.reflect.get_agent_llm",
        lambda **kw: SimpleNamespace(invoke=lambda messages: SimpleNamespace(content=text)),
    )
    result = reflect_node({"progress_metrics": metrics})
    draft = result["reflection_draft"]
    assert draft["evidence"] == metrics
    assert draft["evidence"] is not metrics
    assert draft["validation_warnings"] == ["MODEL_EVIDENCE_CONFLICT"]
    assert "999" not in result["response"]
    assert draft["planning_signal"]["duration_factor"] == 1
    draft["evidence"]["activity"]["actual_minutes"] = 7
    assert metrics["activity"]["actual_minutes"] == 100


def test_weekly_missed_earlier_session_survives_completed_last_session_and_duplicate_guard():
    observed = {
        "week_start": "2026-10-05",
        "sessions": [
            {
                "block_id": "first",
                "status": "missed",
                "planned_minutes": 60,
                "actual_minutes": 0,
                "source_ref": "ev-missed",
            },
            {
                "block_id": "last",
                "status": "completed",
                "planned_minutes": 60,
                "actual_minutes": 60,
                "completion_percent": 100,
                "source_ref": "ev-complete",
            },
        ],
    }
    result = decide_weekly_replan(signal={}, observations=observed, now=NOW)
    assert result["action"] == "propose_draft"
    assert "missed_block" in result["reasons"]
    assert result["observed_session_count"] == 2
    assert result["trigger_source_refs"] == ["ev-missed"]
    assert result["auto_apply"] is False
    assert decide_weekly_replan(signal={}, observations=observed, previous=result, now=NOW)["reasons"] == [
        "duplicate_signal",
    ]


def test_weekly_evidence_uses_latest_tested_dimension_and_separates_courses():
    def evidence(id, course, dimensions):
        return {
            "id": id,
            "course_id": course,
            "knowledge_component_ids": ["kc"],
            "valid": True,
            "confidence": "high",
            "dimensions": dimensions,
        }

    observed = {
        "assessment_evidence": [
            evidence("old", 1, {"application": "failed"}),
            evidence("new", 1, {"application": "passed"}),
        ]
    }
    assert decide_weekly_replan(signal={}, observations=observed, now=NOW)["action"] == "keep"
    observed["assessment_evidence"].append(evidence("other-course", 2, {"application": "failed"}))
    result = decide_weekly_replan(signal={}, observations=observed, now=NOW)
    assert result["trigger_source_refs"] == ["other-course"]
    observed["assessment_evidence"].append(evidence("recall-only", 2, {"recall": "passed"}))
    assert decide_weekly_replan(signal={}, observations=observed, now=NOW)["action"] == "propose_draft"


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _learner():
    return SessionContext(123, 1, (1, 2), "student", "Test", "", "", "sid", 4102444800)


def _seed_memory(db, learner, course, sessions, settings):
    row = LearnerMemory(
        id=f"{settings.institution_id}:{learner.user_id}:{course}",
        institution_id=settings.institution_id,
        user_id=learner.user_id,
        course_id=course,
        profile_json=json.dumps({"do_history": sessions}),
    )
    db.add(row)
    db.commit()
    return row


def test_observations_scope_week_all_enrolled_courses_and_no_foreign_records(memory_db):
    db, learner, settings = memory_db, _learner(), get_settings()
    for course in (1, 2, 3):
        _seed_memory(
            db,
            learner,
            course,
            [
                {"block_id": f"b{course}", "date": "2026-10-06", "planned_minutes": 60},
                {"block_id": "old", "date": "2026-09-30"},
                {"block_id": "future", "date": "2026-10-10"},
            ],
            settings,
        )
    _seed_memory(
        db,
        replace(learner, user_id=999),
        1,
        [
            {"block_id": "foreign", "date": "2026-10-06"},
        ],
        settings,
    )
    observed = load_reflection_observations(db, learner, settings, {"week_start": "2026-10-05"}, now=NOW)
    assert {item["block_id"] for item in observed["sessions"]} == {"b1", "b2"}
    assert observed["planned_minutes"] == 120
    context = reflection_context(observed, {"planned_minutes": 999})
    assert context["planned_minutes"] == 120
    assert context["self_report"]["planned_minutes"] == 999
    activity = load_reflection_observations(
        db,
        learner,
        settings,
        {
            "week_start": "2026-10-05",
            "reflection_scope": "activity",
            "activity": {"block_id": "missing"},
        },
        now=NOW,
    )
    assert activity["session_count"] == 0
    assert activity["data_status"] == "no_observations"


def test_weekly_confirmation_reads_all_history_not_last_do(memory_db):
    db, learner, settings = memory_db, _learner(), get_settings()
    start = datetime.now(UTC).date()
    row = _seed_memory(
        db,
        learner,
        1,
        [
            {
                "block_id": "missed",
                "recorded_at": start.isoformat(),
                "status": "missed",
                "planned_minutes": 60,
                "actual_minutes": 0,
            },
            {
                "block_id": "last",
                "recorded_at": start.isoformat(),
                "status": "completed",
                "planned_minutes": 60,
                "actual_minutes": 60,
                "completion_percent": 100,
            },
        ],
        settings,
    )
    before_mastery = row.mastery_json
    result = {
        "workflow": "reflect",
        "status": "completed",
        "reflection_draft": {"scope": "weekly", "week_start": start.isoformat(), "planning_signal": {"cause": "none"}},
    }
    persist_agent_outcome(db, learner, settings, result, None)
    decision = result["output"]["replan_decision"]
    assert decision["action"] == "propose_draft"
    assert "missed_block" in decision["reasons"]
    assert row.mastery_json == (before_mastery or "{}")


def test_durable_do_events_survive_memory_cap_and_retries_do_not_double_count(memory_db):
    db, learner, settings = memory_db, _learner(), get_settings()
    for number in range(22):
        do = {
            "action": "complete",
            "block_id": f"b{number}",
            "planned_minutes": 60,
            "actual_minutes": 60,
            "status": "completed",
        }
        persist_agent_outcome(db, learner, settings, {"workflow": "do", "output": {"do_session": do}}, None)
    persist_agent_outcome(db, learner, settings, {"workflow": "do", "output": {"do_session": do}}, None)
    observed = load_reflection_observations(db, learner, settings, {})
    assert observed["session_count"] == 22
    assert (
        len(db.scalars(select(LearningEvent).where(LearningEvent.event_type == "STUDY_SESSION_COMPLETED")).all()) == 22
    )
