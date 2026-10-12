import json
from types import SimpleNamespace

from src.config import Settings
from src.services import aws_queues


class FakeSqsClient:
    def __init__(self, *, messages=None):
        self.messages = messages or []
        self.calls = []

    def send_message(self, **kwargs):
        self.calls.append(("send_message", kwargs))
        return {"MessageId": "message-123"}

    def receive_message(self, **kwargs):
        self.calls.append(("receive_message", kwargs))
        return {"Messages": self.messages}

    def delete_message(self, **kwargs):
        self.calls.append(("delete_message", kwargs))

    def change_message_visibility(self, **kwargs):
        self.calls.append(("change_message_visibility", kwargs))


def test_client_uses_bounded_timeouts_and_configured_region(monkeypatch):
    captured = {}

    def client(service, **kwargs):
        captured.update(service=service, **kwargs)
        return object()

    monkeypatch.setattr("boto3.client", client)
    settings = Settings(
        _env_file=None,
        app_env="test",
        aws_region="ap-southeast-1",
        readiness_timeout_seconds=1.5,
        sqs_wait_time_seconds=10,
    )

    aws_queues._client(settings)

    assert captured["service"] == "sqs"
    assert captured["region_name"] == "ap-southeast-1"
    assert captured["config"].connect_timeout == 1.5
    assert captured["config"].read_timeout == 12
    assert captured["config"].retries == {"max_attempts": 3, "mode": "standard"}


def test_publish_job_keeps_payload_minimal_and_adds_fifo_deduplication(monkeypatch):
    client = FakeSqsClient()
    monkeypatch.setattr(aws_queues, "_client", lambda _: client)
    settings = Settings(_env_file=None, app_env="test")

    standard_id = aws_queues.publish_job(
        settings,
        "https://sqs.example/jobs",
        "rag_ingestion",
        "job-1",
        "ignored-for-standard",
    )
    fifo_id = aws_queues.publish_job(
        settings,
        "https://sqs.example/jobs.fifo",
        "notification",
        "job-2",
        "d" * 200,
    )

    assert standard_id == fifo_id == "message-123"
    standard = client.calls[0][1]
    assert json.loads(standard["MessageBody"]) == {"kind": "rag_ingestion", "job_id": "job-1"}
    assert "MessageGroupId" not in standard
    fifo = client.calls[1][1]
    assert fifo["MessageGroupId"] == "notification"
    assert fifo["MessageDeduplicationId"] == "d" * 128


def test_receive_jobs_bounds_batch_and_rejects_malformed_or_wrong_kind(monkeypatch):
    long_job_id = "j" * 300
    client = FakeSqsClient(
        messages=[
            {"Body": "not-json"},
            {"Body": json.dumps({"kind": "notification", "job_id": "wrong-kind"})},
            {"Body": json.dumps({"kind": "rag_ingestion", "job_id": 7})},
            {
                "Body": json.dumps({"kind": "rag_ingestion", "job_id": long_job_id}),
                "ReceiptHandle": "receipt-1",
                "MessageId": "message-1",
            },
        ]
    )
    monkeypatch.setattr(aws_queues, "_client", lambda _: client)
    settings = Settings(
        _env_file=None,
        app_env="test",
        sqs_wait_time_seconds=7,
        worker_lease_seconds=90,
    )

    messages = aws_queues.receive_jobs(settings, "queue-url", "rag_ingestion", limit=99)

    assert messages == [
        aws_queues.QueueMessage(
            job_id="j" * 255,
            receipt_handle="receipt-1",
            message_id="message-1",
        )
    ]
    request = client.calls[0][1]
    assert request["MaxNumberOfMessages"] == 10
    assert request["WaitTimeSeconds"] == 7
    assert request["VisibilityTimeout"] == 90


def test_receive_jobs_enforces_a_minimum_batch_size(monkeypatch):
    client = FakeSqsClient()
    monkeypatch.setattr(aws_queues, "_client", lambda _: client)

    assert aws_queues.receive_jobs(Settings(_env_file=None, app_env="test"), "queue-url", "notification", limit=0) == []
    assert client.calls[0][1]["MaxNumberOfMessages"] == 1


def test_delete_and_visibility_extension_use_only_delivery_identifiers(monkeypatch):
    client = FakeSqsClient()
    monkeypatch.setattr(aws_queues, "_client", lambda _: client)
    settings = Settings(_env_file=None, app_env="test", worker_lease_seconds=75)

    aws_queues.delete_message(settings, "queue-url", "receipt-delete")
    aws_queues.extend_visibility(settings, "queue-url", "receipt-extend")

    assert client.calls == [
        ("delete_message", {"QueueUrl": "queue-url", "ReceiptHandle": "receipt-delete"}),
        (
            "change_message_visibility",
            {"QueueUrl": "queue-url", "ReceiptHandle": "receipt-extend", "VisibilityTimeout": 75},
        ),
    ]


def test_visibility_heartbeat_extends_once_and_always_stops(monkeypatch):
    events = []

    class FakeEvent:
        def __init__(self):
            self.waits = 0

        def wait(self, seconds):
            events.append(("wait", seconds))
            self.waits += 1
            return self.waits > 1

        def set(self):
            events.append(("set", None))

    class FakeThread:
        def __init__(self, *, target, daemon, name):
            assert daemon and name == "sqs-visibility"
            self.target = target

        def start(self):
            self.target()

        def join(self, timeout):
            events.append(("join", timeout))

    monkeypatch.setattr(aws_queues.threading, "Event", FakeEvent)
    monkeypatch.setattr(aws_queues.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        aws_queues,
        "extend_visibility",
        lambda settings, queue_url, receipt: events.append((queue_url, receipt)),
    )
    settings = SimpleNamespace(worker_lease_seconds=30)

    with aws_queues.visibility_heartbeat(settings, "queue-url", "receipt"):
        events.append(("body", None))

    assert events == [
        ("wait", 10),
        ("queue-url", "receipt"),
        ("wait", 10),
        ("body", None),
        ("set", None),
        ("join", 1),
    ]


def test_visibility_heartbeat_stops_after_extension_failure(monkeypatch):
    class FakeEvent:
        def wait(self, _seconds):
            return False

        def set(self):
            return None

    class FakeThread:
        def __init__(self, *, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

        def join(self, timeout):
            assert timeout == 1
            return None

    monkeypatch.setattr(aws_queues.threading, "Event", FakeEvent)
    monkeypatch.setattr(aws_queues.threading, "Thread", FakeThread)
    monkeypatch.setattr(aws_queues, "extend_visibility", lambda *_: (_ for _ in ()).throw(RuntimeError("SQS unavailable")))

    with aws_queues.visibility_heartbeat(SimpleNamespace(worker_lease_seconds=30), "queue-url", "receipt"):
        pass
