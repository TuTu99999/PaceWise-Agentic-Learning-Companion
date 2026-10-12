"""Course-scoped instructor workspace projections and validation.

Instructor mutations are persisted as immutable ``InstructorAction`` rows.  This
module folds those events into a stable projection used by the UI and student
calendar sync.  LMS-owned records never enter this write path.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException

from src.persistence_models import InstructorAction

INSTRUCTOR_WORKSPACE_ACTIONS = {
    "schedule",
    "course_structure",
    "feedback",
    "settings",
}
SCHEDULE_TYPES = {
    "offline",
    "online",
    "practice",
    "review",
    "quiz",
    "office_hour",
    "other",
}
FEEDBACK_SCOPES = {"class", "group"}
FEEDBACK_KINDS = {"guidance", "resource", "reassessment", "intervention"}


def _text(value: Any, *, field: str, maximum: int = 500, required: bool = True) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise HTTPException(status_code=422, detail=f"{field} is required")
    if len(result) > maximum:
        raise HTTPException(status_code=422, detail=f"{field} exceeds {maximum} characters")
    return result


def _iso_datetime(value: Any, *, field: str) -> str:
    result = _text(value, field=field, maximum=64)
    try:
        datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field} must be an ISO datetime") from exc
    return result


def _string_list(value: Any, *, field: str, maximum: int = 50) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > maximum:
        raise HTTPException(status_code=422, detail=f"{field} must be a list of at most {maximum} items")
    return [_text(item, field=field, maximum=128) for item in value]


def _integer(
    value: Any,
    *,
    field: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        result = int(default if value is None or value == "" else value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field} must be an integer") from exc
    if result < minimum or result > maximum:
        raise HTTPException(
            status_code=422,
            detail=f"{field} must be between {minimum} and {maximum}",
        )
    return result


def _schedule_payload(payload: dict[str, Any]) -> dict[str, Any]:
    operation = str(payload.get("operation") or "upsert")
    if operation == "delete":
        return {"operation": "delete"}
    source = str(payload.get("source") or "pacewise")
    if source != "pacewise":
        raise HTTPException(status_code=409, detail="LMS-owned schedule items are read-only in PaceWise")
    event_type = str(payload.get("type") or "offline")
    if event_type not in SCHEDULE_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported teaching event type")
    starts_at = _iso_datetime(payload.get("startAt"), field="startAt")
    ends_at = _iso_datetime(payload.get("endAt"), field="endAt")
    start = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
    if end <= start:
        raise HTTPException(status_code=422, detail="endAt must be after startAt")
    recurrence = str(payload.get("recurrence") or "none")
    if recurrence not in {"none", "weekly"}:
        raise HTTPException(status_code=422, detail="Unsupported recurrence")
    recurrence_count = _integer(
        payload.get("recurrenceCount"),
        field="recurrenceCount",
        default=12,
        minimum=1,
        maximum=24,
    )
    status = str(payload.get("status") or "scheduled")
    if status not in {"scheduled", "cancelled"}:
        raise HTTPException(status_code=422, detail="Unsupported schedule status")
    return {
        "operation": "upsert",
        "title": _text(payload.get("title"), field="title", maximum=160),
        "type": event_type,
        "startAt": starts_at,
        "endAt": ends_at,
        "location": _text(payload.get("location"), field="location", maximum=160, required=False),
        "meetingUrl": _text(payload.get("meetingUrl"), field="meetingUrl", maximum=500, required=False),
        "moduleId": _text(payload.get("moduleId"), field="moduleId", maximum=128, required=False),
        "knowledgeComponentIds": _string_list(
            payload.get("knowledgeComponentIds"), field="knowledgeComponentIds"
        ),
        "preparation": _text(
            payload.get("preparation"), field="preparation", maximum=1000, required=False
        ),
        "recurrence": recurrence,
        "recurrenceCount": recurrence_count,
        "status": status,
        "source": "pacewise",
    }


def _course_structure_payload(payload: dict[str, Any]) -> dict[str, Any]:
    modules = payload.get("modules") or []
    components = payload.get("knowledgeComponents") or []
    if not isinstance(modules, list) or not isinstance(components, list):
        raise HTTPException(status_code=422, detail="modules and knowledgeComponents must be lists")
    if len(modules) > 100 or len(components) > 500:
        raise HTTPException(status_code=422, detail="Course structure is too large")

    normalized_modules: list[dict[str, Any]] = []
    module_ids: set[str] = set()
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            raise HTTPException(status_code=422, detail="Each module must be an object")
        module_id = _text(module.get("id"), field="module.id", maximum=128)
        if module_id in module_ids:
            raise HTTPException(status_code=422, detail=f"Duplicate module id: {module_id}")
        module_ids.add(module_id)
        normalized_modules.append(
            {
                "id": module_id,
                "title": _text(module.get("title"), field="module.title", maximum=160),
                "description": _text(
                    module.get("description"), field="module.description", maximum=1000, required=False
                ),
                "position": _integer(
                    module.get("position"),
                    field="module.position",
                    default=index + 1,
                    minimum=1,
                    maximum=100,
                ),
            }
        )

    normalized_components: list[dict[str, Any]] = []
    component_ids: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            raise HTTPException(status_code=422, detail="Each knowledge component must be an object")
        component_id = _text(component.get("id"), field="knowledgeComponent.id", maximum=128)
        if component_id in component_ids:
            raise HTTPException(status_code=422, detail=f"Duplicate knowledge component id: {component_id}")
        component_ids.add(component_id)
        module_id = _text(
            component.get("moduleId"), field="knowledgeComponent.moduleId", maximum=128
        )
        if module_id not in module_ids:
            raise HTTPException(status_code=422, detail=f"Unknown module id: {module_id}")
        status = str(component.get("status") or "approved")
        if status not in {"approved", "provisional"}:
            raise HTTPException(status_code=422, detail="Unsupported knowledge component status")
        normalized_components.append(
            {
                "id": component_id,
                "moduleId": module_id,
                "name": _text(component.get("name"), field="knowledgeComponent.name", maximum=160),
                "description": _text(
                    component.get("description"),
                    field="knowledgeComponent.description",
                    maximum=1000,
                    required=False,
                ),
                "prerequisiteIds": _string_list(
                    component.get("prerequisiteIds"), field="prerequisiteIds"
                ),
                "objectives": _string_list(component.get("objectives"), field="objectives"),
                "misconceptions": _string_list(
                    component.get("misconceptions"), field="misconceptions"
                ),
                "status": status,
            }
        )

    for component in normalized_components:
        unknown = set(component["prerequisiteIds"]) - component_ids
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown prerequisite ids: {', '.join(sorted(unknown))}",
            )
        if component["id"] in component["prerequisiteIds"]:
            raise HTTPException(status_code=422, detail="A knowledge component cannot require itself")
    dependencies = {
        component["id"]: set(component["prerequisiteIds"])
        for component in normalized_components
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(component_id: str) -> None:
        if component_id in visiting:
            raise HTTPException(status_code=422, detail="Knowledge component prerequisites contain a cycle")
        if component_id in visited:
            return
        visiting.add(component_id)
        for prerequisite_id in dependencies.get(component_id, set()):
            visit(prerequisite_id)
        visiting.remove(component_id)
        visited.add(component_id)

    for component_id in dependencies:
        visit(component_id)
    return {"modules": normalized_modules, "knowledgeComponents": normalized_components}


def _feedback_payload(payload: dict[str, Any]) -> dict[str, Any]:
    scope = str(payload.get("scope") or "class")
    kind = str(payload.get("kind") or "guidance")
    if scope not in FEEDBACK_SCOPES:
        raise HTTPException(status_code=422, detail="Unsupported feedback scope")
    if kind not in FEEDBACK_KINDS:
        raise HTTPException(status_code=422, detail="Unsupported feedback kind")
    group_id = _text(payload.get("groupId"), field="groupId", maximum=128, required=False)
    if scope == "group" and not group_id:
        raise HTTPException(status_code=422, detail="groupId is required for group feedback")
    return {
        "scope": scope,
        "kind": kind,
        "groupId": group_id or None,
        "topic": _text(payload.get("topic"), field="topic", maximum=160),
        "message": _text(payload.get("message"), field="message", maximum=2000),
        "knowledgeComponentIds": _string_list(
            payload.get("knowledgeComponentIds"), field="knowledgeComponentIds"
        ),
        "recommendedMinutes": _integer(
            payload.get("recommendedMinutes"),
            field="recommendedMinutes",
            default=0,
            minimum=0,
            maximum=360,
        ),
    }


def _settings_payload(payload: dict[str, Any]) -> dict[str, Any]:
    minimum = _integer(
        payload.get("minimumGroupSize"),
        field="minimumGroupSize",
        default=5,
        minimum=5,
        maximum=50,
    )
    return {
        "minimumGroupSize": minimum,
        "allowIndividualReview": bool(payload.get("allowIndividualReview", False)),
        "requireStudentConsent": bool(payload.get("requireStudentConsent", True)),
        "autoPublishApprovedResources": bool(payload.get("autoPublishApprovedResources", False)),
    }


def normalize_instructor_workspace_action(action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action_type == "schedule":
        return _schedule_payload(payload)
    if action_type == "course_structure":
        return _course_structure_payload(payload)
    if action_type == "feedback":
        return _feedback_payload(payload)
    if action_type == "settings":
        return _settings_payload(payload)
    return payload


def _payload(action: InstructorAction) -> dict[str, Any]:
    try:
        value = json.loads(action.payload_json or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def fold_instructor_workspace(actions: Iterable[InstructorAction]) -> dict[str, Any]:
    ordered = list(actions)
    schedule_by_id: dict[str, dict[str, Any]] = {}
    feedback: list[dict[str, Any]] = []
    course_structure = {"modules": [], "knowledgeComponents": []}
    settings = {
        "minimumGroupSize": 5,
        "allowIndividualReview": False,
        "requireStudentConsent": True,
        "autoPublishApprovedResources": False,
    }
    for action in ordered:
        payload = _payload(action)
        if action.action_type == "schedule":
            if payload.get("operation") == "delete":
                schedule_by_id.pop(action.entity_id, None)
            else:
                schedule_by_id[action.entity_id] = {
                    "id": action.entity_id,
                    **payload,
                    "updatedAt": action.created_at.isoformat(),
                }
        elif action.action_type == "course_structure":
            course_structure = payload
        elif action.action_type == "feedback":
            feedback.append(
                {
                    "id": action.entity_id,
                    **payload,
                    "createdAt": action.created_at.isoformat(),
                }
            )
        elif action.action_type == "settings":
            settings = {**settings, **payload}
    schedule = sorted(schedule_by_id.values(), key=lambda item: (item.get("startAt", ""), item["id"]))
    return {
        "schedule": schedule,
        "courseStructure": course_structure,
        "feedback": list(reversed(feedback[-100:])),
        "settings": settings,
    }


def pacewise_calendar_items(actions: Iterable[InstructorAction], course_id: int) -> list[dict[str, Any]]:
    workspace = fold_instructor_workspace(actions)
    result = []
    for event in workspace["schedule"]:
        if event.get("status") == "cancelled":
            continue
        start = datetime.fromisoformat(str(event["startAt"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(event["endAt"]).replace("Z", "+00:00"))
        occurrences = int(event.get("recurrenceCount") or 12) if event.get("recurrence") == "weekly" else 1
        for occurrence in range(occurrences):
            occurrence_start = start + timedelta(weeks=occurrence)
            occurrence_end = end + timedelta(weeks=occurrence)
            suffix = f"-w{occurrence + 1}" if occurrences > 1 else ""
            result.append(
                {
                "id": f"pacewise-{event['id']}{suffix}",
                "source_id": 0,
                "type": "event",
                "course_id": course_id,
                "course_code": None,
                "title": event["title"],
                "starts_at": occurrence_start.isoformat(),
                "ends_at": occurrence_end.isoformat(),
                "duration_minutes": max(1, int((end - start).total_seconds() // 60)),
                "event_kind": f"teaching_{event.get('type', 'other')}",
                "editable": False,
                "source": "pacewise_instructor",
                "location": event.get("location", ""),
                "meeting_url": event.get("meetingUrl", ""),
                "module_id": event.get("moduleId", ""),
                "knowledge_component_ids": event.get("knowledgeComponentIds", []),
                "preparation": event.get("preparation", ""),
                }
            )
    return result
