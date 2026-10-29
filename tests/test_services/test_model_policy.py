import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from src.config import Settings
from src.observability import render_prometheus
from src.services import private_tracing
from src.services.model_policy import ControlledModel, ModelBusyError, model_tier


def wrapper(provider, *, task="qa", scope=None, **settings):
    return ControlledModel(
        provider,
        Settings(_env_file=None, **settings),
        task=task,
        tier=model_tier(task),
        model_name="fake",
        cache_scope=scope,
    )


def test_cache_is_scoped_bounded_expires_and_only_caches_safe_exact_tasks():
    class Provider:
        calls = 0

        def invoke(self, messages):
            self.calls += 1
            return SimpleNamespace(content="source-grounded-answer")

    provider = Provider()
    scope = str(uuid4())
    messages = [HumanMessage(content="same question")]
    first = wrapper(provider, scope=scope, llm_cache_ttl_seconds=1)
    first.invoke(messages).content = "client-mutated"
    assert first.invoke(messages).content == "source-grounded-answer" and provider.calls == 1
    wrapper(provider, scope=scope + ":other-user").invoke(messages)
    wrapper(provider, scope=scope + ":new-file-version").invoke(messages)
    assert provider.calls == 3
    time.sleep(1.05)
    first.invoke(messages)
    assert provider.calls == 4
    plan = wrapper(provider, task="plan", scope=scope + ":plan")
    plan.invoke(messages)
    plan.invoke(messages)
    assert provider.calls == 5
    assessment = wrapper(provider, task="assessment", scope=scope)
    assessment.invoke(messages)
    assessment.invoke(messages)
    assert provider.calls == 7
    assert model_tier("assessment") == "fast"
    assert model_tier("qa", "complex") == "fast"
    assert model_tier("qa") == "fast"
    assert model_tier("plan") == "fast"
    assert model_tier("reflect") == "fast"
    assert model_tier("reflect", "complex") == "reasoning"
    assert model_tier("recover") == "reasoning"


def test_1000_synthetic_requests_bound_provider_work_and_reject_overload():
    class Provider:
        active = peak = calls = 0
        lock = Lock()

        def invoke(self, messages):
            with self.lock:
                self.active += 1
                self.calls += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.01)
            with self.lock:
                self.active -= 1
            return SimpleNamespace(content="fake")

    provider = Provider()
    controlled = wrapper(
        provider, task="assessment", llm_max_concurrent=4, llm_max_waiting=4, llm_queue_timeout_seconds=0.03
    )

    def call(index):
        try:
            controlled.invoke([HumanMessage(content=str(index))])
            return "accepted"
        except ModelBusyError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=64) as executor:
        outcomes = list(executor.map(call, range(1000)))
    assert provider.peak <= 4 and provider.active == 0
    assert outcomes.count("rejected") > 0
    assert provider.calls == outcomes.count("accepted")
    metrics = render_prometheus()
    assert "pacewise_llm_duration_seconds_bucket" in metrics
    assert "pacewise_llm_active 0" in metrics
    print(
        {
            "synthetic_requests": 1000,
            "client_workers": 64,
            "provider_peak": provider.peak,
            "accepted": outcomes.count("accepted"),
            "rejected": outcomes.count("rejected"),
            "real_provider": False,
        }
    )


def test_langsmith_exports_no_learner_content_or_raw_error(monkeypatch):
    sent = []
    monkeypatch.setattr(
        private_tracing,
        "get_settings",
        lambda: Settings(_env_file=None, langsmith_enabled=True, langsmith_api_key="test-only"),
    )
    monkeypatch.setattr(private_tracing, "_enqueue", lambda method, payload: sent.append((method, payload)))
    with pytest.raises(RuntimeError):
        with private_tracing.trace_span("assessment"):
            raise RuntimeError("password=SECRET email=private@test.edu learner_answer=PRIVATE")
    text = str(sent)
    assert "SECRET" not in text and "private@test.edu" not in text and "learner_answer" not in text
    assert sent[0][1]["inputs"] == {} and sent[-1][1]["error"] == "RuntimeError"
    assert sent[-1][1]["outputs"] == {"outcome": "error"}


def test_langsmith_disabled_is_no_network(monkeypatch):
    monkeypatch.setattr(private_tracing, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(private_tracing, "_enqueue", lambda *_: pytest.fail("trace must be opt-in"))
    with private_tracing.trace_span("qa"):
        pass
