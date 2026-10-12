from scripts.benchmark_replan_architecture import build_report


def test_evidence_aware_replan_outperforms_a_context_free_rerun_without_overreacting():
    report = build_report()

    assert report["passed"], report
    by_name = {case["name"]: case for case in report["cases"]}
    assert by_name["slow_progress"]["workDeltaMin"] == 60
    assert by_name["validated_knowledge_gap"]["workDeltaMin"] == 45
    assert by_name["unexpected_interruption"]["workDeltaMin"] == 0
    assert by_name["deadline_overload"]["newDeficitMin"] > by_name["deadline_overload"]["legacyDeficitMin"]
    assert by_name["deadline_overload"]["invariants"]["noAfterDeadline"] is True
