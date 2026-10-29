"""Persistent Do sub-agent orchestration, with server-owned attempts and due probes."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from src.config import Settings
from src.persistence_models import AdaptiveAssessmentSession, AgentReviewCase, DelayedAssessmentProbe, InstructorAction
from src.security import SessionContext
from src.services.agent_memory import load_approved_assessment
from src.services.assessment_policy import (
    DIMENSION,
    HINTS,
    STAGES,
    item_stage,
    next_step,
    question_fingerprint,
    select_item,
)
from src.services.assessment_review_policy import MAX_VERIFICATION_QUESTIONS
from src.services.learning_events import audit
from src.services.question_design import generate_candidate, instance_bank

POLICY_VERSION = "adaptive-do-v2"


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def now_utc() -> datetime:
    return datetime.now(UTC)


def configured_checkpoint_stages(seed: dict, bank: list[dict], kc_id: str) -> list[str]:
    """Expose only stages that can actually issue a trusted question.

    A teacher-approved generative template can cover every declared stage. A
    fixed/legacy bank cannot: its sequence must be limited to stages for which
    an approved item exists, otherwise learners are shown a fake N-step flow
    that immediately dead-ends on an empty stage.
    """
    design = seed.get("question_design") or {}
    requested = [value for value in design.get("stages", []) if value in STAGES]
    if design.get("mode") in {"relation_template", "llm_followup"} and requested:
        return requested
    available = [
        stage
        for stage in STAGES
        if any(
            kc_id in item.get("knowledge_component_ids", [])
            and not item.get("kc_provisional")
            and item_stage(item) == stage
            for item in bank
        )
    ]
    if requested:
        available = [stage for stage in requested if stage in available]
    return available or [item_stage(seed)]


def assessment_set_bank(bank: list[dict], state: dict) -> list[dict]:
    """Keep a checkpoint inside the teacher-approved question set that started it.

    Legacy assessments have no set id and retain the previous KC-scoped behavior.
    Generated follow-ups inherit their parent's set id through ``_instance``.
    """
    assessment_set_id = str(state.get("assessment_set_id") or "").strip()
    if not assessment_set_id:
        return bank
    return [item for item in bank if item.get("assessment_set_id") == assessment_set_id]


def checkpoint_bank(bank: list[dict], state: dict) -> list[dict]:
    return instance_bank(assessment_set_bank(bank, state), state)


async def approved_bank(db: Session, session: SessionContext, settings: Settings) -> list[dict]:
    rows = db.scalars(
        select(InstructorAction)
        .where(InstructorAction.course_id == session.course_id, InstructorAction.action_type == "assessment")
        .order_by(InstructorAction.created_at.desc())
    ).all()
    latest: dict[str, dict] = {}
    for row in rows:
        latest.setdefault(row.entity_id, json.loads(row.payload_json or "{}"))
    approved = {
        identifier: payload
        for identifier, payload in latest.items()
        if payload.get("status") == "approved"
    }
    bank = []
    for identifier, payload in approved.items():
        try:
            bank.append(await load_approved_assessment(db, session, settings, identifier))
        except HTTPException as exc:
            if exc.status_code not in {404, 409, 422}:
                raise
    return bank


def scoped_checkpoint(db: Session, session: SessionContext, settings: Settings, identifier: str):
    row = db.scalar(
        select(AdaptiveAssessmentSession)
        .where(
            AdaptiveAssessmentSession.id == identifier,
            AdaptiveAssessmentSession.institution_id == settings.institution_id,
            AdaptiveAssessmentSession.student_user_id == session.user_id,
            AdaptiveAssessmentSession.course_id == session.course_id,
        )
        .with_for_update()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Checkpoint not found in this student/course")
    return row, json.loads(row.state_json)


def public_state(row: AdaptiveAssessmentSession, state: dict, bank: list[dict]) -> dict:
    bank = checkpoint_bank(bank, state)
    item = next((item for item in bank if item["assessment_id"] == state.get("item_id")), None)
    configured_stages = [stage for stage in state.get("checkpoint_stages", STAGES) if stage in STAGES]
    if not configured_stages:
        configured_stages = list(STAGES)
    stage_number = configured_stages.index(state["stage"]) + 1 if state["stage"] in configured_stages else 1
    return {
        "session_id": row.id,
        "policy_version": POLICY_VERSION,
        "status": state["status"],
        "stage": state["stage"],
        "stage_number": stage_number,
        "stage_total": len(configured_stages),
        "reason": state.get("reason", ""),
        "kc_id": row.kc_id,
        "mode": row.mode,
        "assessment_set_id": state.get("assessment_set_id"),
        "hint_level": state.get("hint_level", 0),
        "probe_id": state.get("probe_id"),
        "hint": state.get("hint", ""),
        "attempts": state.get("attempts", 0),
        "review": state.get("review"),
        "verification_count": state.get("verification_count", 0),
        "verification_limit": MAX_VERIFICATION_QUESTIONS,
        "blocks_planning": False,
        "blocks_learning": False,
        "question": {
            "id": item["assessment_id"],
            "text": item["question"],
            "source": item["source"],
            "version": item["rubric_version"],
            "origin": "llm_formative"
            if item.get("formative_only")
            else "verified_template"
            if item.get("parent_assessment_id")
            else "approved_anchor",
            "formative_only": bool(item.get("formative_only")),
        }
        if item
        else None,
        "last_result": state.get("last_result"),
        "coverage_gap": state.get("coverage_gap"),
        "delayed_probe": state.get("delayed_probe"),
        "requires_confirmation": False,
    }


def save(row: AdaptiveAssessmentSession, state: dict) -> None:
    row.state_json = json.dumps(state, ensure_ascii=False)


def audit_question(
    db: Session,
    session: SessionContext,
    settings: Settings,
    row: AdaptiveAssessmentSession,
    state: dict,
    bank: list[dict],
) -> None:
    """Keep the displayed question even if it is never answered or its parent changes."""
    item = next((value for value in checkpoint_bank(bank, state) if value["assessment_id"] == state.get("item_id")), None)
    if not item:
        return
    audit(
        db,
        session,
        settings,
        "ASSESSMENT_QUESTION_ISSUED",
        row.id,
        f"{row.id}:{item['assessment_id']}:{item['rubric_version']}:{question_fingerprint(item)}",
        {
            "question_id": item["assessment_id"],
            "question": item["question"],
            "source": item["source"],
            "stage": state["stage"],
            "parent_assessment_id": item.get("parent_assessment_id"),
            "parent_version": item.get("parent_version"),
            "generation_version": item.get("generation_version"),
            "formative_only": bool(item.get("formative_only")),
        },
    )


async def assign(state: dict, bank: list[dict], kc_id: str) -> None:
    bank = assessment_set_bank(bank, state)
    item = state.pop("_next_candidate", None) or await run_in_threadpool(
        generate_candidate, state, bank, kc_id, state.get("checkpoint_seed", kc_id)
    )
    if item:
        state.setdefault("generated_items", {})[item["assessment_id"]] = item
    else:
        candidates = instance_bank(bank, state)
        if state.get("force_anchor"):
            candidates = [value for value in candidates if not value.get("formative_only")]
        preferred_id = state.get("preferred_item_id")
        preferred = [value for value in candidates if value.get("assessment_id") == preferred_id]
        item = select_item(
            preferred,
            kc_id,
            state["stage"],
            state.get("used", []),
            state.get("seen_questions", []),
        )
        if not item:
            item = select_item(
                candidates,
                kc_id,
                state["stage"],
                state.get("used", []),
                state.get("seen_questions", []),
            )
    state.pop("force_anchor", None)
    if not item:
        state.update(status="coverage_gap", reason="no_approved_item", item_id=None, coverage_gap=state["stage"])
    else:
        state.update(
            item_id=item["assessment_id"],
            item_version=item["rubric_version"],
            hint_level=0,
            hint="",
            attempts=0,
            coverage_gap=None,
        )


def current_item(state: dict, bank: list[dict]) -> dict:
    bank = checkpoint_bank(bank, state)
    item = next((item for item in bank if item["assessment_id"] == state.get("item_id")), None)
    if not item or item["rubric_version"] != state.get("item_version"):
        raise HTTPException(status_code=409, detail="Question approval/rubric changed; restart checkpoint")
    if state["status"] not in {"active", "needs_support", "verification_required"}:
        raise HTTPException(status_code=409, detail="Checkpoint is not accepting responses")
    return item


def receipt(state: dict, key: str, body: str) -> dict | None:
    previous = (state.get("receipts") or {}).get(key)
    if previous and previous["body"] != hashlib.sha256(body.encode()).hexdigest():
        raise HTTPException(status_code=409, detail="Retry key was reused with different content")
    return previous["response"] if previous else None


def remember(state: dict, key: str, body: str, response: dict) -> None:
    receipts = state.setdefault("receipts", {})
    if len(receipts) >= 64:
        raise HTTPException(status_code=409, detail="Checkpoint retry receipt limit reached")
    receipts[key] = {"body": hashlib.sha256(body.encode()).hexdigest(), "response": response}


async def start(
    db: Session,
    session: SessionContext,
    settings: Settings,
    *,
    block_id: str,
    assessment_id: str,
    probe_id: str | None = None,
    restart: bool = False,
) -> dict:
    bank = await approved_bank(db, session, settings)
    seed = next((item for item in bank if item["assessment_id"] == assessment_id), None)
    if not seed or seed.get("kc_provisional") or not seed.get("knowledge_component_ids"):
        raise HTTPException(status_code=409, detail="Checkpoint requires an approved mapped assessment")
    kc_id = seed["knowledge_component_ids"][0]
    assessment_set_id = seed.get("assessment_set_id")
    design = seed.get("question_design") or {}
    configured_stages = configured_checkpoint_stages(
        seed,
        assessment_set_bank(bank, {"assessment_set_id": assessment_set_id}),
        kc_id,
    )
    probe = None
    if probe_id:
        probe = db.scalar(
            select(DelayedAssessmentProbe)
            .where(
                DelayedAssessmentProbe.id == probe_id,
                DelayedAssessmentProbe.institution_id == settings.institution_id,
                DelayedAssessmentProbe.student_user_id == session.user_id,
                DelayedAssessmentProbe.course_id == session.course_id,
                DelayedAssessmentProbe.kc_id == kc_id,
            )
            .with_for_update()
        )
        if not probe or probe.status != "pending":
            raise HTTPException(status_code=409, detail="Delayed probe is unavailable")
        if now_utc() < utc(probe.due_at):
            raise HTTPException(status_code=409, detail="Delayed reassessment is not due yet")
        block_id = f"probe:{probe.id}"
    mode = "retention" if probe else "learning"
    row = db.scalar(
        select(AdaptiveAssessmentSession)
        .where(
            AdaptiveAssessmentSession.institution_id == settings.institution_id,
            AdaptiveAssessmentSession.student_user_id == session.user_id,
            AdaptiveAssessmentSession.course_id == session.course_id,
            AdaptiveAssessmentSession.block_id == block_id,
            AdaptiveAssessmentSession.kc_id == kc_id,
            AdaptiveAssessmentSession.mode == mode,
        )
        .with_for_update()
    )
    if row:
        state = json.loads(row.state_json)
        state["checkpoint_seed"] = row.id
        set_changed = mode == "learning" and state.get("assessment_set_id") != assessment_set_id
        stages_changed = mode == "learning" and state.get("checkpoint_stages") != configured_stages
        if stages_changed or set_changed:
            # A teacher-approved sequence change invalidates the old position.
            # A different question set for the same KC must also start a clean
            # conversation rather than borrowing an item from the old set.
            state.update(
                status="active",
                stage=configured_stages[0],
                checkpoint_stages=configured_stages,
                assessment_set_id=assessment_set_id,
                used=[],
                seen_questions=[],
                dimensions={},
                evidence_ids=[],
                receipts={},
                generated_items={},
                attempts=0,
                item_id=None,
            )
            for key in ("last_result", "review", "coverage_gap", "delayed_probe"):
                state.pop(key, None)
            await assign(state, bank, kc_id)
        elif mode == "learning" and not state.get("checkpoint_stages"):
            state["checkpoint_stages"] = configured_stages
            if state.get("status") == "coverage_gap":
                state["stage"] = configured_stages[0]
        if design.get("mode") == "fixed":
            state["preferred_item_id"] = seed["assessment_id"]
        if not stages_changed and restart and state["status"] in {"stopped", "review_required"}:
            state["status"] = "active"
            if state.get("item_id"):
                state["used"].append(state["item_id"])
                old_item = next(
                    (item for item in checkpoint_bank(bank, state) if item["assessment_id"] == state["item_id"]), None
                )
                if old_item:
                    state.setdefault("seen_questions", []).append(question_fingerprint(old_item))
            await assign(state, bank, kc_id)
        if not stages_changed and state["status"] == "coverage_gap":
            state["status"] = "active"
            await assign(state, bank, kc_id)
        elif not stages_changed and state["status"] in {"active", "needs_support", "verification_required"}:
            current = next(
                (item for item in checkpoint_bank(bank, state) if item["assessment_id"] == state.get("item_id")), None
            )
            if not current or current["rubric_version"] != state.get("item_version"):
                # Do not carry stale success/attempts into a changed rubric.
                state["status"] = "active"
                state["dimensions"] = {}
                state["stage"] = state.get("checkpoint_stages", list(STAGES))[0] if mode == "learning" else state["stage"]
                state["used"] = [] if mode == "learning" else state["used"]
                state["generated_items"] = {}
                await assign(state, bank, kc_id)
        save(row, state)
        audit_question(db, session, settings, row, state, bank)
        return public_state(row, state, bank)
    row = AdaptiveAssessmentSession(
        id=f"AS-{uuid.uuid4().hex[:20]}",
        institution_id=settings.institution_id,
        student_user_id=session.user_id,
        course_id=session.course_id,
        block_id=block_id,
        kc_id=kc_id,
        mode=mode,
    )
    baseline = json.loads(probe.payload_json) if probe else {}
    state = {
        "checkpoint_seed": row.id,
        "assessment_set_id": assessment_set_id,
        "status": "active",
        "stage": baseline.get("stage", configured_stages[0]),
        "checkpoint_stages": baseline.get("checkpoint_stages", configured_stages),
        "preferred_item_id": seed["assessment_id"] if design.get("mode") == "fixed" else None,
        "used": baseline.get("used", []),
        "seen_questions": baseline.get("seen_questions", []),
        "dimensions": baseline.get("dimensions", {}),
        "evidence_ids": [],
        "receipts": {},
        "probe_id": probe.id if probe else None,
        "baseline_evidence_id": probe.baseline_evidence_id if probe else None,
    }
    await assign(state, bank, kc_id)
    save(row, state)
    db.add(row)
    db.flush()
    audit(db, session, settings, "ASSESSMENT_STARTED", row.id, row.id, {"mode": mode, "kc_id": kc_id})
    audit_question(db, session, settings, row, state, bank)
    return public_state(row, state, bank)


def add_hint(
    db: Session,
    session: SessionContext,
    settings: Settings,
    row: AdaptiveAssessmentSession,
    state: dict,
    bank: list[dict],
    key: str,
) -> dict:
    cached = receipt(state, key, "hint")
    if cached:
        return cached
    item = current_item(state, bank)
    level = min(5, state.get("hint_level", 0) + 1)
    approved_hints = item.get("hints") or []
    specific = str(approved_hints[level - 1]) if len(approved_hints) >= level else ""
    state.update(hint_level=level, hint=f"H{level}: {HINTS[level - 1]}" + (f"\n{specific}" if specific else ""))
    audit(
        db,
        session,
        settings,
        "HINT_REQUESTED",
        row.id,
        f"{row.id}:{key}",
        {"assessment_id": item["assessment_id"], "hint_level": level},
    )
    response = public_state(row, state, bank)
    remember(state, key, "hint", response)
    save(row, state)
    return response


def resolve_verified_reviews(
    db: Session,
    session: SessionContext,
    settings: Settings,
    row: AdaptiveAssessmentSession,
    state: dict,
    evidence: dict,
) -> list[str]:
    """New independent evidence resolves uncertainty, not a teacher decision.

    Scope to this exact checkpoint and stage. Never re-grade historical evidence
    or mark an untested dimension passed; the accepted new evidence stands alone.
    """
    if (
        not evidence.get("can_update_knowledge")
        or evidence.get("hint_level")
        or evidence.get("dimensions", {}).get(DIMENSION[state["stage"]]) != "passed"
    ):
        return []
    cases = db.scalars(
        select(AgentReviewCase)
        .where(
            AgentReviewCase.institution_id == settings.institution_id,
            AgentReviewCase.student_user_id == session.user_id,
            AgentReviewCase.course_id == session.course_id,
            AgentReviewCase.case_type == "understanding_review",
            AgentReviewCase.status.in_(("pending", "in_review", "needs_evidence")),
        )
        .with_for_update()
    ).all()
    resolved = []
    for case in cases:
        payload = json.loads(case.payload_json)
        context = payload.get("assessment_review") or {}
        if context.get("checkpoint_id") != row.id or context.get("stage") != state["stage"]:
            continue
        case.status = "superseded"
        payload["resolution"] = {
            "reason": "new_independent_evidence",
            "evidence_id": evidence["id"],
            "resolved_at": now_utc().isoformat(),
        }
        payload["instructor_note"] = "Đã có bằng chứng độc lập mới; không tự duyệt kết luận cũ."
        case.payload_json = json.dumps(payload, ensure_ascii=False)
        audit(db, session, settings, "ASSESSMENT_REVIEW_SUPERSEDED", case.id, evidence["id"], payload["resolution"])
        resolved.append(case.id)
    return resolved


async def advance(
    db: Session,
    session: SessionContext,
    settings: Settings,
    row: AdaptiveAssessmentSession,
    state: dict,
    bank: list[dict],
    result: dict,
    answer: str,
    key: str,
) -> dict:
    item = current_item(state, bank)
    state["previous_answer"] = answer[:1500]
    state["attempts"] = state.get("attempts", 0) + 1
    assessment = result.get("assessment_result") or {}
    rubric_labels = {
        str(criterion.get("criterion_id")): str(
            criterion.get("name") or criterion.get("description") or criterion.get("criterion_id")
        )
        for criterion in item.get("approved_rubric") or []
        if criterion.get("criterion_id")
    }
    criterion_scores = [
        {**score, "criterion_text": rubric_labels.get(str(score.get("criterion_id")), str(score.get("criterion_id") or ""))}
        for score in assessment.get("criterion_scores") or []
        if isinstance(score, dict)
    ]
    evidence = (result.get("output") or {}).get("learning_evidence") or {}
    decision = result.get("assessment_review") or {}
    resolved = (
        resolve_verified_reviews(db, session, settings, row, state, evidence)
        if decision.get("status") == "accepted"
        else []
    )
    state["review"] = {
        **decision,
        "resolved_case_ids": resolved,
        "case_id": (result.get("output") or {}).get("review_case_id"),
    }
    state["last_result"] = {
        "feedback": result.get("response"),
        "status": assessment.get("status"),
        "confidence": evidence.get("confidence", "low"),
        "demonstrated_level": evidence.get("demonstrated_level", "no_evidence"),
        "provisional": decision.get("status") != "accepted" if decision else not evidence.get("can_update_knowledge"),
        "criterion_scores": criterion_scores,
        "evidence_ids": assessment.get("evidence_ids") or [],
        "requires_instructor_review": decision.get("status") == "pending_review"
        if decision
        else result.get("status") == "awaiting_teacher",
    }
    accepted = evidence.get("valid") and evidence.get("confidence") in {"medium", "high"}
    if not accepted:
        result = {**result, "status": "awaiting_teacher"}
        state["last_result"]["requires_instructor_review"] = (
            decision.get("status") == "pending_review" if decision else True
        )
    if item.get("formative_only"):
        state["used"].append(item["assessment_id"])
        state.setdefault("seen_questions", []).append(question_fingerprint(item))
        state.update(status="verification_required", reason="formative_requires_approved_anchor", force_anchor=True)
        await assign(state, bank, row.kc_id)
    elif decision.get("status") in {"verifying", "pending_review", "abstained"}:
        audit(
            db,
            session,
            settings,
            "ASSESSMENT_REVIEW_DECIDED",
            row.id,
            f"review:{key}",
            {**decision, "evidence_id": evidence.get("id")},
        )
        if decision["status"] == "verifying":
            state["used"].append(item["assessment_id"])
            state.setdefault("seen_questions", []).append(question_fingerprint(item))
            state["verification_count"] = state.get("verification_count", 0) + 1
            state.update(status="verification_required", reason=decision["reason"])
            await assign(state, bank, row.kc_id)
        else:
            state.update(
                status="review_required" if decision["status"] == "pending_review" else "stopped",
                reason=decision["reason"],
            )
    elif row.mode == "retention":
        probe = db.get(DelayedAssessmentProbe, state["probe_id"])
        passed = evidence.get("retention_status") == "passed"
        if accepted and result.get("status") != "awaiting_teacher":
            probe.status = "passed" if passed else "failed"
            state.update(status="completed", reason="retention_passed" if passed else "retention_not_demonstrated")
        else:
            state.update(status="review_required", reason="insufficient_retention_evidence")
    else:
        step = next_step(
            state["stage"],
            result,
            hint_level=state.get("hint_level", 0),
            attempts=state["attempts"],
            stages=state.get("checkpoint_stages") or STAGES,
        )
        if step["status"] in {"active", "completed"}:
            state["dimensions"][DIMENSION[state["stage"]]] = "passed"
            state["evidence_ids"].extend(assessment.get("evidence_ids") or [])
        if step["status"] in {"active", "completed", "verification_required"}:
            state["used"].append(item["assessment_id"])
            state.setdefault("seen_questions", []).append(question_fingerprint(item))
        state.update(step)
        if state["status"] in {"active", "verification_required"}:
            await assign(state, bank, row.kc_id)
        if (
            evidence.get("can_update_knowledge")
            and not evidence.get("hint_level")
            and evidence.get("demonstrated_level") in {"application", "transfer"}
        ):
            existing = db.scalar(
                select(DelayedAssessmentProbe).where(DelayedAssessmentProbe.baseline_evidence_id == evidence["id"])
            )
            if not existing:
                pending = db.scalars(
                    select(DelayedAssessmentProbe).where(
                        DelayedAssessmentProbe.institution_id == settings.institution_id,
                        DelayedAssessmentProbe.student_user_id == session.user_id,
                        DelayedAssessmentProbe.course_id == session.course_id,
                        DelayedAssessmentProbe.kc_id == row.kc_id,
                        DelayedAssessmentProbe.status == "pending",
                    )
                ).all()
                for older in pending:
                    older.status = "superseded"
                due_at = now_utc() + timedelta(hours=settings.assessment_retention_delay_hours)
                probe = DelayedAssessmentProbe(
                    id=f"DP-{uuid.uuid4().hex[:20]}",
                    institution_id=settings.institution_id,
                    student_user_id=session.user_id,
                    course_id=session.course_id,
                    kc_id=row.kc_id,
                    baseline_evidence_id=evidence["id"],
                    due_at=due_at,
                    payload_json=json.dumps(
                        {
                            "stage": item_stage(item),
                            "dimensions": state["dimensions"],
                            "used": state["used"],
                            "seen_questions": state.get("seen_questions", []),
                        }
                    ),
                )
                db.add(probe)
                state["delayed_probe"] = {"id": probe.id, "due_at": due_at.isoformat(), "status": "pending"}
    audit_question(db, session, settings, row, state, bank)
    response = public_state(row, state, bank)
    remember(state, key, f"answer:{answer}", response)
    save(row, state)
    return response
