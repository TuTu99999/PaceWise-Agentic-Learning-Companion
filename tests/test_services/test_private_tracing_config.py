"""Credential compatibility and opt-in privacy, using fake keys only."""

import pytest

from src.config import Settings
from src.services import private_tracing


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY", "LANGSMITH_ENABLED", "LANGSMITH_WORKSPACE_ID", "LANGCHAIN_WORKSPACE_ID"):
        monkeypatch.delenv(name, raising=False)


def test_legacy_key_is_supported_without_implicitly_enabling_traces(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_API_KEY", "legacy-test-only")
    settings = Settings(_env_file=None)
    assert settings.langsmith_api_key == "legacy-test-only"
    assert settings.langsmith_enabled is False
    assert "legacy-test-only" not in repr(settings)


def test_modern_key_wins_over_legacy_key(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_API_KEY", "legacy-test-only")
    monkeypatch.setenv("LANGSMITH_API_KEY", "modern-test-only")
    assert Settings(_env_file=None).langsmith_api_key == "modern-test-only"


def test_explicit_empty_modern_key_does_not_fall_back(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_API_KEY", "legacy-test-only")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    assert Settings(_env_file=None).langsmith_api_key == ""


def test_explicit_constructor_key_wins_over_environment(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "environment-test-only")
    assert Settings(_env_file=None, langsmith_api_key="test-only").langsmith_api_key == "test-only"


def test_workspace_alias_and_modern_precedence(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_WORKSPACE_ID", "legacy-workspace")
    assert Settings(_env_file=None).langsmith_workspace_id == "legacy-workspace"
    monkeypatch.setenv("LANGSMITH_WORKSPACE_ID", "modern-workspace")
    assert Settings(_env_file=None).langsmith_workspace_id == "modern-workspace"


def test_private_client_uses_one_queue_and_omits_runtime_metadata(monkeypatch):
    captured = {}
    import langsmith

    monkeypatch.setattr(langsmith, "Client", lambda **kwargs: captured.update(kwargs) or object())
    monkeypatch.setattr(private_tracing, "get_settings", lambda: Settings(_env_file=None, langsmith_api_key="test-only", langsmith_workspace_id="test-workspace"))
    private_tracing._client.cache_clear()
    try:
        private_tracing._client()
        assert captured["auto_batch_tracing"] is False
        assert captured["omit_traced_runtime_info"] is True
        assert captured["hide_inputs"] is True
        assert captured["workspace_id"] == "test-workspace"
    finally:
        private_tracing._client.cache_clear()


def test_span_exposes_only_technical_id_and_preserves_parent_relationship(monkeypatch):
    captured = []
    monkeypatch.setattr(private_tracing, "get_settings", lambda: Settings(_env_file=None, langsmith_enabled=True, langsmith_api_key="test-only"))
    monkeypatch.setattr(private_tracing, "_enqueue", lambda method, payload: captured.append((method, payload)))
    with private_tracing.trace_span("coordinator") as root_id:
        with private_tracing.trace_span("assessment") as child_id:
            assert root_id != child_id
    child = captured[0][1]
    assert child["parent_run_id"] == root_id
    assert child["trace_id"] == root_id
    assert all(payload.get("inputs", {}) == {} for _, payload in captured)
    assert all(method == "create_run" and payload["end_time"] is not None for method, payload in captured)


def test_completed_spans_are_batched_without_sdk_queue(monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    sent = []
    monkeypatch.setattr(private_tracing, "_client", lambda: SimpleNamespace(batch_ingest_runs=lambda **kwargs: sent.append(kwargs)))
    payload = {"project_name": "private-test", "inputs": {}, "outputs": {"outcome": "ok"}, "end_time": datetime.now(UTC)}
    private_tracing._deliver_batch([("create_run", payload), ("create_run", payload)])
    assert len(sent) == 1 and len(sent[0]["create"]) == 2
    assert all(run["session_name"] == "private-test" and "project_name" not in run for run in sent[0]["create"])
    assert payload["project_name"] == "private-test"  # No mutation of caller data.


def test_incomplete_spans_are_not_delivered(monkeypatch):
    monkeypatch.setattr(private_tracing, "_client", lambda: pytest.fail("incomplete spans must not reach SDK"))
    with pytest.raises(ValueError):
        private_tracing._deliver_batch([("create_run", {"project_name": "private-test"})])
