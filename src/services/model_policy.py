"""Bounded model admission, deterministic tier selection and scoped exact cache."""

import copy
import hashlib
import json
import time
from collections import OrderedDict
from contextlib import contextmanager
from functools import lru_cache
from threading import BoundedSemaphore, Lock

from src.observability import gauge_delta, increment, observe
from src.services.private_tracing import trace_span


class ModelBusyError(RuntimeError):
    pass


class ModelAdmission:
    def __init__(self, concurrent: int, waiting: int, timeout: float):
        self._total = BoundedSemaphore(concurrent + waiting)
        self._active = BoundedSemaphore(concurrent)
        self.timeout = timeout

    @contextmanager
    def enter(self):
        if not self._total.acquire(blocking=False):
            increment("pacewise_llm_admission_total", outcome="rejected")
            raise ModelBusyError("Model capacity busy")
        acquired = False
        started = time.perf_counter()
        gauge_delta("pacewise_llm_waiting", 1)
        try:
            acquired = self._active.acquire(timeout=self.timeout)
        finally:
            gauge_delta("pacewise_llm_waiting", -1)
        try:
            observe("pacewise_llm_queue_duration_seconds", time.perf_counter() - started)
            if not acquired:
                increment("pacewise_llm_admission_total", outcome="timeout")
                raise ModelBusyError("Model capacity busy")
            gauge_delta("pacewise_llm_active", 1)
            increment("pacewise_llm_admission_total", outcome="accepted")
            try:
                yield
            finally:
                gauge_delta("pacewise_llm_active", -1)
        finally:
            if acquired:
                self._active.release()
            self._total.release()


@lru_cache(maxsize=4)
def admission(concurrent, waiting, timeout):
    return ModelAdmission(concurrent, waiting, timeout)


def model_tier(task: str, complexity: str = "simple") -> str:
    # Student-facing tutoring, bounded plan decomposition and formative
    # assessment stay on the low-latency model. Reflect is routed explicitly:
    # activity and low-evidence weeks use Luna, while evidence-rich or
    # contradictory weeks use Sol.  In both cases deterministic services keep
    # authority over minutes, factors, mastery and calendar changes.
    if task == "reflect":
        return "reasoning" if complexity == "complex" else "fast"
    if task in {"qa", "plan", "assessment", "understanding", "question_design"}:
        return "fast"
    return (
        "reasoning"
        if task == "recover" or complexity == "complex"
        else "fast"
    )


_cache = OrderedDict()
_cache_lock = Lock()
_key_locks = [Lock() for _ in range(64)]


class ControlledModel:
    def __init__(self, model, settings, *, task, tier, model_name, cache_scope=None):
        self.model, self.settings = model, settings
        self.task, self.tier, self.model_name = task, tier, model_name
        # Exact QA and plan decomposition responses may be reused briefly.
        # Assessment, reflection and decisions are intentionally never cached.
        self.cache_scope = cache_scope if task in {"qa", "plan"} else None
        self.gate = admission(settings.llm_max_concurrent, settings.llm_max_waiting, settings.llm_queue_timeout_seconds)

    def _key(self, messages):
        data = {
            "scope": self.cache_scope,
            "model": self.model_name,
            "policy": "grounded-tutor-v1",
            "messages": [
                (getattr(message, "type", "unknown"), str(getattr(message, "content", message))) for message in messages
            ],
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def invoke(self, messages, **kwargs):
        ttl = self.settings.llm_cache_ttl_seconds
        key = self._key(messages) if self.cache_scope and ttl > 0 else None
        if not key:
            return self._invoke(messages, **kwargs)
        lock = _key_locks[int(key[:8], 16) % len(_key_locks)]
        if not lock.acquire(timeout=self.settings.llm_queue_timeout_seconds):
            raise ModelBusyError("Cached request busy")
        try:
            with _cache_lock:
                entry = _cache.get(key)
                if entry and entry[0] > time.monotonic():
                    _cache.move_to_end(key)
                    increment("pacewise_llm_cache_total", outcome="hit")
                    return copy.deepcopy(entry[1])
                _cache.pop(key, None)
            increment("pacewise_llm_cache_total", outcome="miss")
            result = self._invoke(messages, **kwargs)
            with _cache_lock:
                _cache[key] = (time.monotonic() + ttl, copy.deepcopy(result))
                while len(_cache) > self.settings.llm_cache_max_entries:
                    _cache.popitem(last=False)
            return result
        finally:
            lock.release()

    def _invoke(self, messages, **kwargs):
        started = time.perf_counter()
        outcome = "error"
        try:
            with self.gate.enter(), trace_span(self.task, "llm"):
                increment("pacewise_llm_routing_total", task=self.task, tier=self.tier)
                result = self.model.invoke(messages, **kwargs)
                outcome = "ok"
                return result
        finally:
            observe("pacewise_llm_duration_seconds", time.perf_counter() - started, task=self.task, outcome=outcome)

    def stream(self, messages, **kwargs):
        """Stream provider chunks under the same admission and telemetry policy.

        Exact-response caching is intentionally bypassed: a cache hit would be
        one large chunk and defeat time-to-first-content guarantees.
        """
        started = time.perf_counter()
        outcome = "error"
        try:
            with self.gate.enter(), trace_span(self.task, "llm_stream"):
                increment("pacewise_llm_routing_total", task=self.task, tier=self.tier)
                yield from self.model.stream(messages, **kwargs)
                outcome = "ok"
        finally:
            observe("pacewise_llm_duration_seconds", time.perf_counter() - started, task=self.task, outcome=outcome)
