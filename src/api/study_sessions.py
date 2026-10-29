"""Student-owned timer checkpoints and explicitly confirmed rhythm trials."""
import hashlib
import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.agents.workflows.do import evaluate_completion
from src.config import Settings, get_settings
from src.db import get_db
from src.persistence_models import (
    LearnerMemory,
    LearningEvent,
    LearningEvidenceRecord,
    StudyTimerSession,
    UserWorkspace,
)
from src.security import SessionContext, get_current_session, require_csrf
from src.services.agent_memory import persist_agent_outcome
from src.services.do_chat_memory import clear_transcript, is_open, public_messages
from src.services.do_preparation import confirmed_block, load_do_context
from src.services.learning_events import audit
from src.services.notification_policy import StudyPreferences
from src.services.planning_time import block_at, instant_at
from src.services.study_activity import effective_rhythm
from src.services.study_rhythm import compare_rhythm_trial, propose_rhythm, summarize_independent_assessment
from src.services.study_sessions import HEARTBEAT_SECONDS, advance_timer

router = APIRouter(prefix="/study-sessions", tags=["Study observations"])


def student(session: SessionContext) -> None:
    if session.role != "student":
        raise HTTPException(403, "Student study sessions only")


def now() -> datetime:
    return datetime.now(UTC)


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    course_id: int = Field(alias="courseId", gt=0)
    block_id: str = Field(alias="blockId", min_length=1, max_length=128)


@router.post("/prepare")
async def prepare(payload: Start, session: SessionContext = Depends(require_csrf),
                  settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    scoped = replace(session, course_id=payload.course_id)
    block = confirmed_block(db, scoped, settings, payload.block_id)
    db.rollback()  # Release the connection before waiting on LMS network calls.
    context = await load_do_context(scoped, settings, block)
    return context["do_session"]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    action: Literal["checkpoint", "pause", "resume", "recover", "complete", "cancel"]
    event_key: str = Field(alias="eventKey", min_length=8, max_length=100)
    expected_version: int = Field(alias="expectedVersion", ge=1)
    interruption_reason: Literal["none", "unexpected", "fatigue", "difficulty", "outside", "unknown"] | None = Field(
        default=None,
        alias="interruptionReason",
    )
    length_feeling: Literal["not_reported", "comfortable", "long", "too_long"] = Field(
        default="not_reported",
        alias="lengthFeeling",
    )
    completion_percent: int = Field(default=0, alias="completionPercent", ge=0, le=100)
    work_result: Literal["planned_part_done", "needs_more_time", "blocked"] | None = Field(
        default=None,
        alias="workResult",
    )
    additional_minutes: int = Field(default=0, alias="additionalMinutes", ge=0, le=1440)
    understanding_self_report: Literal["not_reported", "can_continue", "needs_review", "needs_help"] = Field(
        default="not_reported",
        alias="understandingSelfReport",
    )
    blocker: Literal["none", "knowledge", "time", "interruption", "other"] = "none"
    outside_minutes: int = Field(default=0, alias="outsideMinutes", ge=0, le=1440)
    note: str = Field(default="", max_length=500)


def owned(db: Session, session: SessionContext, settings: Settings, identifier: str) -> StudyTimerSession:
    student(session)
    row = db.get(StudyTimerSession, identifier)
    if (not row or row.institution_id != settings.institution_id or row.user_id != session.user_id
            or row.course_id not in session.course_ids):
        raise HTTPException(404, "Study session not found")
    return row


def public(row: StudyTimerSession) -> dict:
    data = json.loads(row.state_json)
    data.pop("receipts", None)
    return {**data, "id": row.id, "courseId": str(row.course_id), "taskId": row.task_id,
            "blockId": row.block_id, "version": row.version, "heartbeatSeconds": HEARTBEAT_SECONDS}


def _auto_cancel_reason(db: Session, session: SessionContext, settings: Settings,
                        row: StudyTimerSession, at: datetime) -> str | None:
    """Return why an active timer can no longer belong to the confirmed plan."""
    memories = db.scalars(select(LearnerMemory).where(
        LearnerMemory.institution_id == settings.institution_id,
        LearnerMemory.user_id == session.user_id,
        LearnerMemory.course_id.in_(session.course_ids),
    )).all()
    plans = []
    for memory in memories:
        try:
            plan = json.loads(memory.profile_json or "{}").get("last_confirmed_plan") or {}
        except (TypeError, ValueError, json.JSONDecodeError):
            plan = {}
        if plan:
            plans.append(plan)
    # A confirmed plan can contain several courses but is stored under the
    # course that was active when the learner confirmed it. Never interpret a
    # missing per-course copy as proof that another course's active Do vanished.
    block = next((item for plan in plans for item in plan.get("blocks", [])
                  if item.get("id") == row.block_id), None)
    if block is None:
        return "plan_replaced" if plans else None
    if block.get("status") in {"history", "tentative"} or block.get("taskId") != row.task_id:
        return "plan_replaced"
    try:
        if block_at(block["date"], block["end"], settings.app_timezone) <= at:
            return "block_ended"
    except (KeyError, TypeError, ValueError):
        return "plan_replaced"
    return None


def _auto_cancel_stale_active(db: Session, session: SessionContext, settings: Settings,
                              row: StudyTimerSession | None, at: datetime) -> bool:
    """Release a timer whose block ended or disappeared from the latest plan."""
    if row is None:
        return False
    reason = _auto_cancel_reason(db, session, settings, row, at)
    if reason is None:
        return False
    state = json.loads(row.state_json)
    previous_version = row.version
    if state.get("status") not in {"completed", "cancelled"}:
        state = advance_timer(state, {"action": "cancel"}, at)
    state.update(auto_cancel_reason=reason, cancelled_at=at.isoformat())
    row.state_json = json.dumps(state)
    clear_transcript(row)
    row.active_scope = None
    row.version += 1
    audit(db, replace(session, course_id=row.course_id), settings, "STUDY_TIMER_AUTO_CANCELLED", row.id,
          f"auto-cancel:{previous_version}", {"reason": reason, "block_id": row.block_id})
    return True


def _restore_false_plan_cancel(db: Session, session: SessionContext, settings: Settings,
                               row: StudyTimerSession | None, at: datetime) -> bool:
    """Restore a session cancelled by the former per-course plan lookup bug."""
    if row is None:
        return False
    state = json.loads(row.state_json)
    if state.get("status") != "cancelled" or state.get("auto_cancel_reason") != "plan_replaced":
        return False
    if _auto_cancel_reason(db, session, settings, row, at) is not None:
        return False
    active_scope = f"{settings.institution_id}:{session.user_id}"
    occupied = db.scalar(select(StudyTimerSession).where(
        StudyTimerSession.active_scope == active_scope,
        StudyTimerSession.id != row.id,
    ))
    if occupied is not None:
        return False
    previous_version = row.version
    state.update(status="paused", checkpoint_at=at.isoformat(), unobserved_gap=False)
    state.pop("auto_cancel_reason", None)
    state.pop("cancelled_at", None)
    row.state_json = json.dumps(state)
    row.active_scope = active_scope
    row.version += 1
    audit(db, replace(session, course_id=row.course_id), settings, "STUDY_TIMER_FALSE_CANCEL_RESTORED", row.id,
          f"restore-false-cancel:{previous_version}", {"block_id": row.block_id})
    return True


@router.get("/current")
def current(block_id: str = Query(alias="blockId"), session: SessionContext = Depends(get_current_session),
            settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    student(session)
    row = db.scalar(select(StudyTimerSession).where(StudyTimerSession.institution_id == settings.institution_id,
                    StudyTimerSession.user_id == session.user_id, StudyTimerSession.block_id == block_id))
    if _restore_false_plan_cancel(db, session, settings, row, now()):
        db.commit()
        db.refresh(row)
    active = db.scalar(select(StudyTimerSession).where(
        StudyTimerSession.active_scope == f"{settings.institution_id}:{session.user_id}",
        StudyTimerSession.course_id.in_(session.course_ids)))
    if _auto_cancel_stale_active(db, session, settings, active, now()):
        db.commit()
        if row:
            db.refresh(row)
        active = None
    return {"session": public(row) if row and row.course_id in session.course_ids else None,
            "activeSession": public(active) if active else None}


@router.get("/chat")
def chat_history(
    course_id: int = Query(alias="courseId", gt=0),
    block_id: str = Query(alias="blockId", min_length=1, max_length=128),
    session: SessionContext = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    """Restore only the authenticated learner's still-active Do transcript."""
    student(session)
    if course_id not in session.course_ids:
        raise HTTPException(403, "Course is outside enrollment")
    row = db.scalar(select(StudyTimerSession).where(
        StudyTimerSession.institution_id == settings.institution_id,
        StudyTimerSession.user_id == session.user_id,
        StudyTimerSession.course_id == course_id,
        StudyTimerSession.block_id == block_id,
    ))
    if row is None:
        return {"messages": []}
    if _auto_cancel_stale_active(db, session, settings, row, now()):
        db.commit()
        return {"messages": []}
    if not is_open(row):
        if row.chat_json not in {None, "", "[]"}:
            clear_transcript(row)
            db.commit()
        return {"messages": []}
    return {"messages": public_messages(row)}


@router.post("")
def start(payload: Start, session: SessionContext = Depends(require_csrf),
          settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    student(session)
    if payload.course_id not in session.course_ids:
        raise HTTPException(403, "Course is outside enrollment")
    existing = db.scalar(select(StudyTimerSession).where(StudyTimerSession.institution_id == settings.institution_id,
                         StudyTimerSession.user_id == session.user_id, StudyTimerSession.block_id == payload.block_id))
    if existing and existing.course_id != payload.course_id:
        raise HTTPException(409, "Block belongs to another course")
    if _restore_false_plan_cancel(db, session, settings, existing, now()):
        db.commit()
        db.refresh(existing)
    active_scope = f"{settings.institution_id}:{session.user_id}"
    active = db.scalar(select(StudyTimerSession).where(StudyTimerSession.active_scope == active_scope))
    if _auto_cancel_stale_active(db, session, settings, active, now()):
        db.commit()
        if existing:
            db.refresh(existing)
    if existing and json.loads(existing.state_json)["status"] != "cancelled":
        return public(existing)
    other = db.scalar(select(StudyTimerSession).where(StudyTimerSession.active_scope == active_scope,
                        StudyTimerSession.block_id != payload.block_id))
    if other:
        raise HTTPException(409, "Finish or cancel the previous study session first")
    memories = db.scalars(select(LearnerMemory).where(LearnerMemory.institution_id == settings.institution_id,
                         LearnerMemory.user_id == session.user_id, LearnerMemory.course_id.in_(session.course_ids)))
    block = None
    readiness = "unknown"
    for memory in memories:
        plan = json.loads(memory.profile_json or "{}").get("last_confirmed_plan") or {}
        candidate = next((b for b in plan.get("blocks", []) if b.get("id") == payload.block_id), None)
        if candidate and str(candidate.get("taskId", "")).startswith(f"{payload.course_id}:"):
            block = candidate
            # Versioned baseline KC readiness, never inferred from timer use.
            scoped_memory = db.get(LearnerMemory, f"{settings.institution_id}:{session.user_id}:{payload.course_id}")
            knowledge = json.loads(scoped_memory.mastery_json or "{}") if scoped_memory else {}
            kcs = {component.get("componentId") for milestone in plan.get("milestones", [])
                   if milestone.get("taskId") == candidate["taskId"] for component in milestone.get("knowledgeComponents", [])}
            levels = {kc: {"level": knowledge.get(kc, {}).get("level", "no_evidence"),
                            "unresolved": sorted(knowledge.get(kc, {}).get("unresolved_dimensions", []))}
                      for kc in kcs if kc and isinstance(knowledge.get(kc, {}), dict)}
            readiness = hashlib.sha256(json.dumps(levels, sort_keys=True).encode()).hexdigest()[:16]
            break
    if not block or block.get("status") in {"history", "tentative"}:
        raise HTTPException(409, "Start from a server-confirmed study block")
    earliest_start = instant_at(block.get("earliestStartAt"), settings.app_timezone)
    if earliest_start is not None and now() < earliest_start:
        raise HTTPException(409, "Complete the prerequisite learning before starting this study block")
    if block_at(block["date"], block["end"], settings.app_timezone) <= now():
        raise HTTPException(409, "Study block has ended; re-plan remaining work")
    workspace = db.get(UserWorkspace, session.user_id)
    saved = json.loads(workspace.state_json or "{}") if workspace else {}
    preferences = StudyPreferences.model_validate(saved.get("studyPreferences") or {}).model_dump(by_alias=True)
    state = {"status": "running", "observed_seconds": 0, "checkpoint_at": now().isoformat(),
             "interruption_reason": "none", "unobserved_gap": False, "had_unexpected_interruption": False,
             "outside_minutes": 0, "length_feeling": "not_reported", "readiness_key": readiness,
             "rhythm": block.get("rhythm") or effective_rhythm(preferences, payload.course_id, block.get("activityType", "unknown")),
             "activity_type": block.get("activityType", "unknown"),
             "activity_source": block.get("activitySource", "unmapped"),
             "checkpoint_minutes": block.get("checkpointMinutes", preferences["checkpointMinutes"]),
             "planned_minutes": int((block_at(block["date"], block["end"], settings.app_timezone)
                                     - block_at(block["date"], block["start"], settings.app_timezone)).total_seconds() / 60),
             "date": block["date"], "receipts": {}}
    if existing:
        try:
            count = db.execute(update(StudyTimerSession).where(StudyTimerSession.id == existing.id,
                StudyTimerSession.version == existing.version).values(state_json=json.dumps(state), version=existing.version + 1,
                    active_scope=active_scope, chat_json="[]"), execution_options={"synchronize_session": False}).rowcount
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "Finish or cancel the previous study session first") from exc
        if count != 1:
            db.rollback()
            raise HTTPException(409, "Session changed; reload the checkpoint")
        db.commit()
        db.refresh(existing)
        return public(existing)
    row = StudyTimerSession(id=f"SS-{uuid.uuid4().hex}", institution_id=settings.institution_id,
                           user_id=session.user_id, course_id=payload.course_id, block_id=payload.block_id,
                           task_id=block["taskId"], version=1, active_scope=active_scope, state_json=json.dumps(state))
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.scalar(select(StudyTimerSession).where(StudyTimerSession.institution_id == settings.institution_id,
                        StudyTimerSession.user_id == session.user_id, StudyTimerSession.block_id == payload.block_id))
        if row is None:
            raise HTTPException(409, "Refresh the study session")
    return public(row)


@router.post("/{identifier}/events")
def command(identifier: str, payload: Command, session: SessionContext = Depends(require_csrf),
            settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    row = owned(db, session, settings, identifier)
    state = json.loads(row.state_json)
    body = payload.model_dump(exclude_unset=True, by_alias=True)
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    receipts = state.get("receipts") or {}
    if payload.event_key in receipts:
        if receipts[payload.event_key] != digest:
            raise HTTPException(409, "Event key was already used for another command")
        return public(row)
    if payload.expected_version != row.version:
        raise HTTPException(409, "Session changed in another tab; reload its checkpoint")
    changed = advance_timer(state, body, now())
    changed["receipts"] = {**dict(list(receipts.items())[-29:]), payload.event_key: digest}
    scoped = replace(session, course_id=row.course_id)
    if payload.action == "complete":
        evidence = list(db.scalars(select(LearningEvidenceRecord).where(
            LearningEvidenceRecord.institution_id == settings.institution_id,
            LearningEvidenceRecord.student_user_id == session.user_id,
            LearningEvidenceRecord.course_id == row.course_id, LearningEvidenceRecord.block_id == row.block_id)))
        result = evaluate_completion({"block_id": row.block_id, "task_id": row.task_id,
                            "planned_minutes": state["planned_minutes"],
                            "actual_minutes": int(changed["observed_seconds"] / 60) + payload.outside_minutes,
                            "completion_percent": payload.completion_percent, "blocker": payload.blocker,
                            "blocker_note": payload.note, "work_result": payload.work_result,
                            "remaining_minutes": payload.additional_minutes,
                            "understanding_self_report": payload.understanding_self_report})
        observation = result["output"]["do_session"]
        assessment_summary, assessment_refs = summarize_independent_assessment([
            {**json.loads(record.payload_json or "{}"), "id": record.id,
             "valid": bool(record.valid), "hint_level": record.hint_level}
            for record in sorted(evidence, key=lambda item: (item.created_at, item.id))])
        observation.update(session_id=row.id, course_id=row.course_id, date=state["date"],
                           interruption_reason="unexpected" if changed["had_unexpected_interruption"] else changed["interruption_reason"],
                           unobserved_gap=changed["unobserved_gap"], length_feeling=payload.length_feeling,
                           time_source="self_report" if payload.outside_minutes else "timer",
                           rhythm=state["rhythm"], readiness_key=state["readiness_key"],
                           activity_type=state.get("activity_type", "unknown"), activity_source=state.get("activity_source", "unmapped"),
                           checkpoint_minutes=state.get("checkpoint_minutes", 0),
                           assessment_evidence_ids=assessment_refs,
                           assessment_summary=assessment_summary,
                           hint_count=sum(e.hint_level > 0 for e in evidence))
        changed["evaluation"] = observation
    count = db.execute(update(StudyTimerSession).where(StudyTimerSession.id == row.id,
                       StudyTimerSession.version == payload.expected_version)
                       .values(version=payload.expected_version + 1, state_json=json.dumps(changed),
                               active_scope=None if changed["status"] in {"completed", "cancelled"} else row.active_scope),
                       execution_options={"synchronize_session": False}).rowcount
    if count != 1:
        db.rollback()
        raise HTTPException(409, "Session changed in another tab; reload its checkpoint")
    if payload.action == "complete":
        persist_agent_outcome(db, scoped, settings, result, None, commit=False)
    if changed["status"] in {"completed", "cancelled"}:
        clear_transcript(row)
    if payload.action != "checkpoint":
        audit(db, scoped, settings, f"STUDY_TIMER_{payload.action.upper()}", row.id, payload.event_key,
              {"status": changed["status"], "observed_seconds": changed["observed_seconds"],
               "interruption_reason": changed["interruption_reason"]})
    db.commit()
    db.refresh(row)
    return public(row)


def rhythm_report(db: Session, session: SessionContext, settings: Settings) -> dict:
    student(session)
    workspace = db.get(UserWorkspace, session.user_id)
    saved = json.loads(workspace.state_json or "{}") if workspace else {}
    preferences = StudyPreferences.model_validate(saved.get("studyPreferences") or {}).model_dump(by_alias=True)
    rows = db.scalars(select(StudyTimerSession).where(StudyTimerSession.institution_id == settings.institution_id,
                      StudyTimerSession.user_id == session.user_id, StudyTimerSession.course_id.in_(session.course_ids))
                      .order_by(StudyTimerSession.updated_at.desc()).limit(60))
    observations = []
    for row in rows:
        state = json.loads(row.state_json)
        if state.get("evaluation"):
            observations.append({**state["evaluation"], "recorded_at": state.get("completed_at", "")})
    trial_event = db.scalar(select(LearningEvent).where(LearningEvent.institution_id == settings.institution_id,
        LearningEvent.student_user_id == session.user_id, LearningEvent.course_id.in_(session.course_ids),
        LearningEvent.event_type == "RHYTHM_TRIAL_ACCEPTED").order_by(LearningEvent.occurred_at.desc()).limit(1))
    trial = json.loads(trial_event.payload_json) if trial_event else None
    return {**propose_rhythm(observations, preferences), "comparison": compare_rhythm_trial(observations, trial)}


@router.get("/rhythm/proposal")
def rhythm(session: SessionContext = Depends(get_current_session), settings: Settings = Depends(get_settings),
           db: Session = Depends(get_db)):
    return rhythm_report(db, session, settings)


class ConfirmRhythm(BaseModel):
    proposal_id: str = Field(alias="proposalId", min_length=32, max_length=32)


@router.post("/rhythm/confirm")
def confirm_rhythm(payload: ConfirmRhythm, session: SessionContext = Depends(require_csrf),
                   settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    report = rhythm_report(db, session, settings)
    proposal = report["proposal"]
    if not proposal or proposal["id"] != payload.proposal_id:
        raise HTTPException(409, "Rhythm evidence/preferences changed; refresh the proposal")
    audit(db, replace(session, course_id=proposal["courseId"]), settings, "RHYTHM_TRIAL_ACCEPTED", proposal["id"], proposal["id"],
          {**proposal, "baseline_preferences": report["current"], "accepted_at": now().isoformat()})
    db.commit()
    # The existing versioned workspace autosave persists this explicit choice.
    # Never mutate the plan, original remaining minutes or Knowledge State here.
    return {"preferences": proposal["preferences"], "scope": {"courseId": proposal["courseId"], "activityType": proposal["activityType"]},
            "planChanged": False, "requiresPlanPreview": True}
