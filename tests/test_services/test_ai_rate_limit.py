from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from src.agents.telemetry import ModelUsage
from src.config import Settings
from src.db import Base
from src.persistence_models import AiUsageBucket, AiUsageReservation
from src.services.ai_rate_limit import finalize_ai_request, reserve_ai_request


def _request(ip: str = "127.0.0.1") -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/chat", "headers": [], "client": (ip, 1234)})


def _settings(**overrides) -> Settings:
    values = {
        "pacewise_session_secret": "test-session-secret-with-at-least-32-characters",
        "ai_rate_limit_enabled": True,
        "ai_burst_requests": 3,
        "ai_burst_window_seconds": 10,
        "ai_requests_per_minute": 10,
        "ai_requests_per_hour": 60,
        "ai_ip_requests_per_minute": 30,
        "ai_daily_token_limit_per_user": 100_000,
        "ai_estimated_tokens_per_request": 1000,
        "ai_max_concurrent_per_user": 1,
        "ai_max_concurrent_global": 10,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_concurrent_request_is_rejected_and_slot_is_released(db):
    settings = _settings()
    identity = SimpleNamespace(user_id=12)
    first = reserve_ai_request(db, _request(), identity, settings, workflow="qa", payload_context={})

    with pytest.raises(HTTPException) as rejected:
        reserve_ai_request(db, _request(), identity, settings, workflow="qa", payload_context={})

    assert rejected.value.status_code == 429
    assert rejected.value.detail["code"] == "AI_REQUEST_IN_PROGRESS"
    finalize_ai_request(db, first, ModelUsage(input_tokens=100, output_tokens=50), settings, succeeded=True)
    second = reserve_ai_request(db, _request(), identity, settings, workflow="qa", payload_context={})
    assert second is not None


def test_daily_token_reservation_is_reconciled_to_actual_usage(db):
    settings = _settings(ai_daily_token_limit_per_user=1500)
    identity = SimpleNamespace(user_id=12)
    reservation = reserve_ai_request(db, _request(), identity, settings, workflow="qa", payload_context={})
    finalize_ai_request(
        db,
        reservation,
        ModelUsage(input_tokens=100, output_tokens=100, estimated_cost_usd=0.0),
        settings,
        succeeded=True,
    )

    token_bucket = db.scalar(select(AiUsageBucket).where(AiUsageBucket.limit_type == "daily_tokens"))
    stored = db.get(AiUsageReservation, reservation.id)
    assert token_bucket.used == 200
    assert stored.status == "completed"
    assert stored.actual_input_tokens == 100
    assert stored.actual_output_tokens == 100


def test_request_rate_limit_returns_retry_after(db):
    settings = _settings(ai_burst_requests=2)
    identity = SimpleNamespace(user_id=12)
    now = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
    for _ in range(2):
        reservation = reserve_ai_request(
            db,
            _request(),
            identity,
            settings,
            workflow="qa",
            payload_context={},
            now=now,
        )
        finalize_ai_request(db, reservation, ModelUsage(), settings, succeeded=True)

    with pytest.raises(HTTPException) as rejected:
        reserve_ai_request(
            db,
            _request(),
            identity,
            settings,
            workflow="qa",
            payload_context={},
            now=now,
        )

    assert rejected.value.status_code == 429
    assert rejected.value.detail["code"] == "AI_RATE_LIMITED"
    assert int(rejected.value.headers["Retry-After"]) >= 1
    assert rejected.value.headers["X-RateLimit-Remaining"] == "0"


def test_image_request_uses_configured_weight(db):
    settings = _settings(ai_burst_requests=2, ai_image_request_weight=3)
    identity = SimpleNamespace(user_id=12)

    with pytest.raises(HTTPException) as rejected:
        reserve_ai_request(
            db,
            _request(),
            identity,
            settings,
            workflow="qa",
            payload_context={"image_url": "https://example.invalid/page.png"},
        )

    assert rejected.value.detail["limit_type"] == "burst"


def test_finalize_retry_does_not_release_twice(db):
    settings = _settings()
    reservation = reserve_ai_request(
        db, _request(), SimpleNamespace(user_id=12), settings, workflow="qa", payload_context={}
    )
    finalize_ai_request(db, reservation, ModelUsage(input_tokens=200), settings, succeeded=True)
    finalize_ai_request(db, reservation, ModelUsage(input_tokens=200), settings, succeeded=True)
    assert all(
        row.used == 0 for row in db.scalars(select(AiUsageBucket).where(AiUsageBucket.limit_type == "concurrent"))
    )
    assert db.scalar(select(AiUsageBucket).where(AiUsageBucket.limit_type == "daily_tokens")).used == 200


def test_missing_provider_usage_keeps_reservation(db):
    settings = _settings()
    reservation = reserve_ai_request(
        db, _request(), SimpleNamespace(user_id=12), settings, workflow="qa", payload_context={}
    )
    finalize_ai_request(db, reservation, ModelUsage(missing_usage=True), settings, succeeded=False)
    assert (
        db.scalar(select(AiUsageBucket).where(AiUsageBucket.limit_type == "daily_tokens")).used
        == reservation.reserved_tokens
    )


def test_global_capacity_rejection_rolls_back_user_slot(db):
    settings = _settings(ai_max_concurrent_global=1)
    first = reserve_ai_request(db, _request(), SimpleNamespace(user_id=12), settings, workflow="qa", payload_context={})
    with pytest.raises(HTTPException) as error:
        reserve_ai_request(db, _request(), SimpleNamespace(user_id=13), settings, workflow="qa", payload_context={})
    assert error.value.status_code == 503
    finalize_ai_request(db, first, ModelUsage(), settings, succeeded=True)
    assert reserve_ai_request(db, _request(), SimpleNamespace(user_id=13), settings, workflow="qa", payload_context={})


def test_request_crossing_midnight_reconciles_original_window(db, monkeypatch):
    from src.services import ai_rate_limit

    current = datetime(2026, 10, 11, 23, 59, 58, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return current.astimezone(tz) if tz else current.replace(tzinfo=None)

    monkeypatch.setattr(ai_rate_limit, "datetime", Clock)
    settings = _settings()
    reservation = reserve_ai_request(
        db, _request(), SimpleNamespace(user_id=12), settings, workflow="qa", payload_context={}
    )
    current += timedelta(seconds=5)
    finalize_ai_request(db, reservation, ModelUsage(input_tokens=100, output_tokens=50), settings, succeeded=True)
    bucket = db.scalar(select(AiUsageBucket).where(AiUsageBucket.limit_type == "daily_tokens"))
    assert bucket.used == 150
    assert datetime.fromtimestamp(bucket.window_start, UTC).date().isoformat() == "2026-10-11"


def test_usd_budget_cannot_silently_treat_unknown_prices_as_free(db):
    settings = _settings(ai_daily_budget_usd=10, llm_input_cost_per_million=0, llm_output_cost_per_million=0)
    with pytest.raises(HTTPException) as error:
        reserve_ai_request(db, _request(), SimpleNamespace(user_id=12), settings, workflow="qa", payload_context={})
    assert error.value.status_code == 503
