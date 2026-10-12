"""Conservative, server-owned selection of an executable plan subset.

Capacity is not permission to violate a deadline or a prerequisite. Reject
invalid blocks (and their dependent milestones), never silently shrink work.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.services.planning_time import block_at


def confirmation_constraints(draft: dict[str, Any], workspace: dict[str, Any], calendar: list[dict[str, Any]]) -> dict[str, Any]:
    """Overlay latest saved personal/sleep constraints and live LMS events."""
    timezone = draft.get("timezone") or "Asia/Ho_Chi_Minh"
    slots = list((draft.get("input") or {}).get("unavailable") or [])
    if "unavailable" in workspace:
        slots = [s for s in slots if s.get("source") == "lms"] + list(workspace["unavailable"])
    routine = workspace.get("routineProfile")
    if routine:
        slots = [s for s in slots if s.get("source") != "routine"]
        sleep, wake = routine["sleepTime"], routine["wakeTime"]
        spans = [(sleep, wake)] if sleep < wake else [(sleep, "24:00"), ("00:00", wake)]
        if sleep != wake:
            slots.extend({"weekday": day, "start": start, "end": end, "source": "routine"}
                         for day in range(7) for start, end in spans if start < end)
    # Replace stale LMS slots rather than retaining deleted classes forever.
    slots = [s for s in slots if s.get("source") != "lms"]
    zone = ZoneInfo(timezone)
    for event in calendar:
        if event.get("type") != "event" or not event.get("ends_at"):
            continue  # Assignment deadlines are points, not busy intervals.
        def parse(value: str) -> datetime:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return (parsed.replace(tzinfo=zone) if parsed.tzinfo is None else parsed).astimezone(zone)
        start, end = parse(event["starts_at"]), parse(event["ends_at"])
        day = start.date()
        while day <= end.date():
            left = start.strftime("%H:%M") if day == start.date() else "00:00"
            right = end.strftime("%H:%M") if day == end.date() else "24:00"
            if left < right:
                slots.append({"date": day.isoformat(), "start": left, "end": right, "source": "lms"})
            day += timedelta(days=1)
    return {**draft, "input": {**draft.get("input", {}), "unavailable": slots,
                               **({"availability": workspace["availability"]} if "availability" in workspace else {})}}


def work_minutes(block: dict[str, Any], timezone: str) -> int:
    if block.get("workMinutes") is not None:
        return max(0, int(block["workMinutes"]))
    try:
        duration = (block_at(block["date"], block["end"], timezone)
                    - block_at(block["date"], block["start"], timezone)).total_seconds() / 60
        return max(0, int(duration) - int(block.get("checkpointMinutes") or 0))
    except (ValueError, TypeError, KeyError):
        return 0


def partial_confirmation_preview(
    draft: dict[str, Any], assignments: list[dict[str, Any]], quality: dict[str, Any],
    *, now: datetime | None = None,
) -> dict[str, Any]:
    from src.services.plan_intelligence import evaluate_plan_quality

    timezone = draft.get("timezone") or "Asia/Ho_Chi_Minh"
    candidates = [b for b in draft.get("blocks") or [] if b.get("status") not in {"history", "tentative"}]
    rejected: dict[str, list[dict[str, Any]]] = {}
    blocked_milestones: set[str] = set()
    global_errors = []
    identifiers = Counter(str(b.get("id") or "") for b in candidates)
    for block in candidates:
        identifier = str(block.get("id") or "")
        if not identifier or identifiers[identifier] > 1:
            rejected[identifier] = [{"code": "INVALID_BLOCK_ID"}]
    for error in sorted(quality.get("violations") or [], key=lambda e: e.get("code") == "BLOCK_OVERLAP"):
        if error.get("milestoneId"):
            blocked_milestones.add(str(error["milestoneId"]))
        ids = error.get("blockIds") or ([error["blockId"]] if error.get("blockId") else [])
        if error.get("code") == "BLOCK_OVERLAP" and any(str(v) in rejected for v in ids):
            continue  # Recheck overlaps after removing already-invalid entries.
        for identifier in ids:
            rejected.setdefault(str(identifier), []).append(error)
        if not ids and not error.get("milestoneId"):
            global_errors.append(error)

    milestones = draft.get("milestones") or []
    # Excluding an invalid prerequisite can invalidate its successors. Iterate
    # to a fixed point and re-run the independent validator on each subset.
    eligible = candidates
    for _ in range(len(milestones) + len(candidates) + 1):
        for block in eligible:
            if str(block.get("milestoneId") or "") in blocked_milestones:
                rejected.setdefault(str(block.get("id") or ""), []).append({"code": "DEPENDENCY_UNAVAILABLE"})
        eligible = [b for b in eligible if str(b.get("id") or "") not in rejected]
        selected_milestones = {str(b.get("milestoneId")) for b in eligible if b.get("milestoneId")}
        subset = {**draft, "blocks": eligible,
                  "milestones": [m for m in milestones if str(m.get("milestoneId")) in selected_milestones]}
        checked = evaluate_plan_quality(subset, assignments, now=now, include_partial=False)
        errors = checked["violations"]
        if not errors:
            break
        before = (len(rejected), len(blocked_milestones))
        for error in errors:
            if error.get("milestoneId"):
                blocked_milestones.add(str(error["milestoneId"]))
            for identifier in error.get("blockIds") or ([error["blockId"]] if error.get("blockId") else []):
                rejected.setdefault(str(identifier), []).append(error)
            if not error.get("milestoneId") and not error.get("blockId") and not error.get("blockIds"):
                global_errors.append(error)
        if before == (len(rejected), len(blocked_milestones)):
            global_errors.extend(errors)
            break
    excluded = [{"blockId": b.get("id"), "taskId": b.get("taskId"),
                 "reasons": rejected.get(str(b.get("id") or ""), [])}
                for b in candidates if str(b.get("id") or "") in rejected]
    shortfalls = {str(s["taskId"]): int(s["missingMin"]) for s in (draft.get("feasibility") or {}).get("shortfalls") or []}
    for block in candidates:
        if str(block.get("id") or "") in rejected:
            task_id = str(block.get("taskId") or "")
            shortfalls[task_id] = shortfalls.get(task_id, 0) + work_minutes(block, timezone)
    return {"canConfirm": bool(eligible) and not global_errors,
            "blockIds": [b["id"] for b in eligible] if not global_errors else [],
            "scheduledWorkMin": sum(work_minutes(b, timezone) for b in eligible) if not global_errors else 0,
            "excludedBlocks": excluded, "errors": global_errors,
            "shortfalls": [{"taskId": task, "missingMin": minutes} for task, minutes in shortfalls.items() if minutes > 0],
            "requiresAcknowledgement": True}


def confirm_partial_plan(draft: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    """Called only after fresh validation and explicit student acknowledgement."""
    if not preview["canConfirm"]:
        raise ValueError("No safe study blocks are available")
    confirmed = deepcopy(draft)
    allowed = set(preview["blockIds"])
    confirmed["blocks"] = [b for b in confirmed.get("blocks") or []
                           if b.get("status") == "history" or b.get("id") in allowed]
    shortfalls = preview["shortfalls"]
    confirmed["feasibility"] = {**confirmed.get("feasibility", {}), "feasible": False,
                                "shortfalls": shortfalls,
                                "deficitMin": max(sum(s["missingMin"] for s in shortfalls),
                                                  int(confirmed.get("feasibility", {}).get("deficitMin") or 0))}
    confirmed["confirmation"] = {"mode": "partial", "acknowledgedShortfall": True, **preview}
    return confirmed
