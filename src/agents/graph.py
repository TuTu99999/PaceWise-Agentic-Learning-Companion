"""
Master LangGraph: kết nối Coordinator và 7 workflow nhánh với durable PostgreSQL
checkpointer ở runtime; MemorySaver chỉ dùng cho unit test/SQLite local.
"""

import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.agents.state import LearningGraphState
from src.agents.workflows.coordinator import coordinator_node
from src.agents.workflows.do import do_node
from src.agents.workflows.plan import plan_node
from src.agents.workflows.qa import qa_node
from src.agents.workflows.quality_gate import quality_gate_node, repair_node
from src.agents.workflows.recover import recover_node
from src.agents.workflows.reflect import reflect_node
from src.agents.workflows.tracking import tracking_node
from src.agents.workflows.understanding import understanding_node
from src.config import Settings
from src.observability import observe_agent_node
from src.services.private_tracing import trace_span


def route_workflow(state: LearningGraphState) -> str:
    """Điều hướng từ coordinator sang workflow tương ứng."""
    workflow = state.get("workflow", "qa")
    valid_workflows = {"plan", "do", "tracking", "qa", "understanding", "recover", "reflect"}
    return workflow if workflow in valid_workflows else "qa"


def route_quality_review(state: LearningGraphState) -> str:
    """Allow one repair pass, then always terminate safely."""
    review = state.get("quality_review") or {}
    if review.get("passed") or int(state.get("quality_repair_count") or 0) >= 1:
        return "end"
    return "repair"


# Checkpointer mặc định lưu trạng thái hội thoại nhiều lượt trong bộ nhớ
default_checkpointer = MemorySaver()


def _audit_delta(
    previous_events: list[dict[str, Any]],
    returned_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize legacy full-history node output into reducer-safe deltas."""
    prefix_length = len(previous_events)
    if returned_events[:prefix_length] == previous_events:
        return returned_events[prefix_length:]
    return returned_events


def instrument_node(name: str, node: Callable[[LearningGraphState], dict[str, Any]]):
    """Attach privacy-safe latency/status telemetry to every workflow node."""

    def run(state: LearningGraphState) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = node(state)
            outcome = "ok"
            duration = time.perf_counter() - started
            observe_agent_node(name, outcome, duration)
            node_events = _audit_delta(
                state.get("audit_events") or [],
                result.get("audit_events") or [],
            )
            return result | {
                "audit_events": [
                    *node_events,
                    {
                        "event": "AGENT_NODE_COMPLETED",
                        "node": name,
                        "workflow": result.get("current_node", name),
                        "outcome": outcome,
                        "latency_ms": round(duration * 1000, 2),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                ]
            }
        except Exception as exc:
            observe_agent_node(name, "error", time.perf_counter() - started)
            exc.add_note(f"agent_node={name}")
            raise

    def wrapped(state: LearningGraphState) -> dict[str, Any]:
        with trace_span(name):
            return run(state)

    return wrapped


def create_agent(checkpointer: Any = default_checkpointer):
    """
    Khởi tạo và biên dịch StateGraph cho Multi-Agent system.
    Tích hợp Checkpointer để duy trì bộ nhớ phiên hội thoại nhiều lượt.
    """
    builder = StateGraph(LearningGraphState)

    # 1. Thêm các Node
    builder.add_node("coordinator", instrument_node("coordinator", coordinator_node))
    builder.add_node("plan", instrument_node("plan", plan_node))
    builder.add_node("do", instrument_node("do", do_node))
    builder.add_node("tracking", instrument_node("tracking", tracking_node))
    builder.add_node("qa", instrument_node("qa", qa_node))
    builder.add_node("understanding", instrument_node("understanding", understanding_node))
    builder.add_node("recover", instrument_node("recover", recover_node))
    builder.add_node("reflect", instrument_node("reflect", reflect_node))
    builder.add_node("quality_gate", instrument_node("quality_gate", quality_gate_node))
    builder.add_node("repair", instrument_node("repair", repair_node))

    # 2. Đặt điểm bắt đầu
    builder.set_entry_point("coordinator")

    # 3. Thêm cạnh rẽ nhánh từ coordinator
    builder.add_conditional_edges(
        "coordinator",
        route_workflow,
        {
            "plan": "plan",
            "do": "do",
            "tracking": "tracking",
            "qa": "qa",
            "understanding": "understanding",
            "recover": "recover",
            "reflect": "reflect",
        },
    )

    # 4. Specialist output always passes through a shared critic before END.
    for workflow in ("plan", "do", "tracking", "qa", "understanding", "recover", "reflect"):
        builder.add_edge(workflow, "quality_gate")
    builder.add_conditional_edges(
        "quality_gate",
        route_quality_review,
        {"repair": "repair", "end": END},
    )
    builder.add_edge("repair", "quality_gate")

    if checkpointer is not None:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()


# Instance agent chính dùng cho API và CLI (được trang bị Checkpointer)
agent = create_agent()
checkpointer = default_checkpointer


def _postgres_checkpoint_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@asynccontextmanager
async def runtime_agent(settings: Settings):
    """Use durable Postgres state in deployed environments and memory in local tests."""
    if settings.use_postgres_checkpoint and settings.database_url.startswith("postgresql"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(
            _postgres_checkpoint_url(settings.database_url)
        ) as postgres_checkpointer:
            await postgres_checkpointer.setup()
            yield create_agent(postgres_checkpointer)
        return
    yield agent
