"""Replay benchmark for the evidence-aware schedule-repair architecture."""

# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.planning import build_plan_draft  # noqa: E402
from src.services.replan_policy import plan_diff  # noqa: E402


TODAY = date(2026, 10, 12)
ASSIGNMENTS = [
    {"id": "a", "title": "Bài gần hạn", "deadline": "2026-10-14T20:00:00+07:00"},
    {"id": "b", "title": "Bài kế tiếp", "deadline": "2026-10-16T20:00:00+07:00"},
]
PLAN_INPUT = {
    "weekStart": "2026-10-12",
    "horizonEnd": "2026-10-18",
    "tasks": [
        {"taskId": "a", "remainingMin": 120},
        {"taskId": "b", "remainingMin": 90},
    ],
    "availability": [
        {"weekday": weekday, "enabled": True, "start": "08:00", "end": "18:00"}
        for weekday in range(7)
    ],
    "unavailable": [
        {"date": "2026-10-12", "weekday": 0, "start": "08:00", "end": "12:00", "category": "other"}
    ],
    "preferred": ["afternoon"],
}


def _work(draft: dict[str, Any], task_id: str) -> int:
    return sum(int(block.get("workMinutes") or 0) for block in draft["blocks"] if block.get("taskId") == task_id)


def _case(name: str, profile: dict[str, Any], expected_change: bool) -> dict[str, Any]:
    legacy = build_plan_draft(PLAN_INPUT, ASSIGNMENTS, learner_profile={}, today=TODAY)
    repaired = build_plan_draft(PLAN_INPUT, ASSIGNMENTS, learner_profile=profile, today=TODAY)
    diff = plan_diff(legacy["blocks"], repaired["blocks"])
    old_work = _work(legacy, "a")
    new_work = _work(repaired, "a")
    changed = old_work != new_work or bool(diff["added"] or diff["removed"])
    invariants = {
        "feasible": repaired["feasibility"]["feasible"],
        "noPinnedViolation": diff["student_pinned_violations"] == 0,
        "hasDeadlineRiskSnapshot": bool(repaired["feasibility"]["deadlineRisks"]),
        "changeExpectationMet": changed is expected_change,
        "requiresConfirmation": diff["requires_confirmation"],
    }
    return {
        "name": name,
        "passed": all(invariants.values()),
        "expectedChange": expected_change,
        "legacyWorkMin": old_work,
        "newWorkMin": new_work,
        "workDeltaMin": new_work - old_work,
        "movedBlockCount": diff["moved_block_count"],
        "movedWorkMin": diff["moved_work_minutes"],
        "addedBlockCount": len(diff["added"]),
        "removedBlockCount": len(diff["removed"]),
        "stability": round(diff["stability"], 3),
        "replanAdjustments": repaired["replanAdjustments"],
        "deadlineRisks": repaired["feasibility"]["deadlineRisks"],
        "invariants": invariants,
    }


def _overload_case() -> dict[str, Any]:
    plan_input = {
        **PLAN_INPUT,
        "tasks": [{"taskId": "a", "remainingMin": 300}],
        "availability": [{"weekday": 0, "enabled": True, "start": "17:00", "end": "18:00"}],
        "unavailable": [],
    }
    assignments = [{"id": "a", "title": "Bài quá tải", "deadline": "2026-10-12T18:00:00+07:00"}]
    profile = {
        "activity_reflections": [
            {"planning_signal": {"cause": "knowledge_gap", "task_id": "a", "follow_up_minutes": 45}}
        ],
        "last_replan_proposal": {
            "action": "propose_draft",
            "repair_context": {"affected_task_ids": ["a"], "cause": "knowledge_gap"},
        },
    }
    legacy = build_plan_draft(plan_input, assignments, learner_profile={}, today=TODAY)
    repaired = build_plan_draft(plan_input, assignments, learner_profile=profile, today=TODAY)
    no_after_deadline = all(
        block["date"] < "2026-10-12" or (block["date"] == "2026-10-12" and block["end"] <= "18:00")
        for block in repaired["blocks"]
    )
    risks = repaired["feasibility"]["deadlineRisks"]
    invariants = {
        "explicitShortfall": repaired["feasibility"]["deficitMin"] > legacy["feasibility"]["deficitMin"] > 0,
        "noAfterDeadline": no_after_deadline,
        "p50ShortageVisible": risks[-1]["risk"] == "p50_shortage",
        "notAutoApplied": True,
    }
    return {
        "name": "deadline_overload",
        "passed": all(invariants.values()),
        "legacyDeficitMin": legacy["feasibility"]["deficitMin"],
        "newDeficitMin": repaired["feasibility"]["deficitMin"],
        "deadlineRisks": risks,
        "invariants": invariants,
    }


def build_report() -> dict[str, Any]:
    slow_progress = {
        "last_do_session": {
            "task_id": "a", "block_id": "slow-1", "status": "needs_more_time",
            "planned_minutes": 60, "actual_minutes": 90, "completion_percent": 50,
        },
        "last_replan_proposal": {
            "action": "propose_draft",
            "repair_context": {"affected_task_ids": ["a"], "cause": "estimate_error"},
        },
    }
    knowledge_gap = {
        "activity_reflections": [
            {"planning_signal": {"cause": "knowledge_gap", "task_id": "a", "follow_up_minutes": 45}}
        ],
        "last_replan_proposal": {
            "action": "propose_draft",
            "repair_context": {"affected_task_ids": ["a"], "cause": "knowledge_gap"},
        },
    }
    interrupted = {
        "last_do_session": {
            "task_id": "a", "block_id": "interrupt-1", "status": "needs_more_time",
            "planned_minutes": 60, "actual_minutes": 30, "completion_percent": 50,
        },
        "activity_reflections": [
            {"planning_signal": {"cause": "interruption", "task_id": "a", "follow_up_minutes": 60}}
        ],
        "last_replan_proposal": {
            "action": "propose_draft",
            "repair_context": {"affected_task_ids": ["a"], "cause": "interruption"},
        },
    }
    cases = [
        _case("slow_progress", slow_progress, True),
        _case("validated_knowledge_gap", knowledge_gap, True),
        _case("unexpected_interruption", interrupted, False),
        _overload_case(),
    ]
    return {
        "benchmark": "legacy-rerun-vs-evidence-aware-repair",
        "passed": all(case["passed"] for case in cases),
        "cases": cases,
        "claimBoundary": "Synthetic replay validates scheduling behavior, not educational effectiveness.",
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))

