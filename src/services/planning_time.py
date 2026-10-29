"""Shared local-time semantics for scheduling and independent validation."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def partition_open_assignments(assignments: list[dict], *, now: datetime,
                               timezone_name: str, fallback: date) -> tuple[list[dict], list[dict]]:
    """Expired work is unresolved history, not future deadline capacity.

    Missing due dates retain the existing planning-horizon fallback. Never infer
    submission, completion or learning from the passage of time.
    """
    active, expired = [], []
    for assignment in assignments:
        state = str((assignment.get("submission") or {}).get("workflow_state") or "").lower()
        if state in {"submitted", "graded", "pending_review", "excused"}:
            continue
        due = deadline_at(assignment.get("deadline") or assignment.get("due_at"), fallback, timezone_name)
        (expired if due <= now else active).append(assignment)
    return active, expired


def assignment_available_at(assignment: dict, timezone_name: str) -> datetime | None:
    """Return the strongest server-owned earliest placement/start boundary.

    ``unlock_at`` is the LMS availability boundary. ``learning_available_at``
    is derived from an explicitly linked class/material. The assignment remains
    visible to future planning, but no Do block may be placed or started before
    this boundary.
    """

    values = []
    for key in ("unlock_at", "unlockAt", "learning_available_at", "learningAvailableAt"):
        parsed = instant_at(assignment.get(key), timezone_name)
        if parsed is not None:
            values.append(parsed)
    return max(values, default=None)


def instant_at(value: object, timezone_name: str) -> datetime | None:
    """Parse an optional LMS instant; date-only availability starts that day."""

    zone = ZoneInfo(timezone_name)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), time.min, zone)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return (parsed.replace(tzinfo=zone) if parsed.tzinfo is None else parsed).astimezone(zone)
    except ValueError:
        return None


def deadline_at(value: object, fallback: date, timezone_name: str) -> datetime:
    zone = ZoneInfo(timezone_name)
    text = str(value or "").strip()
    if not text or len(text) == 10:
        try:
            day = date.fromisoformat(text) if text else fallback
        except ValueError:
            day = fallback
        return datetime.combine(day + timedelta(days=1), time.min, zone)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return (parsed.replace(tzinfo=zone) if parsed.tzinfo is None else parsed).astimezone(zone)
    except ValueError:
        return datetime.combine(fallback + timedelta(days=1), time.min, zone)


def block_at(day: str, clock: str, timezone_name: str) -> datetime:
    hours, minutes = (int(part) for part in clock.split(":"))
    if not 0 <= hours <= 24 or not 0 <= minutes < 60 or (hours == 24 and minutes):
        raise ValueError("Invalid calendar clock")
    return datetime.combine(date.fromisoformat(day), time.min, ZoneInfo(timezone_name)) + timedelta(
        hours=hours, minutes=minutes
    )
