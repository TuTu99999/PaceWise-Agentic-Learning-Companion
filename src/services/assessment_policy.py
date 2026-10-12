"""Deterministic question policy. Approved items, not LLM text, control progression."""

from __future__ import annotations

import hashlib
from typing import Any

STAGES = ("recall", "explain", "why", "application", "transfer")
DIMENSION = dict(zip(STAGES, ("recall", "conceptual", "reasoning", "application", "transfer"), strict=True))
HINTS = (
    "Hãy xác định dữ kiện, yêu cầu và thử một bước trước.",
    "Kiểm tra lại định nghĩa và prerequisite liên quan trong học liệu được dẫn nguồn.",
    "Thử một ví dụ đơn giản hơn do giảng viên cung cấp, rồi quay lại câu hỏi.",
    "Chia lời giải thành từng bước; ghi phần đã biết và bước còn thiếu.",
    "Xin hướng dẫn đầy đủ từ tài liệu/giảng viên; đáp án sau hỗ trợ không là bằng chứng tự làm.",
)
RATINGS = {
    0: "Không có bằng chứng liên quan hoặc mâu thuẫn cốt lõi.",
    1: "Nhận ra một phần nhưng còn lỗi cốt lõi, chưa giải thích được.",
    2: "Có ý đúng nhưng lập luận hoặc vận dụng còn thiếu đáng kể.",
    3: "Đáp ứng tiêu chí với lập luận/bài làm có bằng chứng, chỉ thiếu sót nhỏ.",
    4: "Đáp ứng đầy đủ tiêu chí, giải thích chính xác và kiểm tra kết quả phù hợp.",
}


def item_stage(item: dict[str, Any]) -> str:
    explicit = str(item.get("assessment_stage") or "")
    if explicit in STAGES:
        return explicit
    return {
        "recognition": "recall",
        "conceptual": "explain",
        "application": "application",
        "transfer": "transfer",
        "reasoning": "why",
    }.get(str(item.get("cognitive_level") or ""), "recall")


def question_fingerprint(item: dict) -> str:
    normalized = " ".join(str(item.get("question") or "").casefold().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def select_item(
    bank: list[dict], kc_id: str, stage: str, used: list[str], seen_questions: list[str] | None = None
) -> dict | None:
    return next(
        (
            item
            for item in sorted(bank, key=lambda value: value["assessment_id"])
            if kc_id in item.get("knowledge_component_ids", [])
            and not item.get("kc_provisional")
            and item_stage(item) == stage
            and item["assessment_id"] not in used
            and question_fingerprint(item) not in (seen_questions or [])
            and (stage == "recall" or item.get("answer_type") == "open")
        ),
        None,
    )


def next_step(stage: str, outcome: dict, *, hint_level: int, attempts: int) -> dict:
    """Abstain/review, remediation, or next stage; never silently skip a missing stage."""
    if outcome.get("status") == "awaiting_teacher":
        return {"status": "review_required", "stage": stage, "reason": "insufficient_evidence"}
    assessment = outcome.get("assessment_result") or {}
    passed = (assessment.get("dimensions") or {}).get(DIMENSION[stage]) == "passed" and assessment.get("status") in {
        "đã thể hiện được",
        "đang hình thành",
        "demonstrated",
        "developing",
    }
    if not passed:
        return {
            "status": "needs_support" if attempts < 2 else "stopped",
            "stage": stage,
            "reason": "checkpoint_not_passed",
        }
    if hint_level:
        return {"status": "verification_required", "stage": stage, "reason": "need_unseen_item_without_hint"}
    index = STAGES.index(stage) + 1
    return {
        "status": "completed" if index == len(STAGES) else "active",
        "stage": STAGES[min(index, len(STAGES) - 1)],
        "reason": "evidence_accepted",
    }


def diagnostic_rubric(criteria: list[dict]) -> list[dict]:
    """Explicit formative 0–4 anchors, unrelated to gradebook or decimal mastery."""
    return [{**criterion, "diagnostic_ratings": RATINGS} for criterion in criteria]


def validate_criterion_scores(raw: Any, criteria: list[dict], answer: str) -> list[dict]:
    if not isinstance(raw, list):
        return []
    expected = {str(item["criterion_id"]) for item in criteria}
    accepted: dict[str, dict] = {}
    normalized = " ".join(answer.casefold().split())
    for item in raw:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("criterion_id") or "")
        if identifier in accepted:
            return []
        score = item.get("score")
        quote = str(item.get("evidence_quote") or "").strip()
        if identifier in expected and type(score) is int and 0 <= score <= 4 and quote:
            if " ".join(quote.casefold().split()) in normalized:
                accepted[identifier] = {"criterion_id": identifier, "score": score, "evidence_quote": quote}
    return list(accepted.values()) if expected and set(accepted) == expected else []
