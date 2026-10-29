from types import SimpleNamespace

import pytest

from src.agents.graph import agent
from src.agents.workflows.qa import stream_qa_tokens


@pytest.mark.asyncio
async def test_agent_basic_flow(mock_llm):
    config = {"configurable": {"thread_id": "test-basic-flow"}}
    result = await agent.ainvoke({"query": "Hello"}, config=config)
    assert "response" in result
    assert result["workflow"] == "qa"
    assert result["current_node"] == "qa"
    assert result["mode"] == "conversation"
    assert "sẵn sàng hỗ trợ" in result["response"]
    assert result.get("source_refs") == []


@pytest.mark.asyncio
async def test_graph_propagates_request_local_qa_stream_sink(monkeypatch):
    citation = "[Giao trinh AI, Trang 1, Doan 2]"
    monkeypatch.setattr(
        "src.agents.workflows.qa.search_course_materials",
        lambda **_kwargs: {
            "passages": [{
                "citation": citation, "content": "Hoc co giam sat dung du lieu gan nhan.",
                "document_title": "Giao trinh AI", "course_code": "AI101",
                "page": 1, "paragraph": 2, "score": 0.9,
            }],
            "insufficient_sources": False,
            "top_score": 0.9,
        },
    )
    chunks = ["Hoc co giam sat. [S", "1]"]
    monkeypatch.setattr(
        "src.agents.workflows.qa.get_agent_llm",
        lambda **_kwargs: SimpleNamespace(stream=lambda _messages: (
            SimpleNamespace(content=value) for value in chunks
        )),
    )
    emitted = []
    with stream_qa_tokens(emitted.append):
        result = await agent.ainvoke(
            {
                "workflow": "qa", "query": "Giai thich hoc co giam sat", "course_id": "AI101",
                "request": {"workflow_hint": "qa"},
            },
            config={"configurable": {"thread_id": "qa-stream-context-propagation"}},
        )

    assert "".join(emitted) == f"Hoc co giam sat. {citation}"
    assert result["response"] == f"Hoc co giam sat. {citation}"


@pytest.mark.asyncio
async def test_agent_state_structure(mock_llm):
    config = {"configurable": {"thread_id": "test-state-structure"}}
    result = await agent.ainvoke({"query": "Test query"}, config=config)
    assert isinstance(result, dict)
    assert "query" in result
    assert isinstance(result["retrieved_passages"], list)
    assert isinstance(result["source_refs"], list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_node"),
    [
        ("Lập kế hoạch tuần và chia nhỏ milestone", "plan"),
        ("Kiểm tra tiến độ và thời gian thực tế", "tracking"),
        ("Giải thích khái niệm trong bài học", "qa"),
        ("Kiểm tra hiểu bài theo rubric", "understanding"),
        ("Mình trễ deadline, hãy cứu lịch", "recover"),
        ("Phản tư và tổng kết cuối tuần", "reflect"),
    ],
)
async def test_graph_routes_all_workflows(mock_llm, query, expected_node):
    config = {"configurable": {"thread_id": f"route-{expected_node}"}}
    result = await agent.ainvoke({"query": query}, config=config)
    assert result["current_node"] == expected_node
    assert any(event["node"] == expected_node for event in result["audit_events"])


@pytest.mark.asyncio
async def test_graph_preserves_workflow_audit_events(mock_llm):
    config = {"configurable": {"thread_id": "audit-citation-dispute"}}
    result = await agent.ainvoke(
        {"query": "Trích dẫn sai [Giáo trình, Trang 2, Đoạn 1]"},
        config=config,
    )
    assert any(event["event"] == "CITATION_DISPUTED" for event in result["audit_events"])


@pytest.mark.asyncio
async def test_graph_appends_only_new_audit_events_per_turn(mock_llm):
    config = {"configurable": {"thread_id": "audit-events-are-deltas"}}

    first = await agent.ainvoke({"query": "Giải thích khái niệm"}, config=config)
    second = await agent.ainvoke({"query": "Giải thích ví dụ tiếp theo"}, config=config)

    first_nodes = [
        event["node"]
        for event in first["audit_events"]
        if event["event"] == "AGENT_NODE_COMPLETED"
    ]
    second_nodes = [
        event["node"]
        for event in second["audit_events"]
        if event["event"] == "AGENT_NODE_COMPLETED"
    ]
    assert first_nodes == ["coordinator", "qa", "quality_gate"]
    assert second_nodes == [
        "coordinator",
        "qa",
        "quality_gate",
        "coordinator",
        "qa",
        "quality_gate",
    ]


@pytest.mark.asyncio
async def test_graph_replaces_resolved_risk_signals(mock_llm):
    config = {"configurable": {"thread_id": "risk-signals-are-a-snapshot"}}
    at_risk = await agent.ainvoke(
        {
            "query": "Kiểm tra tiến độ",
            "assignments": [
                {
                    "id": "assignment-1",
                    "title": "Bài sắp đến hạn",
                    "deadline": "2026-10-01T10:00:00Z",
                    "estimated_hours": 5,
                }
            ],
            "request": {
                "workflow_hint": "tracking",
                "current_time": "2026-10-01T09:00:00Z",
            },
        },
        config=config,
    )
    resolved = await agent.ainvoke(
        {
            "query": "Kiểm tra lại tiến độ",
            "assignments": [],
            "request": {"workflow_hint": "tracking"},
        },
        config=config,
    )

    assert at_risk["risk_signals"]
    assert resolved["risk_signals"] == []


@pytest.mark.asyncio
async def test_graph_replaces_resolved_validation_errors(mock_llm):
    config = {"configurable": {"thread_id": "validation-errors-are-a-snapshot"}}
    assignments = [
        {
            "id": "course:task-1",
            "title": "Database report",
            "description": "Write the schema, queries, test evidence, and review before submission.",
            "deadline": "2026-10-20T20:00:00+07:00",
            "submission_types": ["online_upload"],
            "estimated_hours": 2,
        }
    ]
    invalid = await agent.ainvoke(
        {
            "query": "Lập kế hoạch tuần",
            "assignments": assignments,
            "availability": [{"hours": 1}],
            "request": {"workflow_hint": "plan"},
        },
        config=config,
    )
    valid = await agent.ainvoke(
        {
            "query": "Lập kế hoạch tuần mới",
            "assignments": assignments,
            "availability": [{"hours": 10}],
            "request": {"workflow_hint": "plan"},
        },
        config=config,
    )

    assert invalid["validation_errors"]
    assert valid["validation_errors"] == []
