from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.course_source.db import SessionLocal as CourseSession
from src.course_source.models import Assignment, AssignmentConfiguration, AssignmentGroup
from tests.test_services.test_standalone_source import native as _native  # noqa: F401
from tests.test_services.test_standalone_source import sign_in

ROOT = "/api/v1/instructor/manage/schedule"


@pytest.mark.asyncio
async def test_imported_task_group_name_links_task_after_weights_are_created(client, _native):
    headers = await sign_in(client)
    rows = [
        {
            "course_id": 1,
            "sheet": "Tasks",
            "row": 2,
            "data": {
                "title": "Grouped assignment",
                "kind": "assignment",
                "points_possible": 10,
                "due_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                "published": True,
                "group_name": "Bài tập",
            },
        },
        {
            "course_id": 1,
            "sheet": "Weights",
            "row": 2,
            "data": {
                "groups": [
                    {"name": "Bài tập", "weight": 5},
                    {"name": "Chuyên cần & tham gia", "weight": 5},
                    {"name": "Giữa kỳ", "weight": 20},
                    {"name": "Cuối kỳ", "weight": 70},
                ]
            },
        },
    ]
    response = await client.post(
        ROOT + "/preview",
        headers=headers,
        json={"mode": "append", "course_ids": [1], "rows": rows},
    )
    assert response.status_code == 200 and not response.json()["errors"], response.text

    confirmation = await client.post(
        ROOT + "/confirm",
        headers=headers,
        json={"ticket": response.json()["ticket"]},
    )
    assert confirmation.status_code == 200, confirmation.text
    with CourseSession() as db:
        task = db.scalar(select(Assignment).where(Assignment.title == "Grouped assignment"))
        config = db.get(AssignmentConfiguration, task.id)
        group = db.get(AssignmentGroup, config.assignment_group_id)
        assert group.name == "Bài tập" and group.group_weight == 5
"""Schedule weight import regressions."""

# Imported fixtures are intentionally re-exported for pytest discovery.
# ruff: noqa: F811

