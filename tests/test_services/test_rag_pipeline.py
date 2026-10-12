import json
from types import SimpleNamespace

from src.db import SessionLocal
from src.persistence_models import RagIngestionJob
from src.services import rag_pipeline
from src.services.rag_pipeline import build_scoped_resources, enqueue_course_snapshot


def test_scoped_resources_have_tenant_version_and_acl():
    resources = build_scoped_resources(
        [{"id": 7, "title": "Week 1", "body": "<p>Neural networks</p>", "published": True}],
        institution_id="university-a",
        course_id=10,
        course_code="CS101",
    )
    assert resources[0]["institution_id"] == "university-a"
    assert resources[0]["course_id"] == "10"
    assert resources[0]["resource_id"] == "7"
    assert len(resources[0]["resource_version"]) == 64
    assert resources[0]["access_scope"] == "course"
    assert resources[0]["content"] == "Neural networks"


def test_course_snapshot_job_is_idempotent():
    resources = build_scoped_resources(
        [{"id": 8, "title": "Week 2", "body": "Regression", "published": True}],
        institution_id="university-b",
        course_id=20,
        course_code="CS101",
    )
    with SessionLocal() as db:
        first = enqueue_course_snapshot(
            db,
            institution_id="university-b",
            course_id=20,
            resources=resources,
        )
        db.commit()
        first_id = first.id
    with SessionLocal() as db:
        second = enqueue_course_snapshot(
            db,
            institution_id="university-b",
            course_id=20,
            resources=resources,
        )
        assert second.id == first_id
        payload = json.loads(second.resources_json)
        assert payload[0]["snapshot_version"] == second.resource_version
        assert db.query(RagIngestionJob).filter(RagIngestionJob.id == first_id).count() == 1


def test_ingestion_publishes_new_snapshot_before_deleting_stale_points(monkeypatch):
    calls = []
    monkeypatch.setattr(
        rag_pipeline,
        "ingest_course_resources",
        lambda resources: (
            calls.append(("ingest", resources[0]["snapshot_version"])) or {"status": "success", "total_chunks": 1}
        ),
    )
    monkeypatch.setattr(
        rag_pipeline,
        "delete_stale_course_resources",
        lambda **kwargs: calls.append(("delete_stale", kwargs["current_snapshot_version"])),
    )
    job = SimpleNamespace(
        institution_id="university-a",
        course_id=10,
        resource_version="snapshot-v2",
        resources_json=json.dumps([{"content": "Updated", "snapshot_version": "snapshot-v2"}]),
    )

    result = rag_pipeline.process_ingestion_job(job)

    assert result["status"] == "success"
    assert calls == [("ingest", "snapshot-v2"), ("delete_stale", "snapshot-v2")]
