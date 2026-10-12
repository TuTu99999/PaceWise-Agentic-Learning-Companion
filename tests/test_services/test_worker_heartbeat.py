"""Worker health is durable across API and worker processes."""

from src.config import get_settings
from src.db import SessionLocal
from src.persistence_models import WorkerHeartbeat
from src.services.sync_worker import record_worker_heartbeat


def test_worker_heartbeat_is_persisted_with_bounded_counters():
    result = record_worker_heartbeat(get_settings())

    assert result["workerKind"] == "sync-ingestion"
    assert result["queueLag"] >= 0
    assert result["failedJobs"] >= 0
    with SessionLocal() as db:
        stored = db.get(WorkerHeartbeat, f"sync-ingestion:{result['instanceId']}")
        assert stored is not None
        assert stored.heartbeat_at is not None
