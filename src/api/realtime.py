"""Authenticated server-sent events for LMS projection changes."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from src.config import Settings, get_settings
from src.db import SessionLocal
from src.persistence_models import LmsEventProjection, PaceWiseSession
from src.security import SessionContext, get_detached_session, live_membership

router = APIRouter(prefix="/lms", tags=["lms-realtime"])
logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.0
HEARTBEAT_INTERVAL_SECONDS = 15.0
EVENT_BATCH_SIZE = 100
SUBSCRIBER_QUEUE_SIZE = 20


def encode_sse_event(*, event_id: int, event_type: str, course_id: int | None) -> str:
    """Serialize the minimal event contract exposed to the browser."""
    payload = json.dumps(
        {"eventId": event_id, "type": event_type, "courseId": course_id},
        separators=(",", ":"),
    )
    return f"id: {event_id}\nevent: lms.changed\ndata: {payload}\n\n"


def _latest_event_id(institution_id: str) -> int:
    with SessionLocal() as db:
        value = db.scalar(
            select(func.max(LmsEventProjection.source_event_id)).where(
                LmsEventProjection.institution_id == institution_id,
            )
        )
    return int(value or 0)


def _events_after(institution_id: str, cursor: int) -> list[LmsEventProjection]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(LmsEventProjection)
                .where(
                    LmsEventProjection.institution_id == institution_id,
                    LmsEventProjection.source_event_id > cursor,
                )
                .order_by(LmsEventProjection.source_event_id)
                .limit(EVENT_BATCH_SIZE)
            )
        )


class LmsEventBroker:
    """Poll the durable projection once and fan changes out to SSE clients."""

    def __init__(self, settings: Settings) -> None:
        self._institution_id = settings.institution_id
        self._subscribers: dict[asyncio.Queue[LmsEventProjection], tuple[frozenset[int], int | None]] = {}
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="lms-event-broker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        self._subscribers.clear()

    def subscribe(self, course_ids: Sequence[int], user_id: int | None = None) -> asyncio.Queue[LmsEventProjection]:
        queue: asyncio.Queue[LmsEventProjection] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self._subscribers[queue] = (frozenset(course_ids), user_id)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[LmsEventProjection]) -> None:
        self._subscribers.pop(queue, None)

    def _publish(self, event: LmsEventProjection) -> None:
        target = None
        if event.event_type in {"enrollment.changed", "invitation.changed"}:
            try:
                target = int(json.loads(event.payload_json).get("target_user_id"))
            except (TypeError, ValueError, AttributeError):
                return  # Malformed targeted events must never broadcast.
        for queue, (course_ids, user_id) in tuple(self._subscribers.items()):
            if target is not None and user_id != target:
                continue
            if event.course_id is not None and event.course_id not in course_ids:
                continue
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    async def _run(self) -> None:
        cursor = await asyncio.to_thread(_latest_event_id, self._institution_id)
        while True:
            try:
                events = await asyncio.to_thread(_events_after, self._institution_id, cursor)
                for event in events:
                    cursor = max(cursor, event.source_event_id)
                    self._publish(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("lms_event_broker_poll_failed error_type=%s", type(exc).__name__)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _event_stream(
    request: Request,
    session: SessionContext,
    broker: LmsEventBroker,
) -> AsyncIterator[str]:
    queue = broker.subscribe(session.course_ids, session.user_id)
    try:
        yield "event: ready\ndata: {}\n\n"
        while not await request.is_disconnected():
            if not await asyncio.to_thread(_session_active, session.sid):
                yield "event: session.revoked\ndata: {}\n\n"
                return
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL_SECONDS)
            except TimeoutError:
                if not await asyncio.to_thread(_session_active, session.sid):
                    return
                yield ": keep-alive\n\n"
                continue
            if not await asyncio.to_thread(_session_active, session.sid):
                return
            if event.event_type == "enrollment.changed":
                session = await asyncio.to_thread(live_membership, session, get_settings())
                broker.unsubscribe(queue)
                queue = broker.subscribe(session.course_ids, session.user_id)
            if get_settings().private_api_required:
                # Browser only needs an invalidation signal, not internal IDs.
                yield "event: lms.changed\ndata: {}\n\n"
            else:
                yield encode_sse_event(
                    event_id=event.source_event_id,
                    event_type=event.event_type,
                    course_id=event.course_id,
                )
    finally:
        broker.unsubscribe(queue)


def _session_active(sid: str) -> bool:
    with SessionLocal() as db:
        row = db.get(PaceWiseSession, sid)
        if not row or row.revoked_at:
            return False
        expires = row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at
        return expires > datetime.now(UTC)


@router.get("/events/stream", include_in_schema=False)
async def stream_lms_events(
    request: Request,
    session: SessionContext = Depends(get_detached_session),
) -> StreamingResponse:
    broker = getattr(request.app.state, "lms_event_broker", None)
    if not isinstance(broker, LmsEventBroker):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Realtime LMS updates are not available",
        )
    return StreamingResponse(
        _event_stream(request, session, broker),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
