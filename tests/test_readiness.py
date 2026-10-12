"""Infrastructure health must be bounded, truthful and safe to expose."""

import pytest

from src.config import Settings
from src.readiness import readiness_report


def test_readiness_report_is_green_only_when_every_required_probe_passes():
    settings = Settings(_env_file=None, app_env="test")
    healthy, checks = readiness_report(
        settings,
        probes={"database": lambda _: None, "objectStore": lambda _: None},
    )

    assert healthy
    assert checks == {"database": {"ok": True}, "objectStore": {"ok": True}}


def test_readiness_report_hides_dependency_error_details():
    settings = Settings(_env_file=None, app_env="test")

    def failed(_: Settings) -> None:
        raise RuntimeError("postgresql://user:secret@private-host/database")

    healthy, checks = readiness_report(settings, probes={"database": failed})

    assert not healthy
    assert checks == {"database": {"ok": False, "errorType": "RuntimeError"}}
    assert "secret" not in str(checks)


@pytest.mark.asyncio
async def test_liveness_and_readiness_are_distinct(client, monkeypatch):
    assert (await client.get("/livez")).json() == {"status": "alive"}
    monkeypatch.setattr("src.main.readiness_report", lambda _settings: (False, {"database": {"ok": False}}))

    response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
