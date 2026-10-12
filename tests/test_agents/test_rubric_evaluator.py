import pytest

from src.agents.tools.rubric_evaluator import evaluate_closed_question, parse_approved_rubric


@pytest.mark.parametrize(
    ("student", "correct", "expected"),
    [
        ("A", "A. Đáp án", True),
        ("đúng", "True", True),
        ("B", "A", False),
        ("Nội dung", "nội dung", True),
    ],
)
def test_evaluate_closed_question(student, correct, expected):
    assert evaluate_closed_question(student, correct)["is_correct"] is expected


@pytest.mark.parametrize(
    ("student", "correct", "question_type", "expected"),
    [
        ("Apple", "Ant", "exact_text", False),
        ("10", "11", "numeric", False),
        ("A", "A. Quan hệ tương đương", "multiple_choice", True),
        ("A", "Apple", "exact_text", False),
        ("1/2", "0.5", "numeric", True),
        (" ĐÚNG ", "true", "boolean", True),
        ("quan hệ  tương đương", "Quan hệ tương đương", "exact_text", True),
    ],
)
def test_closed_evaluator_is_item_type_aware(student, correct, question_type, expected):
    result = evaluate_closed_question(student, correct, question_type=question_type)
    assert result["is_correct"] is expected
    assert result["evaluator_version"] == "closed-v2"


def test_parse_canvas_rubric():
    result = parse_approved_rubric(
        {
            "criteria": [
                {
                    "id": "c1",
                    "description": "Đúng khái niệm",
                    "points": 4,
                    "ratings": [{"id": "r1", "description": "Đạt", "points": 4}],
                }
            ]
        }
    )
    assert result[0]["criterion_id"] == "c1"
    assert result[0]["levels"][0]["points"] == 4.0


def test_parse_mapping_rubric():
    result = parse_approved_rubric({"Lập luận": ["Tốt", "Cần cải thiện"]})
    assert result[0]["name"] == "Lập luận"
    assert len(result[0]["levels"]) == 2
