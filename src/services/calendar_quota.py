"""Fail-closed Google admission and budgets, serialized in the shared database.

Current + previous minute is deliberately conservative for a rolling minute.
Current + previous 24 hourly buckets is conservative for a rolling 24 hours.
Counts include unsuccessful attempts, refresh/userinfo and retries.
"""

import asyncio
import hashlib
import hmac
import json
import math
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from src.db import SessionLocal
from src.observability import increment
from src.persistence_models import GoogleQuotaState


class CalendarQuotaExceeded(HTTPException):
    def __init__(self, retry_after=60, *, reason="rate"):
        increment("pacewise_google_admission_total", outcome=reason)
        super().__init__(
            429,
            "Google Calendar đang bận hoặc đã đạt giới hạn an toàn. Hãy thử lại sau.",
            headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
        )


def _locked(db):
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    db.execute(insert(GoogleQuotaState).values(id="google-api", state_json="{}").on_conflict_do_nothing())
    return db.scalar(select(GoogleQuotaState).where(GoogleQuotaState.id == "google-api").with_for_update())


def reserve(settings, user_id, *, now=None):
    now = time.time() if now is None else now
    minute, hour = int(now // 60), int(now // 3600)
    principal = hmac.new(settings.pacewise_session_secret.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
    try:
        with SessionLocal() as db:
            row = _locked(db)
            state = json.loads(row.state_json)
            if state.get("cooldown", 0) > now:
                raise CalendarQuotaExceeded(state["cooldown"] - now, reason="provider_cooldown")
            leases = {k: v for k, v in state.get("leases", {}).items() if v > now}
            if len(leases) >= settings.google_api_max_concurrent:
                raise CalendarQuotaExceeded(2, reason="concurrency")
            hours = {k: v for k, v in state.get("hours", {}).items() if int(k) >= hour - 24}
            if sum(hours.values()) >= settings.google_api_daily_budget:
                retry = (min(map(int, hours)) + 25) * 3600 - now
                raise CalendarQuotaExceeded(retry, reason="daily_budget")
            counters = {k: v for k, v in state.get("minutes", {}).items() if v[0] >= minute - 1}
            keys = [
                ("project", settings.google_api_project_per_minute),
                (principal, settings.google_api_user_per_minute),
            ]
            for key, limit in keys:
                previous = counters.get(key, [minute, 0, 0])
                if previous[0] < minute:
                    previous = [minute, 0, previous[1]]
                if previous[1] + previous[2] >= limit:
                    raise CalendarQuotaExceeded((minute + 2) * 60 - now, reason="minute_budget")
                previous[1] += 1
                counters[key] = previous
            lease = uuid4().hex
            leases[lease] = now + 120
            operation = state.get("operations", {}).get(principal)
            if operation:
                operation[1] = now + 120
            hours[str(hour)] = hours.get(str(hour), 0) + 1
            state.update({"leases": leases, "hours": hours, "minutes": counters, "cooldown": 0})
            row.state_json = json.dumps(state)
            db.commit()
            increment("pacewise_google_admission_total", outcome="accepted")
            return lease
    except SQLAlchemyError as exc:
        # Losing the shared store must never silently bypass the budget.
        raise HTTPException(503, "Google Calendar safety limiter unavailable") from exc


def release(lease):
    try:
        with SessionLocal() as db:
            row = _locked(db)
            state = json.loads(row.state_json)
            state.get("leases", {}).pop(lease, None)
            row.state_json = json.dumps(state)
            db.commit()
    except SQLAlchemyError:
        increment("pacewise_google_admission_total", outcome="release_error")
        # The bounded lease expires even if release cannot reach the database.


def cooldown(seconds):
    with SessionLocal() as db:
        row = _locked(db)
        state = json.loads(row.state_json)
        state["cooldown"] = max(state.get("cooldown", 0), time.time() + seconds)
        row.state_json = json.dumps(state)
        db.commit()


@asynccontextmanager
async def google_admission(settings, user_id):
    # Shield acquisition so cancellation cannot leave an unaccounted live lease.
    task = asyncio.create_task(asyncio.to_thread(reserve, settings, user_id))
    try:
        lease = await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            lease = await task
            await asyncio.shield(asyncio.to_thread(release, lease))
        finally:
            raise
    try:
        yield
    finally:
        await asyncio.shield(asyncio.to_thread(release, lease))


def operation_slot(settings, user_id, *, acquire, lease=None):
    principal = hmac.new(settings.pacewise_session_secret.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
    with SessionLocal() as db:
        row = _locked(db)
        state = json.loads(row.state_json)
        now = time.time()
        operations = {key: value for key, value in state.get("operations", {}).items() if value[1] > now}
        if acquire:
            if principal in operations:
                raise CalendarQuotaExceeded(2, reason="duplicate_operation")
            lease = uuid4().hex
            operations[principal] = [lease, now + 120]
        elif operations.get(principal, [None])[0] == lease:
            operations.pop(principal, None)
        state["operations"] = operations
        row.state_json = json.dumps(state)
        db.commit()
        return lease


@asynccontextmanager
async def sync_operation(session, settings):
    task = asyncio.create_task(asyncio.to_thread(operation_slot, settings, session.user_id, acquire=True))
    try:
        lease = await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            lease = await task
            await asyncio.shield(
                asyncio.to_thread(operation_slot, settings, session.user_id, acquire=False, lease=lease)
            )
        finally:
            raise
    try:
        yield
    finally:
        await asyncio.shield(asyncio.to_thread(operation_slot, settings, session.user_id, acquire=False, lease=lease))
