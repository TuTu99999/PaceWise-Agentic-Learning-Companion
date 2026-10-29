"""
Workflow Reflect: Phản tư và tổng kết tuần học.
Agent phụ trách: Reflection Agent.
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from copy import deepcopy
from statistics import median
from threading import BoundedSemaphore
from time import monotonic
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.guardrails import normalize_text
from src.agents.llm import get_agent_llm
from src.agents.prompts.reflection import REFLECTION_SYSTEM_PROMPT
from src.agents.state import LearningGraphState
from src.agents.validators import build_pending_action
from src.services.reflection_policy import (
    recommend_reflection,
    route_reflection,
    validate_hypothesis,
)

logger = logging.getLogger("pacewise.agents.reflect")
_REFLECT_MODEL_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pacewise-reflect")
_REFLECT_MODEL_SLOTS = BoundedSemaphore(8)


def _short(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _public_text(value: object, limit: int = 700) -> str:
    """Remove internal audit/entity identifiers from student-facing prose."""
    text = _short(value, limit)
    text = re.sub(r"\[?EV-[A-Za-z0-9-]+\]?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:SS|blk)-[A-Za-z0-9-]+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+:\d+\b", "", text)
    return re.sub(r"\s{2,}", " ", text).strip(" -–—,.;")


def _provider_report(value: object, limit: int = 1200) -> str:
    """Minimise the learner report before it leaves the backend boundary."""
    text = _public_text(value, limit)
    text = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[email]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<!\d)(?:\+?84|0)\d{9,10}(?!\d)", "[phone]", text)
    text = re.sub(r"https?://\S+", "[url]", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b(?:mssv|mã sinh viên|student\s*id)\s*[:#-]?\s*[A-Za-z0-9_-]+",
        "[student-id]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(?:tôi|em|mình)\s+(?:tên là|là)\s+[^,.;:\n]{2,80}",
        "[name]",
        text,
        flags=re.IGNORECASE,
    )
    return text


def _provider_evidence(evidence: dict) -> dict:
    """Return an anonymous fact bundle; identifiers never leave the backend."""
    allowed_record_fields = {
        "date",
        "status",
        "planned_minutes",
        "actual_minutes",
        "completion_percent",
        "remaining_minutes",
        "missed",
        "blocker",
        "unobserved_gap",
        "interruption_reason",
        "activity_type",
        "outcome",
        "time_source",
        "score",
        "level",
        "valid",
    }

    def anonymous_record(value: object) -> dict:
        if not isinstance(value, dict):
            return {}
        return {key: item for key, item in value.items() if key in allowed_record_fields}

    return {
        "scope": evidence.get("scope"),
        "week_start": evidence.get("week_start"),
        "week_end": evidence.get("week_end"),
        "period_complete": evidence.get("period_complete"),
        "data_status": evidence.get("data_status"),
        "totals": evidence.get("totals") or {},
        "activity": anonymous_record(evidence.get("activity")),
        "recent_session_details": [
            anonymous_record(item) for item in evidence.get("recent_session_details") or []
        ],
        "session_details_included": evidence.get("session_details_included", 0),
        "assessment_details": [
            anonymous_record(item) for item in evidence.get("assessment_details") or []
        ],
        "assessment_details_included": evidence.get("assessment_details_included", 0),
    }


def _invoke_with_deadline(llm: object, messages: list, deadline_seconds: float):
    """Bound user-visible latency and the number of lingering provider calls."""
    if not _REFLECT_MODEL_SLOTS.acquire(blocking=False):
        raise RuntimeError("reflect_model_capacity_busy")
    future = _REFLECT_MODEL_POOL.submit(llm.invoke, messages)
    future.add_done_callback(lambda _future: _REFLECT_MODEL_SLOTS.release())
    try:
        return future.result(timeout=deadline_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError("reflect_model_deadline_exceeded") from exc


def _compact_record(value: object) -> dict[str, Any]:
    """Keep only reflection facts that the model may cite or classify."""
    if not isinstance(value, dict):
        return {}
    keys = (
        "id", "block_id", "task_id", "course_id", "course_code", "date", "status",
        "planned_minutes", "actual_minutes", "completion_percent", "remaining_minutes",
        "missed", "blocker", "unobserved_gap", "interruption_reason", "activity_type",
        "readiness_key", "rhythm",
        "outcome", "time_source", "source_ref", "knowledge_component", "kc_id", "topic",
        "score", "level", "valid",
    )
    result: dict[str, Any] = {}
    for key in keys:
        item = value.get(key)
        if item is None or item == "" or item == []:
            continue
        result[key] = _short(item, 240) if isinstance(item, str) else item
    components = value.get("knowledge_components") or value.get("affected_kcs")
    if isinstance(components, list):
        result["knowledge_components"] = [_short(item, 160) for item in components[:20] if _short(item, 160)]
    return result


def _mastery_ids(profile: object) -> list[str]:
    if not isinstance(profile, dict):
        return []
    values: list[str] = []
    by_course = profile.get("__by_course__")
    sources = by_course.values() if isinstance(by_course, dict) else [profile]
    for source in sources:
        if not isinstance(source, dict):
            continue
        values.extend(_short(key, 160) for key in source if key and not str(key).startswith("__"))
    return list(dict.fromkeys(item for item in values if item))[:40]


def _reflection_model_context(progress_metrics: dict, mastery_profile: object) -> tuple[dict, set[str], set[str]]:
    """Build a compact provider payload while preserving server-owned totals.

    Top-level totals cover every observation in the selected period. Per-record
    detail is bounded because it is supporting context, not the source of totals.
    """
    sessions = [item for item in progress_metrics.get("sessions") or [] if isinstance(item, dict)]
    assessments = [
        item for item in progress_metrics.get("assessment_evidence") or [] if isinstance(item, dict)
    ]
    activity = _compact_record(progress_metrics.get("activity"))
    task_ids = {
        _short(item.get("task_id"), 160)
        for item in [progress_metrics.get("activity") or {}, *sessions]
        if isinstance(item, dict) and _short(item.get("task_id"), 160)
    }
    knowledge_ids = set(_mastery_ids(mastery_profile))
    for item in [progress_metrics.get("activity") or {}, *sessions, *assessments]:
        if not isinstance(item, dict):
            continue
        for key in ("knowledge_component", "kc_id", "topic"):
            if _short(item.get(key), 160):
                knowledge_ids.add(_short(item.get(key), 160))
        components = item.get("knowledge_components") or []
        if isinstance(components, list):
            knowledge_ids.update(_short(value, 160) for value in components if _short(value, 160))

    evidence = {
        "scope": "activity" if progress_metrics.get("reflection_scope") == "activity" else "weekly",
        "week_start": progress_metrics.get("week_start"),
        "week_end": progress_metrics.get("week_end"),
        "effective_week_start": progress_metrics.get("effective_week_start"),
        "period_complete": progress_metrics.get("period_complete"),
        "data_status": progress_metrics.get("data_status"),
        "totals": {
            "session_count": progress_metrics.get("session_count", len(sessions)),
            "missed_count": progress_metrics.get("missed_count"),
            "planned_minutes": progress_metrics.get("planned_minutes"),
            "actual_minutes": progress_metrics.get("actual_minutes"),
            "assessment_count": len(assessments),
        },
        "activity": activity,
        "recent_session_details": [_compact_record(item) for item in sessions[-24:]],
        "session_details_included": min(len(sessions), 24),
        "assessment_details": [_compact_record(item) for item in assessments[-12:]],
        "assessment_details_included": min(len(assessments), 12),
        "provenance": progress_metrics.get("provenance") or {},
        "warnings": progress_metrics.get("warnings") or [],
    }
    return evidence, task_ids, knowledge_ids


def _parse_reflection_json(text: str) -> dict[str, Any]:
    match = re.search(r"```json\s*([\s\S]*?)```", text)
    candidate = match.group(1) if match else text.strip()
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        candidate = candidate[start : end + 1] if start >= 0 and end > start else ""
    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _structured_answers(query: str, scope: str) -> dict[str, str]:
    labels = (
        {
            "effective": ("Kết quả sau hoạt động:", "Activity outcome:"),
            "difficulty": ("Điều hỗ trợ hoặc gây khó khăn:", "What helped or caused difficulty:"),
            "next_step": ("Bước tiếp theo:", "Next step:"),
        }
        if scope == "activity"
        else {
            "effective": ("Điều hiệu quả:", "What worked:"),
            "deviation_cause": ("Nguyên nhân lệch:", "Reason for plan drift:"),
            "adjustment": ("Điều chỉnh tuần sau:", "Adjustment for next week:"),
        }
    )
    result: dict[str, str] = {}
    for line in query.splitlines():
        for key, aliases in labels.items():
            for label in aliases:
                if line.startswith(label):
                    result[key] = _short(line[len(label) :], 700)
                    break
    return result if result and all(key in result for key in labels) else {}


def _calibration(metrics: dict) -> tuple[int, float]:
    """Return reliable homogeneous timing evidence and its median ratio."""
    contexts: dict[tuple, list[float]] = {}
    for item in metrics.get("sessions") or []:
        if not isinstance(item, dict):
            continue
        rhythm = item.get("rhythm") if isinstance(item.get("rhythm"), dict) else {}
        reference = item.get("session_id") or item.get("block_id") or item.get("source_ref")
        interrupted = item.get("interruption_reason") not in {None, "none"}
        reliable = (
            item.get("time_source") == "timer"
            and item.get("completion_percent") == 100
            and item.get("blocker", "none") == "none"
            and not item.get("unobserved_gap")
            and not interrupted
            and bool(reference)
            and bool(item.get("readiness_key"))
            and bool(rhythm.get("sessionMinutes"))
            and bool(rhythm.get("breakMinutes"))
        )
        try:
            planned = float(item.get("planned_minutes") or 0)
            actual = float(item.get("actual_minutes") or 0)
        except (TypeError, ValueError):
            planned = actual = 0
        if not reliable or planned <= 0 or actual <= 0:
            continue
        key = (
            item.get("task_id"),
            item.get("activity_type", "unknown"),
            item.get("readiness_key"),
            rhythm.get("sessionMinutes"),
            rhythm.get("breakMinutes"),
        )
        contexts.setdefault(key, []).append(actual / planned)
    ratios = max(contexts.values(), key=len, default=[])
    return len(ratios), round(min(1.5, max(0.75, median(ratios))), 2) if ratios else 1.0


def _remaining_minutes(metrics: dict) -> int:
    values = []
    for item in metrics.get("sessions") or []:
        if not isinstance(item, dict):
            continue
        try:
            values.append(max(0, min(1440, int(float(item.get("remaining_minutes") or 0)))))
        except (TypeError, ValueError):
            continue
    if not values and isinstance(metrics.get("activity"), dict):
        try:
            values.append(max(0, min(1440, int(float(metrics["activity"].get("remaining_minutes") or 0)))))
        except (TypeError, ValueError):
            pass
    return sum(values)


def _date_label(value: object) -> str:
    text = _short(value, 10)
    return f"{text[8:10]}/{text[5:7]}" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else text


def _weekly_response(
    draft: dict,
    metrics: dict,
    calibration_count: int,
    recommendation: dict,
    locale: str = "vi",
) -> str:
    sessions = [item for item in metrics.get("sessions") or [] if isinstance(item, dict)]
    count = int(metrics.get("session_count") or len(sessions))
    planned = int(round(float(metrics.get("planned_minutes") or 0)))
    actual = int(round(float(metrics.get("actual_minutes") or 0)))
    start, end = _date_label(metrics.get("week_start")), _date_label(metrics.get("week_end"))
    period = f" {start}–{end}" if start and end else ""
    if locale == "en":
        parts = [
            f"For the week{period}, the system recorded {count} Do session{'s' if count != 1 else ''}: "
            f"{planned} planned minutes and {actual} actual minutes."
        ]
        if len(sessions) == 1:
            session = sessions[0]
            completion = session.get("completion_percent")
            remaining = _remaining_minutes(metrics)
            if completion is not None:
                sentence = f"You reported {int(float(completion))}% completion for this session"
                sentence += f", with about {remaining} minutes remaining." if remaining else "."
                parts.append(sentence)
        if draft.get("effective"):
            parts.append(f"What worked: {_public_text(draft['effective'])}.")
        if draft.get("deviation_cause"):
            parts.append(f"Reported cause: {_public_text(draft['deviation_cause'])}.")
        if calibration_count < 3:
            parts.append("Observed data is not stable enough, so PaceWise has not changed the general duration factor.")
        else:
            parts.append(f"{calibration_count} comparable sessions meet the requirements for duration calibration.")
        action = recommendation.get("action")
        minutes = int(recommendation.get("minutes") or 0)
        if action == "complete_remaining_work" and minutes:
            parts.append(f"Safe suggestion: schedule one {minutes}-minute session to finish the remaining work and check understanding again.")
        elif action == "review_verified_kc" and minutes:
            parts.append(f"Suggestion based on verified assessment evidence: spend {minutes} minutes reviewing the related knowledge.")
        elif action == "recover_schedule":
            parts.append("This suggestion affects the schedule; PaceWise will use Recover to check capacity before creating a new draft.")
        elif recommendation.get("duration_factor") != 1.0:
            factor = str(recommendation["duration_factor"])
            parts.append(f"Comparable sessions now provide enough evidence; the backend suggests a duration factor of {factor} for your review.")
        else:
            parts.append("Safe suggestion: keep one small change next week and review it again after more Do evidence is available.")
        return "\n\n".join(parts)

    parts = [
        f"Tuần{period}, hệ thống ghi nhận {count} phiên Do: {planned} phút dự kiến và {actual} phút thực tế."
    ]
    if len(sessions) == 1:
        session = sessions[0]
        completion = session.get("completion_percent")
        remaining = _remaining_minutes(metrics)
        if completion is not None:
            sentence = f"Bạn tự đánh giá phiên này hoàn thành {int(float(completion))}%"
            sentence += f" và còn khoảng {remaining} phút." if remaining else "."
            parts.append(sentence)
    if draft.get("effective"):
        parts.append(f"Bạn ghi nhận điều hiệu quả: {_public_text(draft['effective'])}.")
    if draft.get("deviation_cause"):
        parts.append(f"Nguyên nhân bạn ghi nhận: {_public_text(draft['deviation_cause'])}.")

    if calibration_count < 3:
        parts.append(
            "Dữ liệu quan sát chưa đủ ổn định, vì vậy PaceWise chưa điều chỉnh hệ số thời lượng chung."
        )
    else:
        parts.append(f"Có {calibration_count} phiên tương đồng đủ điều kiện để hiệu chỉnh thời lượng.")

    adjustment = normalize_text(draft.get("student_adjustment") or draft.get("adjustment") or "")
    if any(value in adjustment for value in ("buoi sang", "buoi chieu", "buoi toi", "chieu", "toi")):
        parts.append(
            "Khung giờ bạn chọn được ghi nhận là sở thích cá nhân, chưa phải bằng chứng rằng đó là khung học hiệu quả nhất."
        )
    action = recommendation.get("action")
    minutes = int(recommendation.get("minutes") or 0)
    if action == "complete_remaining_work" and minutes:
        parts.append(
            f"Đề xuất an toàn: dành một phiên {minutes} phút để hoàn tất phần còn lại và kiểm tra lại mức độ hiểu bài."
        )
    elif action == "review_verified_kc" and minutes:
        parts.append(
            f"Đề xuất dựa trên assessment đã xác minh: dành {minutes} phút ôn lại phần kiến thức liên quan."
        )
    elif action == "recover_schedule":
        parts.append("Đề xuất này ảnh hưởng lịch; PaceWise sẽ chuyển sang Recover để kiểm tra capacity trước khi dựng lịch mới.")
    elif recommendation.get("duration_factor") != 1.0:
        factor = str(recommendation["duration_factor"]).replace(".", ",")
        parts.append(
            f"Các phiên tương đồng đã đủ bằng chứng; backend đề xuất hệ số thời lượng {factor} để sinh viên xem xét."
        )
    else:
        parts.append("Đề xuất an toàn: giữ một thay đổi nhỏ trong tuần tới và đánh giá lại sau khi có thêm dữ liệu Do.")
    return "\n\n".join(parts)


def _recommendation_label(recommendation: dict, locale: str = "vi") -> str:
    action = recommendation.get("action")
    minutes = int(recommendation.get("minutes") or 0)
    if locale == "en":
        if action == "complete_remaining_work" and minutes:
            return f"Use one {minutes}-minute session to finish the remaining work and check understanding again."
        if action == "review_verified_kc" and minutes:
            return f"Spend {minutes} minutes reviewing knowledge verified by the assessment."
        if action == "recover_schedule":
            return "Use Recover to check capacity and create a new schedule draft."
        if recommendation.get("duration_factor") != 1.0:
            return f"Use a duration factor of {recommendation['duration_factor']} for comparable sessions with sufficient evidence."
        return "Keep the current plan and collect more evidence before making changes."
    if action == "complete_remaining_work" and minutes:
        return f"Dành một phiên {minutes} phút để hoàn tất phần còn lại và kiểm tra lại mức độ hiểu bài."
    if action == "review_verified_kc" and minutes:
        return f"Dành {minutes} phút ôn lại KC đã được assessment xác minh."
    if action == "recover_schedule":
        return "Chuyển sang Recover để kiểm tra capacity và dựng bản lịch mới."
    if recommendation.get("duration_factor") != 1.0:
        factor = str(recommendation["duration_factor"]).replace(".", ",")
        return f"Dùng hệ số thời lượng {factor} cho nhóm phiên tương đồng đã đủ bằng chứng."
    return "Giữ kế hoạch hiện tại và thu thập thêm bằng chứng trước khi điều chỉnh."


def reflect_node(state: LearningGraphState) -> dict:
    """
    Reflection Agent: Tổng kết tuần dựa trên dữ kiện khách quan và đề xuất 1 điều chỉnh cho tuần sau.
    """
    query = state.get("query") or ""
    if not query and state.get("messages"):
        last_msg = state["messages"][-1]
        query = last_msg.get("content", "") if isinstance(last_msg, dict) else getattr(last_msg, "content", "")

    normalized_query = normalize_text(query)
    locale = "en" if str((state.get("request") or {}).get("locale") or "vi").lower() == "en" else "vi"
    progress_metrics = deepcopy(state.get("progress_metrics") or {})
    scope = "activity" if progress_metrics.get("reflection_scope") == "activity" else "weekly"
    model_evidence, trusted_task_ids, trusted_kcs = _reflection_model_context(
        progress_metrics,
        state.get("mastery_profile") or {},
    )
    pending_action = state.get("pending_action") or {}
    if pending_action.get("workflow") == "reflect" and any(
        word in normalized_query for word in ("xac nhan", "dong y", "chap nhan", "confirm")
    ):
        draft = pending_action.get("payload") or {}
        activity_scope = draft.get("scope") == "activity"
        recommendation = draft.get("recommendation") or {}
        handoff = (
            {
                "next_workflow": "recover",
                "reason": recommendation.get("reason"),
                "task_id": recommendation.get("task_id", ""),
                "requested_minutes": recommendation.get("minutes", 0),
            }
            if recommendation.get("requires_recover")
            else None
        )
        return {
            "current_node": "reflect",
            "response": (
                "The activity reflection was saved. Its schedule-impacting suggestion was sent to Recover to create a draft."
                if locale == "en" and activity_scope and handoff
                else "The activity reflection was saved."
                if locale == "en" and activity_scope
                else "The weekly reflection was saved. Its schedule-impacting suggestion was sent to Recover to create a draft."
                if locale == "en" and handoff
                else "The adjustment for next week was confirmed."
                if locale == "en"
                else "Ghi nhận sau hoạt động đã được lưu. Đề xuất ảnh hưởng lịch đã được chuyển sang Recover để dựng bản nháp."
                if activity_scope and handoff
                else "Ghi nhận sau hoạt động đã được lưu."
                if activity_scope
                else "Bản phản tư đã được lưu. Đề xuất ảnh hưởng lịch đã được chuyển sang Recover để dựng bản nháp."
                if handoff
                else "Điều chỉnh cho tuần sau đã được xác nhận."
            ),
            "reflection_draft": draft,
            "pending_action": None,
            "status": "completed",
            "student_decision": {"action": "confirmed", "workflow": "reflect"},
            "output": {"reflect_handoff": handoff} if handoff else {},
        }

    direct_answers = _structured_answers(query, scope)
    route = route_reflection(scope, progress_metrics, query)
    model_status = "ok"
    try:
        complex_route = route["complexity"] == "complex"
        # Measured with the exact deidentified Reflect contract. These deadlines
        # absorb normal proxy jitter without returning to the old 15-second path.
        deadline_seconds = 12.0 if complex_route else (8.0 if scope == "activity" else 8.5)
        model_started = monotonic()
        llm = get_agent_llm(
            temperature=0.1,
            max_tokens=180,
            task="reflect",
            complexity=route["complexity"],
            timeout=deadline_seconds,
            max_retries=0,
        )
        messages = [
            SystemMessage(content=REFLECTION_SYSTEM_PROMPT),
            HumanMessage(
                content=json.dumps(
                    {
                        "scope": scope,
                        "ROUTE": route,
                        "STUDENT_REPORT": _provider_report(query),
                        "SERVER_EVIDENCE": _provider_evidence(model_evidence),
                        "IDENTIFIERS_AVAILABLE": False,
                        "OUTPUT_LANGUAGE": "English" if locale == "en" else "Vietnamese",
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            ),
        ]
        remaining_budget = deadline_seconds - (monotonic() - model_started)
        if remaining_budget <= 0:
            raise TimeoutError("reflect_model_setup_deadline_exceeded")
        res = _invoke_with_deadline(llm, messages, remaining_budget)
        response_text = res.content.strip()
    except Exception as exc:
        model_status = "fallback"
        logger.warning(
            "reflect_model_fallback scope=%s tier=%s deadline_seconds=%.1f error_type=%s",
            scope,
            route["model_tier"],
            deadline_seconds,
            type(exc).__name__,
        )
        # A provider timeout must not block Reflect. Keep the learner's words
        # local and let deterministic policy create the recommendation.
        response_text = json.dumps(
            {
                "effective": direct_answers.get("effective", ""),
                "difficulty": direct_answers.get("difficulty")
                or direct_answers.get("deviation_cause")
                or _short(query, 700),
                "cause": "unknown",
                "confidence": 0.0,
                "recommended_action": "collect_more_evidence",
                "rationale": (
                    "No model analysis is available; the backend is using verified facts only."
                    if locale == "en"
                    else "Chưa có phân tích mô hình; backend chỉ dùng dữ kiện đã xác minh."
                ),
                "task_id": "",
                "affected_kcs": [],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    if scope == "activity":
        reflection_draft = {
            "scope": "activity",
            "activity": progress_metrics.get("activity") or {},
            "effective": "",
            "difficulty": "",
            "next_step": "Keep the next step small and specific." if locale == "en" else "Giữ một bước tiếp theo nhỏ và cụ thể.",
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
    else:
        reflection_draft = {
            "scope": "weekly",
            "effective": "",
            "deviation_cause": "",
            "adjustment": "Keep one small, specific change for next week." if locale == "en" else "Giữ một thay đổi nhỏ, cụ thể cho tuần sau.",
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
    parsed = _parse_reflection_json(response_text)
    claimed = parsed.get("evidence") if parsed else None
    evidence_conflict = claimed is not None and not _agrees(claimed, progress_metrics)
    hypothesis, validation_warnings = validate_hypothesis(
        parsed,
        metrics=progress_metrics,
        trusted_task_ids=trusted_task_ids,
        trusted_kcs=trusted_kcs,
    )
    for key in ("effective", "difficulty", "rationale"):
        hypothesis[key] = _public_text(hypothesis.get(key), 700)
    if evidence_conflict:
        hypothesis.update(
            effective="",
            difficulty="",
            rationale="",
            cause="unknown",
            confidence=0.0,
            recommended_action="collect_more_evidence",
            task_id="",
            affected_kcs=[],
        )
        validation_warnings.append("MODEL_EVIDENCE_CONFLICT")

    calibration_count, calibration_factor = _calibration(progress_metrics)
    recommendation, signal = recommend_reflection(
        hypothesis,
        metrics=progress_metrics,
        calibration_count=calibration_count,
        calibration_factor=calibration_factor,
        trusted_task_ids=trusted_task_ids,
    )
    reflection_draft["hypothesis"] = hypothesis
    reflection_draft["recommendation"] = recommendation
    reflection_draft["planning_signal"] = signal
    reflection_draft["routing"] = route
    reflection_draft["model_status"] = model_status
    reflection_draft["timing_evidence_count"] = calibration_count
    reflection_draft["validation_warnings"] = list(dict.fromkeys(validation_warnings))
    reflection_draft["effective"] = hypothesis["effective"] or direct_answers.get("effective", "")
    if scope == "activity":
        reflection_draft["difficulty"] = hypothesis["difficulty"] or direct_answers.get("difficulty", "")
        reflection_draft["next_step"] = _recommendation_label(recommendation, locale)
    else:
        reflection_draft["deviation_cause"] = (
            hypothesis["difficulty"] or direct_answers.get("deviation_cause", "")
        )
        reflection_draft["student_adjustment"] = direct_answers.get("adjustment", "")
        reflection_draft["adjustment"] = _recommendation_label(recommendation, locale)

    if scope == "activity":
        clean_response = "\n".join(
            item for item in (
                f"What worked: {_public_text(reflection_draft['effective'])}" if locale == "en" and reflection_draft["effective"] else f"Điều hiệu quả: {_public_text(reflection_draft['effective'])}" if reflection_draft["effective"] else "",
                f"What remains difficult: {_public_text(reflection_draft['difficulty'])}" if locale == "en" and reflection_draft["difficulty"] else f"Điểm còn khó: {_public_text(reflection_draft['difficulty'])}" if reflection_draft["difficulty"] else "",
                f"Next step: {_public_text(reflection_draft['next_step'])}" if locale == "en" else f"Bước tiếp theo: {_public_text(reflection_draft['next_step'])}",
            ) if item
        )
    else:
        clean_response = _weekly_response(
            reflection_draft,
            progress_metrics,
            calibration_count,
            recommendation,
            locale,
        )
    if evidence_conflict:
        # Suppress model prose, but retain the server-owned recommendation.
        clean_response = (
            "The AI returned figures that did not match the record. That commentary was removed; the original facts and backend suggestion were retained."
            if locale == "en"
            else "AI đưa ra số liệu không khớp bản ghi. Đã loại bỏ nhận xét đó; dữ kiện gốc và đề xuất backend được giữ nguyên."
        )
    pending = build_pending_action(
        "reflect",
        "save_activity_reflection" if scope == "activity" else "confirm_adjustment",
        reflection_draft,
    )

    suffix = (
        "\n\nConfirm before saving this activity reflection."
        if locale == "en" and scope == "activity"
        else "\n\nConfirm before applying the adjustment for next week."
        if locale == "en"
        else "\n\nHãy xác nhận trước khi lưu ghi nhận cho hoạt động này."
        if scope == "activity"
        else "\n\nHãy xác nhận trước khi áp dụng điều chỉnh cho tuần sau."
    )

    return {
        "current_node": "reflect",
        "response": clean_response + suffix,
        "analysis": (
            "Reflection Agent recorded the activity outcome, obstacle, and next step."
            if locale == "en" and scope == "activity"
            else "Reflection Agent summarized objective evidence and suggested one adjustment."
            if locale == "en"
            else "Reflection Agent đã ghi nhận kết quả, trở ngại và bước tiếp theo của một hoạt động."
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
