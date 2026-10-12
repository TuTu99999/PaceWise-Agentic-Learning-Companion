from scripts.evaluate_plan_personas import build_report


def test_scheduler_persona_matrix_and_seeded_calendar_fuzz():
    report = build_report(variants=64)

    assert report["passed"], report
    assert len(report["personas"]) >= 9
    assert all(item["passed"] for item in report["personas"])
    assert report["fuzz"]["variants"] == 64
    assert report["fuzz"]["failed"] == 0
    # Exercise both scheduler outcomes: safe placement and explicit refusal.
    assert report["fuzz"]["feasible"] > 0
    assert report["fuzz"]["infeasible"] > 0
