"""Database-backed rate limits and cost reservations for AI endpoints."""

from __future__ import annotations

import hashlib
import hmac
import math
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request
from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from src.agents.telemetry import ModelUsage
from src.config import Settings
from src.observability import increment
from src.persistence_models import AiUsageBucket, AiUsageReservation
from src.security import SessionContext


@dataclass(frozen=True)
class AiReservation:
    id: str
    user_scope_hash: str
    reserved_tokens: int
    reserved_cost_microusd: int


class _LimitRejectedError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        retry_after: int,
        limit_type: str,
        limit: int,
        status_code: int = 429,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = max(1, retry_after)
        self.limit_type = limit_type
        self.limit = limit
        self.status_code = status_code


def _scope_hash(settings: Settings, value: str) -> str:
    secret = settings.pacewise_session_secret.encode("utf-8")
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _client_ip(request: Request) -> str:
    # Do not trust X-Forwarded-For until a trusted-proxy list is configured.
    return request.client.host if request.client else "unknown"


def _bucket_id(scope_type: str, scope_hash: str, limit_type: str, window_start: int) -> str:
    raw = f"{scope_type}:{scope_hash}:{limit_type}:{window_start}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ensure_bucket(
    db: Session,
    *,
    scope_type: str,
    scope_hash: str,
    limit_type: str,
    window_start: int,
    expires_at: datetime,
) -> str:
    bucket_id = _bucket_id(scope_type, scope_hash, limit_type, window_start)
    values = {
        "id": bucket_id,
        "scope_type": scope_type,
        "scope_hash": scope_hash,
        "limit_type": limit_type,
        "window_start": window_start,
        "used": 0,
        "expires_at": expires_at,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        statement = postgres_insert(AiUsageBucket).values(**values).on_conflict_do_nothing(index_elements=["id"])
    elif dialect == "sqlite":
        statement = sqlite_insert(AiUsageBucket).values(**values).on_conflict_do_nothing(index_elements=["id"])
    else:
        existing = db.get(AiUsageBucket, bucket_id)
        if existing is None:
            db.add(AiUsageBucket(**values))
            db.flush()
        return bucket_id
    db.execute(statement)
    return bucket_id


def _consume(
    db: Session,
    *,
    scope_type: str,
    scope_hash: str,
    limit_type: str,
    amount: int,
    limit: int,
    window_seconds: int,
    now_epoch: int,
    rejection_code: str = "AI_RATE_LIMITED",
    rejection_message: str = "Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau.",
    status_code: int = 429,
) -> str:
    window_start = (now_epoch // window_seconds) * window_seconds if window_seconds else 0
    expires_epoch = window_start + window_seconds if window_seconds else now_epoch + 86400
    bucket_id = _ensure_bucket(
        db,
        scope_type=scope_type,
        scope_hash=scope_hash,
        limit_type=limit_type,
        window_start=window_start,
        expires_at=datetime.fromtimestamp(expires_epoch, UTC),
    )
    changed = db.execute(
        update(AiUsageBucket)
        .where(AiUsageBucket.id == bucket_id, AiUsageBucket.used + amount <= limit)
        .values(used=AiUsageBucket.used + amount, updated_at=datetime.now(UTC))
    ).rowcount
    if not changed:
        retry_after = max(1, expires_epoch - now_epoch) if window_seconds else 1
        raise _LimitRejectedError(rejection_code, rejection_message, retry_after, limit_type, limit, status_code)
    return bucket_id


def _release_bucket(db: Session, bucket_id: str, amount: int) -> None:
    db.execute(update(AiUsageBucket).where(AiUsageBucket.id == bucket_id).values(used=AiUsageBucket.used - amount))


def _cleanup_expired_reservations(db: Session, now: datetime) -> None:
    expired = (
        db.query(AiUsageReservation)
        .filter(AiUsageReservation.status == "reserved", AiUsageReservation.expires_at <= now)
        .limit(100)
        .all()
    )
    for row in expired:
        changed = db.execute(
            update(AiUsageReservation)
            .where(AiUsageReservation.id == row.id, AiUsageReservation.status == "reserved")
            .values(status="expired", finished_at=now)
        ).rowcount
        if changed:
            _release_bucket(db, _bucket_id("user", row.user_scope_hash, "concurrent", 0), 1)
            _release_bucket(db, _bucket_id("global", "global", "concurrent", 0), 1)


def _request_weight(payload_context: dict, settings: Settings) -> int:
    has_image = any(
        payload_context.get(key) for key in ("image", "image_url", "page_image", "attachment", "attachments")
    )
    return settings.ai_image_request_weight if has_image else settings.ai_text_request_weight


def _to_http_error(rejection: _LimitRejectedError) -> HTTPException:
    increment("pacewise_ai_rate_limit_rejections_total", limit_type=rejection.limit_type)
    return HTTPException(
        status_code=rejection.status_code,
        detail={
            "code": rejection.code,
            "message": rejection.message,
            "retry_after_seconds": rejection.retry_after,
            "limit_type": rejection.limit_type,
        },
        headers={
            "Retry-After": str(rejection.retry_after),
            "X-RateLimit-Limit": str(rejection.limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(datetime.now(UTC).timestamp()) + rejection.retry_after),
        },
    )


def reserve_ai_request(
    db: Session,
    request: Request,
    session: SessionContext,
    settings: Settings,
    *,
    workflow: str | None,
    payload_context: dict,
    now: datetime | None = None,
) -> AiReservation | None:
    """Atomically reserve request/token/cost capacity before expensive work."""
    if not settings.ai_rate_limit_enabled:
        return None

    now = now or datetime.now(UTC)
    now_epoch = int(now.timestamp())
    user_scope = _scope_hash(settings, f"{settings.institution_id}:{session.user_id}")
    institution_scope = _scope_hash(settings, settings.institution_id)
    ip_scope = _scope_hash(settings, _client_ip(request))
    weight = _request_weight(payload_context, settings)
    reserved_tokens = settings.ai_estimated_tokens_per_request * weight
    max_cost_per_million = max(settings.llm_input_cost_per_million, settings.llm_output_cost_per_million)
    if (settings.ai_daily_budget_usd > 0 or settings.ai_institution_daily_budget_usd > 0) and max_cost_per_million <= 0:
        raise HTTPException(status_code=503, detail="AI budget pricing is not configured")
    reserved_cost_microusd = math.ceil(reserved_tokens * max_cost_per_million)
    acquired_concurrency: list[str] = []

    try:
        _cleanup_expired_reservations(db, now)
        db.execute(
            delete(AiUsageBucket).where(
                AiUsageBucket.limit_type != "concurrent",
                AiUsageBucket.expires_at < now - timedelta(days=1),
            )
        )
        _consume(
            db,
            scope_type="ip",
            scope_hash=ip_scope,
            limit_type="ip_minute",
            amount=1,
            limit=settings.ai_ip_requests_per_minute,
            window_seconds=60,
            now_epoch=now_epoch,
        )
        _consume(
            db,
            scope_type="user",
            scope_hash=user_scope,
            limit_type="burst",
            amount=weight,
            limit=settings.ai_burst_requests,
            window_seconds=settings.ai_burst_window_seconds,
            now_epoch=now_epoch,
        )
        _consume(
            db,
            scope_type="user",
            scope_hash=user_scope,
            limit_type="minute",
            amount=weight,
            limit=settings.ai_requests_per_minute,
            window_seconds=60,
            now_epoch=now_epoch,
        )
        _consume(
            db,
            scope_type="user",
            scope_hash=user_scope,
            limit_type="hour",
            amount=weight,
            limit=settings.ai_requests_per_hour,
            window_seconds=3600,
            now_epoch=now_epoch,
        )
        _consume(
            db,
            scope_type="user",
            scope_hash=user_scope,
            limit_type="daily_tokens",
            amount=reserved_tokens,
            limit=settings.ai_daily_token_limit_per_user,
            window_seconds=86400,
            now_epoch=now_epoch,
            rejection_code="AI_DAILY_QUOTA_EXCEEDED",
            rejection_message="Bạn đã sử dụng hết hạn mức AI trong ngày.",
        )
        if settings.ai_institution_daily_budget_usd > 0:
            _consume(
                db,
                scope_type="institution",
                scope_hash=institution_scope,
                limit_type="daily_cost",
                amount=reserved_cost_microusd,
                limit=math.floor(settings.ai_institution_daily_budget_usd * 1_000_000),
                window_seconds=86400,
                now_epoch=now_epoch,
                rejection_code="AI_BUDGET_EXCEEDED",
                rejection_message="Dịch vụ AI của tổ chức đã đạt hạn mức chi phí trong ngày.",
            )
        if settings.ai_daily_budget_usd > 0:
            _consume(
                db,
                scope_type="global",
                scope_hash="global",
                limit_type="daily_cost",
                amount=reserved_cost_microusd,
                limit=math.floor(settings.ai_daily_budget_usd * 1_000_000),
                window_seconds=86400,
                now_epoch=now_epoch,
                rejection_code="AI_BUDGET_EXCEEDED",
                rejection_message="Dịch vụ AI đã đạt hạn mức chi phí trong ngày.",
            )

        user_concurrency = _consume(
            db,
            scope_type="user",
            scope_hash=user_scope,
            limit_type="concurrent",
            amount=1,
            limit=settings.ai_max_concurrent_per_user,
            window_seconds=0,
            now_epoch=now_epoch,
            rejection_code="AI_REQUEST_IN_PROGRESS",
            rejection_message="Một yêu cầu AI khác của bạn đang được xử lý.",
        )
        acquired_concurrency.append(user_concurrency)
        global_concurrency = _consume(
            db,
            scope_type="global",
            scope_hash="global",
            limit_type="concurrent",
            amount=1,
            limit=settings.ai_max_concurrent_global,
            window_seconds=0,
            now_epoch=now_epoch,
            rejection_code="AI_CAPACITY_EXCEEDED",
            rejection_message="Dịch vụ AI đang bận. Vui lòng thử lại sau.",
            status_code=503,
        )
        acquired_concurrency.append(global_concurrency)

        reservation_id = str(uuid.uuid4())
        db.add(
            AiUsageReservation(
                id=reservation_id,
                institution_id=settings.institution_id,
                user_id=session.user_id,
                user_scope_hash=user_scope,
                workflow=workflow or "qa",
                request_weight=weight,
                reserved_tokens=reserved_tokens,
                estimated_cost_microusd=reserved_cost_microusd,
                created_at=now,
                expires_at=now + timedelta(seconds=settings.ai_reservation_ttl_seconds),
            )
        )
        db.commit()
        increment("pacewise_ai_requests_total", outcome="allowed", workflow=workflow or "qa")
        return AiReservation(reservation_id, user_scope, reserved_tokens, reserved_cost_microusd)
    except _LimitRejectedError as rejection:
        db.rollback()
        raise _to_http_error(rejection) from rejection
    except Exception:
        db.rollback()
        raise


def finalize_ai_request(
    db: Session,
    reservation: AiReservation | None,
    usage: ModelUsage,
    settings: Settings,
    *,
    succeeded: bool,
) -> None:
    """Reconcile actual usage and always release distributed concurrency slots."""
    if reservation is None:
        return
    now = datetime.now(UTC)
    actual_tokens = usage.input_tokens + usage.output_tokens
    actual_cost_microusd = math.ceil(usage.estimated_cost_usd * 1_000_000)
    if usage.missing_usage:
        # Unknown provider usage is not free; keep the conservative reservation.
        actual_tokens = max(actual_tokens, reservation.reserved_tokens)
        actual_cost_microusd = max(actual_cost_microusd, reservation.reserved_cost_microusd)
    try:
        row = db.get(AiUsageReservation, reservation.id)
        if row is None or row.status != "reserved":
            return
        changed = db.execute(
            update(AiUsageReservation)
            .where(AiUsageReservation.id == row.id, AiUsageReservation.status == "reserved")
            .values(status="reconciling")
        ).rowcount
        if not changed:
            return
        # Debit the window that admitted the request, including across midnight.
        admitted_at = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
        day_start = (int(admitted_at.timestamp()) // 86400) * 86400
        token_bucket = _bucket_id("user", reservation.user_scope_hash, "daily_tokens", day_start)
        token_delta = actual_tokens - reservation.reserved_tokens
        if token_delta:
            db.execute(
                update(AiUsageBucket)
                .where(AiUsageBucket.id == token_bucket)
                .values(used=AiUsageBucket.used + token_delta)
            )
        cost_delta = actual_cost_microusd - reservation.reserved_cost_microusd
        if cost_delta:
            institution_scope = _scope_hash(settings, settings.institution_id)
            for scope_type, scope_hash in (("institution", institution_scope), ("global", "global")):
                db.execute(
                    update(AiUsageBucket)
                    .where(AiUsageBucket.id == _bucket_id(scope_type, scope_hash, "daily_cost", day_start))
                    .values(used=AiUsageBucket.used + cost_delta)
                )
        _release_bucket(db, _bucket_id("user", reservation.user_scope_hash, "concurrent", 0), 1)
        _release_bucket(db, _bucket_id("global", "global", "concurrent", 0), 1)
        row.actual_input_tokens = usage.input_tokens
        row.actual_output_tokens = usage.output_tokens
        row.estimated_cost_microusd = actual_cost_microusd
        row.status = "completed" if succeeded else "failed"
        row.finished_at = now
        db.commit()
        increment("pacewise_ai_requests_total", outcome=row.status, workflow=row.workflow)
    except Exception:
        db.rollback()
        # Usage accounting must not replace the original user response/error.
        increment("pacewise_ai_usage_reconciliation_total", outcome="error")


@asynccontextmanager
async def ai_request_slot(payload, request, session, settings):
    """Own short accounting transactions; never retain DB connections during I/O."""
    from src.agents.telemetry import collect_model_usage
    from src.db import SessionLocal

    with SessionLocal() as db:
        reservation = reserve_ai_request(
            db, request, session, settings, workflow=payload.workflow, payload_context=payload.context
        )
    succeeded = False
    with collect_model_usage() as usage:
        try:
            yield
            succeeded = True
        finally:
            with SessionLocal() as db:
                finalize_ai_request(db, reservation, usage, settings, succeeded=succeeded)


def purge_expired_ai_buckets(db: Session) -> int:
    """Optional maintenance hook; current-window and concurrency buckets are retained."""
    cutoff = datetime.now(UTC) - timedelta(days=1)
    result = db.execute(
        delete(AiUsageBucket).where(
            AiUsageBucket.limit_type != "concurrent",
            AiUsageBucket.expires_at < cutoff,
        )
    )
    db.commit()
    return int(result.rowcount or 0)
