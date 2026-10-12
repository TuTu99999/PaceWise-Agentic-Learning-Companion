import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api import realtime
from src.api.realtime import LmsEventBroker, _event_stream, _events_after, _latest_event_id, encode_sse_event
from src.config import Settings
from src.db import SessionLocal
from src.persistence_models import LmsEventProjection


def projection(event_id: int, course_id: int) -> LmsEventProjection:
    return LmsEventProjection(
        id=f"realtime-test:{event_id}",
        institution_id="realtime-test",
        source_event_id=event_id,
        event_type="assignment.updated",
        aggregate_type="assignment",
        aggregate_id=str(event_id),
        course_id=course_id,
    )


def test_encode_sse_event_exposes_only_refresh_metadata():
    message = encode_sse_event(event_id=42, event_type="assignment.updated", course_id=7)

    assert message.startswith("id: 42\nevent: lms.changed\ndata: ")
    payload = json.loads(message.split("data: ", maxsplit=1)[1])
    assert payload == {"eventId": 42, "type": "assignment.updated", "courseId": 7}
    assert message.endswith("\n\n")


@pytest.mark.asyncio
async def test_lms_event_stream_requires_authentication(client):
    response = await client.get("/api/v1/lms/events/stream")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_projection_queries_return_new_events_in_order():
    with SessionLocal() as db:
        db.query(LmsEventProjection).filter(LmsEventProjection.institution_id == "realtime-test").delete()
        db.add_all([projection(12, 7), projection(11, 7)])
        db.commit()

    assert _latest_event_id("realtime-test") == 12
    assert [event.source_event_id for event in _events_after("realtime-test", 10)] == [11, 12]


def test_broker_fans_out_only_to_authorized_courses():
    broker = LmsEventBroker(Settings(_env_file=None, institution_id="realtime-test"))
    course_seven = broker.subscribe([7])
    course_eight = broker.subscribe([8])
    event = projection(20, 7)

    broker._publish(event)

    assert course_seven.get_nowait() is event
    assert course_eight.empty()
    broker.unsubscribe(course_seven)
    broker.unsubscribe(course_eight)


@pytest.mark.asyncio
async def test_event_stream_emits_ready_then_course_change(monkeypatch):
    monkeypatch.setattr(realtime, "_session_active", lambda sid: True)
    broker = LmsEventBroker(Settings(_env_file=None, institution_id="realtime-test"))
    request = SimpleNamespace(is_disconnected=lambda: _false())
    session = SimpleNamespace(course_ids=(7,), sid="test-session", user_id=12)
    stream = _event_stream(request, session, broker)

    assert await anext(stream) == "event: ready\ndata: {}\n\n"
    broker._publish(projection(21, 7))
    assert "id: 21" in await anext(stream)
    await stream.aclose()
    assert broker._subscribers == {}


async def _false() -> bool:
    return False


@pytest.mark.asyncio
async def test_revoked_stream_does_not_publish_queued_course_events(monkeypatch):
    monkeypatch.setattr(realtime, "_session_active", lambda sid: False)
    broker = LmsEventBroker(Settings(_env_file=None, institution_id="realtime-test"))
    stream = _event_stream(SimpleNamespace(is_disconnected=lambda: _false()),
                           SimpleNamespace(course_ids=(7,), sid="revoked", user_id=12), broker)
    assert await anext(stream) == "event: ready\ndata: {}\n\n"
    broker._publish(projection(21, 7))
    assert "session.revoked" in await anext(stream)
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert broker._subscribers == {}


@pytest.mark.asyncio
async def test_broker_start_and_stop(monkeypatch):
    monkeypatch.setattr(realtime, "_latest_event_id", lambda _institution_id: 0)
    monkeypatch.setattr(realtime, "_events_after", lambda _institution_id, _cursor: [])
    broker = LmsEventBroker(Settings(_env_file=None, institution_id="realtime-test"))

    await broker.start()
    await broker.start()
    await _wait_for_broker_tick()
    await broker.stop()
    await broker.stop()

    assert broker._task is None


async def _wait_for_broker_tick() -> None:
    import asyncio

    await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_stream_returns_unavailable_without_started_broker():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    session = SimpleNamespace(course_ids=(7,))

    with pytest.raises(HTTPException) as exc_info:
        await realtime.stream_lms_events(request, session)

    assert exc_info.value.status_code == 503
