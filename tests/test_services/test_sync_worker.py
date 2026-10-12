import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.config import get_settings
from src.db import SessionLocal
from src.persistence_models import (
    CourseProjection,
    LmsCourseContextProjection,
    LmsEventProjection,
    RagIngestionJob,
    SyncCursor,
)
from src.services import sync_worker
from src.services.sync_worker import (
    bootstrap_course_snapshots,
    process_pending_ingestion_jobs,
    project_lms_events,
    recover_interrupted_ingestion_jobs,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type,content,risk", [
    ("assignment.override.created", False, True), ("assignment.override.deleted", False, True),
    ("assignment.policy.updated", False, True), ("assignment_group.updated", False, True),
    ("rubric.attached", False, True), ("submission.workflow.updated", False, True),
    ("module.created", True, False), ("module_item.created", True, False),
    ("module.rules.updated", True, False), ("course.activity.created", True, True),
    ("quiz.questions.updated", False, True),
])
async def test_planning_contract_events_invalidate_correct_projection(monkeypatch, event_type, content, risk):
    settings = get_settings()
    with SessionLocal() as db:
        db.query(SyncCursor).delete()
        db.commit()
    client = AsyncMock()
    client.service_get.return_value = [{"id": 9901, "type": event_type, "course_id": 7, "payload": {}}]
    refresh = AsyncMock()
    monkeypatch.setattr(sync_worker, "_refresh_course", refresh)
    assert await project_lms_events(client, settings) == 1
    refresh.assert_awaited_once_with(client, settings, 7, refresh_content=content, refresh_assignments=risk, event_id=9901)


@pytest.mark.asyncio
async def test_lms_event_updates_projection_and_enqueues_rag_snapshot():
    settings = get_settings()
    with SessionLocal() as db:
        db.query(LmsEventProjection).delete()
        db.query(RagIngestionJob).delete()
        db.query(CourseProjection).delete()
        db.query(LmsCourseContextProjection).delete()
        db.query(SyncCursor).delete()
        db.commit()

    async def service_get(path, params=None):
        if path.endswith("/events"):
            assert params["after_id"] == 0
            return [
                {
                    "id": 901,
                    "type": "content.updated",
                    "aggregate_type": "page",
                    "aggregate_id": "11",
                    "course_id": 7,
                    "actor_user_id": 2,
                    "payload": {"title": "Updated lesson"},
                    "created_at": "2026-09-28T10:00:00Z",
                }
            ]
        if path == "/api/pacewise/v1/courses":
            return [{"id": 7, "code": "AI101", "name": "AI"}]
        if path.endswith("/content"):
            return [{"id": 11, "title": "Updated lesson", "body": "Fresh content", "published": True}]
        if path.endswith("/modules"):
            return [{"id": 1, "name": "Week 1", "items": []}]
        if path.endswith("/files"):
            return []
        raise AssertionError(path)

    client = AsyncMock()
    client.service_get.side_effect = service_get
    count = await project_lms_events(client, settings)
    assert count == 1
    with SessionLocal() as db:
        event = db.get(LmsEventProjection, f"{settings.institution_id}:901")
        projection = db.get(CourseProjection, f"{settings.institution_id}:7")
        context = db.get(LmsCourseContextProjection, f"{settings.institution_id}:7")
        job = db.scalar(db.query(RagIngestionJob).statement)
        cursor = db.get(SyncCursor, "lms-global")
        assert event is not None
        assert projection is not None and projection.content_version
        assert json.loads(context.modules_json)[0]["name"] == "Week 1"
        assert json.loads(job.resources_json)[0]["course_id"] == "7"
        assert cursor.last_event_id == 901


def test_worker_recovers_interrupted_ingestion_jobs():
    settings = get_settings()
    job = RagIngestionJob(
        id="interrupted-job",
        institution_id=settings.institution_id,
        course_id=7,
        resource_version="v1",
        resources_json="[]",
        status="processing",
        attempts=1,
        lease_owner="dead-worker",
        lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    with SessionLocal() as db:
        db.query(RagIngestionJob).filter(RagIngestionJob.id == job.id).delete()
        db.add(job)
        db.commit()

    assert recover_interrupted_ingestion_jobs() == 1
    with SessionLocal() as db:
        recovered = db.get(RagIngestionJob, job.id)
        assert recovered.status == "retry"
        assert "lease expired" in recovered.last_error
        assert recovered.lease_owner is None


def test_worker_does_not_reclaim_an_active_ingestion_lease():
    settings = get_settings()
    job = RagIngestionJob(
        id="active-job",
        institution_id=settings.institution_id,
        course_id=7,
        resource_version="v-active",
        resources_json="[]",
        status="processing",
        attempts=1,
        lease_owner="live-worker",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
    )
    with SessionLocal() as db:
        db.query(RagIngestionJob).filter(RagIngestionJob.id == job.id).delete()
        db.add(job)
        db.commit()

    assert recover_interrupted_ingestion_jobs(settings) == 0
    with SessionLocal() as db:
        active = db.get(RagIngestionJob, job.id)
        assert active.status == "processing"
        assert active.lease_owner == "live-worker"


@pytest.mark.asyncio
async def test_assignment_event_refreshes_risk_projection():
    settings = get_settings()
    with SessionLocal() as db:
        db.query(LmsEventProjection).delete()
        db.query(CourseProjection).delete()
        db.query(LmsCourseContextProjection).delete()
        db.query(SyncCursor).delete()
        db.commit()

    async def service_get(path, params=None):
        if path.endswith("/events"):
            return [
                {
                    "id": 902,
                    "type": "assignment.updated",
                    "aggregate_type": "assignment",
                    "aggregate_id": "12",
                    "course_id": 8,
                    "payload": {},
                    "created_at": "2026-10-02T10:00:00Z",
                }
            ]
        if path == "/api/pacewise/v1/courses":
            return [{"id": 8, "code": "CS8", "name": "Systems"}]
        if path.endswith("/assignments"):
            return [
                {
                    "id": 12,
                    "title": "Urgent project",
                    "due_at": "2020-01-01T00:00:00Z",
                    "points_possible": 10,
                    "published": True,
                },
                {"id": 13, "title": "Draft", "published": False},
            ]
        raise AssertionError(path)

    client = AsyncMock()
    client.service_get.side_effect = service_get
    assert await project_lms_events(client, settings) == 1
    with SessionLocal() as db:
        projection = db.get(CourseProjection, f"{settings.institution_id}:8")
        context = db.get(LmsCourseContextProjection, f"{settings.institution_id}:8")
        assert json.loads(projection.risk_signals_json)[0]["assignment_id"] == "12"
        assert json.loads(context.assignments_json)[0]["title"] == "Urgent project"


@pytest.mark.asyncio
async def test_bootstrap_refreshes_each_course_and_skips_missing_course(monkeypatch):
    settings = get_settings()
    client = AsyncMock()
    client.service_get.return_value = [{"id": 7}, {"id": 8}]
    refresh = AsyncMock()
    monkeypatch.setattr(sync_worker, "_refresh_course", refresh)

    await bootstrap_course_snapshots(client, settings)

    assert refresh.await_count == 2
    assert refresh.await_args_list[0].kwargs == {
        "refresh_content": True,
        "refresh_assignments": True,
    }

    missing_client = AsyncMock()
    missing_client.service_get.return_value = []
    await sync_worker._refresh_course(
        missing_client,
        settings,
        999,
        refresh_content=True,
        refresh_assignments=True,
    )


def _queue_job(job_id: str, attempts: int = 0) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        db.query(RagIngestionJob).filter(
            RagIngestionJob.status.in_(("pending", "retry", "processing"))
        ).delete(synchronize_session=False)
        db.add(
            RagIngestionJob(
                id=job_id,
                institution_id=settings.institution_id,
                course_id=7,
                resource_version=f"version-{job_id}",
                resources_json="[]",
                status="pending",
                attempts=attempts,
            )
        )
        db.commit()


def test_pending_ingestion_jobs_complete_and_retry(monkeypatch, caplog):
    settings = get_settings()
    settings.worker_batch_size = 1
    _queue_job("coverage-job-success")
    monkeypatch.setattr(sync_worker, "process_ingestion_job", lambda _job: {"status": "ok"})
    assert process_pending_ingestion_jobs(settings) == 1
    with SessionLocal() as db:
        completed = db.get(RagIngestionJob, "coverage-job-success")
        assert completed.status == "completed"
        assert completed.attempts == 1

    _queue_job("coverage-job-failure", attempts=2)

    def fail(_job):
        raise RuntimeError("vector store unavailable password=PRIVATE_SECRET")

    monkeypatch.setattr(sync_worker, "process_ingestion_job", fail)
    assert process_pending_ingestion_jobs(settings) == 1
    with SessionLocal() as db:
        failed = db.get(RagIngestionJob, "coverage-job-failure")
        assert failed.status == "failed"
        assert failed.last_error == "RuntimeError: ingestion unavailable"
        assert "PRIVATE_SECRET" not in caplog.text


def test_two_workers_cannot_claim_the_same_job_and_restart_does_not_repeat_it(monkeypatch):
    settings = get_settings()
    _queue_job("single-owner-job")
    first = sync_worker.claim_ingestion_job(settings, job_id="single-owner-job", owner="worker-a")
    assert first is not None
    assert sync_worker.claim_ingestion_job(settings, job_id="single-owner-job", owner="worker-b") is None
    monkeypatch.setattr(sync_worker, "process_ingestion_job", lambda _job: {"status": "ok"})
    assert sync_worker._finish_ingestion_job(settings, first) == "completed"
    assert sync_worker.process_ingestion_job_by_id(settings, "single-owner-job", owner="worker-after-restart") == "not_claimed"


def test_qdrant_timeout_is_bounded_and_records_failure_reason(monkeypatch):
    settings = get_settings()
    settings.worker_batch_size = 1
    _queue_job("qdrant-timeout-job", attempts=settings.worker_max_attempts - 1)
    monkeypatch.setattr(sync_worker, "process_ingestion_job", lambda _job: (_ for _ in ()).throw(TimeoutError()))

    assert process_pending_ingestion_jobs(settings) == 1
    with SessionLocal() as db:
        failed = db.get(RagIngestionJob, "qdrant-timeout-job")
        assert failed.status == "failed"
        assert failed.failure_reason == "TimeoutError"
        assert failed.last_error == "TimeoutError: ingestion unavailable"


@pytest.mark.asyncio
async def test_worker_runs_one_complete_iteration(monkeypatch):
    settings = get_settings()
    stop = __import__("asyncio").Event()
    bootstrap = AsyncMock()
    project = AsyncMock()

    def process(_settings):
        stop.set()
        return 0

    monkeypatch.setattr(sync_worker, "recover_interrupted_ingestion_jobs", lambda *_args: 0)
    monkeypatch.setattr(sync_worker, "bootstrap_course_snapshots", bootstrap)
    monkeypatch.setattr(sync_worker, "project_lms_events", project)
    monkeypatch.setattr(sync_worker, "process_pending_ingestion_jobs", process)
    monkeypatch.setattr(sync_worker, "recover_file_leases", lambda *_args: 0)
    monkeypatch.setattr(sync_worker, "process_file_extractions", AsyncMock(return_value=0))
    monkeypatch.setattr(sync_worker, "process_file_indexes", lambda *_args: 0)
    monkeypatch.setattr(sync_worker, "record_worker_heartbeat", lambda *_args: {})

    await sync_worker.run_worker(settings, stop)

    bootstrap.assert_awaited_once()
    project.assert_awaited_once()
