from src.agents.evaluation import (
    adversarial_safety_dataset,
    assessment_truth_dataset,
    grounding_safety_dataset,
    plan_intelligence_dataset,
    planning_dataset,
    run_assessment_truth_evaluation,
    run_full_evaluation,
    run_plan_intelligence_evaluation,
    understanding_journey_dataset,
)


def test_each_versioned_dataset_has_at_least_120_samples():
    assert len(planning_dataset()) >= 120
    assert len(grounding_safety_dataset()) >= 120
    assert len(understanding_journey_dataset()) >= 120
    assert len(adversarial_safety_dataset()) >= 100
    assert len(plan_intelligence_dataset()) >= 100
    assert len(assessment_truth_dataset()) >= 120


def test_plan_intelligence_release_metrics_pass():
    report = run_plan_intelligence_evaluation()
    assert report["sample_count"] >= 100
    assert report["overall_pass"] is True
    assert all(report["passed"].values())


def test_deterministic_release_metrics_pass():
    report = run_full_evaluation()
    assert report["overall_pass"] is True
    assert all(report["passed"].values())


def test_assessment_truth_metrics_block_false_mastery_updates():
    report = run_assessment_truth_evaluation()
    assert report["overall_pass"] is True
    assert report["metrics"]["false_mastery_acceptance_rate"] == 0
    assert report["metrics"]["knowledge_update_gate_accuracy"] == 1
