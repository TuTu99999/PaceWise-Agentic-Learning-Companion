import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db import get_db
from src.persistence_models import (
    AgentReviewCase,
    InstructorAction,
    LoginAttempt,
    PaceWiseSession,
    UserWorkspace,
)
from src.security import SessionContext, get_current_session, require_csrf, require_instructor
from src.services.agent_memory import resolve_review_case
from src.services.instructor_workspace import (
    INSTRUCTOR_WORKSPACE_ACTIONS,
    normalize_instructor_workspace_action,
)
from src.services.notification_policy import ReminderPreferences, StudyPreferences
from src.services.question_design import QuestionDesign, preview_design
from src.services.reminder_schedule import reconcile_jobs

router = APIRouter()

WORKSPACE_KEYS = {
    "studyPreferences",
    "plan",
    "provisionalBlocks",
    "planHistory",
    "availability",
    "unavailable",
    "routineProfile",
    "sessions",
    "wizardInput",
    "planDraft",
    "calendarDraft",
    "quickChecks",
    "guidance",
    "reflection",
    "settings",
    "dismissedDrifts",
    "recoveryOptions",
    "recoveryOptionsKey",
    "taskProgress",
    "reflections",
    "planImpacts",
    "estimateProfiles",
    "pilotMetricsHistory",
    "recoveryCount",
    "lmsBaseline",
    "reminders",
    "qaMessages",
    "qaHistory",
    "qaConversations",
    "activeConversationId",
}


class WorkspaceRequest(BaseModel):
    state: dict
    expected_version: int | None = Field(default=None, alias="expectedVersion", ge=0)


class InstructorActionRequest(BaseModel):
    action_type: str = Field(
        alias="actionType",
        pattern="^(review|assessment|guidance|schedule|course_structure|feedback|settings)$",
    )
    entity_id: str = Field(alias="entityId", min_length=1, max_length=128)
    payload: dict = Field(default_factory=dict)


ASSESSMENT_CONTENT_FIELDS = (
    "question",
    "rubric",
    "level",
    "source",
    "answerType",
    "knowledgeComponentIds",
    "kcProvisional",
    "assessmentStage",
    "hints",
    "questionDesign",
)
REVIEW_STATUSES = {"pending", "in_review", "approved", "edited", "rejected", "needs_evidence"}


class DesignPreviewRequest(BaseModel):
    design: QuestionDesign
    rubric: list[str] = Field(min_length=2, max_length=6)
    source: str = Field(min_length=1, max_length=300)


@router.post("/instructor/assessment/design-preview")
def assessment_design_preview(
    payload: DesignPreviewRequest,
    session: SessionContext = Depends(require_instructor),
    _: SessionContext = Depends(require_csrf),
) -> dict:
    return {
        "examples": preview_design(payload.design, [text[:500] for text in payload.rubric], payload.source),
        "saved": False,
        "course_id": session.course_id,
    }


def _versioned_assessment_payload(
    db: Session,
    course_id: int,
    entity_id: str,
    incoming: dict,
) -> dict:
    if "questionDesign" in incoming:
        from pydantic import ValidationError

        try:
            incoming = {
                **incoming,
                "questionDesign": QuestionDesign.model_validate(incoming["questionDesign"]).model_dump(),
            }
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="Invalid assessment design configuration") from exc
    if "assessmentStage" in incoming and incoming["assessmentStage"] not in {
        "recall",
        "explain",
        "why",
        "application",
        "transfer",
    }:
        raise HTTPException(status_code=422, detail="Unsupported adaptive assessment stage")
    if "hints" in incoming:
        hints = incoming["hints"]
        if (
            not isinstance(hints, list)
            or len(hints) > 5
            or any(not isinstance(item, str) or len(item) > 2000 for item in hints)
        ):
            raise HTTPException(
                status_code=422, detail="Hints must be at most five text entries, each <=2000 characters"
            )
    if "knowledgeComponentIds" in incoming:
        identifiers = incoming["knowledgeComponentIds"]
        if (
            not isinstance(identifiers, list)
            or len(identifiers) > 20
            or any(not isinstance(value, str) or not value.strip() or len(value) > 160 for value in identifiers)
        ):
            raise HTTPException(status_code=422, detail="knowledgeComponentIds must be bounded non-empty text IDs")
    previous_action = db.scalar(
        select(InstructorAction)
        .where(
            InstructorAction.course_id == course_id,
            InstructorAction.action_type == "assessment",
            InstructorAction.entity_id == entity_id,
        )
        .order_by(InstructorAction.created_at.desc())
    )
    previous = json.loads(previous_action.payload_json or "{}") if previous_action else {}
    version = max(0, int(previous.get("version") or 0))
    content_changed = any(
        field in incoming and incoming[field] != previous.get(field) for field in ASSESSMENT_CONTENT_FIELDS
    )
    if version == 0 or content_changed:
        version += 1
    combined = {**previous, **incoming, "version": version}
    if (combined.get("questionDesign") or {}).get("mode", "fixed") != "fixed" and combined.get("status") == "approved":
        if (
            not combined.get("knowledgeComponentIds")
            or combined.get("kcProvisional")
            or len(combined.get("rubric") or []) < 2
        ):
            raise HTTPException(
                status_code=422, detail="Approved designs require a mapped KC and at least two rubric criteria"
            )
    return combined


def _safe_workspace(value: dict) -> dict:
    result = {key: value[key] for key in WORKSPACE_KEYS if key in value}
    try:
        if "studyPreferences" in result:
            result["studyPreferences"] = StudyPreferences.model_validate(result["studyPreferences"]).model_dump(by_alias=True)
        if "reminders" in result:
            result["reminders"] = {**result["reminders"], "preferences": ReminderPreferences.model_validate(
                result["reminders"].get("preferences") or {}).model_dump(by_alias=True)}
    except (ValidationError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid study or notification preferences") from exc
    encoded = json.dumps(result, ensure_ascii=False)
    if len(encoded.encode()) > 1_000_000:
        raise HTTPException(status_code=413, detail="Workspace exceeds 1 MB")
    return result


@router.get("/workspace")
def get_workspace(
    session: SessionContext = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(UserWorkspace, session.user_id)
    return {
        "state": json.loads(row.state_json) if row else {},
        "version": row.version if row else 0,
        "updatedAt": row.updated_at.isoformat() if row else None,
    }


@router.put("/workspace")
def save_workspace(
    payload: WorkspaceRequest,
    session: SessionContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    safe = _safe_workspace(payload.state)
    if any(item["courseId"] not in session.course_ids for item in safe.get("studyPreferences", {}).get("activityRhythms", [])):
        raise HTTPException(status_code=403, detail="Activity rhythm requires an enrolled course")
    row = db.get(UserWorkspace, session.user_id)
    current_version = row.version if row else 0
    if payload.expected_version is not None and payload.expected_version != current_version:
        raise HTTPException(
            status_code=409,
            detail=f"Workspace version conflict: expected {payload.expected_version}, current {current_version}",
        )
    if row:
        row.state_json = json.dumps(safe, ensure_ascii=False)
        row.version += 1
    else:
        row = UserWorkspace(user_id=session.user_id, state_json=json.dumps(safe, ensure_ascii=False))
        db.add(row)
    if session.role == "student":
        try:
            reconcile_jobs(db, session.user_id, safe)
        except (TypeError, AttributeError, KeyError, ValueError) as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail="Invalid reminder source data") from exc
    db.commit()
    db.refresh(row)
    return {"version": row.version, "updatedAt": row.updated_at.isoformat()}


@router.post("/instructor/actions")
def create_instructor_action(
    payload: InstructorActionRequest,
    session: SessionContext = Depends(require_instructor),
    _: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    action_payload = dict(payload.payload)
    if payload.action_type in INSTRUCTOR_WORKSPACE_ACTIONS:
        action_payload = normalize_instructor_workspace_action(
            payload.action_type,
            action_payload,
        )
    if payload.action_type == "assessment":
        action_payload = _versioned_assessment_payload(
            db,
            session.course_id,
            payload.entity_id,
            action_payload,
        )
    if payload.action_type == "review":
        status = str(action_payload.get("status") or "")
        if status not in REVIEW_STATUSES:
            raise HTTPException(status_code=422, detail="Unsupported review status")
        if status in {"edited", "rejected", "needs_evidence"} and not str(action_payload.get("note") or "").strip():
            raise HTTPException(
                status_code=422,
                detail="A decision note is required for this review status",
            )
    action = InstructorAction(
        id=str(uuid.uuid4()),
        course_id=session.course_id,
        actor_user_id=session.user_id,
        action_type=payload.action_type,
        entity_id=payload.entity_id,
        payload_json=json.dumps(action_payload, ensure_ascii=False),
    )
    if payload.action_type == "review":
        review_case = db.scalar(
            select(AgentReviewCase).where(AgentReviewCase.id == payload.entity_id).with_for_update()
        )
        if review_case and (
            review_case.course_id != session.course_id or review_case.institution_id != settings.institution_id
        ):
            raise HTTPException(status_code=404, detail="Review case not found in this instructor scope")
        if review_case and review_case.course_id == session.course_id:
            if review_case.status == "superseded":
                raise HTTPException(
                    status_code=409,
                    detail="New independent evidence resolved this case; the old conclusion cannot be approved",
                )
            review_case.status = str(action_payload.get("status") or review_case.status)
            review_payload = json.loads(review_case.payload_json or "{}")
            if action_payload.get("note"):
                review_payload["instructor_note"] = action_payload["note"]
            if action_payload.get("edited_result"):
                review_payload["edited_result"] = action_payload["edited_result"]
            review_case.payload_json = json.dumps(review_payload, ensure_ascii=False)
            resolve_review_case(db, review_case, action_payload, settings)
    # Validate the review's terminal state before adding the action: the scoped
    # SELECT may autoflush, even when the request will subsequently return 409.
    db.add(action)
    db.commit()
    return {
        "id": action.id,
        "createdAt": action.created_at.isoformat(),
        "payload": action_payload,
    }


def check_login_rate_limit(request: Request, email: str, db: Session, settings: Settings) -> None:
    key_hash = _login_key(request, email)
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.login_rate_window_seconds)
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < cutoff - timedelta(days=1)))
    attempts = db.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.key_hash == key_hash,
            LoginAttempt.created_at >= cutoff,
        )
    )
    if int(attempts or 0) >= settings.login_rate_limit:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")


def record_failed_login(request: Request, email: str, db: Session) -> None:
    key_hash = _login_key(request, email)
    db.add(LoginAttempt(key_hash=key_hash))
    db.commit()


def _login_key(request: Request, email: str) -> str:
    import hashlib

    ip = request.client.host if request.client else "unknown"
    return hashlib.sha256(f"{ip}:{email.lower().strip()}".encode()).hexdigest()


def revoke_session(session: SessionContext, db: Session) -> None:
    row = db.get(PaceWiseSession, session.sid)
    if row and not row.revoked_at:
        row.revoked_at = datetime.now(UTC)
        db.commit()
