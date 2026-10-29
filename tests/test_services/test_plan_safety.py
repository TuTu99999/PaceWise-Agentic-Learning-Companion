from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.services.plan_intelligence import evaluate_plan_quality
from src.services.planning import build_plan_draft

NOW = datetime(2026, 10, 8, 10, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


def _input(start="17:00", end="21:00", **extra):
    return {
        "weekStart": "2026-10-05",
        "tasks": [{"taskId": "a1", "remainingMin": 60}],
        "availability": [{"weekday": 3, "enabled": True, "start": start, "end": end}],
        "unavailable": [],
        "preferred": "evening",
        **extra,
    }


def _draft(deadline, start="17:00", end="21:00", **kwargs):
    return build_plan_draft(
        _input(start, end), [{"id": "a1", "title": "Task", "deadline": deadline}], now=NOW, **kwargs
    )


@pytest.mark.parametrize("deadline", ["2026-10-08T12:00:00+07:00", "2026-10-08T05:00:00Z", "2026-10-08T12:00:00"])
def test_no_work_after_noon_even_on_same_day(deadline):
    draft = _draft(deadline)
    assert draft["blocks"] == []
    assert draft["feasibility"]["shortfalls"] == [{"taskId": "a1", "missingMin": 60}]
    assert not draft["feasibility"]["robustFeasible"]
    assert not draft["qualityEvaluation"]["canConfirm"]


def test_clips_exact_deadline_and_does_not_consume_later_capacity():
    draft = _draft("2026-10-08T12:00:00+07:00", "11:00", "21:00")
    assert draft["blocks"][0]["end"] == "12:00"
    assert draft["feasibility"]["feasible"]
    assert not draft["feasibility"]["robustFeasible"]
    assert draft["qualityEvaluation"]["canConfirm"]
    assert {w["code"] for w in draft["qualityEvaluation"]["warnings"]} == {"ROBUST_CAPACITY_RISK"}


def test_utc_deadline_is_converted_to_calendar_timezone():
    draft = _draft("2026-10-07T23:30:00Z", "17:00", "21:00")
    assert not draft["blocks"]  # 06:30 on Oct 8, not an Oct 7 date-only constraint.
    assert draft["priorityOrder"] == []  # Already expired at NOW=10:00 local.
    assert draft["expiredTasks"][0]["deadline"] == "2026-10-08T06:30:00+07:00"
    assert draft["feasibility"]["deficitMin"] == 0


def test_date_only_deadline_allows_end_at_midnight():
    draft = _draft("2026-10-08", "23:00", "24:00")
    assert draft["blocks"][0]["end"] == "24:00"
    assert draft["qualityEvaluation"]["canConfirm"]


def test_deadline_at_midnight_allows_nothing_later_that_day():
    assert not _draft("2026-10-08T00:00:00+07:00")["blocks"]


def test_earlier_time_deadline_beats_personal_priority():
    payload = _input(
        "11:00",
        "13:00",
        tasks=[
            {"taskId": "later", "remainingMin": 60, "personalPriority": 4},
            {"taskId": "a1", "remainingMin": 60, "personalPriority": 1},
        ],
    )
    draft = build_plan_draft(
        payload,
        [
            {"id": "later", "deadline": "2026-10-08T13:00:00+07:00"},
            {"id": "a1", "deadline": "2026-10-08T12:00:00+07:00"},
        ],
        now=NOW,
    )
    assert draft["priorityOrder"][0]["taskId"] == "a1"
    assert draft["blocks"][0]["taskId"] == "a1"


def test_history_adjusts_proposed_duration_without_mutating_student_input():
    payload = _input()
    profile = {"do_history": [{"task_id": "a1", "block_id": f"b{i}", "completion_percent": 100, "planned_minutes": 60, "actual_minutes": 120,
                              "time_source": "timer", "readiness_key": "application", "rhythm": {"sessionMinutes": 60, "breakMinutes": 10}}
                             for i in range(3)]}
    draft = build_plan_draft(payload, [{"id": "a1", "deadline": "2026-10-09"}], now=NOW, learner_profile=profile)
    assert draft["input"] == payload
    assert payload["tasks"][0]["remainingMin"] == 60
    assert draft["planningTargets"][0]["targetMin"] == 105
    assert draft["durationAdjustments"][0]["requiresConfirmation"]
    assert (
        sum(
            int(b["end"][:2]) * 60 + int(b["end"][3:]) - int(b["start"][:2]) * 60 - int(b["start"][3:])
            for b in draft["blocks"]
        )
        == 105
    )
    assert draft["milestones"][0]["estimate"]["p50_minutes"] == 105  # Not multiplied twice.


def _quality(blocks, milestones=None, **extra):
    return evaluate_plan_quality(
        {
            "scheduleStart": "2026-10-08",
            "blocks": blocks,
            "milestones": milestones or [],
            "feasibility": {"feasible": True, "robustFeasible": True},
            **extra,
        },
        [{"id": "a1", "deadline": "2026-10-08T12:00:00+07:00"}],
    )


def test_independent_gate_detects_intraday_deadline_violation():
    q = _quality([{"id": "bad", "taskId": "a1", "date": "2026-10-08", "start": "17:00", "end": "18:00"}])
    assert not q["canConfirm"]
    assert "AFTER_DEADLINE" in {e["code"] for e in q["blockingErrors"]}


def test_independent_gate_rejects_block_moved_before_prerequisite_lesson_end():
    q = evaluate_plan_quality(
        {
            "scheduleStart": "2026-10-08",
            "blocks": [{"id": "too-early", "taskId": "a1", "date": "2026-10-08", "start": "15:00", "end": "16:00"}],
            "milestones": [],
            "feasibility": {"feasible": True, "robustFeasible": True},
        },
        [{
            "id": "a1",
            "deadline": "2026-10-08T22:00:00+07:00",
            "learning_available_at": "2026-10-08T16:30:00+07:00",
        }],
        now=NOW,
    )
    assert not q["canConfirm"]
    assert "BEFORE_PREREQUISITE" in {e["code"] for e in q["blockingErrors"]}


def test_independent_gate_requires_dependency_completion_not_just_start():
    blocks = [
        {"taskId": "a1", "milestoneId": "M1", "date": "2026-10-08", "start": "10:00", "end": "10:30"},
        {"taskId": "a1", "milestoneId": "M2", "date": "2026-10-08", "start": "10:40", "end": "11:00"},
        {"taskId": "a1", "milestoneId": "M1", "date": "2026-10-08", "start": "11:10", "end": "11:40"},
    ]
    q = _quality(blocks, [{"milestoneId": "M1"}, {"milestoneId": "M2", "dependsOn": ["M1"]}])
    assert "DEPENDENCY_ORDER" in {e["code"] for e in q["blockingErrors"]}
    assert not q["canConfirm"]


def test_unknown_dependency_is_hard_error_but_missing_coverage_is_warning():
    q = _quality([], [{"milestoneId": "M1", "dependsOn": ["unknown"]}])
    assert not q["canConfirm"]
    q = _quality(
        [],
        rubricCoverage=[{"taskId": "a1", "criteria": ["R1"], "coveredCriterionIds": [], "missingCriterionIds": ["R1"]}],
    )
    assert q["canConfirm"]
    assert not q["releaseReady"]
    assert "RUBRIC_COVERAGE_GAP" in {w["code"] for w in q["warnings"]}
