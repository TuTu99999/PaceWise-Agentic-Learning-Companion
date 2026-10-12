"""Small, payload-safe SQS adapter used by the durable DB job queues.

The database remains the source of truth. SQS messages contain only a job kind
and opaque job id, so duplicate delivery is harmless and no learner data leaves
the application database.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

from src.config import Settings

QueueKind = Literal["rag_ingestion", "notification"]


@dataclass(frozen=True)
class QueueMessage:
    job_id: str
    receipt_handle: str
    message_id: str


def _client(settings: Settings):
    import boto3
    from botocore.config import Config

    return boto3.client(
        "sqs",
        region_name=settings.aws_region,
        config=Config(
            connect_timeout=settings.readiness_timeout_seconds,
            read_timeout=max(settings.readiness_timeout_seconds, settings.sqs_wait_time_seconds + 2),
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def publish_job(settings: Settings, queue_url: str, kind: QueueKind, job_id: str, idempotency_key: str) -> str:
    body = json.dumps({"kind": kind, "job_id": job_id}, separators=(",", ":"))
    params: dict = {"QueueUrl": queue_url, "MessageBody": body}
    if queue_url.endswith(".fifo"):
        params.update(
            MessageGroupId=kind,
            MessageDeduplicationId=idempotency_key[:128],
        )
    response = _client(settings).send_message(**params)
    return str(response.get("MessageId") or "")


def receive_jobs(settings: Settings, queue_url: str, expected_kind: QueueKind, *, limit: int = 10) -> list[QueueMessage]:
    response = _client(settings).receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=max(1, min(10, limit)),
        WaitTimeSeconds=settings.sqs_wait_time_seconds,
        VisibilityTimeout=settings.worker_lease_seconds,
        AttributeNames=["ApproximateReceiveCount"],
    )
    result: list[QueueMessage] = []
    for raw in response.get("Messages") or []:
        try:
            payload = json.loads(raw.get("Body") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if payload.get("kind") != expected_kind or not isinstance(payload.get("job_id"), str):
            continue
        result.append(
            QueueMessage(
                job_id=payload["job_id"][:255],
                receipt_handle=str(raw.get("ReceiptHandle") or ""),
                message_id=str(raw.get("MessageId") or ""),
            )
        )
    return result


def delete_message(settings: Settings, queue_url: str, receipt_handle: str) -> None:
    _client(settings).delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)


def extend_visibility(settings: Settings, queue_url: str, receipt_handle: str) -> None:
    _client(settings).change_message_visibility(
        QueueUrl=queue_url,
        ReceiptHandle=receipt_handle,
        VisibilityTimeout=settings.worker_lease_seconds,
    )


@contextmanager
def visibility_heartbeat(settings: Settings, queue_url: str, receipt_handle: str):
    """Keep a long-running SQS delivery leased without placing payload in logs."""
    stop = threading.Event()

    def pulse() -> None:
        while not stop.wait(max(5, settings.worker_lease_seconds // 3)):
            try:
                extend_visibility(settings, queue_url, receipt_handle)
            except Exception:
                return

    thread = threading.Thread(target=pulse, daemon=True, name="sqs-visibility")
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)
