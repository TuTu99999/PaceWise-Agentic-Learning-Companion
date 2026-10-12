"""
Workflow Plan: Phân rã bài tập lớn thành milestone và lập lịch tuần.
Agent phụ trách: Milestone Agent.
Tích hợp:
- Lập kế hoạch lộ trình milestone bài tập ban đầu.
- Tự động nhận diện ngữ cảnh phiên hội thoại (Multi-turn): điều chỉnh chính xác milestone được yêu cầu thay vì tạo lại từ đầu.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.guardrails import normalize_text
from src.agents.llm import get_agent_llm
from src.agents.prompts.milestone import MILESTONE_SYSTEM_PROMPT, WEEKLY_GOAL_SYSTEM_PROMPT
from src.agents.state import LearningGraphState
from src.agents.validators import build_pending_action, validate_plan_constraints
from src.services.plan_intelligence import (
    assignment_structure,
    build_template_milestones,
    normalize_rubric_criteria,
)


def _parse_int_minutes(val: Any) -> int:
    """Chuyển đổi chuỗi thời lượng (ví dụ '45 phút', '1.5h', '2 tiếng') thành số phút nguyên."""
    if isinstance(val, (int, float)):
        return max(15, int(val))
    if isinstance(val, str):
        text = val.strip().lower()
        # 1. Nếu có chữ 'phút' hoặc 'min', lấy số phút
        min_match = re.search(r"(\d+)\s*(?:phút|min)", text)
        if min_match:
            return max(15, int(min_match.group(1)))

        # 2. Nếu có 'tiếng', 'giờ', hoặc 'h' (dạng 1.5h, 2 giờ)
        hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|tiếng|giờ)\b", text)
        if hour_match:
            return max(15, int(float(hour_match.group(1)) * 60))

        # 3. Fallback lấy số nguyên đầu tiên
        nums = re.findall(r"\d+", text)
        if nums:
            return max(15, int(nums[0]))
    return 60


def _parse_depends_on(val: Any) -> list[str]:
    """Chuẩn hóa danh sách các milestone phụ thuộc."""
    if isinstance(val, list):
        return [
            str(x).strip()
            for x in val
            if str(x).strip() and str(x).strip().lower() not in {"không", "none", "no", "-", "khong"}
        ]
    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned or cleaned.lower() in {"không", "none", "no", "-", "khong"}:
            return []
        parts = re.split(r"[,;]+", cleaned)
        return [p.strip() for p in parts if p.strip()]
    return []


def _semantic_milestone_fields(item: dict[str, Any]) -> dict[str, Any]:
    """Keep optional evidence fields from structured model output."""
    fields: dict[str, Any] = {}
    for source_key, target_key in (
        ("rubric_criteria", "rubric_criteria"),
        ("rubricCriteria", "rubric_criteria"),
        ("knowledge_components", "knowledge_components"),
        ("knowledgeComponents", "knowledge_components"),
    ):
        values = item.get(source_key)
        if values and target_key not in fields:
            fields[target_key] = list(values) if isinstance(values, list) else [values]
    confidence = item.get("mapping_confidence", item.get("mappingConfidence"))
    if confidence is not None:
        try:
            fields["mapping_confidence"] = min(1.0, max(0.0, float(confidence)))
        except (TypeError, ValueError):
            pass
    return fields


def _goal_candidates(
    assignments: list[dict[str, Any]],
    requested: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return a small, stable set of open LMS tasks for weekly goal review."""
    requested_ids = {
        str(item.get("task_id") or item.get("taskId") or "")
        for item in (requested or [])
        if str(item.get("task_id") or item.get("taskId") or "")
    }
    open_items = []
    for assignment in assignments:
        if requested_ids and str(assignment.get("id")) not in requested_ids:
            continue
        submission = assignment.get("submission") or {}
        if str(submission.get("workflow_state") or "").lower() in {"submitted", "graded", "pending_review", "excused"}:
            continue
        open_items.append(assignment)
    return sorted(
        open_items,
        key=lambda item: (
            str(item.get("deadline") or "9999-12-31"),
            -float((item.get("assignment_group") or {}).get("weight") or 0),
            -float(item.get("points_possible") or 0),
        ),
    )[:4]


def _assignment_goal_source_refs(assignment: dict[str, Any]) -> list[str]:
    task_id = str(assignment.get("id") or "")
    refs = [f"assignment:{task_id}"] if task_id else []
    rubric = assignment.get("rubric")
    if isinstance(rubric, dict) and rubric.get("id"):
        refs.append(f"rubric:{rubric['id']}")
    chapter = str(assignment.get("chapter") or "").strip()
    if chapter:
        refs.append(f"module:{assignment.get('course_id') or 'course'}:{chapter}")
    for item in assignment.get("planning_evidence") or []:
        if isinstance(item, dict) and item.get("sourceRef"):
            refs.append(str(item["sourceRef"]))
    return list(dict.fromkeys(refs))


def _weekly_goal_context(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bound official assignment context before it is sent to the model."""
    result = []
    for item in candidates:
        evidence = []
        for row in item.get("planning_evidence") or []:
            if not isinstance(row, dict):
                continue
            evidence.append(
                {
                    "section": str(row.get("section") or "")[:200],
                    "content": str(row.get("content") or "")[:1800],
                    "source_ref": str(row.get("sourceRef") or ""),
                }
            )
        result.append(
            {
                "task_id": str(item.get("id") or ""),
                "course_code": str(item.get("course_code") or item.get("course_id") or ""),
                "module": str(item.get("chapter") or ""),
                "title": str(item.get("title") or "")[:300],
                "description": str(item.get("description") or "")[:2500],
                "deadline": item.get("deadline"),
                "points_possible": item.get("points_possible"),
                "assignment_group_weight": (item.get("assignment_group") or {}).get("weight"),
                "rubric_criteria": normalize_rubric_criteria(item),
                "planning_evidence": evidence[:4],
                "allowed_source_refs": _assignment_goal_source_refs(item),
            }
        )
    return result


def _extract_weekly_goals(text: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed_items: list[Any] = []
    json_match = re.search(r"```json\s*([\s\S]*?)```", text)
    payload_text = json_match.group(1) if json_match else text.strip()
    if payload_text:
        try:
            payload = json.loads(payload_text)
            parsed_items = payload.get("weekly_goals", []) if isinstance(payload, dict) else payload
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed_items = []
    candidate_by_id = {str(item.get("id")): item for item in candidates}
    candidate_ids = set(candidate_by_id)
    goals: list[dict[str, Any]] = []
    for index, item in enumerate(parsed_items if isinstance(parsed_items, list) else []):
        if not isinstance(item, dict):
            continue
        task_ids = list(dict.fromkeys(
            str(value)
            for value in item.get("task_ids", item.get("taskIds", []))
            if str(value) in candidate_ids
        ))
        title = str(item.get("title") or "").strip()
        if title and task_ids:
            allowed_refs = {
                ref
                for task_id in task_ids
                for ref in _assignment_goal_source_refs(candidate_by_id[task_id])
            }
            source_refs = [
                str(value)
                for value in item.get("source_refs", item.get("sourceRefs", [])) or []
                if str(value) in allowed_refs
            ]
            if not source_refs:
                source_refs = [f"assignment:{task_id}" for task_id in task_ids]
            goals.append(
                {
                    "id": str(item.get("id") or f"goal-{index + 1}"),
                    "title": title,
                    "taskIds": task_ids,
                    "confirmed": False,
                    "rationale": str(item.get("rationale") or "").strip(),
                    "sourceRefs": list(dict.fromkeys(source_refs)),
                    "analysisSource": "model",
                }
            )
    covered = {task_id for goal in goals for task_id in goal["taskIds"]}
    if goals and covered == candidate_ids:
        return goals[:4]
    return [
        {
            "id": f"goal-{index + 1}",
            "title": f"Hoàn thành phần cần thiết của {item.get('title') or 'nhiệm vụ'} trước hạn",
            "taskIds": [str(item.get("id"))],
            "confirmed": False,
            "rationale": (
                f"Nhiệm vụ có hạn {item.get('deadline')}; mục tiêu giữ đúng phạm vi assignment đã công bố."
                if item.get("deadline")
                else "Mục tiêu giữ đúng phạm vi assignment đã công bố."
            ),
            "sourceRefs": _assignment_goal_source_refs(item),
            "analysisSource": "assignment_rule",
        }
        for index, item in enumerate(candidates)
    ]


def _extract_milestones_from_text(text: str) -> list[dict[str, Any]]:
    """
    Trích xuất danh sách proposed_milestones từ câu trả lời của LLM.
    Ưu tiên khối ```json, sau đó đến bảng markdown, và fallback mặc định nếu rỗng.
    """
    # Providers may return the requested object without Markdown fences.
    # Normalize that valid shape before applying the same parser and boundary checks.
    if "```" not in text and text.lstrip().startswith(("{", "[")):
        text = f"```json\n{text.strip()}\n```"

    # 1. Thử parse từ khối ```json ... ```
    if "```json" in text:
        try:
            block = text.split("```json")[1].split("```")[0].strip()
            data = json.loads(block)
            items = (
                data.get("milestones")
                if isinstance(data, dict)
                else (data if isinstance(data, list) else None)
            )
            if isinstance(items, list) and items:
                result = []
                for idx, item in enumerate(items):
                    if isinstance(item, dict):
                        m_id = str(item.get("milestone_id") or item.get("id") or f"M{idx + 1}")
                        title = str(item.get("title") or item.get("name") or f"Milestone {idx + 1}")
                        deliv = str(item.get("deliverable") or item.get("output") or "Đầu ra kiểm chứng được")
                        est_min = _parse_int_minutes(
                            item.get("estimated_minutes") or item.get("duration_minutes") or item.get("duration")
                        )
                        deps = _parse_depends_on(item.get("depends_on") or item.get("dependencies"))
                        task_id = str(item.get("task_id") or "")
                        source_refs = [
                            str(value)
                            for value in (item.get("source_refs", item.get("sourceRefs", [])) or [])
                            if str(value).strip()
                        ]
                        result.append({
                            "milestone_id": m_id,
                            **({"task_id": task_id} if task_id else {}),
                            "title": title,
                            "deliverable": deliv,
                            "estimated_minutes": est_min,
                            "depends_on": deps,
                            **({"source_refs": source_refs} if source_refs else {}),
                            **_semantic_milestone_fields(item),
                        })
                if result:
                    return result
        except Exception:
            pass

    # 2. Thử parse từ bất kỳ code block ``` ... ``` nào có dạng JSON
    if "```" in text:
        for chunk in text.split("```")[1::2]:
            try:
                data = json.loads(chunk.strip())
                items = (
                    data.get("milestones")
                    if isinstance(data, dict)
                    else (data if isinstance(data, list) else None)
                )
                if isinstance(items, list) and items:
                    result = []
                    for idx, item in enumerate(items):
                        if isinstance(item, dict):
                            task_id = str(item.get("task_id") or "")
                            result.append({
                                "milestone_id": str(item.get("milestone_id") or f"M{idx + 1}"),
                                **({"task_id": task_id} if task_id else {}),
                                "title": str(item.get("title") or f"Milestone {idx + 1}"),
                                "deliverable": str(item.get("deliverable") or "Đầu ra kiểm chứng được"),
                                "estimated_minutes": _parse_int_minutes(item.get("estimated_minutes")),
                                "depends_on": _parse_depends_on(item.get("depends_on")),
                                **(
                                    {"source_refs": [
                                        str(value)
                                        for value in (item.get("source_refs", item.get("sourceRefs", [])) or [])
                                        if str(value).strip()
                                    ]}
                                    if (item.get("source_refs") or item.get("sourceRefs"))
                                    else {}
                                ),
                                **_semantic_milestone_fields(item),
                            })
                    if result:
                        return result
            except Exception:
                continue

    # 3. Fallback: Parse từ bảng Markdown (cột M1, M2...)
    table_rows = re.findall(
        r"\|\s*(M\d+|[0-9]+)\s*\|\s*([^\|]+)\|\s*([^\|]+)\|\s*([^\|]+)\|\s*([^\|]+)\|\s*([^\|]+)\|",
        text,
    )
    if table_rows:
        result = []
        for row in table_rows:
            m_id = row[0].strip()
            title = row[1].strip()
            deliv = row[3].strip() if len(row) > 3 else row[2].strip()
            duration_str = row[4].strip() if len(row) > 4 else "60"
            dep_str = row[5].strip() if len(row) > 5 else "Không"
            result.append({
                "milestone_id": m_id,
                "title": title,
                "deliverable": deliv,
                "estimated_minutes": _parse_int_minutes(duration_str),
                "depends_on": _parse_depends_on(dep_str),
            })
        if result:
            return result

    # Keep the workflow confirmable when the model is unavailable. The server
    # scheduler replaces this neutral milestone with task-aware decomposition
    # for multi-assignment plans.
    return [
        {
            "milestone_id": "M1",
            "title": "Đọc yêu cầu và xác định đầu ra",
            "deliverable": "Checklist yêu cầu cần hoàn thành",
            "estimated_minutes": 60,
            "depends_on": [],
        },
        {
            "milestone_id": "M2",
            "title": "Thực hiện và rà soát nhiệm vụ đã chọn",
            "deliverable": "Nhiệm vụ sẵn sàng để kiểm tra hoặc nộp",
            "estimated_minutes": 60,
            "depends_on": ["M1"],
        },
    ]


def _validate_model_milestone_scope(
    milestones: list[dict[str, Any]],
    expected_task_ids: set[str],
    allowed_source_refs_by_task: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """Reject ambiguous model decomposition before it reaches the scheduler.

    A milestone without an explicit task ID cannot be safely associated with an
    assignment. Positional/title-based matching is intentionally forbidden:
    model output must cover every selected task and may only reference those
    tasks. The caller replaces the entire response with deterministic
    milestones when this boundary validation fails.
    """
    errors: list[dict[str, Any]] = []
    if not milestones:
        errors.append({"code": "empty_milestones"})

    seen_milestone_ids: set[str] = set()
    covered_task_ids: set[str] = set()
    for index, milestone in enumerate(milestones):
        task_id = str(milestone.get("task_id") or "").strip()
        milestone_id = str(milestone.get("milestone_id") or "").strip()
        if not task_id:
            errors.append({"code": "missing_task_id", "index": index})
        elif task_id not in expected_task_ids:
            errors.append({"code": "unknown_task_id", "index": index})
        else:
            covered_task_ids.add(task_id)
            if allowed_source_refs_by_task is not None:
                source_refs = [str(value) for value in milestone.get("source_refs") or [] if str(value).strip()]
                if not source_refs:
                    errors.append({"code": "missing_source_refs", "index": index, "taskId": task_id})
                invalid_refs = sorted(set(source_refs) - allowed_source_refs_by_task.get(task_id, set()))
                if invalid_refs:
                    errors.append(
                        {
                            "code": "invalid_source_ref",
                            "index": index,
                            "taskId": task_id,
                            "sourceRefs": invalid_refs,
                        }
                    )
        if not milestone_id:
            errors.append({"code": "missing_milestone_id", "index": index})
        elif milestone_id in seen_milestone_ids:
            errors.append({"code": "duplicate_milestone_id", "milestoneId": milestone_id})
        else:
            seen_milestone_ids.add(milestone_id)

    for task_id in sorted(expected_task_ids - covered_task_ids):
        errors.append({"code": "missing_task_coverage", "taskId": task_id})

    return {
        "valid": not errors,
        "errors": errors,
        "expectedTaskIds": sorted(expected_task_ids),
        "coveredTaskIds": sorted(covered_task_ids),
        "fallbackApplied": bool(errors),
    }


def _apply_deterministic_adjustment(milestones: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """
    Áp dụng trực tiếp các chỉ thị số liệu rõ ràng trong câu hỏi của người dùng
    (ví dụ: 'giảm thời lượng xuống 45 phút' cho 'Milestone 3' hoặc 'M3').
    """
    updated = [dict(m) for m in milestones]
    q_lower = query.lower()

    # Tìm milestone mục tiêu: ví dụ Milestone 3, m3, m 3
    target_match = re.search(r"\b(?:milestone|mốc|m)\s*([0-9]+)\b", q_lower)
    if not target_match:
        return updated

    target_num = target_match.group(1)
    target_id_candidates = {f"M{target_num}", f"m{target_num}", target_num}

    # Tìm thời lượng yêu cầu: ví dụ '45 phút', '1 giờ', '30 min'
    time_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:phút|min|h|tiếng|giờ)", q_lower)
    new_minutes = None
    if time_match:
        new_minutes = _parse_int_minutes(time_match.group(0))

    for m in updated:
        curr_id = str(m.get("milestone_id", ""))
        if curr_id in target_id_candidates or curr_id.endswith(target_num):
            if new_minutes is not None:
                m["estimated_minutes"] = new_minutes
            if "dời" in q_lower or "ngày mai" in q_lower:
                m["status"] = "rescheduled"
                if "notes" not in m:
                    m["notes"] = "Đã dời theo yêu cầu của sinh viên"

    return updated


def plan_node(state: LearningGraphState) -> dict[str, Any]:
    """
    Milestone Agent: chia nhỏ assignment thành các milestone cụ thể và xếp ưu tiên.
    Hỗ trợ cả lập mới (Turn 1) và chỉnh sửa thông minh đa lượt (Multi-turn Refinement).
    Cập nhật dữ liệu có cấu trúc vào state["proposed_milestones"].
    """
    query = state.get("query") or ""
    if not query and state.get("messages"):
        last_msg = state["messages"][-1]
        query = last_msg.get("content", "") if isinstance(last_msg, dict) else getattr(last_msg, "content", "")

    if state.get("planning_stage") == "goal_proposal":
        candidates = _goal_candidates(
            state.get("assignments") or [],
            state.get("goals") or [],
        )
        response_text = ""
        provider_available = False
        if candidates:
            try:
                llm = get_agent_llm(temperature=0.2, max_tokens=900, task="plan")
                response = llm.invoke(
                    [
                        SystemMessage(content=WEEKLY_GOAL_SYSTEM_PROMPT),
                        HumanMessage(
                            content=(
                                "Dữ liệu nhiệm vụ chính thức đã giới hạn phạm vi:\n"
                                + json.dumps(_weekly_goal_context(candidates), ensure_ascii=False, indent=2)
                            )
                        ),
                    ]
                )
                response_text = str(response.content or "").strip()
                provider_available = True
            except Exception:
                response_text = ""
        weekly_goals = _extract_weekly_goals(response_text, candidates)
        model_covered = bool(weekly_goals) and all(
            goal.get("analysisSource") == "model" for goal in weekly_goals
        )
        source = "model" if provider_available and model_covered else "assignment_rule_fallback"
        titles = "\n".join(f"- {item['title']}" for item in weekly_goals)
        return {
            "current_node": "plan",
            "response": (
                "Plan Agent đề xuất các mục tiêu sau. Bạn có thể sửa, bỏ hoặc đổi ưu tiên trước khi lập lịch:\n"
                + (titles or "- Chưa có deadline mở trong dữ liệu LMS.")
            ),
            "analysis": (
                "Plan Agent đã phân tích assignment, module, rubric và tài liệu bài tập được gắn nguồn."
                if source == "model"
                else "Model chưa trả đầu ra hợp lệ; dùng mục tiêu an toàn từ assignment, deadline và trọng số."
            ),
            "status": "awaiting_student" if weekly_goals else "completed",
            "output": {
                "weekly_goals": weekly_goals,
                "plan_validation": {"valid": True, "errors": []},
                "goal_analysis": {
                    "source": source,
                    "fallbackApplied": source != "model",
                    "candidateTaskIds": [str(item.get("id")) for item in candidates],
                    "coveredTaskIds": sorted(
                        {task_id for goal in weekly_goals for task_id in goal.get("taskIds", [])}
                    ),
                },
            },
        }

    existing_milestones = state.get("proposed_milestones") or []
    q_lower = query.lower()
    normalized_query = normalize_text(query)
    pending_action = state.get("pending_action") or {}
    if pending_action.get("workflow") == "plan":
        if any(word in normalized_query for word in ("xac nhan", "dong y", "chap nhan", "confirm")):
            confirmed_plan = pending_action.get("payload", {})
            return {
                "current_node": "plan",
                "response": "Kế hoạch đã được xác nhận.",
                "status": "completed",
                "pending_action": None,
                "student_decision": {"action": "confirmed", "workflow": "plan"},
                "output": {"confirmed_plan": confirmed_plan},
            }
        if any(word in normalized_query for word in ("huy", "tu choi", "cancel")):
            return {
                "current_node": "plan",
                "response": "Đã hủy bản kế hoạch nháp; lịch hiện tại không bị thay đổi.",
                "status": "completed",
                "pending_action": None,
                "student_decision": {"action": "cancelled", "workflow": "plan"},
            }

    requested_goals = state.get("goals") or []
    requested_by_id = {
        str(item.get("task_id") or item.get("taskId") or ""): item
        for item in requested_goals
        if str(item.get("task_id") or item.get("taskId") or "")
    }
    selected_assignments = [
        item
        for item in (state.get("assignments") or [])
        if not requested_by_id or str(item.get("id") or "") in requested_by_id
    ]
    decomposition_routes = {
        str(item.get("id") or ""): assignment_structure(item)
        for item in selected_assignments
        if str(item.get("id") or "")
    }
    template_only = bool(decomposition_routes) and all(
        item["route"] == "template" for item in decomposition_routes.values()
    )
    rule_based_milestones = [
        milestone
        for assignment in selected_assignments
        for milestone in build_template_milestones(
            assignment,
            target_minutes=int(
                requested_by_id.get(str(assignment.get("id") or ""), {}).get("remaining_minutes")
                or requested_by_id.get(str(assignment.get("id") or ""), {}).get("remainingMin")
                or float(assignment.get("estimated_hours") or 1) * 60
            ),
        )
    ]
    template_milestones = rule_based_milestones if template_only else []
    expected_task_ids = {
        str(assignment.get("id") or "").strip()
        for assignment in selected_assignments
        if str(assignment.get("id") or "").strip()
    }
    allowed_milestone_sources = {
        str(assignment.get("id") or ""): {
            *_assignment_goal_source_refs(assignment),
            *(criterion["sourceRef"] for criterion in normalize_rubric_criteria(assignment)),
        }
        for assignment in selected_assignments
        if str(assignment.get("id") or "")
    }

    # Nhận diện nếu đây là lượt điều chỉnh kế hoạch đã có (Multi-turn Human-in-the-loop)
    is_adjustment = bool(
        existing_milestones
        and any(k in q_lower for k in ["dời", "giảm", "tăng", "sửa", "đổi", "chỉnh", "milestone", "thời lượng", "mốc", "m1", "m2", "m3", "m4"])
    )

    if template_only and not is_adjustment:
        llm = None
    else:
        try:
            llm = get_agent_llm(temperature=0.3, task="plan")
        except Exception:
            llm = None

    if is_adjustment:
        prompt_content = (
            f"BẠN ĐANG TRONG PHIÊN LÀM VIỆC ĐA LƯỢT VỚI SINH VIÊN (MULTI-TURN SESSION).\n"
            f"KẾ HOẠCH MILESTONES HIỆN TẠI:\n"
            f"{json.dumps(existing_milestones, ensure_ascii=False, indent=2)}\n\n"
            f"YÊU CẦU ĐIỀU CHỈNH: '{query}'\n\n"
            f"YÊU CẦU: Trả lời ngắn gọn, cập nhật milestone được yêu cầu, giữ nguyên các mốc khác. "
            f"MỌI milestone phải giữ đúng trường task_id hiện có và BẮT BUỘC kèm khối ```json danh sách milestones cập nhật."
        )
        default_analysis = f"Milestone Agent đã cập nhật kế hoạch ({len(existing_milestones)} milestones) theo yêu cầu chỉnh sửa."
    else:
        planning_context = {
            "assignments": state.get("assignments") or [],
            "availability": state.get("availability") or [],
            "unavailable_slots": state.get("unavailable_slots") or [],
            "goals": state.get("goals") or [],
            "learner_profile": state.get("learner_profile") or {},
            "mastery_profile": state.get("mastery_profile") or {},
            "misconceptions": state.get("misconceptions") or [],
        }
        prompt_content = (
            f"Nhiệm vụ của sinh viên: '{query}'\n\n"
            f"DỮ LIỆU LMS VÀ QUỸ THỜI GIAN ĐÃ XÁC THỰC:\n"
            f"{json.dumps(planning_context, ensure_ascii=False, indent=2)}\n\n"
            "Hãy chia TỪNG nhiệm vụ đã chọn thành số milestone phù hợp với loại và khối lượng công việc; "
            "không ép mọi nhiệm vụ thành 4 mốc. Mỗi milestone phải có task_id, title, deliverable, "
            "estimated_minutes, depends_on, rubric_criteria, knowledge_components, mapping_confidence "
            "và source_refs trỏ về assignment hoặc rubric đã dùng. Chỉ map knowledge component có trong "
            "dữ liệu chính thức; nếu chưa có thì đánh dấu đề xuất với confidence thấp. "
            "BẮT BUỘC đính kèm khối JSON ```json chứa danh sách milestones ở cuối bài."
        )
        default_analysis = "Milestone Agent đã phân rã lộ trình milestone mới."

    if template_only and not is_adjustment:
        response_text = "Nhiệm vụ đã có đủ cấu trúc; PaceWise dùng template kiểm chứng được thay vì gọi LLM để chia việc."
    elif llm:
        try:
            messages = [
                SystemMessage(content=MILESTONE_SYSTEM_PROMPT),
                HumanMessage(content=prompt_content),
            ]
            res = llm.invoke(messages)
            response_text = res.content.strip()
        except Exception:
            response_text = "Mình chưa thể tạo kế hoạch bằng AI lúc này; hệ thống sẽ dùng bản nháp an toàn để bạn kiểm tra."
    else:
        response_text = "[Thông báo]: Đang hoạt động ở chế độ fallback baseline."

    # Bóc tách milestones từ LLM. Model output is untrusted until every
    # milestone carries an exact task_id and every selected task is covered.
    extracted = template_milestones or _extract_milestones_from_text(response_text)
    model_output_validation: dict[str, Any] = {
        "valid": True,
        "errors": [],
        "expectedTaskIds": sorted(expected_task_ids),
        "coveredTaskIds": sorted(expected_task_ids),
        "fallbackApplied": False,
        "source": "deterministic_template" if template_only and not is_adjustment else "model",
    }
    if expected_task_ids and not (template_only and not is_adjustment):
        model_output_validation = {
            **_validate_model_milestone_scope(
                extracted,
                expected_task_ids,
                allowed_source_refs_by_task=allowed_milestone_sources,
            ),
            "source": "model",
        }
        if not model_output_validation["valid"]:
            # Fail closed: never guess task ownership from list position or
            # title similarity. Replace the whole decomposition immediately.
            extracted = rule_based_milestones
            model_output_validation["source"] = "rule_based_fallback"

    if is_adjustment:
        # Nếu LLM trả về danh sách đầy đủ
        if len(extracted) >= len(existing_milestones):
            proposed_milestones = extracted
        elif extracted:
            # Nếu LLM chỉ trả về milestone được sửa -> merge vào danh sách cũ
            id_map = {m["milestone_id"]: m for m in extracted}
            proposed_milestones = [id_map.get(m["milestone_id"], m) for m in existing_milestones]
        else:
            proposed_milestones = existing_milestones

        # Áp dụng chuẩn hóa số liệu theo câu lệnh người dùng
        proposed_milestones = _apply_deterministic_adjustment(proposed_milestones, query)
    else:
        proposed_milestones = extracted

    # Loại bỏ khối JSON thô để sinh viên chỉ nhìn thấy bảng lộ trình và lời khuyên dạng text/markdown
    clean_response = re.sub(r"```json[\s\S]*?```", "", response_text).strip()
    if not clean_response:
        clean_response = response_text
    if model_output_validation.get("fallbackApplied"):
        clean_response = (
            "Đầu ra phân rã tự động chưa gắn đúng từng nhiệm vụ. "
            "PaceWise đã chuyển ngay sang bản phân rã rule-based an toàn để bạn kiểm tra."
        )
        default_analysis = "MODEL_MILESTONE_SCOPE_INVALID_RULE_FALLBACK"

    validation = validate_plan_constraints(
        proposed_milestones,
        state.get("availability"),
        state.get("unavailable_slots"),
    )
    pending = None
    status = "awaiting_student"
    if validation["valid"]:
        pending = build_pending_action(
            "plan",
            "confirm_plan",
            {"milestones": proposed_milestones, "validation": validation},
        )
        clean_response += "\n\nKế hoạch này mới là bản nháp. Hãy xác nhận trước khi lưu."
    else:
        clean_response += (
            "\n\nKế hoạch chưa thể xác nhận vì vi phạm ràng buộc: "
            + ", ".join(error["code"] for error in validation["errors"])
        )

    return {
        "current_node": "plan",
        "response": clean_response,
        "proposed_milestones": proposed_milestones,
        "analysis": default_analysis,
        "status": status,
        "pending_action": pending,
        "validation_errors": validation["errors"],
        "output": {
            "plan_validation": validation,
            "decomposition_routes": decomposition_routes,
            "model_output_validation": model_output_validation,
        },
    }
