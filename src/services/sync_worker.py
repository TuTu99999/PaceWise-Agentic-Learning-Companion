"""Durable LMS event projection and asynchronous RAG ingestion worker."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from src.agents.tools.schedule_calculator import check_deadline_slack
from src.config import Settings, get_settings
from src.db import SessionLocal
from src.persistence_models import (
    CourseProjection,
    LmsCourseContextProjection,
    LmsEventProjection,
    RagIngestionJob,
    SyncCursor,
    WorkerHeartbeat,
)
from src.services.lms_client import LMSClient
from src.services.lms_files import (
    process_file_extractions,
    process_file_indexes,
    recover_file_leases,
    sync_course_files,
)
from src.services.rag_pipeline import (
    build_scoped_resources,
    enqueue_course_snapshot,
    process_ingestion_job,
    snapshot_version,
)

logger = logging.getLogger("pacewise.worker")
CONTENT_EVENTS = {
    "resource.created", "resource.updated", "resource.deleted",
    "resource.version.created", "resource.access.updated",
    "content.created",
    "content.updated",
    "content.deleted",
    "course.created",
    "course.updated",
    "course.activity.created", "module.created", "module.updated", "module.deleted",
    "module_item.created", "module_item.updated", "module_item.deleted", "module.rules.updated",
}
RISK_EVENTS = {
    "assignment.created",
    "assignment.updated",
    "assignment.deleted",
    "submission.submitted",
    "grade.updated",
    "quiz.attempted",
    "course.activity.created", "assignment.policy.updated", "assignment.override.created",
    "assignment.override.deleted", "assignment_group.created", "assignment_group.updated",
    "assignment_group.deleted", "rubric.created", "rubric.attached", "rubric.assessed",
    "submission.workflow.updated", "submission.comment.created", "outcome.aligned", "quiz.questions.updated",
    "section.member.added", "group.member.added",
}


def record_worker_heartbeat(settings: Settings, worker_kind: str = "sync-ingestion") -> dict:
    """Publish bounded health counters without relying on process-local metrics."""
    instance_id = os.getenv("ECS_CONTAINER_METADATA_URI_V4", "").rsplit("/", 1)[-1] or socket.gethostname()
    identifier = f"{worker_kind}:{instance_id}"[:255]
    with SessionLocal() as db:
        queued_rag = db.scalar(
            select(func.count()).select_from(RagIngestionJob).where(RagIngestionJob.status.in_(("pending", "retry")))
        ) or 0
        failed_rag = db.scalar(
            select(func.count()).select_from(RagIngestionJob).where(RagIngestionJob.status == "failed")
        ) or 0
        row = db.get(WorkerHeartbeat, identifier) or WorkerHeartbeat(
            id=identifier,
            worker_kind=worker_kind,
            instance_id=instance_id[:160],
        )
        row.queue_lag = int(queued_rag)
        row.failed_jobs = int(failed_rag)
        row.heartbeat_at = datetime.now(UTC)
        db.add(row)
        db.commit()
        return {
            "workerKind": row.worker_kind,
            "instanceId": row.instance_id,
            "queueLag": row.queue_lag,
            "failedJobs": row.failed_jobs,
            "heartbeatAt": row.heartbeat_at.isoformat(),
        }


def worker_identity(worker_kind: str = "rag-ingestion") -> str:
    instance_id = os.getenv("ECS_CONTAINER_METADATA_URI_V4", "").rsplit("/", 1)[-1] or socket.gethostname()
    return f"{worker_kind}:{instance_id}:{os.getpid()}"[:255]


def recover_interrupted_ingestion_jobs(settings: Settings | None = None, now: datetime | None = None) -> int:
    """Recover only expired leases; live work owned by another task is untouched."""
    settings = settings or get_settings()
    now = now or datetime.now(UTC)
    with SessionLocal() as db:
        jobs = db.scalars(
            select(RagIngestionJob)
            .where(
                RagIngestionJob.status == "processing",
                RagIngestionJob.lease_expires_at.is_not(None),
                RagIngestionJob.lease_expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        ).all()
        for job in jobs:
            job.status = "retry" if job.attempts < settings.worker_max_attempts else "failed"
            job.last_error = "Worker lease expired before the ingestion job completed"
            job.failure_reason = "lease_expired"
            job.lease_owner = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            job.queued_at = None
        db.commit()

        return len(jobs)


def _projection_id(settings: Settings, event_id: int) -> str:
    return f"{settings.institution_id}:{event_id}"


async def _refresh_course(
    client: LMSClient,
    settings: Settings,
    course_id: int,
    *,
    refresh_content: bool,
    refresh_assignments: bool,
    event_id: int = 0,
) -> None:
    courses = await client.service_get("/api/pacewise/v1/courses")
    course = next((item for item in courses if int(item["id"]) == course_id), None)
    if not course:
        return
    content = await client.service_get(f"/api/pacewise/v1/courses/{course_id}/content") if refresh_content else None
    assignments = (
        await client.service_get(f"/api/pacewise/v1/courses/{course_id}/assignments") if refresh_assignments else None
    )
    modules = (
        await client.service_get(f"/api/pacewise/v1/courses/{course_id}/modules")
        if refresh_content
        else None
    )

    with SessionLocal() as db:
        identifier = f"{settings.institution_id}:{course_id}"
        projection = db.get(CourseProjection, identifier) or CourseProjection(
            id=identifier,
            institution_id=settings.institution_id,
            course_id=course_id,
        )
        db.add(projection)
        if assignments is not None:
            projection.assignments_json = json.dumps(assignments, ensure_ascii=False)
            risk_signals = []
            for assignment in assignments:
                if not assignment.get("due_at") or not assignment.get("published", True):
                    continue
                estimated_hours = max(
                    0.5,
                    min(4.0, float(assignment.get("points_possible") or 5) * 0.2),
                )
                risk = check_deadline_slack(assignment["due_at"], estimated_hours)
                if risk["is_at_risk"]:
                    risk_signals.append(
                        {
                            "assignment_id": str(assignment["id"]),
                            "title": assignment.get("title", "Bài tập"),
                            "risk_level": risk["risk_level"],
                            "slack_hours": risk["slack_hours"],
                            "source": "lms_event_projection",
                        }
                    )
            projection.risk_signals_json = json.dumps(risk_signals, ensure_ascii=False)
            projection.risk_refresh_required = 1
        if content is not None:
            resources = build_scoped_resources(
                content,
                institution_id=settings.institution_id,
                course_id=course_id,
                course_code=str(course.get("code") or course_id),
            )
            projection.content_version = snapshot_version(resources)
            enqueue_course_snapshot(
                db,
                institution_id=settings.institution_id,
                course_id=course_id,
                resources=resources,
            )
        projection.last_event_id = max(projection.last_event_id or 0, event_id)
        context_id = f"{settings.institution_id}:{course_id}"
        context = db.get(LmsCourseContextProjection, context_id) or LmsCourseContextProjection(
            id=context_id,
            institution_id=settings.institution_id,
            course_id=course_id,
        )
        context.course_json = json.dumps(course, ensure_ascii=False)
        if assignments is not None:
            context.assignments_json = json.dumps(assignments, ensure_ascii=False)
        if modules is not None:
            context.modules_json = json.dumps(modules, ensure_ascii=False)
        db.add(context)
        db.commit()

    if refresh_content:
        await sync_course_files(client, settings, course_id, str(course.get("code") or course_id))


async def bootstrap_course_snapshots(client: LMSClient, settings: Settings) -> None:
    """Ensure a fresh deployment has course projections without waiting for an event."""
    courses = await client.service_get("/api/pacewise/v1/courses")
    for course in courses:
        await _refresh_course(
            client,
            settings,
            int(course["id"]),
            refresh_content=True,
            refresh_assignments=True,
        )


async def project_lms_events(client: LMSClient, settings: Settings) -> int:
    """Persist LMS events and apply them to course projections."""
    with SessionLocal() as db:
        cursor = db.get(SyncCursor, "lms-global") or SyncCursor(key="lms-global", last_event_id=0)
        after_id = cursor.last_event_id
    events = await client.service_get(
        "/api/pacewise/v1/events",
        {"after_id": after_id, "limit": settings.worker_batch_size},
    )
    for event in events:
        event_id = int(event["id"])
        course_id = int(event["course_id"]) if event.get("course_id") is not None else None
        with SessionLocal() as db:
            identifier = _projection_id(settings, event_id)
            if not db.get(LmsEventProjection, identifier):
                db.add(
                    LmsEventProjection(
                        id=identifier,
                        institution_id=settings.institution_id,
                        source_event_id=event_id,
                        event_type=str(event.get("type") or "unknown"),
                        aggregate_type=str(event.get("aggregate_type") or ""),
                        aggregate_id=str(event.get("aggregate_id") or ""),
                        course_id=course_id,
                        payload_json=json.dumps(event.get("payload") or {}, ensure_ascii=False),
                        occurred_at=str(event.get("created_at") or ""),
                    )
                )
                db.commit()

        event_type = str(event.get("type") or "")
        if course_id is not None and (event_type in CONTENT_EVENTS or event_type in RISK_EVENTS):
            await _refresh_course(
                client,
                settings,
                course_id,
                refresh_content=event_type in CONTENT_EVENTS,
                refresh_assignments=event_type in RISK_EVENTS,
                event_id=event_id,
            )
        with SessionLocal() as db:
            cursor = db.get(SyncCursor, "lms-global") or SyncCursor(key="lms-global", last_event_id=0)
            cursor.last_event_id = max(cursor.last_event_id, event_id)
            db.add(cursor)
            db.commit()
    return len(events)


def claim_ingestion_job(settings: Settings, *, job_id: str | None = None, owner: str | None = None) -> dict | None:
    owner = owner or worker_identity()
    now = datetime.now(UTC)
    with SessionLocal() as db:
        query = select(RagIngestionJob).where(
            RagIngestionJob.status.in_(("pending", "retry")),
            (RagIngestionJob.lease_expires_at.is_(None)) | (RagIngestionJob.lease_expires_at <= now),
        )
        if job_id:
            query = query.where(RagIngestionJob.id == job_id)
        job = db.scalar(query.order_by(RagIngestionJob.created_at).with_for_update(skip_locked=True).limit(1))
        if not job:
            return None
        job.status = "processing"
        job.attempts += 1
        job.lease_owner = owner
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=settings.worker_lease_seconds)
        job.failure_reason = ""
        db.commit()
        return {"id": job.id, "owner": owner}


def heartbeat_ingestion_job(settings: Settings, job_id: str, owner: str) -> bool:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        job = db.scalar(
            select(RagIngestionJob).where(
                RagIngestionJob.id == job_id,
                RagIngestionJob.status == "processing",
                RagIngestionJob.lease_owner == owner,
            ).with_for_update()
        )
        if not job:
            return False
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=settings.worker_lease_seconds)
        db.commit()
        return True


@contextmanager
def ingestion_lease_heartbeat(settings: Settings, job_id: str, owner: str):
    stop = threading.Event()

    def pulse() -> None:
        interval = max(5, settings.worker_lease_seconds // 3)
        while not stop.wait(interval):
            try:
                if not heartbeat_ingestion_job(settings, job_id, owner):
                    return
            except Exception:
                logger.exception("rag_lease_heartbeat_failed job_id=%s", job_id)

    thread = threading.Thread(target=pulse, daemon=True, name=f"rag-lease-{job_id[:8]}")
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)


def _finish_ingestion_job(settings: Settings, claim: dict, *, error: Exception | None = None) -> str:
    with SessionLocal() as db:
        job = db.scalar(
            select(RagIngestionJob).where(
                RagIngestionJob.id == claim["id"],
                RagIngestionJob.status == "processing",
                RagIngestionJob.lease_owner == claim["owner"],
            ).with_for_update()
        )
        if not job:
            return "lost_lease"
        if error is None:
            job.status = "completed"
            job.last_error = ""
            job.failure_reason = ""
            job.completed_at = datetime.now(UTC)
        else:
            job.status = "retry" if job.attempts < settings.worker_max_attempts else "failed"
            job.last_error = f"{type(error).__name__}: ingestion unavailable"
            job.failure_reason = type(error).__name__[:255]
            job.queued_at = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        db.commit()
        return job.status


def process_ingestion_job_by_id(settings: Settings, job_id: str | None = None, *, owner: str | None = None) -> str:
    claim = claim_ingestion_job(settings, job_id=job_id, owner=owner)
    if not claim:
        return "not_claimed"
    try:
        with ingestion_lease_heartbeat(settings, claim["id"], claim["owner"]):
            with SessionLocal() as db:
                job = db.get(RagIngestionJob, claim["id"])
                if not job:
                    return "missing"
                process_ingestion_job(job)
        return _finish_ingestion_job(settings, claim)
    except Exception as exc:
        logger.error("rag_job_failed job_id=%s error_type=%s", claim["id"], type(exc).__name__)
        return _finish_ingestion_job(settings, claim, error=exc)


def publish_pending_ingestion_jobs(settings: Settings, limit: int | None = None) -> int:
    if not settings.sqs_ingestion_queue_url:
        return 0
    from src.services.aws_queues import publish_job

    published = 0
    stale = datetime.now(UTC) - timedelta(minutes=5)
    with SessionLocal() as db:
        jobs = db.scalars(
            select(RagIngestionJob)
            .where(
                RagIngestionJob.status.in_(("pending", "retry")),
                (RagIngestionJob.queued_at.is_(None)) | (RagIngestionJob.queued_at < stale),
            )
            .order_by(RagIngestionJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(limit or settings.worker_batch_size)
        ).all()
        for job in jobs:
            message_id = publish_job(
                settings,
                settings.sqs_ingestion_queue_url,
                "rag_ingestion",
                job.id,
                job.idempotency_key,
            )
            job.queued_at = datetime.now(UTC)
            job.queue_message_id = message_id
            published += 1
        db.commit()
    return published


def process_sqs_ingestion_jobs(settings: Settings) -> int:
    from src.services.aws_queues import delete_message, receive_jobs, visibility_heartbeat

    messages = receive_jobs(
        settings,
        settings.sqs_ingestion_queue_url,
        "rag_ingestion",
        limit=min(10, settings.worker_batch_size),
    )
    owner = worker_identity()
    for message in messages:
        with visibility_heartbeat(settings, settings.sqs_ingestion_queue_url, message.receipt_handle):
            status = process_ingestion_job_by_id(settings, message.job_id, owner=owner)
        terminal = status in {"completed", "failed", "missing"}
        if status == "not_claimed":
            with SessionLocal() as db:
                job = db.get(RagIngestionJob, message.job_id)
                terminal = job is None or job.status in {"completed", "failed"}
        if terminal:
            delete_message(settings, settings.sqs_ingestion_queue_url, message.receipt_handle)
    return len(messages)


def process_pending_ingestion_jobs(settings: Settings) -> int:
    """Local fallback. Production consumes opaque job ids from SQS."""
    processed = 0
    while processed < settings.worker_batch_size:
        status = process_ingestion_job_by_id(settings)
        if status == "not_claimed":
            break
        processed += 1
    return processed


async def run_worker(settings: Settings, stop: asyncio.Event | None = None) -> None:
    stop = stop or asyncio.Event()
    client = LMSClient(settings)
    bootstrapped = False
    last_file_reconcile = 0.0
    await asyncio.to_thread(recover_interrupted_ingestion_jobs, settings)
    while not stop.is_set():
        try:
            if not bootstrapped:
                await bootstrap_course_snapshots(client, settings)
                bootstrapped = True
                last_file_reconcile = time.monotonic()
            await project_lms_events(client, settings)
            if time.monotonic() - last_file_reconcile >= 60:
                # Reconcile missed events and retry extraction after transient LMS failures.
                for course in await client.service_get("/api/pacewise/v1/courses"):
                    await sync_course_files(client, settings, int(course["id"]), str(course.get("code") or course["id"]))
                last_file_reconcile = time.monotonic()
            await asyncio.to_thread(recover_interrupted_ingestion_jobs, settings)
            if settings.sqs_ingestion_queue_url:
                await asyncio.to_thread(publish_pending_ingestion_jobs, settings)
                await asyncio.to_thread(process_sqs_ingestion_jobs, settings)
            else:
                await asyncio.to_thread(process_pending_ingestion_jobs, settings)
            await asyncio.to_thread(recover_file_leases, settings)
            await process_file_extractions(client, settings)
            await asyncio.to_thread(process_file_indexes, settings)
        except Exception as exc:
            logger.error("lms_worker_iteration_failed error_type=%s", type(exc).__name__)
        try:
            await asyncio.to_thread(record_worker_heartbeat, settings)
        except Exception as exc:
            logger.error("worker_heartbeat_failed error_type=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.lms_sync_interval_seconds)
        except TimeoutError:
            continue


# Compatibility for tests and older callers.
poll_lms_events = run_worker
