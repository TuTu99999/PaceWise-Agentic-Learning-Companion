"""Bounded dependency probes for load-balancer readiness checks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy import text

from src.config import Settings
from src.db import engine
from src.schema import SCHEMA_REVISION

Probe = Callable[[Settings], None]


def probe_database(settings: Settings) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        if settings.app_env in {"staging", "production"}:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision != settings.database_schema_revision or revision != SCHEMA_REVISION:
                raise RuntimeError("database schema revision mismatch")


def probe_s3(settings: Settings) -> None:
    if settings.course_storage_backend != "s3":
        return
    import boto3
    from botocore.config import Config

    timeout = settings.readiness_timeout_seconds
    client = boto3.client(
        "s3",
        region_name=settings.aws_region,
        config=Config(
            connect_timeout=timeout,
            read_timeout=timeout,
            retries={"max_attempts": 1, "mode": "standard"},
        ),
    )
    client.head_bucket(Bucket=settings.s3_course_materials_bucket)


def probe_qdrant(settings: Settings) -> None:
    if not settings.qdrant_url.strip():
        return
    headers = {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else {}
    response = httpx.get(
        settings.qdrant_url.rstrip("/") + "/readyz",
        headers=headers,
        timeout=settings.readiness_timeout_seconds,
    )
    response.raise_for_status()


def readiness_report(
    settings: Settings,
    *,
    probes: dict[str, Probe] | None = None,
) -> tuple[bool, dict[str, dict[str, Any]]]:
    selected = probes or {"database": probe_database, "s3": probe_s3, "qdrant": probe_qdrant}
    checks: dict[str, dict[str, Any]] = {}
    healthy = True
    for name, probe in selected.items():
        try:
            probe(settings)
            checks[name] = {"ok": True}
        except Exception as exc:
            healthy = False
            # Readiness is public to infrastructure; never leak endpoints,
            # credentials, SQL or provider response bodies.
            checks[name] = {"ok": False, "errorType": type(exc).__name__}
    return healthy, checks
