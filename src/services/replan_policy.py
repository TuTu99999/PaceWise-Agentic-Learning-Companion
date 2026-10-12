"""Deterministic stability guard: observations propose drafts, never apply schedules."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from src.services.assessment_review_policy import planning_evidence_usable
from src.services.planning_signals import normalize_planning_signal

POLICY_VERSION = "replan-policy-v1"


def _finite(value: Any, default: float = 0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def decide_replan(
    *, signal: dict, last_do: dict, latest_evidence: dict, previous: dict | None = None, now: datetime | None = None
) -> dict:
    instant = now or datetime.now(UTC)
    reasons: list[str] = []
    planned = _finite(last_do.get("planned_minutes"))
    actual = _finite(last_do.get("actual_minutes"))
    completion = _finite(last_do.get("completion_percent"), 100)
    cause = normalize_planning_signal(signal)["cause"]
    normalized_signal = normalize_planning_signal(signal)
    if last_do.get("status") == "missed" and planned >= 30:
        reasons.append("missed_block")
    if planned > 0 and abs(actual - planned) >= 30 and abs(actual - planned) / planned >= 0.25:
        reasons.append("actual_time_deviation")
    if planned >= 30 and completion < 80 and last_do.get("status") in {"blocked", "needs_more_time"}:
        reasons.append("unfinished_work")
    evidence_valid = planning_evidence_usable(latest_evidence)
    if evidence_valid:
        dimensions = latest_evidence.get("dimensions") or {}
        if any(dimensions.get(key) == "failed" for key in ("conceptual", "reasoning", "application", "transfer")):
            reasons.append("knowledge_gap_observed")
        # Low-confidence taxonomy hypotheses do not count as established misconceptions.
        if any(item.get("status") == "confirmed" for item in latest_evidence.get("misconceptions") or []):
            reasons.append("confirmed_misconception")
    if cause in {"deadline_changed", "capacity_changed"} and signal.get("source") == "lms_or_calendar_event":
        reasons.append(cause)
    if cause in {"knowledge_gap", "missing_prerequisite", "misconception"} and not evidence_valid:
        # Self-report requests support, but is not proof of a knowledge deficit.
        evidence_note = "self_report_requires_assessment"
    else:
        evidence_note = None
    affected_task_ids = list(
        dict.fromkeys(
            value
            for value in (
                str(normalized_signal.get("task_id") or "").strip(),
                str(last_do.get("task_id") or "").strip(),
                str(latest_evidence.get("task_id") or "").strip(),
            )
            if value
        )
    )
    observed_remaining = max(0, round(_finite(last_do.get("remaining_minutes"))))
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "task": signal.get("task_id"),
                "reasons": sorted(reasons),
                "block": last_do.get("block_id"),
                "planned": planned,
                "actual": actual,
                "completion": completion,
                "evidence_id": latest_evidence.get("id"),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    decision = {
        "policy_version": POLICY_VERSION,
        "action": "propose_draft" if reasons else "keep",
        "reasons": reasons or ["risk_below_threshold"],
        "evidence_note": evidence_note,
        "requires_confirmation": bool(reasons),
        "auto_apply": False,
        "fingerprint": fingerprint,
        "decided_at": instant.isoformat(),
        "mutable_scope": "future_uncompleted_student_blocks",
        "repair_context": {
            "affected_task_ids": affected_task_ids,
            "cause": cause,
            "observed_remaining_minutes": observed_remaining,
            "signal_follow_up_minutes": int(normalized_signal["follow_up_minutes"]),
        },
    }
    return _stability_guard(decision, reasons, previous, instant)


def _stability_guard(decision: dict, reasons: list[str], previous: dict | None, instant: datetime) -> dict:
    previous = previous or {}
    if reasons and previous.get("action") == "propose_draft":
        same = previous.get("fingerprint") == decision["fingerprint"]
        try:
            previous_time = datetime.fromisoformat(str(previous.get("decided_at")))
            previous_time = previous_time.replace(tzinfo=UTC) if previous_time.tzinfo is None else previous_time
        except (TypeError, ValueError):
            previous_time = instant - timedelta(days=1)
        cooldown = instant - previous_time < timedelta(minutes=30)
        hard_change = any(reason in {"deadline_changed", "capacity_changed"} for reason in reasons)
        if same or (cooldown and not hard_change):
            decision.update(
                action="keep", reasons=["duplicate_signal" if same else "cooldown"], requires_confirmation=False
            )
    return decision


def decide_weekly_replan(
    *,
    signal: dict,
    observations: dict,
    previous: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Evaluate every observed block and latest tested dimension per course/KC.

    A completed last block cannot hide an earlier missed one. Conversely, a
    later valid pass resolves the earlier failure for that specific dimension.
    """
    instant = now or datetime.now(UTC)
    decisions = []
    refs = []
    for item in observations.get("sessions") or []:
        result = decide_replan(signal=signal, last_do=item, latest_evidence={}, now=instant)
        decisions.append(result)
        if result["action"] == "propose_draft":
            refs.append(item.get("source_ref"))
    latest_dimensions = {}
    latest_misconceptions = {}
    for item in observations.get("assessment_evidence") or []:
        if not planning_evidence_usable(item):
            continue
        for kc in item.get("knowledge_component_ids") or []:
            key = (item.get("course_id"), kc)
            for dimension, value in (item.get("dimensions") or {}).items():
                if value in {"passed", "failed"}:
                    latest_dimensions[(*key, dimension)] = (value, item.get("id"))
            for misconception in item.get("misconceptions") or []:
                # Only explicit resolved evidence clears a confirmed hypothesis.
                label = misconception.get("id") or misconception.get("label")
                if label and misconception.get("status") in {"confirmed", "resolved"}:
                    latest_misconceptions[(*key, label)] = (misconception["status"], item.get("id"))
    reasons = sorted(
        {reason for result in decisions if result["action"] == "propose_draft" for reason in result["reasons"]}
    )
    failures = [
        (value, ref)
        for key, (value, ref) in latest_dimensions.items()
        if key[-1] in {"conceptual", "reasoning", "application", "transfer"} and value == "failed"
    ]
    if failures:
        reasons.append("knowledge_gap_observed")
        refs.extend(ref for _, ref in failures)
    confirmed = [ref for status, ref in latest_misconceptions.values() if status == "confirmed"]
    if confirmed:
        reasons.append("confirmed_misconception")
        refs.extend(confirmed)
    if not decisions:
        standalone = decide_replan(signal=signal, last_do={}, latest_evidence={}, now=instant)
        if standalone["action"] == "propose_draft":
            reasons.extend(standalone["reasons"])
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "week": observations.get("week_start"),
                "reasons": sorted(set(reasons)),
                "sessions": sorted(result["fingerprint"] for result in decisions),
                "dimensions": sorted((str(key), value) for key, value in latest_dimensions.items()),
                "misconceptions": sorted((str(key), value) for key, value in latest_misconceptions.items()),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    decision = {
        "policy_version": POLICY_VERSION,
        "action": "propose_draft" if reasons else "keep",
        "reasons": sorted(set(reasons)) or ["risk_below_threshold"],
        "evidence_note": None if observations.get("sessions") or latest_dimensions else "no_observations",
        "requires_confirmation": bool(reasons),
        "auto_apply": False,
        "fingerprint": fingerprint,
        "decided_at": instant.isoformat(),
        "mutable_scope": "future_uncompleted_student_blocks",
        "scope": "weekly",
        "week_start": observations.get("week_start"),
        "observed_session_count": len(observations.get("sessions") or []),
        "trigger_source_refs": sorted({str(ref) for ref in refs if ref}),
    }
    return _stability_guard(decision, reasons, previous, instant)


def plan_diff(
    previous: list[dict],
    proposed: list[dict],
    *,
    previous_risks: list[dict] | None = None,
    proposed_risks: list[dict] | None = None,
) -> dict:
    """Compare semantic placement, not randomized block IDs."""

    def signature(block: dict) -> tuple:
        return tuple(str(block.get(key) or "") for key in ("taskId", "milestoneTitle", "date", "start", "end"))

    before = {signature(block): block for block in previous}
    after = {signature(block): block for block in proposed}
    unchanged = before.keys() & after.keys()
    removed = [before[key] for key in sorted(before.keys() - after.keys())]
    added = [after[key] for key in sorted(after.keys() - before.keys())]

    def identity(block: dict) -> tuple[str, str]:
        milestone = str(block.get("milestoneId") or block.get("milestoneTitle") or "")
        return str(block.get("taskId") or ""), milestone

    def minute(value: str) -> int:
        hours, minutes = str(value).split(":", 1)
        return int(hours) * 60 + int(minutes)

    def duration(block: dict) -> int:
        try:
            return max(0, minute(block.get("end")) - minute(block.get("start")))
        except (TypeError, ValueError, AttributeError):
            return 0

    removed_by_identity: dict[tuple[str, str], list[dict]] = {}
    added_by_identity: dict[tuple[str, str], list[dict]] = {}
    for block in removed:
        removed_by_identity.setdefault(identity(block), []).append(block)
    for block in added:
        added_by_identity.setdefault(identity(block), []).append(block)
    moved = []
    for key in sorted(removed_by_identity.keys() & added_by_identity.keys()):
        old_rows = sorted(removed_by_identity[key], key=lambda row: (str(row.get("date")), str(row.get("start"))))
        new_rows = sorted(added_by_identity[key], key=lambda row: (str(row.get("date")), str(row.get("start"))))
        for old, new in zip(old_rows, new_rows, strict=False):
            moved.append(
                {
                    "taskId": str(old.get("taskId") or new.get("taskId") or ""),
                    "before": old,
                    "after": new,
                    "workMinutes": min(duration(old), duration(new)),
                    "changedDay": old.get("date") != new.get("date"),
                }
            )
    moved_work_minutes = sum(item["workMinutes"] for item in moved)
    changed_days = {
        str(value)
        for item in moved
        if item["changedDay"]
        for value in (item["before"].get("date"), item["after"].get("date"))
        if value
    }
    pinned_violations = sum(
        item["before"].get("placementSource") == "student" for item in moved
    )
    return {
        "added": added,
        "removed": removed,
        "moved": moved,
        "moved_block_count": len(moved),
        "moved_work_minutes": moved_work_minutes,
        "changed_day_count": len(changed_days),
        "student_pinned_violations": pinned_violations,
        "deadline_risk_before": list(previous_risks or []),
        "deadline_risk_after": list(proposed_risks or []),
        "unchanged_count": len(unchanged),
        "stability": len(unchanged) / max(1, len(before)),
        "requires_confirmation": True,
    }
