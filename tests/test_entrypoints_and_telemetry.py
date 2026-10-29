import builtins
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def test_model_usage_callback_records_tokens_cost_and_errors(monkeypatch):
    from src.agents import telemetry

    calls = []
    monkeypatch.setattr(telemetry, "increment", lambda name, **labels: calls.append((name, labels)))
    monkeypatch.setattr(
        telemetry,
        "get_settings",
        lambda: SimpleNamespace(
            llm_input_cost_per_million=2.0,
            llm_output_cost_per_million=4.0,
        ),
    )
    callback = telemetry.ModelUsageCallback()
    callback.on_llm_end(
        SimpleNamespace(
            llm_output={
                "model_name": "test-model",
                "token_usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            }
        )
    )
    callback.on_llm_error(RuntimeError("provider failed"))

    assert ("pacewise_llm_calls_total", {"model": "test-model", "outcome": "ok"}) in calls
    assert any(name == "pacewise_llm_tokens_total" for name, _labels in calls)
    assert any(name == "pacewise_llm_estimated_cost_usd_total" for name, _labels in calls)
    assert calls[-1][1]["outcome"] == "error"


def test_model_usage_callback_reads_message_metadata_and_flags_missing_usage(monkeypatch):
    from src.agents import telemetry

    calls = []
    monkeypatch.setattr(telemetry, "increment", lambda name, **labels: calls.append((name, labels)))
    monkeypatch.setattr(
        telemetry,
        "get_settings",
        lambda: SimpleNamespace(
            llm_input_cost_per_million=0.0,
            llm_output_cost_per_million=0.0,
        ),
    )
    callback = telemetry.ModelUsageCallback()
    message = SimpleNamespace(
        usage_metadata={"input_tokens": 40, "output_tokens": 10, "total_tokens": 50},
        response_metadata={"model_name": "metadata-model"},
    )
    callback.on_llm_end(
        SimpleNamespace(
            llm_output=None,
            generations=[[SimpleNamespace(message=message)]],
        )
    )
    callback.on_llm_end(SimpleNamespace(llm_output={}, generations=[]))

    assert (
        "pacewise_llm_tokens_total",
        {"amount": 50.0, "model": "metadata-model", "token_type": "total"},
    ) in calls
    assert ("pacewise_llm_usage_missing_total", {"model": "unknown"}) in calls


def test_llm_factories_apply_runtime_configuration(monkeypatch):
    from src.agents import llm as agent_llm
    from src.services import llm as service_llm

    created = []

    def fake_chat_openai(**kwargs):
        created.append(kwargs)
        return kwargs

    settings = SimpleNamespace(
        openai_api_key="api-key",
        openai_base_url="https://llm.example/v1",
        model_name="fallback-model",
        llm_fast_model="cx/gpt-5.6-luna",
        llm_reasoning_model="cx/gpt-5.6-sol",
        llm_temperature=0.2,
        llm_timeout_seconds=30.0,
        llm_max_output_tokens=600,
        llm_max_concurrent=8,
        llm_max_waiting=32,
        llm_queue_timeout_seconds=1.0,
        llm_cache_ttl_seconds=300,
        llm_cache_max_entries=256,
    )
    monkeypatch.setattr(agent_llm, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_llm, "ChatOpenAI", fake_chat_openai)
    monkeypatch.setenv("MODEL_NAME", "runtime-model")
    result = agent_llm.get_agent_llm(temperature=0.1)
    assert result["model"] == "runtime-model"
    assert result["callbacks"]

    assert agent_llm.get_agent_llm(model="explicit-model")["model"] == "explicit-model"
    monkeypatch.delenv("MODEL_NAME")
    settings.openai_base_url = "https://screensavers-nutten.example/v1"
    assert agent_llm.get_agent_llm()["model"] == "cx/gpt-5.6-luna"
    settings.openai_base_url = "https://llm.example/v1"
    assert agent_llm.get_agent_llm()["model"] == "fallback-model"

    assert agent_llm.get_agent_llm(task="qa", complexity="complex").model["model"] == "cx/gpt-5.6-luna"
    assert agent_llm.get_agent_llm(task="assessment").model["model"] == "cx/gpt-5.6-luna"
    assert agent_llm.get_agent_llm(task="reflect").model["model"] == "cx/gpt-5.6-luna"

    settings.openai_base_url = "http://host.docker.internal:20128/v1"
    monkeypatch.setattr(agent_llm.os.path, "exists", lambda _path: False)
    assert agent_llm.get_agent_llm()["base_url"] == "http://127.0.0.1:20128/v1"
    settings.openai_base_url = "https://llm.example/v1"

    monkeypatch.setattr(service_llm, "get_settings", lambda: settings)
    monkeypatch.setattr(service_llm, "ChatOpenAI", fake_chat_openai)
    result = service_llm.get_llm()
    assert result["model"] == "fallback-model"
    assert result["temperature"] == 0.2


@pytest.mark.asyncio
async def test_agent_cli_handles_state_new_message_and_exit(monkeypatch, capsys):
    from src.agents import __main__ as cli

    inputs = iter(["/state", "/new", "help me plan", "exit"])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(inputs))
    fake_agent = SimpleNamespace(
        get_state=lambda _config: SimpleNamespace(
            values={
                "current_node": "plan",
                "workflow": "plan",
                "proposed_milestones": [
                    {"milestone_id": "m1", "title": "Read", "estimated_minutes": 30}
                ],
                "retrieved_passages": [{"id": 1}],
                "disputed_evidence": [],
            }
        ),
        ainvoke=AsyncMock(
            return_value={
                "workflow": "plan",
                "current_node": "quality_gate",
                "response": "A complete and safe weekly study plan.",
                "proposed_milestones": [{"milestone_id": "m1"}],
            }
        ),
    )
    monkeypatch.setattr(cli, "agent", fake_agent)

    await cli.main()

    output = capsys.readouterr().out
    assert "quality_gate" in output
    fake_agent.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_cli_falls_back_to_recovery_text(monkeypatch, capsys):
    from src.agents import __main__ as cli

    inputs = iter(["recover", "q"])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(inputs))
    monkeypatch.setattr(
        "src.agents.workflows.recover._format_options_as_text",
        lambda _options: "Choose a recovery option",
    )
    monkeypatch.setattr(
        cli,
        "agent",
        SimpleNamespace(
            ainvoke=AsyncMock(
                return_value={
                    "workflow": "recover",
                    "current_node": "recover",
                    "response": "short",
                    "recovery_options": [{"id": "r1"}],
                }
            )
        ),
    )

    await cli.main()

    assert "Choose a recovery option" in capsys.readouterr().out


def test_ingest_cli_reports_success_and_failure(monkeypatch, capsys):
    from src.agents import ingest

    monkeypatch.setattr(
        ingest,
        "ingest_sample_documents",
        lambda **_kwargs: {
            "status": "success",
            "collection_name": "course_materials",
            "total_chunks": 3,
            "files_processed": ["syllabus.md"],
        },
    )
    ingest.main()
    assert "course_materials" in capsys.readouterr().out

    monkeypatch.setattr(
        ingest,
        "ingest_sample_documents",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("bad document")),
    )
    with pytest.raises(SystemExit) as stopped:
        ingest.main()
    assert stopped.value.code == 1


def test_worker_entrypoint_initializes_and_runs(monkeypatch):
    from src import worker

    settings = SimpleNamespace(log_level="INFO", course_source_mode="external")
    initialized = []
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "initialize_database", lambda: initialized.append(True))

    async def fake_worker(received):
        assert received is settings

    monkeypatch.setattr(worker, "run_worker", fake_worker)
    worker.main()
    assert initialized == [True]


def test_notification_worker_is_an_independent_entrypoint(monkeypatch):
    from src import notification_worker

    settings = SimpleNamespace(log_level="INFO", sqs_notification_queue_url="")
    calls = []

    class StopWorkerError(Exception):
        pass

    monkeypatch.setattr(notification_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(notification_worker, "initialize_database", lambda: calls.append("database"))
    monkeypatch.setattr(notification_worker, "recover_notification_leases", lambda received: calls.append(("recover", received)))
    monkeypatch.setattr(notification_worker, "deliver_due_reminders", lambda received: calls.append(("deliver", received)))
    monkeypatch.setattr(notification_worker, "purge_expired_transcripts", lambda received: calls.append(("purge-do-chat", received)))
    monkeypatch.setattr(
        notification_worker,
        "record_worker_heartbeat",
        lambda received, worker_kind: calls.append(("heartbeat", received, worker_kind)),
    )
    monkeypatch.setattr(
        notification_worker.time,
        "sleep",
        lambda _seconds: (_ for _ in ()).throw(StopWorkerError),
    )

    with pytest.raises(StopWorkerError):
        notification_worker.main()

    assert calls == [
        "database",
        ("purge-do-chat", settings),
        ("recover", settings),
        ("deliver", settings),
        ("heartbeat", settings, "notification"),
    ]


@pytest.mark.asyncio
async def test_application_lifespan_starts_and_stops_dependencies(monkeypatch):
    from src import main

    events = []

    class FakeBroker:
        def __init__(self, settings):
            self.settings = settings

        async def start(self):
            events.append("broker-start")

        async def stop(self):
            events.append("broker-stop")

    @asynccontextmanager
    async def fake_runtime_agent(_settings):
        events.append("agent-start")
        yield "durable-agent"
        events.append("agent-stop")

    monkeypatch.setattr(main, "initialize_database", lambda: events.append("db"))
    monkeypatch.setattr(main, "LmsEventBroker", FakeBroker)
    monkeypatch.setattr(main, "runtime_agent", fake_runtime_agent)

    async with main.lifespan(main.app):
        assert main.app.state.agent == "durable-agent"

    assert events == ["db", "broker-start", "agent-start", "agent-stop", "broker-stop"]
