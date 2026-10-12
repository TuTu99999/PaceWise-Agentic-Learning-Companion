"""Deterministic persona and fuzz evaluation for the PaceWise scheduler.

The suite is intentionally isolated from HTTP, databases, and workspaces. It
uses the four-course medium workbook, synthesizes learner calendar edits in
memory, and writes only a JSON report when executed as a script.
"""

# ruff: noqa: E402, I001

from __future__ import annotations

import argparse
import json
import random
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_plan_background import (
    DEFAULT_WORKBOOK,
    TIMEZONE_NAME,
    _as_datetime,
    _clock,
    read_workbook,
    select_assignments,
)
from src.services.planning import build_plan_draft


DEFAULT_REPORT = ROOT / "outputs" / "plan-background-eval" / "persona-matrix.json"
TIMEZONE = ZoneInfo(TIMEZONE_NAME)
SIMULATION_NOW = datetime(2026, 10, 5, 4, 30, tzinfo=TIMEZONE)
HORIZON_END = date(2026, 10, 12)
SEED = 20261011


def _minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        str(left.get("date"))[:10] == str(right.get("date"))[:10]
        and str(left.get("start")) < str(right.get("end"))
        and str(right.get("start")) < str(left.get("end"))
    )


def _lessons(data: Any) -> list[dict[str, Any]]:
    result = []
    for row in data.lessons:
        lesson_at = _as_datetime(row.get("date"))
        if SIMULATION_NOW.date() <= lesson_at.date() <= HORIZON_END:
            result.append(
                {
                    "date": lesson_at.date().isoformat(),
                    "weekday": lesson_at.weekday(),
                    "start": _clock(row.get("start_time")),
                    "end": _clock(row.get("end_time")),
                    "category": "class",
                    "title": str(row.get("title") or "Buổi học"),
                }
            )
    return result


def _availability(start: str, end: str, enabled_days: set[int] | None = None) -> list[dict[str, Any]]:
    enabled_days = set(range(7)) if enabled_days is None else enabled_days
    return [
        {"weekday": weekday, "enabled": weekday in enabled_days, "start": start, "end": end}
        for weekday in range(7)
    ]


def _split_availability(ranges: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [
        {"weekday": weekday, "enabled": True, "start": start, "end": end}
        for weekday in range(7)
        for start, end in ranges
    ]


def _tasks(assignments: list[dict[str, Any]], minutes: list[int] | None = None) -> list[dict[str, Any]]:
    loads = minutes or [90, 150, 120, 90]
    return [
        {"taskId": assignment["id"], "remainingMin": loads[index]}
        for index, assignment in enumerate(assignments)
    ]


def _base_input(
    assignments: list[dict[str, Any]],
    lessons: list[dict[str, Any]],
    *,
    availability: list[dict[str, Any]],
    preferred: str | list[str],
    personal: list[dict[str, Any]] | None = None,
    pins: list[dict[str, Any]] | None = None,
    session_minutes: int = 60,
    break_minutes: int = 10,
    checkpoint_minutes: int = 5,
    task_minutes: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "weekStart": SIMULATION_NOW.date().isoformat(),
        "horizonEnd": HORIZON_END.isoformat(),
        "tasks": _tasks(assignments, task_minutes),
        "availability": availability,
        "unavailable": [*deepcopy(lessons), *(personal or [])],
        "preferred": preferred,
        "studyPreferences": {
            "sessionMinutes": session_minutes,
            "breakMinutes": break_minutes,
            "checkpointMinutes": checkpoint_minutes,
            "adaptiveSuggestionsEnabled": True,
        },
        "pinnedBlocks": pins or [],
    }


def _invariants(
    draft: dict[str, Any],
    assignments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocks = [item for item in draft.get("blocks") or [] if item.get("status") != "history"]
    agent_blocks = [item for item in blocks if item.get("placementSource") == "agent"]
    known_tasks = {str(item["id"]) for item in assignments}
    deadlines = {str(item["id"]): _as_datetime(item["deadline"]) for item in assignments}
    unavailable = [
        item
        for item in (draft.get("input") or {}).get("unavailable") or []
        if item.get("category") != "self_study"
    ]
    shortfalls = (draft.get("feasibility") or {}).get("shortfalls") or []
    deficit = int((draft.get("feasibility") or {}).get("deficitMin") or 0)
    feasible = bool((draft.get("feasibility") or {}).get("feasible"))
    failures: list[dict[str, Any]] = []

    def require(code: str, passed: bool, detail: Any = None) -> None:
        if not passed:
            failures.append({"code": code, "detail": detail})

    require("known_tasks_only", all(str(block.get("taskId")) in known_tasks for block in blocks))
    require(
        "deadline_cutoff",
        all(
            datetime.fromisoformat(f"{block['date']}T{block['end']}:00").replace(tzinfo=TIMEZONE)
            <= deadlines[str(block["taskId"])]
            for block in blocks
        ),
    )
    require("no_busy_overlap", not any(_overlaps(block, busy) for block in blocks for busy in unavailable))
    require(
        "no_block_overlap",
        not any(_overlaps(left, right) for index, left in enumerate(blocks) for right in blocks[index + 1 :]),
    )
    require(
        "not_in_past",
        all(
            datetime.fromisoformat(f"{block['date']}T{block['end']}:00").replace(tzinfo=TIMEZONE)
            > SIMULATION_NOW
            for block in blocks
        ),
    )
    require(
        "agent_session_bound",
        all(
            int(block.get("workMinutes") or 0)
            <= int((block.get("rhythm") or {}).get("sessionMinutes") or 90)
            - int(block.get("checkpointMinutes") or 0)
            for block in agent_blocks
        ),
    )
    require("deficit_equals_shortfalls", deficit == sum(int(item.get("missingMin") or 0) for item in shortfalls))
    require("feasibility_consistent", feasible == (deficit == 0 and not shortfalls))
    require(
        "quality_has_no_hard_violation",
        not ((draft.get("qualityEvaluation") or {}).get("violations") or []),
        (draft.get("qualityEvaluation") or {}).get("violations") or [],
    )
    return failures


def _persona_cases(assignments: list[dict[str, Any]], lessons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    night_pin = {
        "id": "night-owl-pin",
        "taskId": assignments[-1]["id"],
        "date": "2026-10-10",
        "start": "22:00",
        "end": "22:45",
        "placementSource": "student",
        "checkpointMinutes": 5,
    }
    repeated_blackout = [
        {
            "date": (SIMULATION_NOW.date() + timedelta(days=offset)).isoformat(),
            "weekday": (SIMULATION_NOW.date() + timedelta(days=offset)).weekday(),
            "start": "05:00",
            "end": "23:59",
            "category": "personal",
            "title": "Không thể học",
        }
        for offset in range(8)
    ]
    return [
        {
            "name": "early_bird",
            "expectFeasible": True,
            "input": _base_input(assignments, lessons, availability=_availability("05:00", "11:30"), preferred="morning"),
        },
        {
            "name": "evening_after_work",
            "expectFeasible": True,
            "input": _base_input(assignments, lessons, availability=_availability("18:00", "23:00"), preferred="evening"),
        },
        {
            "name": "night_owl_with_student_pin",
            "expectFeasible": True,
            "requiredPin": "night-owl-pin",
            "input": _base_input(
                assignments,
                lessons,
                availability=_availability("20:30", "23:59"),
                preferred="night",
                pins=[night_pin],
                session_minutes=45,
                break_minutes=10,
            ),
        },
        {
            "name": "split_shift",
            "expectFeasible": True,
            "input": _base_input(
                assignments,
                lessons,
                availability=_split_availability([("05:30", "08:00"), ("19:30", "22:30")]),
                preferred=["morning", "evening"],
            ),
        },
        {
            "name": "weekend_only",
            "expectFeasible": True,
            "input": _base_input(
                assignments,
                lessons,
                availability=_availability("07:00", "22:00", {5, 6}),
                preferred=["morning", "afternoon", "evening"],
            ),
        },
        {
            "name": "micro_sessions_with_breaks",
            "expectFeasible": True,
            "input": _base_input(
                assignments,
                lessons,
                availability=_availability("06:00", "22:00"),
                preferred=["morning", "evening"],
                session_minutes=30,
                break_minutes=15,
                checkpoint_minutes=5,
            ),
        },
        {
            "name": "dragged_self_study_windows",
            "expectFeasible": True,
            "input": _base_input(
                assignments,
                lessons,
                availability=_availability("08:00", "20:00", {0, 2, 4}),
                preferred="afternoon",
                personal=[
                    {"date": "2026-10-06", "weekday": 1, "start": "06:00", "end": "08:00", "category": "self_study"},
                    {"date": "2026-10-08", "weekday": 3, "start": "21:00", "end": "23:00", "category": "self_study"},
                    {"date": "2026-10-10", "weekday": 5, "start": "14:00", "end": "18:00", "category": "self_study"},
                ],
            ),
        },
        {
            "name": "thin_capacity_must_fail",
            "expectFeasible": False,
            "input": _base_input(
                assignments,
                lessons,
                availability=_availability("22:00", "22:30", {0, 2, 4}),
                preferred="evening",
            ),
        },
        {
            "name": "complete_blackout_must_fail",
            "expectFeasible": False,
            "input": _base_input(
                assignments,
                [],
                availability=_availability("05:00", "23:59"),
                preferred=["morning", "evening"],
                personal=repeated_blackout,
            ),
        },
    ]


def _run_case(case: dict[str, Any], assignments: list[dict[str, Any]]) -> dict[str, Any]:
    draft = build_plan_draft(
        case["input"],
        assignments,
        proposed_milestones=[],
        learner_profile={},
        mastery_profile={},
        timezone_name=TIMEZONE_NAME,
        now=SIMULATION_NOW,
        window_days=8,
    )
    failures = _invariants(draft, assignments)
    feasible = bool((draft.get("feasibility") or {}).get("feasible"))
    if feasible is not case["expectFeasible"]:
        failures.append({"code": "unexpected_feasibility", "detail": {"expected": case["expectFeasible"], "actual": feasible}})
    required_pin = case.get("requiredPin")
    if required_pin and not any(block.get("id") == required_pin for block in draft.get("blocks") or []):
        failures.append({"code": "student_pin_not_preserved", "detail": required_pin})
    return {
        "name": case["name"],
        "passed": not failures,
        "feasible": feasible,
        "deficitMin": (draft.get("feasibility") or {}).get("deficitMin"),
        "robustFeasible": (draft.get("feasibility") or {}).get("robustFeasible"),
        "blockCount": len(draft.get("blocks") or []),
        "failures": failures,
    }


def _random_calendar(rng: random.Random, index: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    profile = rng.choice(
        [
            ("morning", "05:00", "11:30"),
            ("afternoon", "11:30", "18:30"),
            ("evening", "17:00", "23:00"),
            ("night", "20:30", "23:59"),
            ("mixed", "06:00", "23:00"),
        ]
    )
    enabled = {day for day in range(7) if rng.random() < 0.72}
    if not enabled:
        enabled.add(rng.randrange(7))
    availability = _availability(profile[1], profile[2], enabled)
    edits: list[dict[str, Any]] = []
    start_bound, end_bound = _minutes(profile[1]), _minutes(profile[2])
    for edit_index in range(rng.randint(3, 12)):
        offset = rng.randrange(8)
        target_day = SIMULATION_NOW.date() + timedelta(days=offset)
        category = "self_study" if rng.random() < 0.35 else "personal"
        if category == "self_study" and rng.random() < 0.45:
            lower, upper = 5 * 60, 23 * 60
        else:
            lower, upper = start_bound, max(start_bound + 30, end_bound)
        start = rng.randrange(lower, max(lower + 1, upper - 29), 15)
        duration = rng.choice([30, 45, 60, 90, 120])
        end = min(23 * 60 + 59, start + duration)
        if end <= start:
            continue
        edits.append(
            {
                "date": target_day.isoformat(),
                "weekday": target_day.weekday(),
                "start": f"{start // 60:02d}:{start % 60:02d}",
                "end": f"{end // 60:02d}:{end % 60:02d}",
                "category": category,
                "title": f"fuzz-{index}-{edit_index}",
            }
        )
    return availability, edits, profile[0]


def build_report(workbook: Path = DEFAULT_WORKBOOK, *, variants: int = 128, seed: int = SEED) -> dict[str, Any]:
    data = read_workbook(workbook)
    assignments = select_assignments(data)
    lessons = _lessons(data)
    personas = [_run_case(case, assignments) for case in _persona_cases(assignments, lessons)]

    rng = random.Random(seed)
    fuzz_failures: list[dict[str, Any]] = []
    feasible_count = 0
    infeasible_count = 0
    for index in range(variants):
        availability, edits, preferred = _random_calendar(rng, index)
        session = rng.choice([30, 45, 60, 90])
        plan_input = _base_input(
            assignments,
            lessons,
            availability=availability,
            preferred=preferred,
            personal=edits,
            session_minutes=session,
            break_minutes=rng.choice([5, 10, 15]),
            checkpoint_minutes=rng.choice([0, 5]),
            task_minutes=[rng.randrange(30, 241, 15) for _ in assignments],
        )
        draft = build_plan_draft(
            plan_input,
            assignments,
            proposed_milestones=[],
            learner_profile={},
            mastery_profile={},
            timezone_name=TIMEZONE_NAME,
            now=SIMULATION_NOW,
            window_days=8,
        )
        failures = _invariants(draft, assignments)
        if (draft.get("feasibility") or {}).get("feasible"):
            feasible_count += 1
        else:
            infeasible_count += 1
        if failures:
            fuzz_failures.append(
                {
                    "variant": index,
                    "preferred": preferred,
                    "sessionMinutes": session,
                    "failures": failures,
                }
            )

    return {
        "suite": "pacewise-plan-persona-matrix",
        "passed": all(item["passed"] for item in personas) and not fuzz_failures,
        "executedAt": datetime.now(TIMEZONE).isoformat(),
        "simulationNow": SIMULATION_NOW.isoformat(),
        "isolation": {"httpRequests": 0, "databaseWrites": 0, "workspaceWrites": 0, "calendarWrites": 0},
        "workbook": str(workbook.resolve()),
        "personas": personas,
        "fuzz": {
            "seed": seed,
            "variants": variants,
            "feasible": feasible_count,
            "infeasible": infeasible_count,
            "failed": len(fuzz_failures),
            "failures": fuzz_failures[:20],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--variants", type=int, default=128)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    report = build_report(args.workbook.resolve(), variants=max(1, args.variants), seed=args.seed)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "personas": report["personas"],
        "fuzz": {key: value for key, value in report["fuzz"].items() if key != "failures"},
        "report": str(args.report.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
