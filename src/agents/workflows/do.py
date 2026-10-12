"""Do workflow: prepare and evaluate one confirmed PaceWise study block."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.agents.state import LearningGraphState
from src.agents.workflows.understanding import understanding_node

_BLOCKERS = {"none", "knowledge", "time", "interruption", "other"}


def _fold(value: Any) -> str:
    normalized = unicodedata.normalize("NFD", str(value or "").casefold())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _terms(value: Any) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", _fold(value)) if len(term) > 2}


def _module_resources(modules: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Rank authorized LMS module items for the current study-block objective."""
    query_terms = _terms(query)
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    sequence = 0
    for module in modules:
        module_title = str(module.get("title") or module.get("name") or "Học liệu môn học")
        items = module.get("items") or module.get("module_items") or []
        if not isinstance(items, list):
            items = []
        if not items:
            items = [module]
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or module_title)
            kind = str(item.get("type") or item.get("item_type") or "module").lower()
            url = str(
                item.get("url")
                or item.get("html_url")
                or item.get("source_url")
                or item.get("external_url")
                or ""
            )
            overlap = len(query_terms & _terms(f"{module_title} {title}"))
            type_bonus = 1 if kind in {"resource", "file", "page", "lecture_video", "video"} else 0
            candidates.append(
                (
                    overlap * 10 + type_bonus,
                    -sequence,
                    {
                        "id": str(item.get("id") or f"module-{sequence + 1}"),
                        "title": title,
                        "kind": kind,
                        "url": url or None,
                        "module": module_title,
                        "citation": f"[{module_title} · {title}]",
                    },
                )
            )
            sequence += 1
    return [item for _, _, item in sorted(candidates, reverse=True, key=lambda value: (value[0], value[1]))[:3]]


def _prepare(state: LearningGraphState, event: dict[str, Any]) -> dict[str, Any]:
    if state.get("do_scope") and (state.get("do_session") or {}).get("action") == "prepare":
        prepared = state["do_session"]
        return {"workflow": "do", "current_node": "do", "status": "completed",
            "response": "Phiên tự học đã sẵn sàng.", "do_session": prepared,
            "source_refs": [], "output": {"do_session": prepared}, "pending_action": None}
    task_id = str(event.get("task_id") or "")
    assignment = next(
        (item for item in state.get("assignments") or [] if str(item.get("id") or "") == task_id),
        {},
    )
    title = str(event.get("title") or assignment.get("title") or "Phiên tự học")
    objective = str(event.get("objective") or event.get("milestone_title") or title)
    resources = _module_resources(state.get("modules") or [], f"{title} {objective}")
    if "lms_files" in state:
        query_terms = _terms(f"{title} {objective}")
        files = sorted(state["lms_files"], key=lambda resource: len(query_terms & _terms(resource.get("title"))), reverse=True)
        resources = (files + resources)[:3]
    source_refs = [
        {
            "id": resource["id"],
            "citation": resource["citation"],
            "document_title": resource["title"],
            "excerpt": f"{resource['module']} · {resource['kind']}",
            "url": resource.get("url"),
        }
        for resource in resources
    ]
    prepared = {
        "action": "prepare",
        "status": "ready",
        "block_id": str(event.get("block_id") or ""),
        "task_id": task_id,
        "title": title,
        "objective": objective,
        "planned_minutes": max(1, int(event.get("planned_minutes") or 1)),
        "recommended_resources": resources,
        "opening_prompt": (
            f"Mục tiêu phiên này: {objective}. Hãy hỏi khi cần giải thích; "
            "trợ lý chỉ dùng học liệu môn học và không làm hộ bài tính điểm."
        ),
    }
    return {
        "workflow": "do",
        "current_node": "do",
        "status": "completed",
        "response": f"Phiên tự học đã sẵn sàng với {len(resources)} tài liệu gợi ý.",
        "source_refs": source_refs,
        "do_session": prepared,
        "output": {"do_session": prepared},
        "pending_action": None,
    }


def evaluate_completion(event: dict[str, Any]) -> dict[str, Any]:
    planned = max(1, int(event.get("planned_minutes") or 1))
    actual = max(0, int(event.get("actual_minutes") or 0))
    completion = min(100, max(0, int(event.get("completion_percent") or 0)))
    blocker = str(event.get("blocker") or "none")
    if blocker not in _BLOCKERS:
        blocker = "other"

    remaining = max(0, round(planned * (100 - completion) / 100))
    variance = actual - planned
    if actual == 0:
        outcome = "missed"
    elif blocker == "knowledge":
        outcome = "blocked"
    elif completion >= 100:
        outcome = "completed"
    elif completion < 80 or remaining >= 30:
        outcome = "needs_more_time"
    else:
        outcome = "on_track"

    needs_recovery = outcome in {"missed", "blocked", "needs_more_time"} and remaining >= 30
    needs_understanding = blocker == "knowledge"
    if needs_understanding:
        next_action = "Gợi ý kiểm tra nhanh hoặc hỏi đáp có nguồn trước khi xếp thêm thời gian."
    elif needs_recovery:
        next_action = "Kiểm tra capacity và mở Recover nếu phần còn lại ảnh hưởng deadline."
    elif outcome == "completed":
        next_action = "Tiếp tục study block kế tiếp theo kế hoạch."
    else:
        next_action = "Giữ kế hoạch hiện tại và theo dõi phiên tiếp theo."

    evaluation = {
        "action": "complete",
        "status": outcome,
        "block_id": str(event.get("block_id") or ""),
        "task_id": str(event.get("task_id") or ""),
        "planned_minutes": planned,
        "actual_minutes": actual,
        "variance_minutes": variance,
        "completion_percent": completion,
        "remaining_minutes": remaining,
        "blocker": blocker,
        "blocker_note": str(event.get("blocker_note") or "")[:500],
        "needs_recovery": needs_recovery,
        "needs_understanding_check": needs_understanding,
        "next_action": next_action,
    }
    return {
        "workflow": "do",
        "current_node": "do",
        "status": "completed",
        "response": next_action,
        "do_session": evaluation,
        "progress_metrics": {"last_do_session": evaluation},
        "risk_signals": (
            [{"kind": "do_session_drift", "task_id": evaluation["task_id"], "deficit_minutes": remaining}]
            if needs_recovery
            else []
        ),
        "output": {"do_session": evaluation},
        "pending_action": (
            {"workflow": "recover", "action": "review_schedule", "payload": evaluation}
            if needs_recovery
            else None
        ),
    }


def do_node(state: LearningGraphState) -> dict[str, Any]:
    metrics = state.get("progress_metrics") or {}
    event = metrics.get("do_session") if isinstance(metrics, dict) else {}
    event = event if isinstance(event, dict) else {}
    if event.get("action") == "assess":
        assessment = understanding_node(state)
        checkpoint = {
            "action": "assess",
            "status": assessment.get("status", "completed"),
            "block_id": str(event.get("block_id") or ""),
            "assessment_id": str((state.get("request") or {}).get("assessment_id") or ""),
            "assessment_result": assessment.get("assessment_result") or {},
        }
        return {
            **assessment,
            "workflow": "do",
            "current_node": "do",
            "do_session": checkpoint,
            "output": {
                **(assessment.get("output") or {}),
                "do_session": checkpoint,
            },
        }
    return evaluate_completion(event) if event.get("action") == "complete" else _prepare(state, event)
