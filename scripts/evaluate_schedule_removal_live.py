"""Exercise native deletion on real PostgreSQL inside a rolled-back transaction.

Only synthetic lessons in a newly created QA course are touched. Commits use
SAVEPOINTs; the outer transaction is always rolled back. Original row checksums
must remain identical. Sequence gaps are expected, not deleted user data.
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
from src.course_source.models import CalendarEvent, Enrollment, TeachingEventLink


async def main():
    assert get_settings().course_source_mode == "standalone"
    assert engine.dialect.name == "postgresql"
    app = internal_app()
    with engine.connect() as connection:
        transaction = connection.begin()
        before = inventory(connection, Base.metadata.sorted_tables)
        actor = connection.scalar(select(Enrollment.user_id).where(Enrollment.role == "instructor").order_by(Enrollment.user_id))
        assert actor is not None

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

                course = await call("POST", "/courses", {"code": "QA-" + uuid4().hex[:12], "name": "Schedule removal QA"})
                cid = course["id"]
                start = datetime.now(UTC) + timedelta(days=2)
                await call("POST", f"/courses/{cid}/lessons", {"title": "QA lesson", "starts_at": start.isoformat(),
                           "ends_at": (start + timedelta(hours=1)).isoformat(), "repeat_count": 2})
                lessons = (await call("GET", f"/courses/{cid}"))["lessons"]
                old_id = lessons[0]["id"]
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    key = db.get(TeachingEventLink, old_id).occurrence_key
                    old_copies = db.scalars(select(CalendarEvent).join(TeachingEventLink)
                                           .where(TeachingEventLink.occurrence_key == key)).all()
                    for row in old_copies:
                        row.starts_at = start - timedelta(days=60)
                        row.ends_at = row.starts_at + timedelta(hours=1)
                        row.attendance_status = "attended"
                    db.commit()
                spec = {"mode": "remove", "course_ids": [cid], "rows": [], "period": "past"}
                draft = await call("POST", "/schedule/preview", {**spec, "lesson_ids": [old_id]})
                assert draft["counts"]["removed_lessons"] == 1 and not draft["errors"]
                assert len((await call("GET", f"/courses/{cid}"))["lessons"]) == 2
                done = await call("POST", "/schedule/confirm", {"ticket": draft["ticket"]})
                assert done["applied"]
                assert await call("POST", "/schedule/confirm", {"ticket": draft["ticket"]}) == done
                assert len((await call("GET", f"/courses/{cid}"))["lessons"]) == 1
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    assert db.get(CalendarEvent, old_id).attendance_status == "attended"
                await call("POST", "/schedule/restore", {"ticket": draft["ticket"]})
                assert len((await call("GET", f"/courses/{cid}"))["lessons"]) == 2
                bulk = await call("POST", "/schedule/preview", {**spec, "period": "all"})
                assert bulk["counts"]["removed_lessons"] == 2
                await call("POST", "/schedule/confirm", {"ticket": bulk["ticket"]})
                assert (await call("GET", f"/courses/{cid}"))["lessons"] == []
                later = start + timedelta(days=20)
                await call("POST", f"/courses/{cid}/lessons", {"title": "QA newly added lesson",
                           "starts_at": later.isoformat(), "ends_at": (later + timedelta(hours=1)).isoformat()})
                repeated = await call("POST", "/schedule/preview", {**spec, "period": "all"})
                assert repeated["ticket"] != bulk["ticket"] and not repeated["applied"]
                assert repeated["counts"]["removed_lessons"] == 1
                await call("POST", "/schedule/confirm", {"ticket": repeated["ticket"]})
                await call("POST", "/schedule/restore", {"ticket": bulk["ticket"]})
                assert len((await call("GET", f"/courses/{cid}"))["lessons"]) == 2
        finally:
            app.dependency_overrides.pop(get_db, None)
            transaction.rollback()
        assert before == inventory(connection, Base.metadata.sorted_tables), "QA changed original source rows"
        print(json.dumps({"passed": True, "target": "native_postgres_rollback", "single_old_removal": True,
                          "bulk_removal": True, "repeated_filters_select_new_lessons": True, "retry_idempotent": True,
                          "restore_old_and_future": True, "attendance_preserved": True,
                          "original_source_row_checksums_unchanged": True}))


if __name__ == "__main__":
    asyncio.run(main())
