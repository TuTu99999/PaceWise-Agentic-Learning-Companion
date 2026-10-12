"""Cumulative deadline-capacity risk for deterministic study planning.

Slack is evaluated at each deadline window, not per assignment in isolation.
Every task due by a cutoff competes for the same capacity before that cutoff.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any


def cumulative_deadline_risks(
    tasks: Sequence[Mapping[str, Any]],
    capacity_intervals: Mapping[date, Sequence[tuple[int, int]]],
    *,
    p50_required_by_task: Mapping[str, int],
    p80_required_by_task: Mapping[str, int],
    pinned_capacity: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return P50/P80 slack snapshots at every distinct deadline.

    ``capacity_intervals`` represents still-free learner time. Valid pinned study
    blocks are added back because they are already committed capacity for the
    same workload. Callers remain responsible for validating those blocks.
    """

    ordered = sorted(
        tasks,
        key=lambda item: (
            item["deadline"],
            int(item.get("deadline_minute", 1440)),
            str(item.get("task_id") or ""),
        ),
    )
    snapshots: list[dict[str, Any]] = []
    cumulative_ids: list[str] = []
    cumulative_p50 = 0
    cumulative_p80 = 0

    for index, task in enumerate(ordered):
        task_id = str(task.get("task_id") or "")
        cumulative_ids.append(task_id)
        cumulative_p50 += max(0, int(p50_required_by_task.get(task_id, 0)))
        cumulative_p80 += max(0, int(p80_required_by_task.get(task_id, 0)))

        deadline = task["deadline"]
        cutoff = int(task.get("deadline_minute", 1440))
        next_task = ordered[index + 1] if index + 1 < len(ordered) else None
        if next_task and (
            next_task["deadline"], int(next_task.get("deadline_minute", 1440))
        ) == (deadline, cutoff):
            continue

        available = sum(
            max(0, min(end, cutoff if day == deadline else 1440) - start)
            for day, intervals in capacity_intervals.items()
            if day <= deadline
            for start, end in intervals
        )
        available += sum(
            max(0, int(block.get("end_minute", 0)) - int(block.get("start_minute", 0)))
            for block in pinned_capacity
            if str(block.get("task_id") or "") in cumulative_ids
            and block.get("date") <= deadline
            and (
                block.get("date") < deadline
                or int(block.get("end_minute", 0)) <= cutoff
            )
        )
        slack_p50 = available - cumulative_p50
        slack_p80 = available - cumulative_p80
        risk = "p50_shortage" if slack_p50 < 0 else "p80_shortage" if slack_p80 < 0 else "safe"
        snapshots.append(
            {
                "deadline": deadline.isoformat(),
                "deadlineMinute": cutoff,
                "taskIds": list(cumulative_ids),
                "availableMin": available,
                "requiredP50Min": cumulative_p50,
                "requiredP80Min": cumulative_p80,
                "slackP50Min": slack_p50,
                "slackP80Min": slack_p80,
                "risk": risk,
            }
        )
    return snapshots

