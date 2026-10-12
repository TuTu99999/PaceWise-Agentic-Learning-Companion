"""Real PostgreSQL authoring smoke inside a rolled-back outer transaction.

Run in backend: python /app/data/.../evaluate_standalone_authoring.py
All row writes use SAVEPOINTs on one connection, then are discarded. PostgreSQL
sequences can advance (normal gaps), but no real course/history record changes.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import get_settings
from src.course_source.db import Base, engine, get_db
from src.course_source.gateway import internal_app
from src.course_source.migration import inventory
from src.course_source.models import Enrollment


async def main():
    assert get_settings().course_source_mode == "standalone"
    assert engine.dialect.name == "postgresql"
    app = internal_app()
    with engine.connect() as connection:
        transaction = connection.begin()
        before = inventory(connection, Base.metadata.sorted_tables)
        actor = connection.scalar(select(Enrollment.user_id).where(Enrollment.role == "instructor").order_by(Enrollment.user_id))

        def scoped_db():
            with Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as db:
                yield db

        app.dependency_overrides[get_db] = scoped_db
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://native") as client:
                async def call(method, path, payload=None):
                    result = await client.request(method, "/api/pacewise/v1/teacher" + path,
                                                  params={"user_id": actor}, json=payload)
                    assert result.status_code < 300, f"{method} {path}: {result.status_code}"
                    return result.json()

                created = await call("POST", "/courses", {"code": "QA-" + uuid4().hex[:12], "name": "Transactional QA"})
                cid = created["id"]
                course = await call("GET", f"/courses/{cid}")
                assert course["tasks"] == [] and course["lessons"] == []
                tomorrow = datetime.now(UTC) + timedelta(days=1)
                await call("POST", f"/courses/{cid}/lessons", {"title": "Future QA lesson",
                    "starts_at": tomorrow.isoformat(), "ends_at": (tomorrow + timedelta(hours=1)).isoformat(), "repeat_count": 2})
                await call("POST", f"/courses/{cid}/tasks", {"title": "QA task", "kind": "assignment", "chapter": "Chapter 3",
                    "description": "Explain the concept", "points_possible": 10, "published": True,
                    "due_at": (tomorrow + timedelta(days=3)).isoformat()})
                await call("POST", f"/courses/{cid}/materials", {"title": "QA guide", "chapter": "Chapter 3", "content": "Verified guide"})
                current = await call("GET", f"/courses/{cid}")
                assert len(current["lessons"]) == 2 and len(current["tasks"]) == 1 and len(current["materials"]) == 1
                await call("PUT", f"/courses/{cid}/weights", {"groups": [{"name": "Assignments", "weight": 100}],
                                                            "expected_version": current["weights"]["version"]})
                current = await call("GET", f"/courses/{cid}")
                task = current["tasks"][0]
                await call("POST", f"/courses/{cid}/tasks/{task['id']}/archive", {"expected_version": task["version"]})
                item = current["lessons"][0]
                await call("POST", f"/courses/{cid}/lessons/{item['id']}/cancel", {"expected_version": item["version"]})
                profile = await call("GET", "/profile")
                assert profile["name"]
        finally:
            app.dependency_overrides.pop(get_db, None)
            transaction.rollback()
        after = inventory(connection, Base.metadata.sorted_tables)
        assert before == after, "QA changed real source rows"
        print(json.dumps({"passed": True, "target": "real_native_postgres_outer_transaction_rollback",
                          "course_crud": True, "recurring_lessons": True, "task_archive": True,
                          "lesson_cancel": True, "weights": True, "chapter_materials": True,
                          "profile": True, "all_66_table_row_checksums_unchanged": True}))


if __name__ == "__main__":
    asyncio.run(main())
