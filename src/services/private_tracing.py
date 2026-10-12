"""Opt-in LangSmith spans with no learner content, IDs, credentials, or raw errors.

Network work is off the request path and the queue is bounded. Native LangChain
tracing must stay disabled: it otherwise exports graph state/prompts by default.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import lru_cache
from queue import Empty, Full, Queue
from threading import Lock, Thread
from uuid import uuid4

from src.config import get_settings
from src.observability import increment

_parent = ContextVar("private_trace_parent", default=None)
_queue = Queue(maxsize=128)
_start_lock = Lock()
_started = False


@lru_cache(maxsize=1)
def _client():
    from langsmith import Client

    settings = get_settings()
    return Client(
        api_key=settings.langsmith_api_key,
        api_url=settings.langsmith_endpoint,
        workspace_id=settings.langsmith_workspace_id or None,
        hide_inputs=True,
        hide_outputs=False,
        timeout_ms=2000,
        # Our bounded worker already batches work off the request path. Avoid a
        # second SDK queue: "ok" must mean HTTP delivery, not merely SDK enqueue.
        auto_batch_tracing=False,
        omit_traced_runtime_info=True,
    )


def _worker():
    while True:
        batch = [_queue.get()]
        # Coalesce completed spans without an unbounded second SDK queue.
        # Batch ingestion also avoids create/PATCH indexing races on child runs.
        while len(batch) < 32:
            try:
                batch.append(_queue.get(timeout=0.05))
            except Empty:
                break
        try:
            _deliver_batch(batch)
            increment("pacewise_trace_operations_total", outcome="ok")
        except Exception:
            increment("pacewise_trace_operations_total", outcome="error")
        finally:
            for _ in batch:
                _queue.task_done()


def _deliver_batch(batch):
    completed = []
    for method, payload in batch:
        if method != "create_run" or payload.get("end_time") is None:
            raise ValueError("Only completed, metadata-only spans may be delivered")
        run = dict(payload)
        run["session_name"] = run.pop("project_name")
        completed.append(run)
    _client().batch_ingest_runs(create=completed)


def _enqueue(method, payload):
    global _started
    with _start_lock:
        if not _started:
            Thread(target=_worker, daemon=True, name="private-langsmith-traces").start()
            _started = True
    try:
        _queue.put_nowait((method, payload))
    except Full:
        increment("pacewise_trace_operations_total", outcome="dropped")


@contextmanager
def trace_span(name: str, run_type: str = "chain"):
    settings = get_settings()
    if (
        not settings.langsmith_enabled
        or not settings.langsmith_api_key
        or settings.langsmith_api_key.startswith("your-")
    ):
        yield None
        return
    # All callers pass application-owned names, never query strings/user input.
    allowed = {
        "coordinator",
        "plan",
        "do",
        "qa",
        "understanding",
        "assessment",
        "reflect",
        "recover",
        "tracking",
        "quality_gate",
        "repair",
        "safety",
        "question_design",
        "llm",
    }
    name = name if name in allowed else "llm"
    run_id, now = uuid4(), datetime.now(UTC)
    parent = _parent.get()
    order = f"{now.strftime('%Y%m%dT%H%M%S%fZ')}{run_id}"
    trace_id = parent[0] if parent else run_id
    dotted = f"{parent[2]}.{order}" if parent else order
    payload = {
        "name": name,
        "inputs": {},
        "run_type": run_type,
        "id": run_id,
        "trace_id": trace_id,
        "dotted_order": dotted,
        "start_time": now,
        "project_name": settings.langsmith_project,
    }
    if parent:
        payload["parent_run_id"] = parent[1]
    token = _parent.set((trace_id, run_id, dotted))
    outcome, error = "ok", None
    try:
        yield run_id
    except Exception as exc:
        outcome, error = "error", type(exc).__name__
        raise
    finally:
        _parent.reset(token)
        # Publish once at completion. Ongoing latency is observed locally by
        # Prometheus; no premature cloud run/PATCH pair can lose its end state.
        _enqueue(
            "create_run",
            {
                **payload,
                "end_time": datetime.now(UTC),
                "outputs": {"outcome": outcome},
                "error": error,
            },
        )
