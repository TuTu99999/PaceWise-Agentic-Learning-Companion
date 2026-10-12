from src.agents.validators import (
    extract_citations,
    validate_assessment_result,
    validate_citations,
    validate_plan_constraints,
    validate_recovery_options,
)


def test_valid_plan_constraints():
    result = validate_plan_constraints(
        [
            {"milestone_id": "M1", "estimated_minutes": 60, "depends_on": []},
            {"milestone_id": "M2", "estimated_minutes": 60, "depends_on": ["M1"]},
        ],
        [{"hours": 3}],
    )
    assert result["valid"] is True


def test_over_capacity_plan_is_rejected():
    result = validate_plan_constraints(
        [{"milestone_id": "M1", "estimated_minutes": 180, "depends_on": []}],
        [{"hours": 2}],
    )
    assert result["valid"] is False
    assert result["errors"][0]["code"] == "CAPACITY_EXCEEDED"


def test_unknown_dependency_is_rejected():
    result = validate_plan_constraints(
        [{"milestone_id": "M1", "estimated_minutes": 30, "depends_on": ["M9"]}]
    )
    assert any(error["code"] == "UNKNOWN_DEPENDENCY" for error in result["errors"])


def test_dependency_cycle_is_rejected():
    result = validate_plan_constraints(
        [
            {"milestone_id": "M1", "estimated_minutes": 30, "depends_on": ["M2"]},
            {"milestone_id": "M2", "estimated_minutes": 30, "depends_on": ["M1"]},
        ]
    )
    assert any(error["code"] == "CYCLIC_DEPENDENCY" for error in result["errors"])


def test_citation_must_exist_in_retrieved_passages():
    citation = "[Giáo trình, Trang 1, Đoạn 2]"
    result = validate_citations(f"Nội dung {citation}", [{"citation": citation}])
    assert result["valid"] is True
    assert extract_citations(f"Nội dung {citation}") == [citation]


def test_hallucinated_citation_is_rejected():
    result = validate_citations(
        "Nội dung [Nguồn giả, Trang 9, Đoạn 1]",
        [{"citation": "[Nguồn thật, Trang 1, Đoạn 1]"}],
    )
    assert result["valid"] is False
    assert result["invalid_citations"]


def test_low_confidence_assessment_requires_review():
    result = validate_assessment_result(
        {"status": "đang hình thành", "confidence": "Thấp", "evidence_quotes": ["bằng chứng"]},
        [{"criterion_id": "c1"}],
    )
    assert result["requires_instructor_review"] is True


def test_valid_assessment_does_not_require_review():
    result = validate_assessment_result(
        {
            "status": "đã thể hiện được",
            "confidence": "Cao",
            "evidence_quotes": ["bằng chứng"],
            "evaluator_version": "open-rubric-v2",
            "dimensions": {"conceptual": "passed", "transfer": "not_tested"},
        },
        [{"criterion_id": "c1"}],
    )
    assert result["valid"] is True


def test_assessment_without_evaluator_provenance_requires_review():
    result = validate_assessment_result(
        {"status": "đã thể hiện được", "confidence": "Cao", "evidence_quotes": ["bằng chứng"]},
        [{"criterion_id": "c1"}],
    )
    assert result["requires_instructor_review"] is True
    assert "missing_evaluator_version" in result["reasons"]


def test_recovery_validation_requires_two_options_and_protects_deadline():
    assignment = {"title": "Bài giữa kỳ", "deadline": "2026-10-01T10:00:00Z"}
    invalid = validate_recovery_options([], [assignment])
    assert invalid["valid"] is False
    assert invalid["errors"][0]["code"] == "INSUFFICIENT_OPTIONS"

    options = [
        {
            "option_name": name,
            "kept_items": ["Ôn tập"],
            "moved_items": [],
            "hours_short_or_free": -1.0,
            "protected_deadlines": [assignment["title"]],
            "remaining_risks": "Còn ít thời gian đệm",
        }
        for name in ("Phương án A", "Phương án B")
    ]
    assert validate_recovery_options(options, [assignment])["valid"] is True
