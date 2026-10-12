import json

import pytest

from src.agents.workflows.plan import (
    _apply_deterministic_adjustment,
    _extract_milestones_from_text,
    _parse_depends_on,
    _parse_int_minutes,
    _validate_model_milestone_scope,
    plan_node,
)
from src.agents.workflows.recover import (
    _clean_json_from_response,
    _extract_recovery_options,
    _format_options_as_text,
    _normalize_string_list,
    _parse_hours_float,
    recover_node,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(30, 30), ("45 phút", 45), ("1.5 giờ", 90), ("khoảng 25", 25), (None, 60)],
)
def test_parse_milestone_minutes(value, expected):
    assert _parse_int_minutes(value) == expected


def test_parse_dependencies():
    assert _parse_depends_on(["M1", "none", "M2"]) == ["M1", "M2"]
    assert _parse_depends_on("M1; M2") == ["M1", "M2"]
    assert _parse_depends_on("không") == []


def test_extract_milestones_from_json():
    text = """Kế hoạch
```json
{"milestones":[{"id":"M1","name":"Đọc bài","output":"Ghi chú","duration":"1 giờ","dependencies":[]}]}
```"""
    result = _extract_milestones_from_text(text)
    assert result == [
        {
            "milestone_id": "M1",
            "title": "Đọc bài",
            "deliverable": "Ghi chú",
            "estimated_minutes": 60,
            "depends_on": [],
        }
    ]


def test_extract_milestones_from_generic_code_block():
    text = '```\n[{"milestone_id":"M1","title":"Quiz","estimated_minutes":30}]\n```'
    assert _extract_milestones_from_text(text)[0]["title"] == "Quiz"


def test_extract_milestones_from_bare_json_object():
    text = '{"milestones":[{"milestone_id":"M1","task_id":"1:a","title":"Draft","estimated_minutes":45}]}'
    result = _extract_milestones_from_text(text)
    assert result[0]["task_id"] == "1:a"
    assert result[0]["estimated_minutes"] == 45


def test_extract_milestones_from_markdown_table():
    text = "| M1 | Đọc bài | mô tả | Ghi chú | 45 phút | Không |"
    result = _extract_milestones_from_text(text)
    assert result[0]["estimated_minutes"] == 45


def test_model_milestones_require_exact_task_id_and_full_task_coverage():
    result = _validate_model_milestone_scope(
        [
            {"milestone_id": "M1", "task_id": "course:task-1"},
            {"milestone_id": "M2"},
        ],
        {"course:task-1", "course:task-2"},
    )

    assert result["valid"] is False
    assert result["fallbackApplied"] is True
    assert {error["code"] for error in result["errors"]} == {
        "missing_task_id",
        "missing_task_coverage",
    }


def test_model_milestones_do_not_accept_task_id_aliases():
    parsed = _extract_milestones_from_text(
        '```json\n{"milestones":[{"milestone_id":"M1","taskId":"course:task-1"}]}\n```'
    )
    result = _validate_model_milestone_scope(parsed, {"course:task-1"})

    assert result["valid"] is False
    assert {error["code"] for error in result["errors"]} == {
        "missing_task_id",
        "missing_task_coverage",
    }


def test_model_milestones_reject_missing_or_invented_sources_when_catalog_is_known():
    result = _validate_model_milestone_scope(
        [
            {"milestone_id": "M1", "task_id": "1:a", "source_refs": ["assignment:1:a", "file:forged"]},
            {"milestone_id": "M2", "task_id": "1:a"},
        ],
        {"1:a"},
        allowed_source_refs_by_task={"1:a": {"assignment:1:a", "rubric:r1"}},
    )
    assert result["valid"] is False
    assert {error["code"] for error in result["errors"]} == {"invalid_source_ref", "missing_source_refs"}


def test_plan_rejects_unscoped_model_milestones_and_falls_back_immediately(monkeypatch):
    class MissingTaskIdModel:
        def invoke(self, _messages):
            return type("Response", (), {
                "content": '```json\n{"milestones":[{"milestone_id":"M1","title":"Draft","estimated_minutes":60}]}\n```'
            })()

    monkeypatch.setattr("src.agents.workflows.plan.get_agent_llm", lambda **_kwargs: MissingTaskIdModel())
    assignments = [
        {"id": "course:task-1", "title": "Project one", "description": "short"},
        {"id": "course:task-2", "title": "Project two", "description": "short"},
    ]
    result = plan_node({
        "query": "Lập kế hoạch",
        "assignments": assignments,
        "goals": [
            {"task_id": "course:task-1", "remaining_minutes": 60},
            {"task_id": "course:task-2", "remaining_minutes": 90},
        ],
        "availability": [{"hours": 10}],
    })

    boundary = result["output"]["model_output_validation"]
    assert boundary["valid"] is False
    assert boundary["source"] == "rule_based_fallback"
    assert result["analysis"] == "MODEL_MILESTONE_SCOPE_INVALID_RULE_FALLBACK"
    assert "```json" not in result["response"]
    assert {item["task_id"] for item in result["proposed_milestones"]} == {
        "course:task-1",
        "course:task-2",
    }


def test_adjust_milestone_duration_and_reschedule():
    result = _apply_deterministic_adjustment(
        [{"milestone_id": "M3", "estimated_minutes": 90}],
        "Dời milestone 3 sang ngày mai và giảm còn 45 phút",
    )
    assert result[0]["estimated_minutes"] == 45
    assert result[0]["status"] == "rescheduled"


def test_adjustment_without_target_keeps_plan():
    original = [{"milestone_id": "M1", "estimated_minutes": 30}]
    assert _apply_deterministic_adjustment(original, "Giữ nguyên") == original


def test_plan_cancel_pending_action():
    result = plan_node(
        {
            "query": "Hủy kế hoạch",
            "pending_action": {"workflow": "plan", "payload": {"milestones": []}},
        }
    )
    assert result["student_decision"]["action"] == "cancelled"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(2, 2.0), ("thiếu -3.5 giờ", -3.5), ("none", 0.0)],
)
def test_parse_recovery_hours(value, expected):
    assert _parse_hours_float(value) == expected


def test_normalize_recovery_lists():
    assert _normalize_string_list("- M1, M2; M3") == ["M1", "M2", "M3"]
    assert _normalize_string_list(["M1", "", "M2"]) == ["M1", "M2"]


def _recovery_payload():
    return {
        "recovery_options": [
            {
                "option_name": "A",
                "kept_items": ["M1"],
                "moved_items": ["M2"],
                "hours_short_or_free": "-2 giờ",
                "protected_deadlines": ["Quiz"],
                "remaining_risks": ["Còn thiếu thời gian"],
            }
        ]
    }


def test_extract_recovery_from_internal_tag():
    text = f"Tư vấn <DATA_RECOVERY>{json.dumps(_recovery_payload())}</DATA_RECOVERY>"
    result = _extract_recovery_options(text)
    assert result[0]["hours_short_or_free"] == -2.0
    assert result[0]["remaining_risks"] == "Còn thiếu thời gian"


def test_extract_recovery_from_json_code_block():
    text = f"```json\n{json.dumps(_recovery_payload())}\n```"
    assert _extract_recovery_options(text)[0]["protected_deadlines"] == ["Quiz"]


def test_format_and_clean_recovery_response():
    options = _extract_recovery_options(f"<DATA_RECOVERY>{json.dumps(_recovery_payload())}</DATA_RECOVERY>")
    formatted = _format_options_as_text(options)
    assert "**A**" in formatted
    cleaned = _clean_json_from_response(
        f"Mô tả <DATA_RECOVERY>{json.dumps(_recovery_payload())}</DATA_RECOVERY>", options
    )
    assert "DATA_RECOVERY" not in cleaned


@pytest.mark.parametrize(("query", "decision"), [("Tôi xác nhận", "confirmed"), ("Hủy", "cancelled")])
def test_recover_pending_decision(query, decision):
    result = recover_node(
        {
            "query": query,
            "pending_action": {"workflow": "recover", "payload": {"options": []}},
        }
    )
    assert result["student_decision"]["action"] == decision
