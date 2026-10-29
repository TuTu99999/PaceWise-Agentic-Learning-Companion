"""Encrypted, session-scoped memory for the learning-support chat in Do."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import SessionLocal
from src.persistence_models import StudyTimerSession

if TYPE_CHECKING:
    from src.config import Settings

MAX_MESSAGES = 40
MAX_TEXT_LENGTH = 5000


def _messages(row: StudyTimerSession) -> list[dict[str, Any]]:
    try:
        raw = json.loads(row.chat_json or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and item.get("role") in {"student", "assistant"}]


def find_do_session(
    db: Session,
    *,
    institution_id: str,
    user_id: int,
    course_id: int,
    block_id: str,
) -> StudyTimerSession | None:
    return db.scalar(
        select(StudyTimerSession).where(
            StudyTimerSession.institution_id == institution_id,
            StudyTimerSession.user_id == user_id,
            StudyTimerSession.course_id == course_id,
            StudyTimerSession.block_id == block_id,
        )
    )


def is_open(row: StudyTimerSession) -> bool:
    try:
        status = str(json.loads(row.state_json or "{}").get("status") or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return status in {"running", "paused"} and bool(row.active_scope)


def public_messages(row: StudyTimerSession) -> list[dict[str, Any]]:
    """Return only fields needed to restore the Do chat UI."""
    return [
        {
            "id": str(item.get("id") or ""),
            "role": item["role"],
            "text": str(item.get("text") or "")[:MAX_TEXT_LENGTH],
            **({"kind": str(item.get("kind") or "abstained"), "sourceRefs": item.get("source_refs") or []}
               if item["role"] == "assistant" else {}),
        }
        for item in _messages(row)
        if str(item.get("text") or "").strip()
    ]


def agent_history(row: StudyTimerSession) -> list[dict[str, str]]:
    """Bound the context exactly like the main chatbot, using server-owned turns."""
    return [
        {
            "role": "user" if item["role"] == "student" else "assistant",
            "content": str(item.get("text") or "")[:1000],
        }
        for item in _messages(row)[-4:]
        if str(item.get("text") or "").strip()
    ]


def append_turn(
    row: StudyTimerSession,
    *,
    question: str,
    response: str,
    kind: str,
    source_refs: list[dict[str, Any]],
) -> None:
    """Append one validated exchange; never retain provider prompts or hidden reasoning."""
    if not is_open(row):
        return
    timestamp = datetime.now(UTC).isoformat()
    turn_id = uuid.uuid4().hex
    messages = _messages(row)
    messages.extend(
        [
            {
                "id": f"do-user-{turn_id}",
                "role": "student",
                "text": question[:MAX_TEXT_LENGTH],
                "created_at": timestamp,
            },
            {
                "id": f"do-assistant-{turn_id}",
                "role": "assistant",
                "text": response[:MAX_TEXT_LENGTH],
                "kind": kind,
                "source_refs": source_refs[:5],
                "created_at": timestamp,
            },
        ]
    )
    row.chat_json = json.dumps(messages[-MAX_MESSAGES:], ensure_ascii=False)


def clear_transcript(row: StudyTimerSession) -> None:
    row.chat_json = "[]"


def purge_expired_transcripts(settings: Settings, *, at: datetime | None = None) -> int:
    """Erase chat for blocks that ended or disappeared, even if the learner never returns."""
    from src.persistence_models import LearnerMemory
    from src.services.planning_time import block_at

    instant = at or datetime.now(UTC)
    cleared = 0
    with SessionLocal() as db:
        rows = db.scalars(select(StudyTimerSession).where(
            StudyTimerSession.institution_id == settings.institution_id,
            StudyTimerSession.active_scope.is_not(None),
        )).all()
        plans_by_user: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            if not _messages(row):
                continue
            if row.user_id not in plans_by_user:
                memories = db.scalars(select(LearnerMemory).where(
                    LearnerMemory.institution_id == settings.institution_id,
                    LearnerMemory.user_id == row.user_id,
                )).all()
                plans = []
                for memory in memories:
                    try:
                        plan = json.loads(memory.profile_json or "{}").get("last_confirmed_plan") or {}
                    except (TypeError, ValueError, json.JSONDecodeError):
                        plan = {}
                    if plan:
                        plans.append(plan)
                plans_by_user[row.user_id] = plans
            plans = plans_by_user[row.user_id]
            block = next((item for plan in plans for item in plan.get("blocks", [])
                          if item.get("id") == row.block_id), None)
            # Absence of every plan snapshot is not positive proof of expiry.
            # Terminal commands still erase the transcript synchronously.
            expired = bool(plans) and (not block or block.get("status") in {"history", "tentative"}
                                       or block.get("taskId") != row.task_id)
            if block and not expired:
                try:
                    expired = block_at(block["date"], block["end"], settings.app_timezone) <= instant
                except (KeyError, TypeError, ValueError):
                    expired = True
            if expired:
                clear_transcript(row)
                cleared += 1
        if cleared:
            db.commit()
    return cleared
