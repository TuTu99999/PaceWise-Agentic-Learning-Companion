"""Bounded verification for plan signals without per-answer human review."""

from __future__ import annotations

from src.services.assessment_policy import DIMENSION, question_fingerprint, select_item

POLICY_VERSION = "assessment-signal-v2"
MAX_VERIFICATION_QUESTIONS = 2
UNCONFIRMED = {"verifying", "pending_review", "abstained"}


def planning_evidence_usable(evidence: dict) -> bool:
    """Confidence alone must not promote an unconfirmed model conclusion."""
    return bool(
        evidence.get("valid")
        and evidence.get("confidence") in {"medium", "high"}
        and evidence.get("review_status") not in UNCONFIRMED
        and not evidence.get("provisional", False)
        and (
            not ({"can_update_knowledge", "can_record_observation"} & evidence.keys())
            or evidence.get("can_update_knowledge")
            or evidence.get("can_record_observation")
        )
    )


def review_decision(state: dict, result: dict, evidence: dict, bank: list[dict], kc_id: str) -> dict:
    assessment = result.get("assessment_result") or {}
    demonstrated = assessment.get("status") in {"đã thể hiện được", "đang hình thành", "demonstrated", "developing"}
    contradictory = (assessment.get("dimensions") or {}).get(DIMENSION[state["stage"]]) == "passed" and not demonstrated
    uncertain = contradictory or result.get("status") == "awaiting_teacher" or not planning_evidence_usable(evidence)
    base = {"policy_version": POLICY_VERSION, "blocks_learning": False, "blocks_planning": False}
    if not uncertain:
        return {**base, "status": "accepted", "reason": "grounded_evidence"}
    # Malformed grading/source metadata is an evaluator failure, not a student
    # deficit. Keep the evidence for audit but do not send fabricated diagnoses.
    incomplete = not evidence.get("valid")
    if incomplete and not (result.get("assessment_result") or {}).get("criterion_scores"):
        return {**base, "status": "abstained", "reason": "invalid_evaluation"}
    used = [*state.get("used", []), state.get("item_id")]
    current = next((item for item in bank if item["assessment_id"] == state.get("item_id")), {})
    seen = [*state.get("seen_questions", []), question_fingerprint(current)]
    candidate = select_item(bank, kc_id, state["stage"], used, seen)
    if state.get("verification_count", 0) < MAX_VERIFICATION_QUESTIONS and candidate:
        return {
            **base,
            "status": "verifying",
            "reason": "contradictory_evaluation" if contradictory else "uncertain_evidence",
            "next_item_id": candidate["assessment_id"],
        }
    if incomplete:
        return {**base, "status": "abstained", "reason": "insufficient_evidence"}
    return {
        **base,
        "status": "abstained",
        "reason": "verification_limit" if candidate else "no_unseen_approved_item",
    }
