"""Scoped facts for reflection, independent of model prose and client totals."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings
from src.persistence_models import LearnerMemory, LearningEvent, LearningEvidenceRecord
from src.security import SessionContext
from src.services.planning_signals import bounded_number


def _object(value: str) -> dict:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def _instant(value: object, zone: ZoneInfo) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=zone) if parsed.tzinfo is None else parsed.astimezone(zone)
    except (ValueError, TypeError):
        return None


def load_reflection_observations(
    db: Session,
    session: SessionContext,
    settings: Settings,
    metrics: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Read the selected week across enrolled courses; activity stays course-scoped.

    Persisted timer/progress values are student-reported observations, not proof
    of understanding. Assessment rows retain their distinct evidence provenance.
    """
    zone = ZoneInfo(settings.app_timezone)
    instant = (now or datetime.now(UTC)).astimezone(zone)
    scope = "activity" if metrics.get("reflection_scope") == "activity" else "weekly"
    day = date.fromisoformat(str(metrics["week_start"])) if metrics.get("week_start") else instant.date()
    start_day = day - timedelta(days=day.weekday())
    start = datetime.combine(start_day, time.min, zone)
    end = start + timedelta(days=7)
    courses = (session.course_id,) if scope == "activity" else session.course_ids
    sessions: dict[tuple[int, str], dict] = {}
    notes = []

    def accept(item: dict, course: int, source: str, recorded_at: object = None) -> None:
        at = _instant(item.get("date") or item.get("recorded_at") or recorded_at, zone)
        if at is None:
            notes.append("SESSION_DATE_UNAVAILABLE")
            return
        if not start <= at < end or at > instant:
            return
        block = str(item.get("block_id") or "")
        key = (course, block or source)
        sessions[key] = {**item, "course_id": course, "source_ref": source}

    memories = db.scalars(
        select(LearnerMemory).where(
            LearnerMemory.institution_id == settings.institution_id,
            LearnerMemory.user_id == session.user_id,
            LearnerMemory.course_id.in_(courses),
        )
    ).all()
    for row in memories:
        profile = _object(row.profile_json)
        for index, item in enumerate(profile.get("do_history") or []):
            if isinstance(item, dict):
                accept(item, row.course_id, f"memory:{row.id}:do:{index}")
    # Durable events recover observations beyond the compact 20-session memory.
    events = db.scalars(
        select(LearningEvent)
        .where(
            LearningEvent.institution_id == settings.institution_id,
            LearningEvent.student_user_id == session.user_id,
            LearningEvent.course_id.in_(courses),
            LearningEvent.event_type == "STUDY_SESSION_COMPLETED",
            LearningEvent.occurred_at <= instant.astimezone(UTC),
        )
        .order_by(LearningEvent.occurred_at, LearningEvent.id)
    ).all()
    for event in events:
        accept(
            _object(event.payload_json),
            event.course_id,
            event.id,
            event.occurred_at.replace(tzinfo=UTC) if event.occurred_at.tzinfo is None else event.occurred_at,
        )

    activity = metrics.get("activity") if isinstance(metrics.get("activity"), dict) else {}
    if scope == "activity":
        # No fallback to another session when the requested block is absent.
        target = str(activity.get("block_id") or "")
        sessions = {key: item for key, item in sessions.items() if target and key[1] == target}
    records = db.scalars(
        select(LearningEvidenceRecord)
        .where(
            LearningEvidenceRecord.institution_id == settings.institution_id,
            LearningEvidenceRecord.student_user_id == session.user_id,
            LearningEvidenceRecord.course_id.in_(courses),
            LearningEvidenceRecord.created_at >= start.astimezone(UTC),
            LearningEvidenceRecord.created_at < end.astimezone(UTC),
        )
        .order_by(LearningEvidenceRecord.created_at, LearningEvidenceRecord.id)
    ).all()
    evidence = []
    for row in records:
        if scope == "activity" and (not activity.get("block_id") or row.block_id != activity["block_id"]):
            continue
        if row.created_at.replace(tzinfo=UTC) > instant:
            continue
        payload = _object(row.payload_json)
        evidence.append({**payload, "id": row.id, "course_id": row.course_id})
    observed = list(sessions.values())
    result = {
        "reflection_scope": scope,
        "week_start": start_day.isoformat(),
        "week_end": (start_day + timedelta(days=6)).isoformat(),
        "effective_week_start": (start_day + timedelta(days=7)).isoformat(),
        "sessions": observed,
        "assessment_evidence": evidence,
        "session_count": len(observed),
        "missed_count": sum(item.get("status") == "missed" for item in observed),
        "planned_minutes": sum(bounded_number(item.get("planned_minutes"), 0, 0, 1440) for item in observed),
        "actual_minutes": sum(bounded_number(item.get("actual_minutes"), 0, 0, 1440) for item in observed),
        "data_status": "observed" if observed or evidence else "no_observations",
        "period_complete": instant >= end,
        "provenance": {"sessions": "persisted_student_report", "assessment_evidence": "assessment_records"},
        "source_refs": [item["source_ref"] for item in observed] + [item["id"] for item in evidence],
        "warnings": sorted(set(notes)),
    }
    if scope == "activity":
        identity = {key: activity.get(key) for key in ("id", "block_id", "kind", "title", "course_code", "date")}
        match = observed[-1] if observed else {}
        result["activity"] = {
            **identity,
            **match,
            "course_id": session.course_id,
            "task_id": match.get("task_id", activity.get("task_id", "")),
        }
    return result


def reflection_context(observed: dict, requested: dict) -> dict:
    """Client counters can be kept for comparison, but not promoted to facts."""
    return {**observed, "self_report": requested}
