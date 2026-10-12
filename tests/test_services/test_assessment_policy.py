import pytest

from src.services.assessment_policy import (
    DIMENSION,
    STAGES,
    next_step,
    question_fingerprint,
    select_item,
    validate_criterion_scores,
)
from src.services.learning_evidence import _highest_level
from src.services.misconception_diagnosis import diagnose


@pytest.mark.parametrize("stage,index", [(stage, index) for index, stage in enumerate(STAGES)])
def test_progresses_only_after_current_dimension_passes(stage, index):
    outcome = {"assessment_result": {"status": "demonstrated", "dimensions": {DIMENSION[stage]: "passed"}}}
    result = next_step(stage, outcome, hint_level=0, attempts=1)
    assert result["stage"] == STAGES[min(index + 1, len(STAGES) - 1)]
    assert result["status"] == ("completed" if stage == "transfer" else "active")


@pytest.mark.parametrize("stage", STAGES)
def test_hinted_pass_requires_unseen_verification(stage):
    outcome = {"assessment_result": {"status": "demonstrated", "dimensions": {DIMENSION[stage]: "passed"}}}
    assert next_step(stage, outcome, hint_level=1, attempts=1)["status"] == "verification_required"


def test_retry_remediation_review_and_inconsistent_status_do_not_progress():
    outcome = {"assessment_result": {"status": "misconception", "dimensions": {"application": "passed"}}}
    assert next_step("application", outcome, hint_level=0, attempts=1)["status"] == "needs_support"
    assert next_step("application", outcome, hint_level=0, attempts=2)["status"] == "stopped"
    outcome["status"] = "awaiting_teacher"
    assert next_step("application", outcome, hint_level=0, attempts=1)["status"] == "review_required"


def test_selection_never_reuses_item_crosses_kc_or_uses_closed_transfer():
    bank = [
        {
            "assessment_id": "Q-1",
            "knowledge_component_ids": ["other"],
            "assessment_stage": "transfer",
            "answer_type": "open",
        },
        {
            "assessment_id": "Q-2",
            "knowledge_component_ids": ["kc"],
            "assessment_stage": "transfer",
            "answer_type": "multiple_choice",
        },
        {
            "assessment_id": "Q-3",
            "knowledge_component_ids": ["kc"],
            "assessment_stage": "transfer",
            "answer_type": "open",
        },
    ]
    assert select_item(bank, "kc", "transfer", []) == bank[2]
    assert select_item(bank, "kc", "transfer", ["Q-3"]) is None


@pytest.mark.parametrize("score", [-1, 5, 3.5, True, "4"])
def test_rubric_rejects_invalid_scores(score):
    criteria = [{"criterion_id": "c1"}]
    assert (
        validate_criterion_scores(
            [{"criterion_id": "c1", "score": score, "evidence_quote": "because"}], criteria, "because"
        )
        == []
    )


def test_rubric_requires_each_criterion_grounded_and_does_not_average():
    criteria = [{"criterion_id": "c1"}, {"criterion_id": "c2"}]
    raw = [
        {"criterion_id": "c1", "score": 4, "evidence_quote": "because"},
        {"criterion_id": "c2", "score": 1, "evidence_quote": "however"},
    ]
    assert len(validate_criterion_scores(raw, criteria, "because however")) == 2
    assert validate_criterion_scores(raw, criteria, "because") == []
    assert validate_criterion_scores(raw[:1], criteria, "because however") == []
    assert validate_criterion_scores([*raw, raw[0]], criteria, "because however") == []


def test_different_item_id_with_identical_question_is_not_unseen():
    item = {
        "assessment_id": "Q-2",
        "question": "SAME question",
        "knowledge_component_ids": ["kc"],
        "assessment_stage": "transfer",
        "answer_type": "open",
    }
    previous = {**item, "assessment_id": "Q-1", "question": "same   question"}
    assert select_item([item], "kc", "transfer", ["Q-1"], [question_fingerprint(previous)]) is None


@pytest.mark.parametrize(
    "dimensions,kind,hint,expected",
    [
        ({}, "open", 0, "no_evidence"),
        ({"transfer": "passed"}, "open", 0, "no_evidence"),
        ({"recall": "passed", "transfer": "passed"}, "multiple_choice", 0, "recognition"),
        ({"conceptual": "passed", "application": "passed"}, "open", 0, "conceptual"),
        ({"conceptual": "passed", "reasoning": "passed", "application": "passed"}, "open", 0, "application"),
        (
            {"conceptual": "passed", "reasoning": "passed", "application": "passed", "transfer": "passed"},
            "open",
            1,
            "application",
        ),
        (
            {
                "conceptual": "passed",
                "reasoning": "passed",
                "application": "passed",
                "transfer": "passed",
                "retention": "passed",
            },
            "open",
            0,
            "transfer",
        ),
    ],
)
def test_level_requires_evidence_not_question_metadata(dimensions, kind, hint, expected):
    assessment = {"status": "demonstrated", "dimensions": dimensions}
    assert _highest_level(assessment, {"answer_type": kind, "cognitive_level": "retained"}, hint_level=hint) == expected


def test_retention_requires_validated_baseline_and_no_hint():
    assessment = {
        "status": "demonstrated",
        "dimensions": dict.fromkeys(("conceptual", "reasoning", "application", "transfer", "retention"), "passed"),
    }
    trusted = {"answer_type": "open", "retention_context": {"validated": True, "baseline_evidence_id": "ev1"}}
    assert _highest_level(assessment, trusted, hint_level=0) == "retained"
    assert _highest_level(assessment, trusted, hint_level=1) != "retained"


def test_unknown_taxonomy_and_ungrounded_hypothesis_abstain():
    hypothesis = [{"label": "symmetry confusion", "evidence_quote": "made up"}]
    assert (
        diagnose(hypothesis, ["symmetry confusion"], answer="actual", kc_id="kc", evidence_ids=[])["status"]
        == "unknown"
    )
    hypothesis[0]["evidence_quote"] = "actual"
    assert diagnose(hypothesis, [], answer="actual", kc_id="kc", evidence_ids=[])["status"] == "unknown"
    result = diagnose(hypothesis, ["symmetry confusion"], answer="actual", kc_id="kc", evidence_ids=["ev1"])
    assert result["candidates"][0]["status"] == "suspected"
    assert result["requires_teacher_review"] is True
