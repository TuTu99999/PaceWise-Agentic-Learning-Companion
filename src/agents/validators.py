"""Deterministic validators for plans, citations, assessments and HITL actions."""

from __future__ import annotations

import re
from typing import Any

from src.agents.tools.schedule_calculator import calculate_available_hours


def validate_plan_constraints(
    milestones: list[dict[str, Any]],
    availability: list[dict[str, Any]] | None = None,
    unavailable_slots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    ids = [str(item.get("milestone_id", "")).strip() for item in milestones]
    known_ids = {item_id for item_id in ids if item_id}

    if not milestones:
        errors.append({"code": "EMPTY_PLAN", "message": "Kế hoạch chưa có milestone."})
    if len(known_ids) != len(ids):
        errors.append({"code": "DUPLICATE_OR_EMPTY_ID", "message": "Milestone phải có mã duy nhất."})

    total_minutes = 0
    dependency_graph: dict[str, list[str]] = {}
    for item in milestones:
        item_id = str(item.get("milestone_id", "")).strip()
        try:
            minutes = int(item.get("estimated_minutes", 0))
        except (TypeError, ValueError):
            minutes = 0
        if minutes <= 0:
            errors.append({"code": "INVALID_DURATION", "milestone_id": item_id})
        total_minutes += max(0, minutes)
        dependencies = [str(dep) for dep in item.get("depends_on", [])]
        dependency_graph[item_id] = dependencies
        missing = [dep for dep in dependencies if dep not in known_ids]
        if missing:
            errors.append({"code": "UNKNOWN_DEPENDENCY", "milestone_id": item_id, "dependencies": missing})

    visiting: set[str] = set()
    visited: set[str] = set()

    def has_cycle(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(has_cycle(dep) for dep in dependency_graph.get(node, []) if dep in dependency_graph):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    if any(has_cycle(node) for node in dependency_graph):
        errors.append({"code": "CYCLIC_DEPENDENCY", "message": "Quan hệ phụ thuộc tạo thành vòng lặp."})

    available_hours = calculate_available_hours(availability or [], unavailable_slots or [])
    required_hours = round(total_minutes / 60.0, 2)
    if availability and required_hours > available_hours:
        errors.append(
            {
                "code": "CAPACITY_EXCEEDED",
                "required_hours": required_hours,
                "available_hours": available_hours,
                "shortage_hours": round(required_hours - available_hours, 2),
            }
        )
    return {
        "valid": not errors,
        "errors": errors,
        "required_hours": required_hours,
        "available_hours": available_hours,
    }


def extract_citations(text: str) -> list[str]:
    return re.findall(
        r"\[[^\[\]\n\(\)]+?(?:,\s*Trang\s+\d+|,\s*Slide\s+\d+)(?:,\s*Đoạn\s+\d+)?\]",
        text or "",
        flags=re.IGNORECASE,
    )


def validate_citations(response: str, passages: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {str(item.get("citation", "")).strip() for item in passages if item.get("citation")}
    cited = set(extract_citations(response))

    # Bổ sung các expected citations xuất hiện trực tiếp trong văn bản response
    for exp in expected:
        if exp and exp in response:
            cited.add(exp)

    # Loại bỏ các chuỗi không phải là citation tài liệu (ví dụ markdown link labels)
    invalid = sorted(c for c in cited if c not in expected)
    valid = sorted(c for c in cited if c in expected)
    return {
        "valid": bool(expected) and bool(valid) and not invalid,
        "citations": sorted(cited),
        "valid_citations": valid,
        "invalid_citations": invalid,
        "coverage": round(len(valid) / len(expected), 4) if expected else 0.0,
    }


def validate_assessment_result(result: dict[str, Any], rubric: list[dict[str, Any]]) -> dict[str, Any]:
    valid_statuses = {"chưa đủ bằng chứng", "còn nhầm lẫn", "đang hình thành", "đã thể hiện được"}
    confidence = str(result.get("confidence", "Thấp"))
    evidence = [str(item).strip() for item in result.get("evidence_quotes", []) if str(item).strip()]
    reasons: list[str] = []
    if result.get("status") not in valid_statuses:
        reasons.append("invalid_status")
    if not rubric:
        reasons.append("missing_approved_rubric")
    if not evidence:
        reasons.append("missing_evidence")
    evaluator_version = str(result.get("evaluator_version") or "").strip()
    if not evaluator_version:
        reasons.append("missing_evaluator_version")
    dimensions = result.get("dimensions") or {}
    allowed_dimension_states = {"passed", "failed", "developing", "not_tested"}
    if not isinstance(dimensions, dict) or any(
        str(value).casefold() not in allowed_dimension_states
        for value in dimensions.values()
    ):
        reasons.append("invalid_dimensions")
    if confidence.lower() in {"thấp", "low"}:
        reasons.append("low_confidence")
    return {"valid": not reasons, "requires_instructor_review": bool(reasons), "reasons": reasons}


def validate_recovery_options(
    options: list[dict[str, Any]],
    assignments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate recovery schema and protection of known important deadlines."""
    errors: list[dict[str, Any]] = []
    required_fields = {
        "option_name",
        "kept_items",
        "moved_items",
        "hours_short_or_free",
        "protected_deadlines",
        "remaining_risks",
    }
    if len(options) < 2:
        errors.append({"code": "INSUFFICIENT_OPTIONS", "minimum": 2})

    protected_values: set[str] = set()
    for index, option in enumerate(options):
        missing = sorted(field for field in required_fields if field not in option)
        if missing:
            errors.append({"code": "MISSING_FIELDS", "option_index": index, "fields": missing})
        protected = option.get("protected_deadlines", [])
        if not isinstance(protected, list) or not protected:
            errors.append({"code": "MISSING_PROTECTED_DEADLINE", "option_index": index})
        else:
            protected_values.update(str(value).strip().casefold() for value in protected if str(value).strip())

    missing_assignments: list[str] = []
    for assignment in assignments or []:
        identifiers: set[str] = set()
        for field in ("title", "name", "deadline", "due_at"):
            value = str(assignment.get(field, "")).strip()
            if value:
                identifiers.add(value.casefold())
        if identifiers and identifiers.isdisjoint(protected_values):
            missing_assignments.append(str(assignment.get("id") or assignment.get("title") or "unknown"))
    if missing_assignments:
        errors.append({"code": "UNPROTECTED_DEADLINE", "assignments": missing_assignments})

    return {
        "valid": not errors,
        "errors": errors,
        "protected_deadline_count": len(protected_values),
    }


def build_pending_action(workflow: str, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow": workflow,
        "type": action_type,
        "payload": payload,
        "requires_confirmation": True,
    }
