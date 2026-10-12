from src.agents.adaptive_evaluation import run_adaptive_evaluation


def test_unique_adaptive_boundary_cases_pass_with_honest_scope():
    report = run_adaptive_evaluation()
    assert report["overall_pass"] is True
    assert report["sample_count"] == report["unique_sample_count"] == 60
    assert report["validation_status"] == "offline_engineering_validation_only"
    assert all(value == 1 for value in report["metrics"].values())
