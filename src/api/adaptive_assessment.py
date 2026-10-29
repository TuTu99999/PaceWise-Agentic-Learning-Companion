"""Adaptive Assessment endpoints belonging to Do, with no separate product phase."""

import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from src.agents.guardrails import evaluate_guardrails
from src.agents.safety import enforce_output_policy
from src.agents.workflows.understanding import understanding_node
from src.config import Settings, get_settings
from src.db import get_db
from src.persistence_models import DelayedAssessmentProbe, InstructorAction, LearningEvidenceRecord
from src.security import SessionContext, get_current_session, require_csrf
from src.services import adaptive_assessment as adaptive
from src.services.agent_memory import load_learner_memory, persist_agent_outcome
from src.services.ai_rate_limit import ai_request_slot
from src.services.assessment_policy import DIMENSION
from src.services.assessment_review_policy import MAX_VERIFICATION_QUESTIONS, review_decision
from src.services.learning_evidence import build_evidence_contract
from src.services.misconception_diagnosis import diagnose
from src.services.question_design import generate_candidate, instance_bank

router = APIRouter(prefix="/do/assessment", tags=["Do checkpoints"])


class StartRequest(BaseModel):
    course_id: int = Field(gt=0)
    block_id: str = Field(min_length=1, max_length=128)
    assessment_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    probe_id: str | None = Field(default=None, max_length=64)
    restart: bool = False


class AttemptRequest(BaseModel):
    course_id: int = Field(gt=0)
    event_key: str = Field(min_length=1, max_length=128)
    answer: str = Field(default="", max_length=5000)
    locale: Literal["vi", "en"] = "vi"


def _scope(session: SessionContext, course_id: int) -> SessionContext:
    if session.role != "student" or course_id not in session.course_ids:
        raise HTTPException(status_code=403, detail="Student enrollment is required for this course")
    return replace(session, course_id=course_id)


@router.post("/start")
async def start_checkpoint(
    payload: StartRequest,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    scoped = _scope(session, payload.course_id)
    try:
        response = await adaptive.start(
            db,
            scoped,
            settings,
            block_id=payload.block_id,
            assessment_id=payload.assessment_id,
            probe_id=payload.probe_id,
            restart=payload.restart,
        )
    except IntegrityError:
        # Two browser mounts may race to create the same scoped session. The
        # unique scope is authoritative; reload it instead of duplicating it.
        db.rollback()
        response = await adaptive.start(
            db,
            scoped,
            settings,
            block_id=payload.block_id,
            assessment_id=payload.assessment_id,
            probe_id=payload.probe_id,
        )
    db.commit()
    return response


@router.get("/due")
def due_probes(
    course_id: int,
    session: SessionContext = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    scoped = _scope(session, course_id)
    probes = db.scalars(
        select(DelayedAssessmentProbe)
        .where(
            DelayedAssessmentProbe.institution_id == settings.institution_id,
            DelayedAssessmentProbe.student_user_id == scoped.user_id,
            DelayedAssessmentProbe.course_id == scoped.course_id,
            DelayedAssessmentProbe.status == "pending",
            DelayedAssessmentProbe.due_at <= adaptive.now_utc(),
        )
        .order_by(DelayedAssessmentProbe.due_at)
        .limit(50)
    ).all()
    return [
        {"id": probe.id, "kc_id": probe.kc_id, "due_at": adaptive.utc(probe.due_at).isoformat()} for probe in probes
    ]


@router.post("/{session_id}/hint")
async def request_hint(
    session_id: str,
    payload: AttemptRequest,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    scoped = _scope(session, payload.course_id)
    bank = await adaptive.approved_bank(db, scoped, settings)
    row, state = adaptive.scoped_checkpoint(db, scoped, settings, session_id)
    response = adaptive.add_hint(db, scoped, settings, row, state, bank, payload.event_key)
    db.commit()
    return response


def _taxonomy(db: Session, course_id: int, kc_id: str) -> list[str]:
    row = db.scalar(
        select(InstructorAction)
        .where(InstructorAction.course_id == course_id, InstructorAction.action_type == "course_structure")
        .order_by(InstructorAction.created_at.desc())
    )
    payload = json.loads(row.payload_json) if row else {}
    components = payload.get("knowledgeComponents") or []
    return next(
        (
            item.get("misconceptions") or []
            for item in components
            if item.get("id") == kc_id and item.get("status") == "approved"
        ),
        [],
    )


@router.post("/{session_id}/answer")
async def submit_answer(
    session_id: str,
    payload: AttemptRequest,
    request: Request,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    scoped = _scope(session, payload.course_id)
    answer = payload.answer.strip()
    if not answer:
        raise HTTPException(status_code=422, detail="Answer is required")
    bank = await adaptive.approved_bank(db, scoped, settings)
    row, state = adaptive.scoped_checkpoint(db, scoped, settings, session_id)
    cached = adaptive.receipt(state, payload.event_key, f"answer:{answer}")
    if cached:
        return cached
    bank = instance_bank(bank, state)
    item = adaptive.current_item(state, bank)
    guardrail = evaluate_guardrails(answer)
    if guardrail.get("action") == "block":
        raise HTTPException(status_code=422, detail="Answer contains unsafe instructions")
    memory = load_learner_memory(db, scoped, settings)
    result = None
    if not item.get("formative_only"):
        admission = SimpleNamespace(
            workflow="understanding",
            context={"assessment_id": item["assessment_id"], "do_block_id": row.block_id},
        )
        async with ai_request_slot(admission, request, scoped, settings):
            result = await run_in_threadpool(
                understanding_node,
                {
                    "query": answer,
                    "approved_rubric": item["approved_rubric"],
                    "mastery_profile": memory["mastery"],
                    "misconceptions": memory["misconceptions"],
                    "request": {
                        "question": item["question"],
                        "question_type": item["question_type"],
                        "answer_type": item["answer_type"],
                        "correct_answer": item["correct_answer"],
                        "assessment_stage": state["stage"],
                        "expected_facts": item.get("expected_facts") or {},
                        "locale": payload.locale,
                        "planning_signal_only": True,
                    },
                },
            )
    if result is None:
        result = {
            "response": (
                "Your formative answer was saved. This AI-generated question is not verified and cannot raise your understanding level; continue with an approved question."
                if payload.locale == "en"
                else "Đã lưu câu trả lời tham khảo. Câu AI này chưa được xác thực nội dung nên không dùng để nâng mức hiểu; hãy kiểm chứng bằng câu đã duyệt."
            ),
            "status": "completed",
            "assessment_result": {
                "status": "chưa đủ bằng chứng",
                "confidence": "Thấp",
                "evidence_quotes": [answer],
                "dimensions": {},
                "evaluator_version": "formative-record-v1",
            },
        }
    if (result.get("output") or {}).get("model_status") == "unavailable":
        # An infrastructure failure is not evidence about the learner. Keep
        # this item and retry key available without consuming an attempt.
        adaptive.audit(
            db,
            scoped,
            settings,
            "ASSESSMENT_UNAVAILABLE",
            row.id,
            key=f"unavailable:{row.id}:{payload.event_key}",
            payload={"session_id": row.id, "error_type": (result.get("output") or {}).get("model_error_type")},
        )
        db.commit()
        raise HTTPException(
            status_code=503,
            detail=(
                "The AI assessment service did not respond. Your answer was not graded; please try again."
                if payload.locale == "en"
                else "AI đánh giá chưa phản hồi. Câu trả lời chưa bị chấm; hãy thử gửi lại."
            ),
        )
    assessment = result.get("assessment_result") or {}
    # Only prior accepted, unhinted checkpoints within this exact KC session
    # establish prerequisites. The LLM cannot invent other passed dimensions.
    current_dimension = DIMENSION[state["stage"]]
    current_value = (assessment.get("dimensions") or {}).get(current_dimension, "not_tested")
    dimensions = {
        **dict.fromkeys(("recall", "conceptual", "reasoning", "application", "transfer", "retention"), "not_tested"),
        **state.get("dimensions", {}),
        current_dimension: current_value,
    }
    trusted = {**item, "knowledge_component_ids": [row.kc_id]}
    if row.mode == "retention":
        probe = db.get(DelayedAssessmentProbe, state["probe_id"])
        baseline = db.get(LearningEvidenceRecord, state["baseline_evidence_id"])
        validated = bool(
            probe
            and baseline
            and probe.status == "pending"
            and adaptive.now_utc() >= adaptive.utc(probe.due_at)
            and baseline.institution_id == settings.institution_id
            and baseline.student_user_id == scoped.user_id
            and baseline.course_id == scoped.course_id
            and row.kc_id in json.loads(baseline.payload_json).get("knowledge_component_ids", [])
            and item["assessment_id"] != baseline.assessment_id
        )
        if not validated:
            raise HTTPException(status_code=409, detail="Retention baseline/due date is invalid")
        dimensions["retention"] = "passed" if current_value == "passed" and not state.get("hint_level") else "failed"
        trusted["retention_context"] = {
            "validated": True,
            "baseline_evidence_id": baseline.id,
            "baseline_level": json.loads(baseline.payload_json).get("demonstrated_level"),
            "probe_id": probe.id,
            "due_at": adaptive.utc(probe.due_at).isoformat(),
        }
    assessment["dimensions"] = dimensions
    assessment["rubric_version"] = item["rubric_version"]
    diagnosis = diagnose(
        assessment.get("misconceptions") or [],
        _taxonomy(db, scoped.course_id, row.kc_id),
        answer=answer,
        kc_id=row.kc_id,
        evidence_ids=[],
    )
    assessment["misconceptions"] = diagnosis["candidates"]
    if diagnosis["requires_teacher_review"]:
        result["status"] = "awaiting_teacher"
        result["pending_action"] = {"workflow": "do", "type": "misconception_review", "payload": diagnosis}
    result.update(
        workflow="do",
        query=answer,
        assessment_result=assessment,
        _trusted_assessment=trusted,
        do_session={"action": "assess"},
        request={
            "topic": item["topic"],
            "assessment_attempt": {
                "block_id": row.block_id,
                "response": answer,
                "hint_level": state.get("hint_level", 0),
                "first_attempt": not state.get("attempts") and not state.get("hint_level"),
                "event_key": f"{row.id}:{payload.event_key}",
            },
        },
        source_refs=[{"id": item["assessment_id"], "citation": item["source"]}],
    )
    result["response"], _ = enforce_output_policy(str(result.get("response") or ""), input_decision=guardrail)
    preview = build_evidence_contract(
        session=scoped,
        settings=settings,
        result=result,
        assessment_id=item["assessment_id"],
        trusted_assessment=trusted,
    )
    decision = review_decision(state, result, preview, bank, row.kc_id)
    if (
        decision["status"] == "pending_review"
        and state.get("verification_count", 0) < MAX_VERIFICATION_QUESTIONS
        and not item.get("formative_only")
    ):
        candidate = await run_in_threadpool(generate_candidate, state, bank, row.kc_id, row.id)
        if candidate and not candidate.get("formative_only"):
            bank.append(candidate)
            state["_next_candidate"] = candidate
            decision = review_decision(state, result, preview, bank, row.kc_id)
    decision.update(checkpoint_id=row.id, stage=state["stage"])
    result["assessment_review"] = decision
    # Student answers are planning signals, not instructor review work. Uncertain
    # evidence is verified with another approved item and otherwise left unknown.
    if decision["status"] != "accepted":
        result["status"] = "completed"
        result["_defer_human_review"] = True
        result["response"] = (
            "Your answer was recorded as an unconfirmed planning signal."
            if payload.locale == "en"
            else "Đã ghi nhận câu trả lời như một tín hiệu kế hoạch chưa xác định."
        )
    persist_agent_outcome(db, scoped, settings, result, item["assessment_id"], commit=False)
    response = await adaptive.advance(db, scoped, settings, row, state, bank, result, answer, payload.event_key)
    db.commit()
    return response
