"""One bounded contract for Reflect proposals and Plan consumption.

Signals are recommendations, not knowledge evidence or permission to edit.
Unknown causes remain visible instead of silently becoming "none".
"""

import math

CAUSES = frozenset(
    {
        "none",
        "unknown",
        "missing_prerequisite",
        "knowledge_gap",
        "task_harder_than_expected",
        "interruption",
        "insufficient_time",
        "misconception",
        "missed_block",
        "estimate_error",
        "schedule_conflict",
        "fatigue",
        "deadline_changed",
        "capacity_changed",
    }
)
ALIASES = {"underestimated": "estimate_error", "distraction": "interruption"}


def bounded_number(value: object, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return min(maximum, max(minimum, number)) if math.isfinite(number) else default


def normalize_planning_signal(value: object, fallback_task_id: str = "") -> dict:
    raw = value if isinstance(value, dict) else {}
    original = str(raw.get("cause") or "none").strip().casefold().replace(" ", "_")
    cause = ALIASES.get(original, original)
    affected = raw.get("affected_kcs", raw.get("affectedKcs")) or []
    if isinstance(affected, str):
        affected = [affected]
    if not isinstance(affected, (list, tuple)):
        affected = []
    signal = {
        "cause": cause if cause in CAUSES else "unknown",
        "duration_factor": round(
            bounded_number(raw.get("duration_factor", raw.get("durationFactor")), 1, 0.75, 1.5), 2
        ),
        "follow_up_minutes": round(bounded_number(raw.get("follow_up_minutes", raw.get("followUpMinutes")), 0, 0, 180)),
        "affected_kcs": list(
            dict.fromkeys(item.strip()[:160] for item in affected if isinstance(item, str) and item.strip())
        )[:20],
        "task_id": str(raw.get("task_id", raw.get("taskId")) or fallback_task_id).strip()[:160],
    }
    if cause not in CAUSES or raw.get("unrecognized_cause"):
        signal["unrecognized_cause"] = str(raw.get("unrecognized_cause") or original)[:160]
    return signal
