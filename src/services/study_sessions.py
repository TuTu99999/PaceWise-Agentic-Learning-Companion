"""Durable, bounded timer observations. Timer presence is NOT learning evidence."""
import json
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.persistence_models import StudyTimerSession

HEARTBEAT_SECONDS = 20
MAX_OBSERVATION_GAP_SECONDS = 45
MAX_TIMER_SECONDS = 24 * 60 * 60


def pause_running_session_on_logout(
    db: Session,
    *,
    institution_id: str,
    user_id: int,
    now: datetime | None = None,
) -> bool:
    """Pause the learner's active timer before revoking authentication.

    Logout is an authoritative server event. Keeping this operation in the
    same transaction as session revocation prevents a failed browser beacon
    from leaving a timer running after the learner can no longer checkpoint it.
    """
    row = db.scalar(
        select(StudyTimerSession).where(
            StudyTimerSession.active_scope == f"{institution_id}:{user_id}",
        )
    )
    if row is None:
        return False
    state = json.loads(row.state_json)
    if state.get("status") != "running":
        return False
    row.state_json = json.dumps(advance_timer(state, {"action": "recover"}, now or datetime.now(UTC)))
    row.version += 1
    return True


def instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def advance_timer(state: dict, command: dict, now: datetime) -> dict:
    """Pure reducer: replay is handled transactionally by API; no client clock."""
    result = {**state}
    action = command["action"]
    if state["status"] in {"completed", "cancelled"}:
        raise HTTPException(409, "Session is already closed")
    gap = max(0, (now - instant(state["checkpoint_at"])).total_seconds())
    if state["status"] == "running":
        if gap > MAX_OBSERVATION_GAP_SECONDS or action == "recover":
            result.update(status="paused", unobserved_gap=True, interruption_reason="unknown")
        else:
            result["observed_seconds"] = min(MAX_TIMER_SECONDS, state["observed_seconds"] + gap)
    reason = command.get("interruptionReason")
    if action in {"checkpoint", "pause", "resume"} and "note" in command:
        result["note"] = command["note"]
    if reason:
        result["interruption_reason"] = reason
        if reason == "unexpected":
            result["had_unexpected_interruption"] = True
    if action == "resume":
        result["status"] = "running"
    elif action in {"pause", "recover"}:
        result["status"] = "paused"
    elif action in {"complete", "cancel"}:
        result["status"] = "completed" if action == "complete" else "cancelled"
    if action == "complete":
        result.update(completion_percent=command.get("completionPercent", 0),
                      length_feeling=command.get("lengthFeeling", "not_reported"),
                      blocker=command.get("blocker", "none"), note=command.get("note", ""),
                      outside_minutes=command.get("outsideMinutes", 0), completed_at=now.isoformat())
    result["checkpoint_at"] = now.isoformat()
    return result
