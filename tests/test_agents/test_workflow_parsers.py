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
    text = '{"milestones":[{"milestone_id":"M1","task_id":"1:a","title":"Draft","estimated_minutes":45,"assignment_part_ids":["S1-P1"]}]}'
    result = _extract_milestones_from_text(text)
    assert result[0]["task_id"] == "1:a"
    assert result[0]["estimated_minutes"] == 45
    assert result[0]["assignment_part_ids"] == ["S1-P1"]


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


def test_model_milestones_must_cover_every_extracted_assignment_part():
    result = _validate_model_milestone_scope(
        [{
            "milestone_id": "M1",
            "task_id": "1:a",
            "source_refs": ["assignment:1:a"],
            "assignment_part_ids": ["S1-P1"],
        }],
        {"1:a"},
        allowed_source_refs_by_task={"1:a": {"assignment:1:a"}},
        expected_part_ids_by_task={"1:a": {"S1-P1", "S1-P2"}},
    )

    assert result["valid"] is False
    assert result["coveredAssignmentPartIds"] == {"1:a": ["S1-P1"]}
    assert result["errors"][-1] == {
        "code": "missing_assignment_part_coverage",
        "taskId": "1:a",
        "partIds": ["S1-P2"],
    }


def test_model_cannot_collapse_a_multi_part_assignment_back_into_one_do_block():
    result = _validate_model_milestone_scope(
        [{
            "milestone_id": "M1",
            "task_id": "1:a",
            "source_refs": ["assignment:1:a"],
            "assignment_part_ids": ["S1-P1", "S1-P2", "S1-P3", "S1-P4"],
        }],
        {"1:a"},
        allowed_source_refs_by_task={"1:a": {"assignment:1:a"}},
        expected_part_ids_by_task={"1:a": {"S1-P1", "S1-P2", "S1-P3", "S1-P4"}},
        minimum_milestones_by_task={"1:a": 2},
    )

    assert result["valid"] is False
    assert result["milestoneCounts"] == {"1:a": 1}
    assert result["errors"][-1] == {
        "code": "collapsed_assignment_parts",
        "taskId": "1:a",
        "minimumMilestones": 2,
        "actualMilestones": 1,
    }


def test_plan_ai_decomposes_all_assignment_questions_and_keeps_confirmed_time_budget(monkeypatch):
    class QuestionModel:
        def invoke(self, _messages):
            return type("Response", (), {"content": json.dumps({"milestones": [
                {
                    "milestone_id": f"M{index}",
                    "task_id": "DB201:exercise-2",
                    "title": f"Làm câu {index}",
                    "deliverable": f"Lời giải câu {index}",
                    "estimated_minutes": 60,
                    "depends_on": [] if index == 1 else [f"M{index - 1}"],
                    "assignment_part_ids": [f"S2-P{index}"],
                    "source_refs": [f"file:9#exercise=2&part=S2-P{index}"],
                }
                for index in range(1, 4)
            ]})})()

    monkeypatch.setattr("src.agents.workflows.plan.get_agent_llm", lambda **_kwargs: QuestionModel())
    assignment = {
        "id": "DB201:exercise-2",
        "course_code": "DB201",
        "title": "Bài tập SQL nhiều câu",
        "description": "Hoàn thành ba câu truy vấn trong đề bài đã phát hành.",
        "estimated_hours": 2,
        "assignment_parts": [
            {
                "partId": f"S2-P{index}",
                "label": f"Câu {index}",
                "content": f"Yêu cầu SQL của câu {index}",
                "sourceRef": f"file:9#exercise=2&part=S2-P{index}",
            }
            for index in range(1, 4)
        ],
    }
    result = plan_node({
        "query": "Lập kế hoạch bài SQL",
        "assignments": [assignment],
        "goals": [{"task_id": assignment["id"], "remaining_minutes": 120}],
        "availability": [{"hours": 10}],
    })

    milestones = result["proposed_milestones"]
    assert result["output"]["model_output_validation"]["valid"] is True
    assert sum(item["estimated_minutes"] for item in milestones) == 120
    assert {part for item in milestones for part in item["assignment_part_ids"]} == {
        "S2-P1", "S2-P2", "S2-P3",
    }


def test_plan_ai_can_split_broad_project_requirements_into_smaller_grounded_tasks(monkeypatch):
    class ProjectModel:
        def invoke(self, _messages):
            return type("Response", (), {"content": json.dumps({"milestones": [
                {
                    "milestone_id": "M1",
                    "task_id": "WEB201:project",
                    "title": "Thiết kế lược đồ dữ liệu",
                    "deliverable": "ERD và danh sách bảng",
                    "estimated_minutes": 60,
                    "depends_on": [],
                    "assignment_part_ids": ["REQ-1"],
                    "source_refs": ["file:84#part=REQ-1"],
                },
                {
                    "milestone_id": "M2",
                    "task_id": "WEB201:project",
                    "title": "Tạo migration và dữ liệu mẫu",
                    "deliverable": "Migration chạy được",
                    "estimated_minutes": 45,
                    "depends_on": ["M1"],
                    "assignment_part_ids": ["REQ-1"],
                    "source_refs": ["file:84#part=REQ-1"],
                },
                {
                    "milestone_id": "M3",
                    "task_id": "WEB201:project",
                    "title": "Xây dựng API sản phẩm",
                    "deliverable": "API CRUD có kiểm tra đầu vào",
                    "estimated_minutes": 75,
                    "depends_on": ["M2"],
                    "assignment_part_ids": ["REQ-2"],
                    "source_refs": ["file:84#part=REQ-2"],
                },
                {
                    "milestone_id": "M4",
                    "task_id": "WEB201:project",
                    "title": "Xây dựng giao diện sản phẩm",
                    "deliverable": "Màn hình danh sách và biểu mẫu",
                    "estimated_minutes": 60,
                    "depends_on": [],
                    "assignment_part_ids": ["REQ-3"],
                    "source_refs": ["file:84#part=REQ-3"],
                },
                {
                    "milestone_id": "M5",
                    "task_id": "WEB201:project",
                    "title": "Tích hợp giao diện với API",
                    "deliverable": "Luồng sản phẩm hoạt động đầu cuối",
                    "estimated_minutes": 60,
                    "depends_on": ["M3", "M4"],
                    "assignment_part_ids": ["REQ-3"],
                    "source_refs": ["file:84#part=REQ-3"],
                },
            ]})})()

    monkeypatch.setattr("src.agents.workflows.plan.get_agent_llm", lambda **_kwargs: ProjectModel())
    assignment = {
        "id": "WEB201:project",
        "course_code": "WEB201",
        "title": "Project Web bán hàng",
        "task_type": "project",
        "assignment_parts": [
            {
                "partId": f"REQ-{index}",
                "label": f"Yêu cầu {index}",
                "content": content,
                "sourceRef": f"file:84#part=REQ-{index}",
            }
            for index, content in enumerate(
                [
                    "Thiết kế cơ sở dữ liệu và tạo migration.",
                    "Xây dựng API quản lý sản phẩm.",
                    "Xây dựng giao diện và tích hợp API.",
                ],
                start=1,
            )
        ],
    }
    result = plan_node({
        "query": "Lập kế hoạch project Web",
        "assignments": [assignment],
        "goals": [{"task_id": assignment["id"], "remaining_minutes": 300}],
        "availability": [{"hours": 10}],
    })

    milestones = result["proposed_milestones"]
    assert result["output"]["model_output_validation"]["valid"] is True
    assert len(milestones) == 5
    assert sum(item["estimated_minutes"] for item in milestones) == 300
    assert [item["assignment_part_ids"] for item in milestones].count(["REQ-1"]) == 2
    assert [item["assignment_part_ids"] for item in milestones].count(["REQ-3"]) == 2
    assert {part for item in milestones for part in item["assignment_part_ids"]} == {
        "REQ-1", "REQ-2", "REQ-3",
    }
    assert milestones[-1]["depends_on"] == ["M3", "M4"]


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


def test_plan_hybrid_assignment_uses_deterministic_fast_path(monkeypatch):
    monkeypatch.setattr(
        "src.agents.workflows.plan.get_agent_llm",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("hybrid route must not call a model")),
    )
    result = plan_node(
        {
            "query": "Lập kế hoạch",
            "assignments": [
                {
                    "id": "course:structured",
                    "title": "Database report",
                    "description": "Write the schema, queries, test evidence, and a concise review before submission.",
                    "deadline": "2026-10-20T20:00:00+07:00",
                    "submission_types": ["online_upload"],
                    "estimated_hours": 2,
                }
            ],
            "goals": [{"task_id": "course:structured", "remaining_minutes": 120}],
            "availability": [{"hours": 10}],
        }
    )

    assert result["output"]["decomposition_routes"]["course:structured"]["route"] == "hybrid"
    assert result["output"]["model_output_validation"]["source"] == "deterministic_hybrid"
    assert {item["task_id"] for item in result["proposed_milestones"]} == {"course:structured"}


def test_plan_mixed_route_sends_only_unstructured_assignment_to_model(monkeypatch):
    captured = {}

    class ScopedModel:
        def invoke(self, messages):
            captured["prompt"] = messages[-1].content
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"milestones":[{"milestone_id":"u1","task_id":"course:unstructured",'
                        '"title":"Clarify task","deliverable":"Checked outline","estimated_minutes":60,'
                        '"depends_on":[],"source_refs":["assignment:course:unstructured"]}]}'
                    )
                },
            )()

    def factory(**kwargs):
        captured["kwargs"] = kwargs
        return ScopedModel()

    monkeypatch.setattr("src.agents.workflows.plan.get_agent_llm", factory)
    result = plan_node(
        {
            "query": "Lập kế hoạch",
            "assignments": [
                {
                    "id": "course:structured",
                    "title": "Database report",
                    "description": "Write the schema, queries, test evidence, and a concise review before submission.",
                    "deadline": "2026-10-20T20:00:00+07:00",
                    "submission_types": ["online_upload"],
                    "estimated_hours": 2,
                },
                {"id": "course:unstructured", "title": "Open task", "description": "Explore"},
            ],
            "goals": [
                {"task_id": "course:structured", "remaining_minutes": 120},
                {"task_id": "course:unstructured", "remaining_minutes": 60},
            ],
            "availability": [{"hours": 10}],
        }
    )

    assert "course:unstructured" in captured["prompt"]
    assert "course:structured" not in captured["prompt"]
    assert captured["kwargs"]["cache_scope"] == "plan-decomposition-v3"
    assert result["output"]["model_output_validation"]["valid"] is True
    assert {item["task_id"] for item in result["proposed_milestones"]} == {
        "course:structured",
        "course:unstructured",
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
