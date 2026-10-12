import os
from pathlib import Path
from tempfile import mkdtemp
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Never let .env or inherited deployment settings select a real database for
# fixtures that intentionally clear tables. Each test invocation owns its store.
_test_data_dir = Path(mkdtemp(prefix="pacewise-pytest-"))
os.environ["DATABASE_URL"] = "sqlite:///" + (_test_data_dir / "test.db").as_posix()
os.environ["APP_ENV"] = "test"
os.environ["CUSTOMER_DATA_KEY_FILE"] = str(_test_data_dir / "customer-data.key")
os.environ["LANGSMITH_ENABLED"] = "false"
os.environ["AI_RATE_LIMIT_ENABLED"] = "false"

# Existing endpoint contract tests use plain in-process requests. Protocol tests
# explicitly enable the mandatory encrypted gateway and verify no bypass.
os.environ.setdefault("PRIVATE_API_REQUIRED", "false")
# Legacy contract tests deliberately exercise the optional external adapter.
# Native end-to-end regressions select standalone explicitly and prohibit HTTP.
os.environ.setdefault("COURSE_SOURCE_MODE", "external")

from src.config import Settings, get_settings  # noqa: E402
from src.db import SessionLocal, initialize_database  # noqa: E402
from src.main import app  # noqa: E402
from src.persistence_models import (  # noqa: E402
    GoogleQuotaState,
    GoogleReadCache,
    LoginAttempt,
    StudyTimerSession,
    WorkerHeartbeat,
)


@pytest.fixture
def auth_settings():
    settings = Settings(_env_file=None, app_env="test", pacewise_api_key="test-service-key",
                        pacewise_session_secret="test-session-secret-at-least-32-characters")
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def initialize_test_database():
    initialize_database()
    with SessionLocal() as db:
        db.query(LoginAttempt).delete()
        db.query(GoogleQuotaState).delete()
        db.query(GoogleReadCache).delete()
        db.query(WorkerHeartbeat).delete()
        # Timers are intentionally durable in production, but tests must not
        # inherit an active/paused session created by a previous test case.
        db.query(StudyTimerSession).delete()
        db.commit()


@pytest.fixture
def mock_llm(monkeypatch):
    """Mock the synchronous LLM interface used by all agent workflows."""
    mock = MagicMock()

    def invoke(messages):
        system_prompt = str(messages[0].content)
        if "Coordinator Agent" in system_prompt:
            return SimpleNamespace(
                content='{"workflow": "qa", "reasoning": "Deterministic test route"}'
            )
        return SimpleNamespace(content="Mocked study-support response")

    mock.invoke.side_effect = invoke

    workflow_modules = (
        "src.agents.workflows.coordinator.get_agent_llm",
        "src.agents.workflows.plan.get_agent_llm",
        "src.agents.workflows.qa.get_agent_llm",
        "src.agents.workflows.understanding.get_agent_llm",
        "src.agents.workflows.recover.get_agent_llm",
        "src.agents.workflows.reflect.get_agent_llm",
    )
    for target in workflow_modules:
        monkeypatch.setattr(target, lambda **_kwargs: mock)

    monkeypatch.setattr(
        "src.agents.workflows.qa.search_course_materials",
        lambda **_kwargs: {
            "passages": [],
            "insufficient_sources": True,
            "top_score": 0.0,
        },
    )
    return mock
