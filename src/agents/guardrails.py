"""Deterministic safety and routing rules used before any model call."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

WORKFLOWS = {"plan", "do", "tracking", "qa", "understanding", "recover", "reflect"}


def normalize_text(text: str) -> str:
    """Normalize Vietnamese text for stable rule matching."""
    normalized = unicodedata.normalize("NFD", str(text or "").lower())
    without_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", without_marks).strip()


INJECTION_PATTERNS = (
    r"\b(ignore|disregard|forget)\b.{0,35}\b(previous|above|system|instructions?)\b",
    r"\b(quen|bo qua|phot lo)\b.{0,35}\b(chi dan|huong dan|quy tac|he thong)\b",
    r"\b(system prompt|developer message|jailbreak|dan mode|developer mode)\b",
    r"\b(reveal|show|print|leak)\b.{0,25}\b(system prompt|hidden instruction|secret|api key)\b",
)

CHEATING_PATTERNS = (
    r"\b(lam ho|viet ho|giai ho|nop ho|lam giup|giai giup)\b",
    r"\b(dua|cho)\b.{0,20}\b(dap an|bai giai|code hoan chinh|bai hoan chinh)\b",
    r"\b(write|solve|complete|do)\b.{0,30}\b(my assignment|my homework|for me|entire answer)\b",
    r"\bchi can dap an\b",
)

SAFE_LEARNING_PATTERNS = (
    r"\b(giai thich|khai niem|vi du tuong tu|goi y|huong dan tung buoc|kiem tra cach lam)\b",
    r"\b(explain|concept|similar example|hint|review my attempt|socratic)\b",
)

ROUTING_PATTERNS: dict[str, tuple[str, ...]] = {
    "do": (
        r"\bphien (tu )?hoc\b",
        r"\bbat dau hoc\b",
        r"\bket thuc phien\b",
        r"\bdo agent\b",
    ),
    "plan": (
        r"\bke hoach\b",
        r"\bchia (nho|viec|milestone)\b",
        r"\bmilestone\b",
        r"\bxep lich\b",
        r"\bmuc tieu tuan\b",
    ),
    "tracking": (
        r"\btien do\b",
        r"\bda hoan thanh\b",
        r"\bthoi gian thuc te\b",
        r"\bcon bao nhieu\b",
        r"\btracking\b",
    ),
    "understanding": (
        r"\bhieu bai\b",
        r"\bkiem tra kien thuc\b",
        r"\btu danh gia\b",
        r"\bquiz\b",
        r"\brubric\b",
    ),
    "recover": (
        r"\btre deadline\b",
        r"\bvo ke hoach\b",
        r"\bqua tai\b",
        r"\bxep lai\b",
        r"\bcuu (lich|ke hoach)\b",
        r"\brecover\b",
    ),
    "reflect": (
        r"\bphan tu\b",
        r"\btong ket (tuan|cuoi tuan)\b",
        r"\btuan sau (doi|cai thien)\b",
        r"\breflect\b",
    ),
    "qa": (
        r"\bgiai thich\b",
        r"\bkhai niem\b",
        r"\btai sao\b",
        r"\bso sanh\b",
        r"\bcong thuc\b",
        r"\bhoi dap\b",
    ),
}


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def evaluate_guardrails(query: str) -> dict[str, Any]:
    """Return deterministic injection and academic-integrity decisions."""
    normalized = normalize_text(query)
    is_injection = _matches_any(normalized, INJECTION_PATTERNS)
    cheating_match = _matches_any(normalized, CHEATING_PATTERNS)
    safe_learning_match = _matches_any(normalized, SAFE_LEARNING_PATTERNS)
    explicit_no_answer = bool(
        re.search(r"\b(khong|dung|do not|without)\b.{0,20}\b(dua|cho|give|dap an|answer)\b", normalized)
    )
    explicit_no_cheating = bool(
        re.search(
            r"\b(khong|dung|do not|without)\b.{0,20}"
            r"\b(lam ho|viet ho|giai ho|nop ho|lam giup|giai giup|complete for me|solve for me)\b",
            normalized,
        )
    )
    is_cheating = cheating_match and not explicit_no_answer and not explicit_no_cheating and not (
        safe_learning_match and not re.search(r"\b(dap an|hoan chinh|nop ho)\b", normalized)
    )

    if is_injection:
        action = "block"
        reason = "prompt_injection"
    elif is_cheating:
        action = "guided_help"
        reason = "academic_integrity"
    else:
        action = "allow"
        reason = "none"

    return {
        "is_injection_attempt": is_injection,
        "is_homework_cheat_attempt": is_cheating,
        "action": action,
        "reason": reason,
        "rule_version": "guardrails_v1",
    }


def classify_workflow(query: str, pending_action: dict[str, Any] | None = None) -> tuple[str, float]:
    """Classify a request without an LLM so routing remains available offline."""
    normalized = normalize_text(query)
    pending_action = pending_action or {}
    if pending_action and re.search(r"\b(xac nhan|dong y|chap nhan|huy|tu choi|confirm|cancel)\b", normalized):
        workflow = str(pending_action.get("workflow", "qa"))
        return (workflow if workflow in WORKFLOWS else "qa", 0.99)

    scores = {
        workflow: sum(1 for pattern in patterns if re.search(pattern, normalized))
        for workflow, patterns in ROUTING_PATTERNS.items()
    }
    best_workflow = max(scores, key=scores.get)
    best_score = scores[best_workflow]
    if best_score == 0:
        return "qa", 0.5
    ties = sum(1 for score in scores.values() if score == best_score)
    confidence = 0.95 if best_score >= 2 else (0.82 if ties == 1 else 0.65)
    return best_workflow, confidence
