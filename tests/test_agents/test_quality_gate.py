from src.agents.workflows.quality_gate import quality_gate_node, repair_node


def test_quality_gate_rejects_invalid_grounded_answer():
    result = quality_gate_node(
        {
            "workflow": "qa",
            "response": "Câu trả lời không có nguồn.",
            "source_refs": [{"citation": "[Nguồn, Trang 1]"}],
            "output": {"citation_validation": {"valid": False}},
        }
    )
    assert result["quality_review"]["passed"] is False
    assert "invalid_citation_contract" in result["quality_review"]["reasons"]

    repaired = repair_node(
        {
            "workflow": "qa",
            "quality_review": result["quality_review"],
            "output": result["output"],
        }
    )
    reviewed = quality_gate_node({"workflow": "qa", **repaired})
    assert repaired["source_refs"] == []
    assert "chưa thể xác minh" in repaired["response"]
    assert reviewed["quality_review"]["passed"] is True
    assert reviewed["quality_review"]["repaired"] is True


def test_quality_gate_accepts_valid_plan():
    result = quality_gate_node(
        {
            "workflow": "plan",
            "response": "Bản kế hoạch nháp.",
            "output": {"plan_validation": {"valid": True}},
        }
    )
    assert result["quality_review"]["passed"] is True


def test_quality_gate_accepts_a_completed_plan_confirmation():
    result = quality_gate_node(
        {
            "workflow": "plan",
            "response": "Kế hoạch đã được xác nhận.",
            "status": "completed",
            "student_decision": {"workflow": "plan", "action": "confirmed"},
            "output": {"confirmed_plan": {"milestones": []}},
        }
    )

    assert result["quality_review"]["passed"] is True
    assert "invalid_plan" not in result["quality_review"]["reasons"]


def test_quality_gate_does_not_return_an_invalid_plan():
    review = quality_gate_node(
        {
            "workflow": "plan",
            "response": "Một kế hoạch không khả thi.",
            "proposed_milestones": [{"milestone_id": "M-1"}],
            "output": {"plan_validation": {"valid": False}},
        }
    )
    result = repair_node(
        {
            "workflow": "plan",
            "quality_review": review["quality_review"],
            "output": review["output"],
        }
    )
    assert result["status"] == "failed"
    assert result["proposed_milestones"] == []
