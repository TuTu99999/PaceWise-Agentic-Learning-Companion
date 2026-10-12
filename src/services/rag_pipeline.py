"""Durable LMS-to-RAG ingestion helpers."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from src.agents.tools.qdrant_retriever import (
    delete_course_resources,
    delete_stale_course_resources,
    ingest_course_resources,
)
from src.persistence_models import RagIngestionJob


def _plain_text(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(value or ""))).strip()


def build_scoped_resources(
    content: list[dict[str, Any]],
    *,
    institution_id: str,
    course_id: int,
    course_code: str,
) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    for index, item in enumerate(content, start=1):
        body = _plain_text(item.get("body"))
        if not body or not item.get("published", True):
            continue
        resource_id = str(item.get("id") or index)
        version = hashlib.sha256(f"{resource_id}|{item.get('updated_at', '')}|{body}".encode()).hexdigest()
        title = str(item.get("title") or f"Học liệu {index}")
        resources.append(
            {
                "institution_id": institution_id,
                "course_id": str(course_id),
                "course_code": course_code,
                "resource_id": resource_id,
                "resource_version": version,
                "access_scope": "course",
                "document_title": title,
                "page": 1,
                "paragraph": index,
                "citation": f"[{title}, Trang 1, Đoạn {index}]",
                "content": body,
            }
        )
    return resources


def snapshot_version(resources: list[dict[str, Any]]) -> str:
    values = sorted(str(item["resource_version"]) for item in resources)
    return hashlib.sha256("|".join(values).encode()).hexdigest()


def enqueue_course_snapshot(
    db: Session,
    *,
    institution_id: str,
    course_id: int,
    resources: list[dict[str, Any]],
) -> RagIngestionJob:
    version = snapshot_version(resources)
    versioned_resources = [dict(item, snapshot_version=version) for item in resources]
    job_id = hashlib.sha256(f"{institution_id}:{course_id}:{version}".encode()).hexdigest()
    existing = db.get(RagIngestionJob, job_id)
    if existing:
        return existing
    job = RagIngestionJob(
        id=job_id,
        idempotency_key=f"rag:{institution_id}:{course_id}:{version}",
        institution_id=institution_id,
        course_id=course_id,
        resource_version=version,
        resources_json=json.dumps(versioned_resources, ensure_ascii=False),
    )
    db.add(job)
    return job


def process_ingestion_job(job: RagIngestionJob) -> dict[str, Any]:
    resources = json.loads(job.resources_json)
    if not resources:
        delete_course_resources(
            institution_id=job.institution_id,
            course_id=str(job.course_id),
        )
        return {"status": "empty", "total_chunks": 0}
    result = ingest_course_resources(resources)
    delete_stale_course_resources(
        institution_id=job.institution_id,
        course_id=str(job.course_id),
        current_snapshot_version=job.resource_version,
    )
    return result
