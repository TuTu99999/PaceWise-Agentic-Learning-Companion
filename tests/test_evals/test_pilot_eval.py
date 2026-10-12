import pytest

from evals.run_pilot_eval import (
    cohen_kappa,
    evaluate_samples,
    quadratic_weighted_kappa,
)


def test_human_and_ai_agreement_metrics_are_reported():
    samples = []
    for index in range(50):
        label = "allow" if index % 2 == 0 else "guided_help"
        samples.append(
            {
                "id": f"safety-{index}",
                "task_type": "safety",
                "rater_1": label,
                "rater_2": label,
                "reference_label": label,
                "ai_label": label,
            }
        )
    for index in range(50):
        label = "đang hình thành" if index % 2 == 0 else "đã thể hiện được"
        samples.append(
            {
                "id": f"understanding-{index}",
                "task_type": "understanding",
                "rater_1": label,
                "rater_2": label,
                "reference_label": label,
                "ai_label": label,
            }
        )

    report = evaluate_samples(samples)

    assert report["sample_count"] == 100
    assert report["metrics"]["safety_false_positive_rate"] == 0
    assert report["metrics"]["understanding_ai_vs_reference_weighted_kappa"] == 1
    assert report["overall_pass"] is True


def test_kappa_rejects_empty_or_mismatched_inputs():
    assert cohen_kappa([], [], ("a", "b")) == 0
    assert quadratic_weighted_kappa(["a"], [], ("a", "b")) == 0


def test_weighted_kappa_rewards_nearby_ordinal_agreement():
    labels = ("low", "medium", "high")
    near = quadratic_weighted_kappa(["low", "medium", "high"], ["medium", "medium", "high"], labels)
    far = quadratic_weighted_kappa(["low", "medium", "high"], ["high", "medium", "low"], labels)
    assert near > far
    assert near == pytest.approx(2 / 3)
