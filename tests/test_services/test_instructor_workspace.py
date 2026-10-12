import json
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from src.persistence_models import InstructorAction
from src.services.instructor_workspace import (
    fold_instructor_workspace,
    normalize_instructor_workspace_action,
    pacewise_calendar_items,
)


def _action(action_type: str, entity_id: str, payload: dict, minute: int = 0) -> InstructorAction:
    return InstructorAction(
        id=f"{action_type}-{entity_id}-{minute}",
        course_id=701,
        actor_user_id=22,
        action_type=action_type,
        entity_id=entity_id,
        payload_json=json.dumps(payload),
        created_at=datetime(2026, 10, 7, 8, minute, tzinfo=UTC),
    )


def test_schedule_validation_rejects_lms_and_invalid_time():
    with pytest.raises(HTTPException, match="read-only"):
        normalize_instructor_workspace_action(
            "schedule",
            {
                "title": "LMS class",
                "source": "lms",
                "startAt": "2026-10-07T08:00:00+07:00",
                "endAt": "2026-10-07T09:00:00+07:00",
            },
        )
    with pytest.raises(HTTPException, match="after"):
        normalize_instructor_workspace_action(
            "schedule",
            {
                "title": "Invalid class",
                "startAt": "2026-10-07T09:00:00+07:00",
                "endAt": "2026-10-07T08:00:00+07:00",
            },
        )


def test_course_structure_validates_references_and_self_prerequisites():
    payload = normalize_instructor_workspace_action(
        "course_structure",
        {
            "modules": [{"id": "m1", "title": "Chapter 3"}],
            "knowledgeComponents": [
                {
                    "id": "kc1",
                    "moduleId": "m1",
                    "name": "Binary relations",
                    "prerequisiteIds": [],
                }
            ],
        },
    )
    assert payload["knowledgeComponents"][0]["status"] == "approved"
    with pytest.raises(HTTPException, match="cannot require itself"):
        normalize_instructor_workspace_action(
            "course_structure",
            {
                "modules": [{"id": "m1", "title": "Chapter 3"}],
                "knowledgeComponents": [
                    {
                        "id": "kc1",
                        "moduleId": "m1",
                        "name": "Binary relations",
                        "prerequisiteIds": ["kc1"],
                    }
                ],
            },
        )
    with pytest.raises(HTTPException, match="contain a cycle"):
        normalize_instructor_workspace_action(
            "course_structure",
            {
                "modules": [{"id": "m1", "title": "Chapter 3"}],
                "knowledgeComponents": [
                    {"id": "kc1", "moduleId": "m1", "name": "One", "prerequisiteIds": ["kc2"]},
                    {"id": "kc2", "moduleId": "m1", "name": "Two", "prerequisiteIds": ["kc1"]},
                ],
            },
        )


def test_workspace_fold_keeps_latest_schedule_and_audit_feedback():
    actions = [
        _action(
            "schedule",
            "event-1",
            {
                "operation": "upsert",
                "title": "Old title",
                "startAt": "2026-10-08T08:00:00+07:00",
                "endAt": "2026-10-08T09:00:00+07:00",
                "status": "scheduled",
                "type": "offline",
                "source": "pacewise",
            },
        ),
        _action(
            "schedule",
            "event-1",
            {
                "operation": "upsert",
                "title": "Updated title",
                "startAt": "2026-10-08T09:00:00+07:00",
                "endAt": "2026-10-08T10:30:00+07:00",
                "status": "scheduled",
                "type": "online",
                "source": "pacewise",
            },
            1,
        ),
        _action(
            "feedback",
            "feedback-1",
            {"scope": "class", "kind": "guidance", "topic": "Relations", "message": "Review", "knowledgeComponentIds": [], "recommendedMinutes": 30},
            2,
        ),
    ]
    workspace = fold_instructor_workspace(actions)
    assert workspace["schedule"][0]["title"] == "Updated title"
    assert workspace["feedback"][0]["message"] == "Review"
    calendar = pacewise_calendar_items(actions, 701)
    assert calendar[0]["duration_minutes"] == 90
    assert calendar[0]["editable"] is False


def test_schedule_delete_and_cancel_are_not_synced_to_students():
    actions = [
        _action(
            "schedule",
            "cancelled",
            {"operation": "upsert", "title": "Cancelled", "startAt": "2026-10-08T09:00:00+07:00", "endAt": "2026-10-08T10:00:00+07:00", "status": "cancelled", "type": "offline", "source": "pacewise"},
        ),
        _action("schedule", "deleted", {"operation": "delete"}),
    ]
    assert pacewise_calendar_items(actions, 701) == []


def test_weekly_schedule_expands_to_a_bounded_student_calendar():
    payload = normalize_instructor_workspace_action(
        "schedule",
        {
            "title": "Weekly class",
            "type": "offline",
            "startAt": "2026-10-08T09:00:00+07:00",
            "endAt": "2026-10-08T10:30:00+07:00",
            "recurrence": "weekly",
            "recurrenceCount": 3,
        },
    )
    calendar = pacewise_calendar_items([_action("schedule", "weekly", payload)], 701)
    assert [item["id"] for item in calendar] == [
        "pacewise-weekly-w1",
        "pacewise-weekly-w2",
        "pacewise-weekly-w3",
    ]


def test_feedback_and_privacy_settings_are_bounded():
    feedback = normalize_instructor_workspace_action(
        "feedback",
        {
            "scope": "class",
            "kind": "reassessment",
            "topic": "Equivalence relations",
            "message": "Complete a transfer question.",
            "recommendedMinutes": 360,
        },
    )
    assert feedback["recommendedMinutes"] == 360
    with pytest.raises(HTTPException, match="recommendedMinutes must be between"):
        normalize_instructor_workspace_action(
            "feedback",
            {
                "scope": "class",
                "kind": "guidance",
                "topic": "Topic",
                "message": "Message",
                "recommendedMinutes": 999,
            },
        )
    with pytest.raises(HTTPException, match="groupId"):
        normalize_instructor_workspace_action(
            "feedback",
            {"scope": "group", "kind": "guidance", "topic": "Topic", "message": "Message"},
        )
    with pytest.raises(HTTPException, match="between 5 and 50"):
        normalize_instructor_workspace_action("settings", {"minimumGroupSize": 2})
