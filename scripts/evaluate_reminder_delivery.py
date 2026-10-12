"""PostgreSQL delivery smoke test in a transaction-local, rolled-back schema.

No learner data is touched. No push provider is contacted. Intended to run
inside the backend container after deploy; no secret is printed.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema

from src.config import get_settings
from src.db import engine
from src.persistence_models import NotificationDailyBudget, NotificationJob, UserWorkspace, WebPushSubscription
from src.services import web_push


def main():
    if engine.dialect.name != "postgresql":
        raise RuntimeError("This smoke test requires PostgreSQL")
    schema = "pacewise_reminder_eval_" + uuid.uuid4().hex
    tables = [
        UserWorkspace.__table__,
        NotificationDailyBudget.__table__,
        NotificationJob.__table__,
        WebPushSubscription.__table__,
    ]
    now = datetime.now(UTC)
    original_factory = web_push.SessionLocal
    result = {}
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(CreateSchema(schema))
            isolated = connection.execution_options(schema_translate_map={None: schema})
            UserWorkspace.metadata.create_all(isolated, tables=tables)
            factory = sessionmaker(bind=isolated, join_transaction_mode="create_savepoint")
            web_push.SessionLocal = factory
            with factory() as db:
                db.add(
                    UserWorkspace(
                        user_id=1,
                        state_json=json.dumps(
                            {"reminders": {"preferences": {"browserEnabled": True, "pushEnabled": True, "dailyCap": 3}}}
                        ),
                    )
                )
                db.add(WebPushSubscription(id="test-device", user_id=1, session_id="test", subscription_json="{}"))
                for index in range(5):
                    db.add(
                        NotificationJob(
                            id=f"test-{index}",
                            user_id=1,
                            reminder_key=f"test-{index}",
                            kind="study_block",
                            scheduled_at=now - timedelta(minutes=1),
                            expires_at=now + timedelta(minutes=15),
                            payload_json="{}",
                        )
                    )
                db.commit()
            sent = []
            with factory() as db:
                eligible = db.scalar(
                    select(func.count(NotificationJob.id))
                    .join(UserWorkspace, UserWorkspace.user_id == NotificationJob.user_id)
                    .where(web_push._push_opted_in(db))
                )
            count = web_push.deliver_due_reminders(get_settings(), now, sender=lambda *args: sent.append(args))
            replay = web_push.deliver_due_reminders(get_settings(), now, sender=lambda *args: sent.append(args))
            with factory() as db:
                budget_row = db.scalar(select(NotificationDailyBudget))
                budget = budget_row.count if budget_row else 0
            assert eligible == 5, f"Unexpected eligible job count: {eligible}"
            assert count == 3 and replay == 0 and len(sent) == 3 and budget == 3, {
                "delivered": count,
                "replay": replay,
                "sent": len(sent),
                "budget": budget,
            }
            result = {
                "database": "postgresql",
                "delivered": count,
                "replay": replay,
                "daily_budget": budget,
                "provider": "mocked",
                "isolation": "transaction_schema_rolled_back",
                "status": "passed",
            }
        finally:
            web_push.SessionLocal = original_factory
            outer.rollback()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
