"""
Coordinator Node: Tiếp nhận state, phân loại ý định người dùng bằng LLM và chọn workflow kế tiếp.
"""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.guardrails import classify_workflow, evaluate_guardrails
from src.agents.llm import get_agent_llm
from src.agents.prompts.coordinator import COORDINATOR_SYSTEM_PROMPT
from src.agents.safety import evaluate_input_policy
from src.agents.state import LearningGraphState


def coordinator_node(state: LearningGraphState) -> dict:
    """
    Node phân loại và điều phối chính của Multi-Agent.
    Sử dụng LLM để xác định chính xác 1 trong 7 workflows:
    plan | do | tracking | qa | understanding | recover | reflect.
    """
    query = state.get("query") or ""
    if not query and state.get("messages"):
        last_msg = state["messages"][-1]
        query = last_msg.get("content", "") if isinstance(last_msg, dict) else getattr(last_msg, "content", "")

    workflow, route_confidence = classify_workflow(query, state.get("pending_action"))
    workflow_hint = str((state.get("request") or {}).get("workflow_hint") or "").lower()
    if workflow_hint in {"plan", "do", "tracking", "qa", "understanding", "recover", "reflect"}:
        workflow, route_confidence = workflow_hint, 1.0
    # Explicit non-answering workflows still run deterministic injection rules
    # and semantic review for suspicious signals, but do not spend a model call
    # classifying ordinary plan/tracking text on every request.
    operational_hint = workflow_hint in {"plan", "do", "tracking", "recover", "reflect"}
    security_flags = evaluate_input_policy(
        query,
        semantic_mode="signals" if operational_hint else None,
    )
    rule_decision = evaluate_guardrails(query)
    if (
        workflow in {"plan", "do", "tracking", "recover", "reflect"}
        and rule_decision["action"] == "allow"
        and security_flags["action"] == "guided_help"
    ):
        # Operational workflows only schedule, measure or summarize learner
        # data; they cannot produce a submission-ready academic answer. Avoid
        # replacing valid workflow output when the optional semantic classifier
        # is unavailable or over-cautious. Prompt injection remains blocked.
        security_flags.update(
            {
                "action": "allow",
                "reason": "non_answering_workflow",
                "is_homework_cheat_attempt": False,
            }
        )
        security_flags.setdefault("layers", []).append("workflow_scope")
    reasoning = "Định tuyến bằng quy tắc xác định trước."
    intent_summary = query[:160]

    if security_flags["is_injection_attempt"]:
        return {
            "workflow": "qa",
            "current_node": "coordinator",
            "analysis": "Guardrail chặn prompt injection trước khi gọi mô hình.",
            "security_flags": security_flags,
            "status": "failed",
            "output": {},
            "quality_review": {},
            "quality_repair_count": 0,
        }

    has_existing_milestones = bool(state.get("proposed_milestones"))
    context_note = f" (Ngữ cảnh: Phiên học đã có {len(state.get('proposed_milestones') or [])} milestones)" if has_existing_milestones else ""

    # Chỉ dùng model để phân xử ca mơ hồ; rule route là fallback có thể kiểm thử.
    try:
        if route_confidence >= 0.8:
            raise RuntimeError("deterministic_route_confident")
        llm = get_agent_llm(temperature=0.0, task="coordinator")
        messages = [
            SystemMessage(content=COORDINATOR_SYSTEM_PROMPT),
            HumanMessage(content=f"Yêu cầu của sinh viên: '{query}'{context_note}"),
        ]
        res = llm.invoke(messages)
        content = res.content.strip()

        # Làm sạch định dạng Markdown JSON nếu có
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        data = json.loads(content)
        detected_workflow = data.get("workflow", "").lower()
        if detected_workflow in {"plan", "do", "tracking", "qa", "understanding", "recover", "reflect"}:
            workflow = detected_workflow
            reasoning = data.get("reasoning", "")
            intent_summary = str(data.get("intent_summary", intent_summary))[:160]
            model_flags = data.get("security_flags")
            if isinstance(model_flags, dict):
                security_flags["model_flags"] = model_flags
    except Exception:
        pass

    return {
        "workflow": workflow,
        "current_node": "coordinator",
        "analysis": reasoning,
        "security_flags": security_flags,
        "output": {},
        "quality_review": {},
        "quality_repair_count": 0,
        "request": {
            **(state.get("request") or {}),
            "intent_summary": intent_summary,
            "route_confidence": route_confidence,
        },
    }
