"""Server-owned reconciliation between completed Do blocks and a new plan."""

from __future__ import annotations

from typing import Any


def observed_plan_progress(profile: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Return remaining work and completed assignment parts per task."""
    profile = profile or {}
    plan = profile.get("last_confirmed_plan") or {}
    blocks = [item for item in plan.get("blocks") or [] if isinstance(item, dict)]
    milestones = [item for item in plan.get("milestones") or [] if isinstance(item, dict)]
    targets = {
        str(item.get("taskId") or ""): max(0, int(item.get("remainingMin") or item.get("targetMin") or 0))
        for item in plan.get("planningTargets") or []
        if isinstance(item, dict) and str(item.get("taskId") or "")
    }
    latest_by_block: dict[str, dict[str, Any]] = {}
    for item in profile.get("do_history") or []:
        if isinstance(item, dict) and str(item.get("block_id") or ""):
            latest_by_block[str(item["block_id"])] = item

    blocks_by_task: dict[str, list[dict[str, Any]]] = {}
    blocks_by_milestone: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for block in blocks:
        task_id = str(block.get("taskId") or "")
        milestone_id = str(block.get("milestoneId") or "")
        if not task_id:
            continue
        blocks_by_task.setdefault(task_id, []).append(block)
        if milestone_id:
            blocks_by_milestone.setdefault((task_id, milestone_id), []).append(block)

    result: dict[str, dict[str, Any]] = {}
    for task_id in set(targets) | set(blocks_by_task):
        baseline = targets.get(task_id)
        if baseline is None:
            continue
        credit = 0
        completed_block_ids: set[str] = set()
        for block in blocks_by_task.get(task_id, []):
            block_id = str(block.get("id") or "")
            observation = latest_by_block.get(block_id)
            if not observation:
                continue
            planned = max(0, int(block.get("workMinutes") or observation.get("planned_minutes") or 0))
            work_result = str(observation.get("work_result") or "")
            remaining = max(0, int(observation.get("remaining_minutes") or 0))
            if work_result == "planned_part_done" or (
                not work_result and str(observation.get("status") or "") == "completed" and remaining == 0
            ):
                credit += planned
                completed_block_ids.add(block_id)
            elif work_result in {"needs_more_time", "blocked"}:
                credit += planned - remaining

        completed_milestone_ids: set[str] = set()
        for (candidate_task_id, milestone_id), milestone_blocks in blocks_by_milestone.items():
            if candidate_task_id != task_id:
                continue
            block_ids = {str(item.get("id") or "") for item in milestone_blocks}
            if block_ids and block_ids <= completed_block_ids:
                completed_milestone_ids.add(milestone_id)

        completed_part_ids: set[str] = set()
        for milestone in milestones:
            if (
                str(milestone.get("taskId") or "") == task_id
                and str(milestone.get("milestoneId") or "") in completed_milestone_ids
            ):
                completed_part_ids.update(
                    str(value) for value in milestone.get("assignmentPartIds") or [] if str(value)
                )
        result[task_id] = {
            "baseline_minutes": baseline,
            "remaining_minutes": max(0, baseline - credit),
            "completed_block_ids": sorted(completed_block_ids),
            "completed_milestone_ids": sorted(completed_milestone_ids),
            "completed_assignment_part_ids": sorted(completed_part_ids),
        }
    return result
