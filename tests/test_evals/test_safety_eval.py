from pathlib import Path

from evals.run_safety_eval import load_cases
from src.agents.guardrails import evaluate_guardrails
from src.agents.safety import _needs_semantic_review


def test_adversarial_dataset_is_independent_and_large_enough():
    cases = load_cases(Path("evals/datasets/safety_adversarial_v1.jsonl"))
    assert len(cases) == 100
    assert {case["expected"] for case in cases} == {"allow", "guided_help", "block"}


def test_every_unsafe_case_reaches_a_safety_layer():
    cases = load_cases(Path("evals/datasets/safety_adversarial_v1.jsonl"))
    uncovered = [
        case["id"]
        for case in cases
        if case["expected"] != "allow"
        and evaluate_guardrails(case["query"])["action"] == "allow"
        and not _needs_semantic_review(case["query"])
    ]
    assert uncovered == []
