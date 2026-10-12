"""
Workflow Reflect: Phản tư và tổng kết tuần học.
Agent phụ trách: Reflection Agent.
"""

import json
import re
from copy import deepcopy

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.guardrails import normalize_text
from src.agents.llm import get_agent_llm
from src.agents.prompts.reflection import REFLECTION_SYSTEM_PROMPT
from src.agents.state import LearningGraphState
from src.agents.validators import build_pending_action
from src.services.planning_signals import normalize_planning_signal


def _normalize_planning_signal(value: object, fallback_task_id: str = "") -> dict:
    return normalize_planning_signal(value, fallback_task_id)


def reflect_node(state: LearningGraphState) -> dict:
    """
    Reflection Agent: Tổng kết tuần dựa trên dữ kiện khách quan và đề xuất 1 điều chỉnh cho tuần sau.
    """
    query = state.get("query") or ""
    if not query and state.get("messages"):
        last_msg = state["messages"][-1]
        query = last_msg.get("content", "") if isinstance(last_msg, dict) else getattr(last_msg, "content", "")

    normalized_query = normalize_text(query)
    progress_metrics = deepcopy(state.get("progress_metrics") or {})
    scope = "activity" if progress_metrics.get("reflection_scope") == "activity" else "weekly"
    pending_action = state.get("pending_action") or {}
    if pending_action.get("workflow") == "reflect" and any(
        word in normalized_query for word in ("xac nhan", "dong y", "chap nhan", "confirm")
    ):
        draft = pending_action.get("payload") or {}
        activity_scope = draft.get("scope") == "activity"
        return {
            "current_node": "reflect",
            "response": (
                "Ghi nhận sau hoạt động đã được lưu."
                if activity_scope
                else "Điều chỉnh cho tuần sau đã được xác nhận."
            ),
            "reflection_draft": draft,
            "pending_action": None,
            "status": "completed",
            "student_decision": {"action": "confirmed", "workflow": "reflect"},
        }

    try:
        llm = get_agent_llm(temperature=0.3, task="reflect")
        messages = [
            SystemMessage(content=REFLECTION_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Phạm vi phản tư: {scope}. Nội dung sinh viên: '{query}'\n"
                    f"Chỉ số tiến độ: {json.dumps(progress_metrics, ensure_ascii=False)}\n"
                    f"Hồ sơ dài hạn: {json.dumps(state.get('learner_profile') or {}, ensure_ascii=False)}\n"
                    f"Knowledge State đã kiểm định: {json.dumps(state.get('mastery_profile') or {}, ensure_ascii=False)}\n"
                    f"Misconception đã ghi nhận: {json.dumps(state.get('misconceptions') or [], ensure_ascii=False)}\n"
                    + (
                        "Cuối phản hồi thêm JSON gồm effective, difficulty, next_step và planning_signal. "
                        "planning_signal gồm cause, duration_factor, follow_up_minutes, affected_kcs và task_id."
                        if scope == "activity"
                        else "Cuối phản hồi thêm JSON gồm effective, deviation_cause, adjustment và planning_signal. "
                        "planning_signal gồm cause, duration_factor, follow_up_minutes, affected_kcs và task_id."
                    )
                )
            ),
        ]
        res = llm.invoke(messages)
        response_text = res.content.strip()
    except Exception:
        response_text = "Mình chưa thể tổng hợp phản tư tự động lúc này; bạn có thể kiểm tra bản điều chỉnh tối thiểu bên dưới."

    if scope == "activity":
        reflection_draft = {
            "scope": "activity",
            "activity": progress_metrics.get("activity") or {},
            "effective": "",
            "difficulty": "",
            "next_step": "Giữ một bước tiếp theo nhỏ và cụ thể.",
            "evidence": progress_metrics,
            "week_start": progress_metrics.get("week_start"),
            "planning_signal": {
                "cause": "none",
                "duration_factor": 1.0,
                "follow_up_minutes": 0,
                "affected_kcs": [],
                "task_id": str((progress_metrics.get("activity") or {}).get("task_id") or ""),
            },
        }
        ai_fields = ("effective", "difficulty", "next_step", "planning_signal")
    else:
        reflection_draft = {
            "scope": "weekly",
            "effective": "",
            "deviation_cause": "",
            "adjustment": "Giữ một thay đổi nhỏ, cụ thể cho tuần sau.",
            "evidence": progress_metrics,
            "week_start": progress_metrics.get("week_start"),
            "week_end": progress_metrics.get("week_end"),
            "effective_week_start": progress_metrics.get("effective_week_start"),
            "planning_signal": {
                "cause": "none",
                "duration_factor": 1.0,
                "follow_up_minutes": 0,
                "affected_kcs": [],
                "task_id": "",
            },
        }
        ai_fields = ("effective", "deviation_cause", "adjustment", "planning_signal")
    evidence_conflict = False
    json_match = re.search(r"```json\s*([\s\S]*?)```", response_text)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            if isinstance(parsed, dict):
                # Evidence is an immutable input snapshot, never model output.
                claimed = parsed.get("evidence")
                evidence_conflict = claimed is not None and not _agrees(claimed, progress_metrics)
                reflection_draft.update(
                    {key: parsed.get(key, reflection_draft[key]) for key in ai_fields}
                )
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    reflection_draft["planning_signal"] = _normalize_planning_signal(
        reflection_draft.get("planning_signal"),
        str((progress_metrics.get("activity") or {}).get("task_id") or ""),
    )
    clean_response = re.sub(r"```json[\s\S]*?```", "", response_text).strip() or response_text
    if evidence_conflict:
        # Suppress advice from a response that fabricated its supporting facts.
        for key in ai_fields:
            if key != "planning_signal":
                reflection_draft[key] = ""
        reflection_draft["planning_signal"] = normalize_planning_signal({})
        reflection_draft["validation_warnings"] = ["MODEL_EVIDENCE_CONFLICT"]
        clean_response = "AI đưa ra số liệu không khớp bản ghi. Đã loại bỏ nhận xét và đề xuất này; dữ kiện gốc được giữ nguyên."
    pending = build_pending_action(
        "reflect",
        "save_activity_reflection" if scope == "activity" else "confirm_adjustment",
        reflection_draft,
    )

    suffix = (
        "\n\nHãy xác nhận trước khi lưu ghi nhận cho hoạt động này."
        if scope == "activity"
        else "\n\nHãy xác nhận trước khi áp dụng điều chỉnh cho tuần sau."
    )

    return {
        "current_node": "reflect",
        "response": clean_response + suffix,
        "analysis": (
            "Reflection Agent đã ghi nhận kết quả, trở ngại và bước tiếp theo của một hoạt động."
            if scope == "activity"
            else "Reflection Agent đã tổng kết dựa trên dữ kiện khách quan và đưa ra 1 gợi ý điều chỉnh."
        ),
        "reflection_draft": reflection_draft,
        "pending_action": pending,
        "status": "awaiting_student",
    }


def _agrees(claimed: object, observed: object) -> bool:
    """A partial evidence echo must agree recursively; extra facts fail."""
    if isinstance(claimed, dict):
        return isinstance(observed, dict) and all(
            key in observed and _agrees(value, observed[key]) for key, value in claimed.items()
        )
    return claimed == observed
