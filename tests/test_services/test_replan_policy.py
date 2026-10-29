from datetime import UTC, datetime, timedelta

import pytest

from src.agents.workflows.do import evaluate_completion
from src.services.plan_intelligence import mastery_for_component
from src.services.planning import build_plan_draft
from src.services.replan_policy import decide_replan, plan_diff


def _decision(**kwargs):
    return decide_replan(
        signal=kwargs.pop("signal", {}),
        last_do=kwargs.pop("last_do", {}),
        latest_evidence=kwargs.pop("latest_evidence", {}),
        **kwargs,
    )


def test_small_signal_and_self_report_are_not_knowledge_proof():
    decision = _decision(
        signal={"cause": "missing_prerequisite", "duration_factor": 1.5},
        last_do={"planned_minutes": 60, "actual_minutes": 65, "completion_percent": 100},
    )
    assert decision["action"] == "keep"
    assert decision["evidence_note"] == "self_report_requires_assessment"
    assert decision["auto_apply"] is False


@pytest.mark.parametrize("cause", ["knowledge_gap", "missing_prerequisite", "misconception"])
def test_self_reported_learning_problem_requires_assessment_before_replan(cause):
    decision = _decision(
        signal={"cause": cause, "duration_factor": 1.5, "follow_up_minutes": 45},
        last_do={
            "status": "completed",
            "planned_minutes": 60,
            "actual_minutes": 60,
            "completion_percent": 100,
        },
        latest_evidence={},
    )
    assert decision["action"] == "keep"
    assert decision["evidence_note"] == "self_report_requires_assessment"
    assert decision["auto_apply"] is False


@pytest.mark.parametrize(
    "last_do,expected",
    [
        ({"status": "missed", "planned_minutes": 60}, "missed_block"),
        (
            {"status": "needs_more_time", "planned_minutes": 60, "actual_minutes": 95, "completion_percent": 60},
            "actual_time_deviation",
        ),
        (
            {"status": "blocked", "planned_minutes": 60, "actual_minutes": 60, "completion_percent": 50},
            "unfinished_work",
        ),
    ],
)
def test_real_drift_proposes_only_future_confirmed_changes(last_do, expected):
    decision = _decision(last_do=last_do)
    assert decision["action"] == "propose_draft"
    assert expected in decision["reasons"]
    assert decision["requires_confirmation"] is True
    assert decision["mutable_scope"] == "future_uncompleted_student_blocks"
    assert decision["auto_apply"] is False
    assert decision["repair_context"]["affected_task_ids"] == ([last_do["task_id"]] if last_do.get("task_id") else [])


def test_uncertain_misconception_does_not_trigger_but_observed_failure_does():
    evidence = {"valid": True, "confidence": "high", "misconceptions": [{"status": "suspected"}], "dimensions": {}}
    assert _decision(latest_evidence=evidence)["action"] == "keep"
    evidence["dimensions"] = {"application": "failed"}
    assert _decision(latest_evidence=evidence)["action"] == "propose_draft"
    evidence["confidence"] = "low"
    assert _decision(latest_evidence=evidence)["action"] == "keep"


def test_duplicates_and_cooldown_avoid_schedule_churn():
    instant = datetime(2026, 10, 8, tzinfo=UTC)
    last = {"block_id": "b1", "status": "missed", "planned_minutes": 60}
    previous = _decision(last_do=last, now=instant)
    assert _decision(last_do=last, previous=previous, now=instant + timedelta(minutes=1))["reasons"] == [
        "duplicate_signal"
    ]
    last["block_id"] = "b2"
    assert _decision(last_do=last, previous=previous, now=instant + timedelta(minutes=1))["reasons"] == ["cooldown"]
    assert _decision(last_do=last, previous=previous, now=instant + timedelta(hours=1))["action"] == "propose_draft"
    assert (
        _decision(
            signal={"cause": "deadline_changed", "source": "lms_or_calendar_event"},
            previous=previous,
            now=instant + timedelta(minutes=1),
        )["action"]
        == "propose_draft"
    )


def test_diff_ignores_random_ids_and_explains_changes():
    block = {"id": "old", "taskId": "t", "date": "2026-10-08", "start": "09:00", "end": "10:00"}
    assert plan_diff([block], [{**block, "id": "new"}])["stability"] == 1
    moved = {**block, "start": "10:00", "end": "11:00"}
    result = plan_diff([block], [moved])
    assert result["removed"] == [block]
    assert result["added"] == [moved]
    assert result["moved_block_count"] == 1
    assert result["moved_work_minutes"] == 60
    assert result["changed_day_count"] == 0
    assert result["student_pinned_violations"] == 0
    assert result["requires_confirmation"] is True


def test_replan_exposes_trusted_repair_context_for_the_scheduler():
    decision = _decision(
        signal={"cause": "estimate_error", "task_id": "task-1"},
        last_do={
            "task_id": "task-1",
            "block_id": "block-1",
            "status": "needs_more_time",
            "planned_minutes": 60,
            "actual_minutes": 90,
            "completion_percent": 50,
            "remaining_minutes": 30,
        },
    )

    assert decision["action"] == "propose_draft"
    assert decision["repair_context"] == {
        "affected_task_ids": ["task-1"],
        "cause": "estimate_error",
        "observed_remaining_minutes": 30,
        "signal_follow_up_minutes": 0,
    }


def test_do_reflection_uses_concrete_remaining_minutes_to_propose_replan_without_asking_for_percent():
    evaluated = evaluate_completion({
        "block_id": "block-1",
        "task_id": "task-1",
        "planned_minutes": 70,
        "actual_minutes": 64,
        "work_result": "needs_more_time",
        "remaining_minutes": 30,
        "blocker": "none",
    })["output"]["do_session"]

    assert evaluated["status"] == "needs_more_time"
    assert evaluated["remaining_minutes"] == 30
    assert evaluated["completion_percent_source"] == "derived_from_remaining_minutes"
    decision = _decision(last_do=evaluated)
    assert decision["action"] == "propose_draft"
    assert decision["reasons"] == ["unfinished_work"]
    assert decision["requires_confirmation"] is True
    assert decision["auto_apply"] is False
    assert decision["repair_context"]["observed_remaining_minutes"] == 30


def test_unknown_kc_and_new_course_do_not_inherit_similarly_named_knowledge():
    profile = {
        "relation.transitivity": {"level": "application", "source_evidence_ids": ["LE-relation"]},
        "new-kc": {"level": "no_evidence", "status": "chưa đủ bằng chứng"},
    }
    assert mastery_for_component(profile, "relation") is None
    assert mastery_for_component(profile, "new-kc") is None
    assert mastery_for_component(profile, "relation.transitivity") is not None


def test_replan_releases_elapsed_agent_blocks_without_completion_evidence():
    elapsed = {
        "id": "old",
        "taskId": "finished",
        "date": "2026-10-05",
        "start": "09:00",
        "end": "10:00",
        "placementSource": "agent",
    }
    draft = build_plan_draft(
        {"weekStart": "2026-10-05", "tasks": [], "pinnedBlocks": [elapsed]},
        [],
        now=datetime(2026, 10, 8, 10, tzinfo=UTC),
    )
    assert draft["blocks"] == []
