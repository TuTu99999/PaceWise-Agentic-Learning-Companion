"""Trusted assessment context, long-term learner memory and review cases."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings
from src.persistence_models import AgentReviewCase, InstructorAction, LearnerMemory, LearningEvidenceRecord
from src.security import SessionContext
from src.services.assessment_review_policy import planning_evidence_usable
from src.services.learning_cycle_metrics import freeze_plan_measurement
from src.services.learning_events import audit
from src.services.learning_evidence import build_evidence_contract, persist_learning_evidence
from src.services.lms_client import LMSClient
from src.services.reflection_observations import load_reflection_observations
from src.services.replan_policy import decide_replan, decide_weekly_replan

MAX_HISTORY_ITEMS = 50


def _json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _memory_id(institution_id: str, user_id: int, course_id: int) -> str:
    return f"{institution_id}:{user_id}:{course_id}"


def load_learner_memory(db: Session, session: SessionContext, settings: Settings) -> dict[str, Any]:
    row = db.get(
        LearnerMemory,
        _memory_id(settings.institution_id, session.user_id, session.course_id),
    )
    if not row:
        return {"profile": {}, "mastery": {}, "misconceptions": [], "history": []}
    return {
        "profile": _json(row.profile_json, {}),
        "mastery": _json(row.mastery_json, {}),
        "misconceptions": _json(row.misconceptions_json, []),
        "history": _json(row.history_json, []),
    }


def load_planning_memory(db: Session, session: SessionContext, settings: Settings) -> dict[str, Any]:
    """Aggregate plan signals across enrolled courses without merging mastery.

    Do/Reflect observations are task-scoped and may affect a multi-course plan.
    Knowledge state remains namespaced by course to prevent cross-course
    transfer from similarly named concepts.
    """

    rows = db.scalars(
        select(LearnerMemory).where(
            LearnerMemory.institution_id == settings.institution_id,
            LearnerMemory.user_id == session.user_id,
            LearnerMemory.course_id.in_(session.course_ids),
        )
    ).all()
    if not rows:
        return {"profile": {}, "mastery": {"__by_course__": {}}, "misconceptions": [], "history": []}

    profiles: list[dict[str, Any]] = []
    do_history: list[dict[str, Any]] = []
    reflections: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    mastery_by_course: dict[str, dict[str, Any]] = {}
    misconceptions: list[Any] = []
    history: list[Any] = []
    current_profile: dict[str, Any] = {}
    for row in rows:
        profile = _json(row.profile_json, {})
        profiles.append(profile)
        if row.course_id == session.course_id:
            current_profile = profile
        do_history.extend(item for item in profile.get("do_history") or [] if isinstance(item, dict))
        reflections.extend(item for item in profile.get("activity_reflections") or [] if isinstance(item, dict))
        proposal = profile.get("last_replan_proposal")
        if isinstance(proposal, dict):
            proposals.append(proposal)
        mastery_by_course[str(row.course_id)] = _json(row.mastery_json, {})
        misconceptions.extend(_json(row.misconceptions_json, []))
        history.extend(_json(row.history_json, []))

    do_history.sort(key=lambda item: str(item.get("recorded_at") or item.get("completed_at") or ""))
    reflections.sort(key=lambda item: str(item.get("confirmed_at") or ""))
    proposals.sort(key=lambda item: str(item.get("decided_at") or ""))
    combined = dict(current_profile or profiles[0])
    combined["do_history"] = do_history[-MAX_HISTORY_ITEMS:]
    combined["activity_reflections"] = reflections[-MAX_HISTORY_ITEMS:]
    combined["replan_proposals"] = proposals[-MAX_HISTORY_ITEMS:]
    if proposals:
        combined["last_replan_proposal"] = proposals[-1]
        affected = set((proposals[-1].get("repair_context") or {}).get("affected_task_ids") or [])
        matching = [item for item in do_history if str(item.get("task_id") or "") in affected]
        if matching:
            combined["last_do_session"] = matching[-1]
    return {
        "profile": combined,
        "mastery": {"__by_course__": mastery_by_course},
        "misconceptions": misconceptions[-MAX_HISTORY_ITEMS:],
        "history": history[-MAX_HISTORY_ITEMS:],
    }


async def load_approved_assessment(
    db: Session,
    session: SessionContext,
    settings: Settings,
    assessment_id: str,
    quizzes: list[dict] | None = None,
) -> dict[str, Any]:
    """Resolve an approved assessment exclusively from trusted server data."""
    if not assessment_id.startswith("Q-"):
        raise HTTPException(status_code=422, detail="Unsupported assessment identifier")
    try:
        question_id = int(assessment_id.removeprefix("Q-"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid assessment identifier") from exc

    approval = db.scalar(
        select(InstructorAction)
        .where(
            InstructorAction.course_id == session.course_id,
            InstructorAction.action_type == "assessment",
            InstructorAction.entity_id == assessment_id,
        )
        .order_by(InstructorAction.created_at.desc())
    )
    approval_payload = _json(approval.payload_json, {}) if approval else {}
    if approval_payload.get("status") != "approved":
        raise HTTPException(status_code=409, detail="Assessment has not been approved by an instructor")

    if quizzes is None:
        quizzes = await LMSClient(settings).service_get(
            f"/api/pacewise/v1/courses/{session.course_id}/quizzes",
            {"include_answers": True},
        )
    for quiz in quizzes:
        for question in quiz.get("questions", []):
            if int(question["id"]) != question_id:
                continue
            rubric = approval_payload.get("rubric") or [
                "Đúng khái niệm",
                "Giải thích có lập luận",
                "Không sao chép đáp án",
            ]
            return {
                "assessment_id": assessment_id,
                "question": approval_payload.get("question") or question.get("prompt", ""),
                "question_type": "open" if (
                    approval_payload.get("answerType") or approval_payload.get("answer_type")
                ) == "open" else question.get("question_type", "open"),
                "answer_type": str(
                    approval_payload.get("answerType")
                    or approval_payload.get("answer_type")
                    or (
                        "multiple_choice"
                        if question.get("options")
                        else "exact_text"
                        if question.get("correct_answer") is not None
                        else "open"
                    )
                ),
                "correct_answer": question.get("correct_answer"),
                "approved_rubric": [
                    {
                        "criterion_id": f"{assessment_id}-{index}",
                        "description": str(description),
                    }
                    for index, description in enumerate(rubric, start=1)
                ],
                "topic": quiz.get("title", ""),
                "rubric_version": max(1, int(approval_payload.get("version") or 1)),
                "knowledge_component_ids": (
                    approval_payload.get("knowledgeComponentIds")
                    or approval_payload.get("knowledge_component_ids")
                    or approval_payload.get("kcIds")
                    or []
                ),
                "kc_provisional": bool(approval_payload.get("kcProvisional", False)),
                "cognitive_level": str(approval_payload.get("level") or "recognition"),
                "assessment_stage": str(approval_payload.get("assessmentStage") or ""),
                "hints": approval_payload.get("hints") or [],
                "counterexample": bool(approval_payload.get("counterexample")),
                "source": str(approval_payload.get("source") or "Canvas quiz"),
                "question_design": approval_payload.get("questionDesign") or {},
            }
    raise HTTPException(status_code=404, detail="Assessment no longer exists in the LMS")


def persist_agent_outcome(
    db: Session,
    session: SessionContext,
    settings: Settings,
    result: dict[str, Any],
    assessment_id: str | None,
    *,
    commit: bool = True,
) -> str | None:
    """Update durable learner memory and create instructor review cases."""
    memory_key = _memory_id(settings.institution_id, session.user_id, session.course_id)
    row = db.get(LearnerMemory, memory_key) or LearnerMemory(
        id=memory_key,
        institution_id=settings.institution_id,
        user_id=session.user_id,
        course_id=session.course_id,
    )
    db.add(row)
    profile = _json(row.profile_json, {})
    mastery = _json(row.mastery_json, {})
    misconceptions = _json(row.misconceptions_json, [])
    history = _json(row.history_json, [])
    now = datetime.now(UTC).isoformat()

    workflow = str(result.get("workflow") or result.get("current_node") or "")
    assessment = result.get("assessment_result") or {}
    is_assessment_workflow = workflow == "understanding" or bool(
        assessment and (result.get("do_session") or {}).get("action") == "assess"
    )
    is_provisional = is_assessment_workflow and result.get("status") == "awaiting_teacher"
    evidence_payload: dict[str, Any] | None = None
    knowledge_snapshots: list[dict[str, Any]] = []
    trusted_assessment = result.get("_trusted_assessment") or {}
    if assessment_id and assessment and trusted_assessment:
        evidence_contract = build_evidence_contract(
            session=session,
            settings=settings,
            result=result,
            assessment_id=assessment_id,
            trusted_assessment=trusted_assessment,
        )
        evidence_payload, knowledge_snapshots = persist_learning_evidence(
            db,
            session,
            settings,
            evidence_contract,
        )
        assessment["evidence_ids"] = [evidence_payload["id"]]
        assessment["knowledge_component_ids"] = evidence_payload["knowledge_component_ids"]
        assessment["demonstrated_level"] = evidence_payload["demonstrated_level"]
        assessment["provisional"] = not bool(knowledge_snapshots)
        result.setdefault("output", {})["learning_evidence"] = evidence_payload
        result["output"]["knowledge_state"] = knowledge_snapshots
        evidence_summary = {
            key: evidence_payload.get(key) for key in ("id", "valid", "confidence", "dimensions", "misconceptions", "knowledge_component_ids", "block_id", "review_status")
        }
        if planning_evidence_usable(evidence_payload):
            profile["last_assessment_evidence"] = evidence_summary
        else:
            profile["last_unconfirmed_assessment_evidence"] = evidence_summary
        for snapshot in knowledge_snapshots:
            topic = str(snapshot["knowledge_component"])
            mastery[topic] = {
                "assessment_id": assessment_id,
                "status": assessment.get("status"),
                "level": snapshot["level"],
                "confidence": snapshot["confidence"],
                "evidence_count": snapshot["evidence_count"],
                "source_evidence_ids": snapshot["source_evidence_ids"],
                "retention_status": snapshot["retention_status"],
                "retained_level": snapshot.get("retained_level"),
                "dimensions": snapshot.get("dimensions") or {},
                "unresolved_dimensions": snapshot.get("unresolved_dimensions") or [],
                "rubric_version": assessment.get("rubric_version"),
                "updated_at": now,
            }
        if knowledge_snapshots and evidence_payload.get("misconceptions"):
            misconceptions.extend(
                {
                    **item,
                    "assessment_id": assessment_id,
                    "evidence_id": evidence_payload["id"],
                    "observed_at": now,
                }
                for item in evidence_payload["misconceptions"]
                if isinstance(item, dict)
            )
    if (
        workflow == "reflect"
        and result.get("status") == "completed"
        and result.get("reflection_draft")
    ):
        reflection = result["reflection_draft"]
        observed_do = profile.get("last_do_session") or {}
        observed_evidence = profile.get("last_assessment_evidence") or {}
        activity = reflection.get("activity") or {}
        if reflection.get("scope") == "activity" and activity.get("block_id"):
            target_block = str(activity["block_id"])
            observed_do = next((item for item in reversed(profile.get("do_history") or [])
                                if item.get("block_id") == target_block), {})
            evidence_rows = db.scalars(select(LearningEvidenceRecord).where(
                LearningEvidenceRecord.institution_id == settings.institution_id,
                LearningEvidenceRecord.student_user_id == session.user_id,
                LearningEvidenceRecord.course_id == session.course_id,
                LearningEvidenceRecord.block_id == target_block,
            ).order_by(LearningEvidenceRecord.created_at.desc())).all()
            observed_evidence = next((payload for record in evidence_rows
                                      if planning_evidence_usable(payload := _json(record.payload_json, {}))), {})
        elif reflection.get("scope") == "activity" and activity.get("kind") not in {None, "self_study", "review"}:
            # A class reflection must not inherit an unrelated Do assessment.
            observed_do, observed_evidence = {}, {}
        if reflection.get("scope") == "weekly":
            observations = load_reflection_observations(db, session, settings, {
                "reflection_scope": "weekly", "week_start": reflection.get("week_start"),
            })
            decision = decide_weekly_replan(
                signal=reflection.get("planning_signal") or {}, observations=observations,
                previous=profile.get("last_replan_proposal"),
            )
        else:
            decision = decide_replan(signal=reflection.get("planning_signal") or {},
                                     last_do=observed_do, latest_evidence=observed_evidence,
                                     previous=profile.get("last_replan_proposal"))
        profile["last_replan_decision"] = decision
        if decision["action"] == "propose_draft":
            profile["last_replan_proposal"] = decision
        result.setdefault("output", {})["replan_decision"] = decision
        key = hashlib.sha256(json.dumps(reflection, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        audit(db, session, settings, "REFLECTION_SUBMITTED", str(reflection.get("week_start") or "activity"), key,
              {"scope": reflection.get("scope"), "planning_signal": reflection.get("planning_signal") or {}})
        audit(db, session, settings, "REPLAN_DECIDED", decision["fingerprint"], decision["fingerprint"], decision)
        if reflection.get("scope") == "activity":
            activity_reflections = list(profile.get("activity_reflections") or [])
            activity_reflections.append({**reflection, "confirmed_at": now})
            profile["activity_reflections"] = activity_reflections[-50:]
        else:
            profile["last_reflection"] = reflection
            profile["next_week_adjustment"] = {
                "effective_week_start": reflection.get("effective_week_start"),
                "adjustment": reflection.get("adjustment"),
                "confirmed_at": now,
            }
    if workflow == "tracking":
        profile["last_progress_metrics"] = result.get("progress_metrics") or {}
    if workflow == "do" and isinstance((result.get("output") or {}).get("do_session"), dict):
        do_session = (result.get("output") or {})["do_session"]
        if do_session.get("action") in {"prepare", "complete"}:
            # An assessment event has no timer/progress metrics and must not
            # erase the observed session used by Reflect and re-plan policy.
            profile["last_do_session"] = do_session
        if do_session.get("action") == "complete":
            do_history = list(profile.get("do_history") or [])
            block_id = str(do_session.get("block_id") or "")
            block = next((item for item in (profile.get("last_confirmed_plan") or {}).get("blocks") or []
                          if str(item.get("id")) == block_id), {})
            observation = {**do_session, "recorded_at": now}
            if block.get("date"):
                observation["date"] = block["date"]
            # One latest outcome per block; retries do not inflate weekly totals.
            if block_id:
                do_history = [item for item in do_history if item.get("block_id") != block_id]
            do_history.append(observation)
            profile["do_history"] = do_history[-20:]
            key = hashlib.sha256(json.dumps(do_session, sort_keys=True).encode()).hexdigest()
            audit(db, session, settings, "STUDY_SESSION_COMPLETED", block_id, key, observation)
        if do_session.get("action") == "prepare":
            audit(db, session, settings, "STUDY_SESSION_STARTED", str(do_session.get("block_id") or ""),
                  str(do_session.get("block_id") or now), {"task_id": do_session.get("task_id")})
    if workflow == "plan" and (result.get("student_decision") or {}).get("action") == "confirmed":
        confirmed = (result.get("output") or {}).get("confirmed_plan") or {}
        key = hashlib.sha256(json.dumps(confirmed, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        confirmed = {**confirmed, "measurement": freeze_plan_measurement(confirmed, datetime.fromisoformat(now), settings.app_timezone)}
        result["output"] = {**(result.get("output") or {}), "confirmed_plan": confirmed}
        audit(db, session, settings, "PLAN_CONFIRMED", key, key, {"confirmed_plan": confirmed})
        if profile.get("last_replan_proposal"):
            audit(db, session, settings, "REPLAN_CONFIRMED", key, key,
                  {"proposal_fingerprint": profile["last_replan_proposal"]["fingerprint"]})
        profile.pop("pending_plan_draft", None)
        profile["last_confirmed_plan"] = confirmed
        profile["outstanding_plan_work"] = {
            "draft_id": confirmed.get("createdAt"),
            "confirmation_mode": (confirmed.get("confirmation") or {}).get("mode", "full"),
            "shortfalls": (confirmed.get("feasibility") or {}).get("shortfalls") or [],
            "feasible": bool((confirmed.get("feasibility") or {}).get("feasible")),
        }
    elif workflow == "plan" and (result.get("output") or {}).get("plan_draft"):
        # Client workspace PUTs cannot replace this server-owned proposal.
        profile["pending_plan_draft"] = result["output"]["plan_draft"]

    history.append(
        {
            "workflow": workflow,
            "assessment_id": assessment_id,
            "status": result.get("status", "completed"),
            "rubric_version": assessment.get("rubric_version"),
            "provisional": is_provisional,
            "recorded_at": now,
        }
    )
    row.profile_json = json.dumps(profile, ensure_ascii=False)
    row.mastery_json = json.dumps(mastery, ensure_ascii=False)
    row.misconceptions_json = json.dumps(misconceptions[-MAX_HISTORY_ITEMS:], ensure_ascii=False)
    row.history_json = json.dumps(history[-MAX_HISTORY_ITEMS:], ensure_ascii=False)

    pending_action = result.get("pending_action") or {}
    review_case_id = None
    if is_assessment_workflow and result.get("status") == "awaiting_teacher" and not result.get("_defer_human_review"):
        review_case_id = _create_review_case(
            db,
            session,
            settings,
            case_type="understanding_review",
            entity_id=assessment_id or str(uuid.uuid4()),
            payload={
                "pending_action": pending_action,
                "assessment_result": assessment,
                "topic": str((result.get("request") or {}).get("topic") or assessment_id or ""),
                "rubric_version": assessment.get("rubric_version"),
                "learning_evidence": evidence_payload,
                "trusted_assessment": trusted_assessment,
                "assessment_review": result.get("assessment_review") or {},
            },
        )
        result.setdefault("output", {})["review_case_id"] = review_case_id
    latest = (result.get("output") or {}).get("citation_dispute")
    if latest:
        _create_review_case(
            db,
            session,
            settings,
            case_type="citation_dispute",
            entity_id=str(latest.get("dispute_id") or uuid.uuid4()),
            payload=latest,
        )
    if commit:
        db.commit()
    else:
        db.flush()
    return review_case_id


def _apply_assessment_result(
    mastery: dict[str, Any],
    misconceptions: list[dict[str, Any]],
    *,
    assessment_id: str,
    topic: str,
    assessment: dict[str, Any],
    recorded_at: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    next_mastery = dict(mastery)
    next_misconceptions = [
        item for item in misconceptions if item.get("assessment_id") != assessment_id
    ]
    next_mastery[topic] = {
        "assessment_id": assessment_id,
        "status": assessment.get("status"),
        "confidence": assessment.get("confidence"),
        "rubric_version": assessment.get("rubric_version"),
        "updated_at": recorded_at,
    }
    normalized_status = str(assessment.get("status") or "").casefold()
    if "nhầm lẫn" in normalized_status or "misconception" in normalized_status:
        next_misconceptions.append(
            {
                "assessment_id": assessment_id,
                "topic": topic,
                "evidence": assessment.get("evidence_quotes") or [],
                "rubric_version": assessment.get("rubric_version"),
                "observed_at": recorded_at,
            }
        )
    return next_mastery, next_misconceptions


def resolve_review_case(
    db: Session,
    review_case: AgentReviewCase,
    decision: dict[str, Any],
    settings: Settings,
) -> None:
    """Apply only a teacher-confirmed understanding result to learner memory."""
    status = str(decision.get("status") or "")
    if review_case.case_type != "understanding_review" or status not in {"approved", "edited"}:
        return
    case_payload = _json(review_case.payload_json, {})
    assessment = dict(case_payload.get("assessment_result") or {})
    if status == "edited":
        assessment.update(decision.get("edited_result") or case_payload.get("edited_result") or {})
    assessment["confidence"] = "teacher_confirmed"
    assessment["rubric_version"] = (
        case_payload.get("rubric_version") or assessment.get("rubric_version")
    )
    topic = str(case_payload.get("topic") or review_case.entity_id)
    memory_key = _memory_id(
        settings.institution_id,
        review_case.student_user_id,
        review_case.course_id,
    )
    row = db.get(LearnerMemory, memory_key) or LearnerMemory(
        id=memory_key,
        institution_id=settings.institution_id,
        user_id=review_case.student_user_id,
        course_id=review_case.course_id,
    )
    db.add(row)
    mastery = _json(row.mastery_json, {})
    misconceptions = _json(row.misconceptions_json, [])
    history = _json(row.history_json, [])
    now = datetime.now(UTC).isoformat()
    original_evidence = case_payload.get("learning_evidence") or {}
    trusted = case_payload.get("trusted_assessment") or {}
    if original_evidence and trusted:
        # Teacher confirmation follows the same evidence gates; it cannot
        # turn an untested transfer/retention dimension into a fact.
        learner = SessionContext(review_case.student_user_id, review_case.course_id,
                                 (review_case.course_id,), "student", "Review", "", "", review_case.id, 0)
        assessment["evaluator_version"] = "teacher-review-v1"
        contract = build_evidence_contract(session=learner, settings=settings,
            assessment_id=review_case.entity_id, trusted_assessment=trusted,
            result={"status": "completed", "query": original_evidence.get("response", ""),
                    "assessment_result": assessment, "request": {"assessment_attempt": {
                        "response": original_evidence.get("response", ""), "hint_level": original_evidence.get("hint_level", 0),
                        "first_attempt": original_evidence.get("first_attempt", False),
                        "block_id": original_evidence.get("block_id", ""), "event_key": f"teacher-review:{review_case.id}"}}})
        contract["review_case_id"] = review_case.id
        contract["reviewed_evidence_id"] = original_evidence["id"]
        _, snapshots = persist_learning_evidence(db, learner, settings, contract)
        for snapshot in snapshots:
            mastery[snapshot["knowledge_component"]] = {**snapshot, "updated_at": now}
        audit(db, learner, settings, "ASSESSMENT_REVIEWED", review_case.id, review_case.id,
              {"evidence_id": original_evidence["id"], "knowledge_state_updated": bool(snapshots)})
    else:
        # Compatibility for pre-evidence review records only.
        mastery, misconceptions = _apply_assessment_result(
            mastery, misconceptions, assessment_id=review_case.entity_id, topic=topic,
            assessment=assessment, recorded_at=now,
        )
    history = [item for item in history if item.get("review_case_id") != review_case.id]
    history.append(
        {
            "workflow": "understanding_review",
            "assessment_id": review_case.entity_id,
            "review_case_id": review_case.id,
            "status": status,
            "rubric_version": assessment.get("rubric_version"),
            "recorded_at": now,
        }
    )
    row.mastery_json = json.dumps(mastery, ensure_ascii=False)
    row.misconceptions_json = json.dumps(
        misconceptions[-MAX_HISTORY_ITEMS:], ensure_ascii=False
    )
    row.history_json = json.dumps(history[-MAX_HISTORY_ITEMS:], ensure_ascii=False)


def _create_review_case(
    db: Session,
    session: SessionContext,
    settings: Settings,
    *,
    case_type: str,
    entity_id: str,
    payload: dict[str, Any],
) -> str:
    duplicate = db.scalar(
        select(AgentReviewCase).where(
            AgentReviewCase.institution_id == settings.institution_id,
            AgentReviewCase.course_id == session.course_id,
            AgentReviewCase.student_user_id == session.user_id,
            AgentReviewCase.case_type == case_type,
            AgentReviewCase.entity_id == entity_id,
            AgentReviewCase.status == "pending",
        )
    )
    if duplicate:
        # The same bank question can be used in different Do checkpoints.
        # Never overwrite another checkpoint's pending evidence/context.
        incoming_scope = (payload.get("assessment_review") or {}).get("checkpoint_id")
        existing_scope = (_json(duplicate.payload_json, {}).get("assessment_review") or {}).get("checkpoint_id")
        if incoming_scope and incoming_scope != existing_scope:
            duplicate = None
    if duplicate:
        duplicate.payload_json = json.dumps(payload, ensure_ascii=False)
        return duplicate.id
    review_case = AgentReviewCase(
        id=f"AR-{uuid.uuid4().hex[:16]}",
        institution_id=settings.institution_id,
        course_id=session.course_id,
        student_user_id=session.user_id,
        case_type=case_type,
        entity_id=entity_id,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    db.add(review_case)
    return review_case.id
