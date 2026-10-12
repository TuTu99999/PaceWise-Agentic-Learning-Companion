"""VAPID Web Push delivery, with endpoint validation and a durable daily cap."""

import base64
import json
import os
import socket
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.config import Settings
from src.db import SessionLocal
from src.persistence_models import NotificationDailyBudget, NotificationJob, UserWorkspace, WebPushSubscription
from src.services.notification_policy import ReminderPreferences


def vapid_keys(settings: Settings) -> tuple[str, str]:
    if not settings.webpush_enabled:
        raise ValueError("Web Push is disabled")
    path = Path(settings.webpush_private_key_file)
    if not path.exists():
        if settings.app_env == "production":
            raise ValueError("A persistent VAPID private key must be configured")
        path.parent.mkdir(parents=True, exist_ok=True)
        pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        # Publish a fully written key atomically. Concurrent API workers must not
        # read a partially written PEM or replace a key used by subscriptions.
        descriptor, temporary = tempfile.mkstemp(prefix=".vapid-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(pem)
                target.flush()
                os.fsync(target.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            Path(temporary).unlink(missing_ok=True)
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("VAPID key must use P-256")
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return str(path), base64.urlsafe_b64encode(public).decode().rstrip("=")


def validate_subscription(payload: dict) -> dict:
    endpoint = str(payload.get("endpoint") or "")
    parsed = urlparse(endpoint)
    host = parsed.hostname or ""
    allowed = host in {
        "fcm.googleapis.com",
        "updates.push.services.mozilla.com",
        "web.push.apple.com",
        "notify.windows.com",
    } or host.endswith(".notify.windows.com")
    if (
        not allowed
        or parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or parsed.fragment
    ):
        raise ValueError("Unsupported Web Push endpoint")
    keys = payload.get("keys") or {}
    try:
        public = base64.urlsafe_b64decode(keys["p256dh"] + "=" * (-len(keys["p256dh"]) % 4))
        auth = base64.urlsafe_b64decode(keys["auth"] + "=" * (-len(keys["auth"]) % 4))
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
        if len(auth) != 16:
            raise ValueError("Invalid auth key")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid Web Push encryption keys") from exc
    return {"endpoint": endpoint, "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}}


def send_push(subscription: dict, payload: dict, settings: Settings, ttl: int) -> None:
    from pywebpush import webpush

    private_key, _ = vapid_keys(settings)
    webpush(
        subscription_info=validate_subscription(subscription),
        data=json.dumps(payload),
        vapid_private_key=private_key,
        vapid_claims={"sub": settings.webpush_subject},
        ttl=ttl,
        timeout=10,
    )


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def daily_budget(db, user_id: int, state: dict, now: datetime) -> NotificationDailyBudget:
    today = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    budget_id = f"{user_id}:{today}"
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    db.execute(insert(NotificationDailyBudget).values(id=budget_id, count=0).on_conflict_do_nothing())
    budget = db.scalar(select(NotificationDailyBudget).where(NotificationDailyBudget.id == budget_id).with_for_update())
    legacy = (state.get("reminders") or {}).get("deliveredAt") or {}
    legacy_count = 0
    for at in legacy.values():
        try:
            parsed = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
            legacy_count += utc(parsed).astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat() == today
        except (TypeError, ValueError):
            continue
    budget.count = max(budget.count, legacy_count)
    return budget


def _push_opted_in(db):
    """Filter dormant users before the batch limit, avoiding queue starvation."""
    return UserWorkspace.push_opted_in.is_(True)


def _quiet_end(prefs: ReminderPreferences, now: datetime) -> datetime:
    local = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    hour, minute = map(int, prefs.quiet_end.split(":"))
    end = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return end if end > local else end + timedelta(days=1)


def notification_owner() -> str:
    return f"notification:{socket.gethostname()}:{os.getpid()}"[:255]


def recover_notification_leases(settings: Settings, now: datetime | None = None) -> int:
    """Release only abandoned reminder claims; active replicas remain untouched."""
    now = now or datetime.now(UTC)
    with SessionLocal() as db:
        jobs = db.scalars(
            select(NotificationJob)
            .where(
                NotificationJob.status == "pending",
                NotificationJob.lease_expires_at.is_not(None),
                NotificationJob.lease_expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        ).all()
        for job in jobs:
            if job.attempts >= settings.worker_max_attempts:
                job.status = "failed"
                job.failure_reason = "lease_expired"
            job.lease_owner = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            job.queued_at = None
        db.commit()
        return len(jobs)


def deliver_due_reminders(
    settings: Settings,
    now: datetime | None = None,
    sender=send_push,
    job_ids: set[str] | None = None,
) -> int:
    """Called independently of LMS polling. Do not log subscription/token payloads.

    Row locks serialize claims and the per-user daily budget on PostgreSQL.
    Provider ambiguity remains best-effort: stable notification tags deduplicate UI.
    """
    now = now or datetime.now(UTC)
    if not settings.webpush_enabled:
        return 0
    delivered = 0
    owner = notification_owner()
    with SessionLocal() as db:
        db.execute(delete(NotificationJob).where(NotificationJob.expires_at < now - timedelta(days=30)))
        db.execute(
            delete(NotificationDailyBudget).where(
                # PostgreSQL's negative substr offset does not mean "last N
                # chars" as it does in SQLite. Use a portable positive offset.
                func.substr(NotificationDailyBudget.id, func.length(NotificationDailyBudget.id) - 9, 10)
                < (now - timedelta(days=35)).date().isoformat()
            )
        )
        db.commit()
        query = (
            select(NotificationJob)
            .join(UserWorkspace, UserWorkspace.user_id == NotificationJob.user_id)
            .where(
                NotificationJob.status == "pending",
                NotificationJob.scheduled_at <= now,
                (NotificationJob.lease_expires_at.is_(None)) | (NotificationJob.lease_expires_at <= now),
                _push_opted_in(db),
                select(WebPushSubscription.id)
                .where(WebPushSubscription.user_id == NotificationJob.user_id)
                .exists(),
            )
            .order_by(NotificationJob.priority, NotificationJob.scheduled_at)
            .limit(settings.worker_batch_size)
        )
        if job_ids is not None:
            query = query.where(NotificationJob.id.in_(job_ids))
        jobs = list(db.scalars(query))
        ids = [job.id for job in jobs]
    for job_id in ids:
        # Claim and commit before contacting a push provider. A stopped worker
        # leaves a renewable/expiring claim instead of an uncommitted row lock.
        with SessionLocal() as db:
            job = db.scalar(
                select(NotificationJob).where(
                    NotificationJob.id == job_id,
                    NotificationJob.status == "pending",
                    (NotificationJob.lease_expires_at.is_(None)) | (NotificationJob.lease_expires_at <= now),
                ).with_for_update(skip_locked=True)
            )
            if not job:
                continue
            job.lease_owner = owner
            job.heartbeat_at = now
            job.lease_expires_at = now + timedelta(seconds=settings.worker_lease_seconds)
            db.commit()
        with SessionLocal() as db:
            job = db.scalar(select(NotificationJob).where(
                NotificationJob.id == job_id,
                NotificationJob.status == "pending",
                NotificationJob.lease_owner == owner,
            ).with_for_update())
            if not job:
                continue

            def release_claim() -> None:
                job.lease_owner = None
                job.lease_expires_at = None
                job.heartbeat_at = None

            if utc(job.expires_at) < now:
                job.status = "expired"
                job.queued_at = None
                release_claim()
                db.commit()
                continue
            workspace = db.get(UserWorkspace, job.user_id)
            state = json.loads(workspace.state_json) if workspace else {}
            prefs = ReminderPreferences.model_validate((state.get("reminders") or {}).get("preferences") or {})
            if not prefs.allows(job.kind) or not prefs.browser_enabled or not prefs.push_enabled:
                job.status = "cancelled"
                job.queued_at = None
                release_claim()
                db.commit()
                continue
            if prefs.quiet(now):
                job.scheduled_at = _quiet_end(prefs, now)
                job.queued_at = None
                release_claim()
                db.commit()
                continue
            subscribers = list(
                db.scalars(select(WebPushSubscription).where(WebPushSubscription.user_id == job.user_id))
            )
            if not subscribers:
                job.queued_at = None
                release_claim()
                db.commit()
                continue
            budget = daily_budget(db, job.user_id, state, now)
            if budget.count >= prefs.daily_cap:
                local = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
                job.scheduled_at = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                job.queued_at = None
                release_claim()
                db.commit()
                continue
            successful = False
            job.attempts += 1
            for subscriber in subscribers:
                try:
                    sender(
                        json.loads(subscriber.subscription_json),
                        json.loads(job.payload_json),
                        settings,
                        max(0, min(300, int((utc(job.expires_at) - now).total_seconds()))),
                    )
                    successful = True
                except Exception as exc:
                    response = getattr(exc, "response", None)
                    status = getattr(response, "status_code", None)
                    job.last_error = "Subscription expired" if status in {404, 410} else "Push provider unavailable"
                    if status in {404, 410}:
                        db.delete(subscriber)
            if successful:
                budget.count += 1
                job.status, job.delivered_at, job.last_error = "delivered", now, ""
                delivered += 1
            elif job.attempts >= settings.worker_max_attempts:
                job.status = "failed"
                job.failure_reason = "push_provider_unavailable"
            else:
                job.scheduled_at = now + timedelta(minutes=job.attempts)
            job.queued_at = None
            release_claim()
            db.commit()
    return delivered


def publish_due_reminder_jobs(settings: Settings, now: datetime | None = None) -> int:
    """Publish opaque due-job ids. SQS never receives notification content or user ids."""
    if not settings.sqs_notification_queue_url or not settings.webpush_enabled:
        return 0
    from src.services.aws_queues import publish_job

    now = now or datetime.now(UTC)
    stale = now - timedelta(minutes=5)
    published = 0
    with SessionLocal() as db:
        jobs = db.scalars(
            select(NotificationJob)
            .join(UserWorkspace, UserWorkspace.user_id == NotificationJob.user_id)
            .where(
                NotificationJob.status == "pending",
                NotificationJob.scheduled_at <= now,
                NotificationJob.expires_at >= now,
                (NotificationJob.queued_at.is_(None)) | (NotificationJob.queued_at < stale),
                (NotificationJob.lease_expires_at.is_(None)) | (NotificationJob.lease_expires_at <= now),
                _push_opted_in(db),
                select(WebPushSubscription.id)
                .where(WebPushSubscription.user_id == NotificationJob.user_id)
                .exists(),
            )
            .order_by(NotificationJob.priority, NotificationJob.scheduled_at)
            .with_for_update(skip_locked=True)
            .limit(settings.worker_batch_size)
        ).all()
        for job in jobs:
            job.idempotency_key = job.idempotency_key or f"notification:{job.id}"
            job.queue_message_id = publish_job(
                settings,
                settings.sqs_notification_queue_url,
                "notification",
                job.id,
                job.idempotency_key,
            )
            job.queued_at = now
            published += 1
        db.commit()
    return published


def process_sqs_reminder_jobs(settings: Settings, sender=send_push) -> int:
    """Consume SQS wakeups; database status remains the idempotency boundary."""
    from src.services.aws_queues import delete_message, receive_jobs

    messages = receive_jobs(
        settings,
        settings.sqs_notification_queue_url,
        "notification",
        limit=min(10, settings.worker_batch_size),
    )
    processed = 0
    for message in messages:
        # The existing delivery transaction rechecks pending status under a row
        # lock, so duplicate SQS delivery cannot send a completed job twice.
        delivered = deliver_due_reminders(settings, sender=sender, job_ids={message.job_id})
        with SessionLocal() as db:
            job = db.get(NotificationJob, message.job_id)
            terminal = job is None or job.status in {"delivered", "failed", "expired", "cancelled"}
            if job and not terminal:
                job.queued_at = None
                db.commit()
        if terminal or delivered:
            delete_message(settings, settings.sqs_notification_queue_url, message.receipt_handle)
        processed += 1
    return processed
