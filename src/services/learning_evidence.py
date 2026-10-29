"""Evidence contracts and deterministic Knowledge State derivation."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings
from src.persistence_models import KnowledgeStateSnapshot, LearningEvent, LearningEvidenceRecord
from src.security import SessionContext

EVIDENCE_SCHEMA_VERSION = "learning-evidence-v2"
KNOWLEDGE_STATE_VERSION = "knowledge-state-v2"
LEVELS = ("no_evidence", "recognition", "conceptual", "application", "transfer", "retained")
_STATUS_MAP = {
    "đã thể hiện được": "demonstrated",
    "đang hình thành": "developing",
    "còn nhầm lẫn": "misconception",
    "chưa đủ bằng chứng": "insufficient_evidence",
    "demonstrated": "demonstrated",
    "developing": "developing",
    "misconception": "misconception",
    "abstained": "insufficient_evidence",
    "insufficient_evidence": "insufficient_evidence",
}


def _stable_key(*parts: object) -> str:
    value = "\x1f".join(str(part or "") for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _confidence(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized in {"cao", "high", "teacher_confirmed"}:
        return "high"
    if normalized in {"trung bình", "trung binh", "medium"}:
        return "medium"
    return "low"


def _status(value: Any) -> str:
    return _STATUS_MAP.get(str(value or "").strip().casefold(), "insufficient_evidence")


def _knowledge_components(trusted: dict[str, Any], assessment_id: str) -> tuple[list[str], bool]:
    raw = trusted.get("knowledge_component_ids") or trusted.get("knowledge_components") or []
    if isinstance(raw, str):
        raw = [raw]
    values = [str(item).strip() for item in raw if str(item).strip()]
    if values:
        return list(dict.fromkeys(values)), bool(trusted.get("kc_provisional"))
    return [f"unmapped:{assessment_id}"], True


def _highest_level(
    assessment: dict[str, Any],
    trusted: dict[str, Any],
    *,
    hint_level: int,
) -> str:
    status = _status(assessment.get("status"))
    if status not in {"demonstrated", "developing"}:
        return "no_evidence"
    dimensions = assessment.get("dimensions") or {}
    dimensions = dimensions if isinstance(dimensions, dict) else {}
    passed = {
        str(name).casefold()
        for name, value in dimensions.items()
        if str(value).casefold() in {"passed", "pass", "true", "đạt", "dat"}
    }
    closed = str(trusted.get("answer_type") or trusted.get("question_type") or "open") != "open"
    if closed:
        return "recognition" if "recall" in passed else "no_evidence"
    if {"conceptual", "reasoning", "application", "transfer"} <= passed and not hint_level:
        level = "transfer"
    elif {"conceptual", "reasoning", "application"} <= passed:
        level = "application"
    elif "conceptual" in passed:
        level = "conceptual"
    elif "recall" in passed:
        # Recall-only evidence cannot inherit a higher cognitive label from the
        # item metadata. A correct closed answer is recognition, not proof of
        # explanation, application or transfer.
        level = "recognition"
    else:
        level = "no_evidence"
    if hint_level >= 4 and LEVELS.index(level) > LEVELS.index("conceptual"):
        level = "conceptual"
    retention = trusted.get("retention_context") or {}
    if ("retention" in passed and retention.get("validated") is True
            and retention.get("baseline_evidence_id") and not hint_level
            and level in {"application", "transfer"}):
        level = "retained"
    return level


def build_evidence_contract(
    *,
    session: SessionContext,
    settings: Settings,
    result: dict[str, Any],
    assessment_id: str,
    trusted_assessment: dict[str, Any],
) -> dict[str, Any]:
    assessment = result.get("assessment_result") or {}
    request = result.get("request") or {}
    attempt = request.get("assessment_attempt") or {}
    hint_level = max(0, min(5, int(attempt.get("hint_level") or 0)))
    first_attempt = bool(attempt.get("first_attempt", hint_level == 0))
    block_id = str(attempt.get("block_id") or request.get("block_id") or "")
    response = str(attempt.get("response") or result.get("query") or "")[:5000]
    client_key = str(attempt.get("event_key") or "").strip() or _stable_key(
        settings.institution_id,
        session.user_id,
        session.course_id,
        assessment_id,
        block_id,
        response,
        hint_level,
        first_attempt,
    )
    # A learner-chosen key must never replay another learner/course's evidence.
    event_key = _stable_key(settings.institution_id, session.user_id, session.course_id, client_key)
    evidence_quotes = [
        str(value).strip()[:1000]
        for value in assessment.get("evidence_quotes") or []
        if str(value).strip() and " ".join(str(value).casefold().split()) in " ".join(response.casefold().split())
    ][:5]
    knowledge_components, provisional = _knowledge_components(trusted_assessment, assessment_id)
    status = _status(assessment.get("status"))
    confidence = _confidence(assessment.get("confidence"))
    raw_dimensions = assessment.get("dimensions") or {}
    dimensions = ({str(key): str(value).casefold() for key, value in raw_dimensions.items()}
                  if isinstance(raw_dimensions, dict) else {})
    level = _highest_level(assessment, trusted_assessment, hint_level=hint_level)
    valid = bool(
        evidence_quotes
        and trusted_assessment.get("rubric_version")
        and assessment.get("evaluator_version")
        and status != "insufficient_evidence"
        and isinstance(raw_dimensions, dict)
        and all(value in {"passed", "failed", "developing", "not_tested"} for value in dimensions.values())
        and not trusted_assessment.get("formative_only")
    )
    if not valid:
        status = "insufficient_evidence"
        level = "no_evidence"
    review_status = (result.get("assessment_review") or {}).get(
        "status", "pending_review" if result.get("status") == "awaiting_teacher" else "accepted"
    )
    can_update_knowledge = bool(
        valid
        and not provisional
        and confidence in {"medium", "high"}
        and result.get("status") != "awaiting_teacher"
        and review_status == "accepted"
        and level != "no_evidence"
    )
    can_record_observation = bool(
        valid and not provisional and confidence in {"medium", "high"}
        and result.get("status") != "awaiting_teacher"
        and review_status == "accepted"
        and any(value in {"passed", "failed"} for value in dimensions.values())
    )
    criterion_scores = [item for item in assessment.get("criterion_scores") or [] if isinstance(item, dict)]
    scored_criteria = [
        item
        for item in criterion_scores
        if type(item.get("score")) is int and 0 <= item["score"] <= 4
    ]
    passed_criteria = sum(1 for item in scored_criteria if item["score"] >= 3)
    failed_criteria = sum(1 for item in scored_criteria if item["score"] < 3)
    planning_metrics = {
        "outcome": status,
        "confidence": confidence,
        "tested_dimensions": sorted(key for key, value in dimensions.items() if value != "not_tested"),
        "passed_dimensions": sorted(key for key, value in dimensions.items() if value == "passed"),
        "failed_dimensions": sorted(key for key, value in dimensions.items() if value == "failed"),
        "criterion_count": len(scored_criteria),
        "passed_criterion_count": passed_criteria,
        "failed_criterion_count": failed_criteria,
        "first_attempt": first_attempt,
        "hint_level": hint_level,
        "support_condition": "with_in_app_hint" if hint_level else "without_in_app_hint",
        "review_status": review_status,
        "usable_for_planning": bool(can_update_knowledge or can_record_observation),
    }
    return {
        "id": f"LE-{uuid.uuid4().hex[:20]}",
        "event_key": event_key,
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "evaluator_version": str(assessment.get("evaluator_version")),
        "assessment_id": assessment_id,
        "block_id": block_id,
        "item_type": str(
            trusted_assessment.get("answer_type")
            or trusted_assessment.get("question_type")
            or "open"
        ),
        "rubric_version": int(trusted_assessment.get("rubric_version") or 0),
        "question_snapshot": str(trusted_assessment.get("question") or "")[:2000],
        "generation": {key: trusted_assessment[key] for key in ("parent_assessment_id", "parent_version", "generation_version", "validation", "formative_only") if key in trusted_assessment},
        "knowledge_component_ids": knowledge_components,
        "kc_provisional": provisional,
        "first_attempt": first_attempt,
        "hint_level": hint_level,
        "response": response,
        "status": status,
        "confidence": confidence,
        "demonstrated_level": level,
        "dimensions": dimensions,
        "criterion_scores": criterion_scores,
        "planning_metrics": planning_metrics,
        "support_condition": "with_in_app_hint" if hint_level else "without_in_app_hint",
        "misconceptions": assessment.get("misconceptions") or [],
        "evidence_quotes": evidence_quotes,
        "source_ref_ids": [str(item.get("id") or item.get("citation") or "") for item in result.get("source_refs") or [] if item],
        "valid": valid,
        "review_status": review_status,
        "can_update_knowledge": can_update_knowledge,
        "can_record_observation": can_record_observation,
        "retention_status": "passed" if level == "retained" else "not_tested",
        "retention_context": trusted_assessment.get("retention_context") or {},
        "retained_level": (trusted_assessment.get("retention_context") or {}).get("baseline_level") if level == "retained" else None,
    }


def persist_learning_evidence(
    db: Session,
    session: SessionContext,
    settings: Settings,
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    existing = db.scalar(
        select(LearningEvidenceRecord).where(
            LearningEvidenceRecord.event_key == contract["event_key"]
        )
    )
    if existing:
        payload = json.loads(existing.payload_json or "{}")
        for field in ("assessment_id", "block_id", "response", "hint_level"):
            if payload.get(field) != contract.get(field):
                raise HTTPException(status_code=409, detail="Evidence retry key was reused with different content")
        snapshots = db.scalars(
            select(KnowledgeStateSnapshot).where(
                KnowledgeStateSnapshot.evidence_id == existing.id
            )
        ).all()
        return payload, [json.loads(item.payload_json or "{}") for item in snapshots]

    payload = dict(contract)
    payload["misconceptions"] = [
        {**item, "evidence_ids": [contract["id"]]}
        for item in contract.get("misconceptions") or [] if isinstance(item, dict)
    ]
    record = LearningEvidenceRecord(
        id=contract["id"],
        event_key=contract["event_key"],
        schema_version=contract["schema_version"],
        evaluator_version=contract["evaluator_version"],
        institution_id=settings.institution_id,
        course_id=session.course_id,
        student_user_id=session.user_id,
        assessment_id=contract["assessment_id"],
        block_id=contract["block_id"],
        item_type=contract["item_type"],
        first_attempt=int(contract["first_attempt"]),
        hint_level=contract["hint_level"],
        valid=int(contract["valid"]),
        response_text=contract["response"],
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    db.add(record)
    db.flush()
    snapshots: list[dict[str, Any]] = []
    if contract["can_update_knowledge"] or contract.get("can_record_observation"):
        for knowledge_component_id in contract["knowledge_component_ids"]:
            previous = db.scalar(
                select(KnowledgeStateSnapshot)
                .where(
                    KnowledgeStateSnapshot.institution_id == settings.institution_id,
                    KnowledgeStateSnapshot.course_id == session.course_id,
                    KnowledgeStateSnapshot.student_user_id == session.user_id,
                    KnowledgeStateSnapshot.knowledge_component_id == knowledge_component_id,
                )
                .order_by(KnowledgeStateSnapshot.created_at.desc())
            )
            previous_payload = json.loads(previous.payload_json or "{}") if previous else {}
            observed_dimensions = {key: value for key, value in contract["dimensions"].items()
                                   if value in {"passed", "failed"}}
            dimensions = {**previous_payload.get("dimensions", {}), **observed_dimensions}
            unresolved = set(previous_payload.get("unresolved_dimensions") or [])
            for dimension, outcome in observed_dimensions.items():
                if outcome == "failed":
                    unresolved.add(dimension)
                else:
                    unresolved.discard(dimension)
            previous_level = previous_payload.get("level", "no_evidence")
            demonstrated_level = contract["demonstrated_level"]
            if previous_level in LEVELS and LEVELS.index(previous_level) > LEVELS.index(demonstrated_level):
                # Preserve what was demonstrated historically, while exposing
                # new failures explicitly instead of silently erasing them.
                demonstrated_level = previous_level
            source_evidence_ids = list(
                dict.fromkeys(
                    [
                        *(
                            str(value)
                            for value in previous_payload.get("source_evidence_ids") or []
                            if str(value)
                        ),
                        record.id,
                    ]
                )
            )
            snapshot_payload = {
                "schema_version": KNOWLEDGE_STATE_VERSION,
                "student_id": str(session.user_id),
                "knowledge_component": knowledge_component_id,
                "level": demonstrated_level,
                "confidence": contract["confidence"],
                "evidence_count": int(previous_payload.get("evidence_count") or 0) + 1,
                "misconceptions": payload["misconceptions"],
                "retention_status": contract["retention_status"],
                "source_evidence_ids": source_evidence_ids,
                "support_condition": contract["support_condition"],
                "criterion_scores": contract["criterion_scores"],
                "dimensions": dimensions,
                "unresolved_dimensions": sorted(unresolved),
                "latest_observed_level": contract["demonstrated_level"],
                "retained_level": contract["retained_level"] or previous_payload.get("retained_level"),
                "last_retention_assessed_at": (
                    record.created_at.isoformat() if contract["retention_status"] == "passed"
                    else previous_payload.get("last_retention_assessed_at")
                ),
                "last_assessed_at": record.created_at.isoformat() if record.created_at else None,
            }
            db.add(
                KnowledgeStateSnapshot(
                    id=f"KS-{uuid.uuid4().hex[:20]}",
                    institution_id=settings.institution_id,
                    course_id=session.course_id,
                    student_user_id=session.user_id,
                    knowledge_component_id=knowledge_component_id,
                    level=demonstrated_level,
                    confidence=contract["confidence"],
                    retention_status=contract["retention_status"],
                    evidence_id=record.id,
                    payload_json=json.dumps(snapshot_payload, ensure_ascii=False),
                )
            )
            snapshots.append(snapshot_payload)
    if snapshots:
        db.add(LearningEvent(
            id=f"EV-{uuid.uuid4().hex[:20]}", event_key=f"{contract['event_key']}:knowledge_updated",
            institution_id=settings.institution_id, course_id=session.course_id,
            student_user_id=session.user_id, event_type="KNOWLEDGE_STATE_UPDATED", entity_id=record.id,
            payload_json=json.dumps({"evidence_id": record.id, "kc_ids": contract["knowledge_component_ids"]}),
        ))
    db.add(
        LearningEvent(
            id=f"EV-{uuid.uuid4().hex[:20]}",
            event_key=f"{contract['event_key']}:assessment_completed",
            institution_id=settings.institution_id,
            course_id=session.course_id,
            student_user_id=session.user_id,
            event_type="ASSESSMENT_COMPLETED",
            entity_id=record.id,
            payload_json=json.dumps(
                {
                    "assessment_id": contract["assessment_id"],
                    "valid": contract["valid"],
                    "knowledge_state_updated": bool(snapshots),
                },
                ensure_ascii=False,
            ),
        )
    )
    db.flush()
    return payload, snapshots
