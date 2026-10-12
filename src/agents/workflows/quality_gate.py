"""Bounded critic/repair workflow shared by every specialist."""

from __future__ import annotations

from typing import Any

from src.agents.state import LearningGraphState


def quality_gate_node(state: LearningGraphState) -> dict[str, Any]:
    """Critique specialist output without silently accepting invalid results."""
    workflow = str(state.get("workflow") or "qa")
    output = dict(state.get("output") or {})
    reasons: list[str] = []
    repair = output.get("quality_repair") or {}

    if repair.get("applied"):
        quality_review = {
            "passed": True,
            "workflow": workflow,
            "reasons": [],
            "repaired": True,
            "original_reasons": repair.get("original_reasons") or [],
            "reviewer": "deterministic_quality_gate_v2",
        }
        output["quality_review"] = quality_review
        return {
            "output": output,
            "quality_review": quality_review,
            **(
                {"source_refs": [], "retrieved_passages": []}
                if workflow not in {"qa", "do"}
                else {}
            ),
        }

    if not str(state.get("response") or "").strip():
        reasons.append("empty_response")
    if workflow == "qa" and state.get("source_refs"):
        citation_validation = output.get("citation_validation") or {}
        if not citation_validation.get("valid"):
            reasons.append("invalid_citation_contract")
    if workflow == "plan":
        decision = state.get("student_decision") or {}
        is_terminal_decision = (
            decision.get("workflow") == "plan"
            and decision.get("action") in {"confirmed", "cancelled"}
        )
        # Confirmation/cancellation turns do not create a new draft. The draft
        # was validated before the pending action was offered, so requiring a
        # second plan_validation object here incorrectly turns a successful
        # confirmation into invalid_plan.
        if not is_terminal_decision:
            plan_validation = output.get("plan_validation") or {}
            if not plan_validation.get("valid"):
                reasons.append("invalid_plan")
    if workflow == "understanding":
        assessment_validation = output.get("assessment_validation") or {}
        reasons.extend(str(item) for item in assessment_validation.get("reasons") or [])
    if workflow == "do" and not isinstance(output.get("do_session"), dict):
        reasons.append("invalid_do_session")

    quality_review = {
        "passed": not reasons,
        "workflow": workflow,
        "reasons": sorted(set(reasons)),
        "reviewer": "deterministic_quality_gate_v2",
    }
    output["quality_review"] = quality_review
    normalized: dict[str, Any] = {"output": output, "quality_review": quality_review}
    if workflow in {"qa", "do", "tracking"}:
        if not reasons:
            normalized["status"] = (
                "failed"
                if (state.get("security_flags") or {}).get("action") == "block"
                else "completed"
            )
            normalized["pending_action"] = None
    if workflow not in {"qa", "do"}:
        normalized.update({"source_refs": [], "retrieved_passages": []})
    return normalized


def repair_node(state: LearningGraphState) -> dict[str, Any]:
    """Apply one conservative repair requested by the critic."""
    workflow = str(state.get("workflow") or "qa")
    review = state.get("quality_review") or {}
    reasons = list(review.get("reasons") or [])
    output = dict(state.get("output") or {})
    output["quality_repair"] = {
        "applied": True,
        "original_reasons": reasons,
        "strategy": "safe_fallback_v1",
    }
    repaired: dict[str, Any] = {
        "output": output,
        "quality_repair_count": int(state.get("quality_repair_count") or 0) + 1,
    }
    if "empty_response" in reasons:
        repaired.update(
            {
                "response": "Hệ thống chưa tạo được phản hồi hợp lệ. Vui lòng thử lại.",
                "status": "failed",
                "pending_action": None,
            }
        )
    if "invalid_citation_contract" in reasons:
        repaired.update(
            {
                "response": (
                    "Mình chưa thể xác minh câu trả lời bằng học liệu môn học, "
                    "nên sẽ không đưa ra kết luận lúc này."
                ),
                "status": "completed",
                "pending_action": None,
                "source_refs": [],
                "retrieved_passages": [],
            }
        )
    if "invalid_plan" in reasons:
        repaired.update(
            {
                "response": (
                    "Kế hoạch nháp chưa thỏa các ràng buộc thời gian và deadline. "
                    "Hãy bổ sung thời gian rảnh hoặc giảm khối lượng mục tiêu."
                ),
                "status": "failed",
                "pending_action": None,
                "proposed_milestones": [],
            }
        )
    if workflow == "understanding" and reasons:
        repaired.update(
            {
                "status": "awaiting_teacher",
                "pending_action": state.get("pending_action")
                or {
                    "workflow": "understanding",
                    "action": "instructor_review",
                    "payload": {"reasons": sorted(set(reasons))},
                },
            }
        )
    return repaired
