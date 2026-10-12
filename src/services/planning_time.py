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
