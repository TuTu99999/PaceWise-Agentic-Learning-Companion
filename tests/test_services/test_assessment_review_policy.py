import pytest

from src.services.assessment_review_policy import planning_evidence_usable, review_decision
from src.services.plan_intelligence import mastery_for_component
from src.services.replan_policy import decide_replan, decide_weekly_replan


def _inputs():
    bank = [
        {
            "assessment_id": f"Q-{i}",
            "question": f"Question {i}",
            "assessment_stage": "explain",
            "answer_type": "open",
            "knowledge_component_ids": ["kc"],
        }
        for i in range(4)
    ]
    return (
        {"stage": "explain", "item_id": "Q-0"},
        {"status": "awaiting_teacher"},
        {"valid": True, "confidence": "low"},
        bank,
    )


def test_uncertainty_asks_same_stage_unseen_item_before_staying_unknown():
    state, result, evidence, bank = _inputs()
    decision = review_decision(state, result, evidence, bank, "kc")
    assert decision["status"] == "verifying"
    assert decision["next_item_id"] == "Q-1"
    assert not decision["blocks_planning"] and not decision["blocks_learning"]


def test_two_supplementary_questions_is_a_server_owned_limit():
    state, result, evidence, bank = _inputs()
    state["verification_count"] = 2
    decision = review_decision(state, result, evidence, bank, "kc")
    assert decision["status"] == "abstained"
    assert decision["reason"] == "verification_limit"


def test_evaluator_failure_is_not_a_student_deficit_or_human_review():
    state, result, evidence, bank = _inputs()
    evidence["valid"] = False
    assert review_decision(state, result, evidence, bank, "kc")["status"] == "abstained"
    result["assessment_result"] = {"criterion_scores": [{"score": 1}]}
    assert review_decision(state, result, evidence, bank, "kc")["status"] == "verifying"
    assert review_decision(state, result, evidence, [], "kc")["status"] == "abstained"


@pytest.mark.parametrize("review_status", ["verifying", "pending_review", "abstained"])
def test_pending_evidence_does_not_inflate_estimate_or_trigger_session_weekly_replan(review_status):
    evidence = {
        "valid": True,
        "confidence": "high",
        "review_status": review_status,
        "level": "recognition",
        "dimensions": {"application": "failed"},
        "knowledge_component_ids": ["kc"],
        "misconceptions": [{"status": "confirmed"}],
    }
    assert not planning_evidence_usable(evidence)
    assert mastery_for_component({"kc": evidence}, "kc") is None
    assert decide_replan(signal={}, last_do={}, latest_evidence=evidence)["action"] == "keep"
    assert decide_weekly_replan(signal={}, observations={"assessment_evidence": [evidence]})["action"] == "keep"
    # A real missed session still matters even if assessment is pending.
    assert (
        decide_replan(signal={}, last_do={"status": "missed", "planned_minutes": 60}, latest_evidence=evidence)[
            "action"
        ]
        == "propose_draft"
    )


def test_unknown_is_not_weak_but_accepted_failure_can_trigger_draft_only():
    assert mastery_for_component({"kc": {"level": "no_evidence"}}, "kc") is None
    decision = decide_replan(
        signal={},
        last_do={},
        latest_evidence={
            "valid": True,
            "confidence": "high",
            "review_status": "accepted",
            "dimensions": {"application": "failed"},
        },
    )
    assert decision["action"] == "propose_draft"
    assert decision["requires_confirmation"] and not decision["auto_apply"]


def test_legacy_provisional_contract_cannot_trigger_replan_even_with_high_confidence():
    evidence = {
        "valid": True,
        "confidence": "high",
        "can_update_knowledge": False,
        "can_record_observation": False,
        "dimensions": {"application": "failed"},
    }
    assert not planning_evidence_usable(evidence)
    assert decide_replan(signal={}, last_do={}, latest_evidence=evidence)["action"] == "keep"


def test_contradictory_model_status_and_rubric_require_verification():
    state, result, evidence, bank = _inputs()
    result.update(
        status="completed", assessment_result={"status": "còn nhầm lẫn", "dimensions": {"conceptual": "passed"}}
    )
    evidence["confidence"] = "high"
    decision = review_decision(state, result, evidence, bank, "kc")
    assert decision["status"] == "verifying"
    assert decision["reason"] == "contradictory_evaluation"
