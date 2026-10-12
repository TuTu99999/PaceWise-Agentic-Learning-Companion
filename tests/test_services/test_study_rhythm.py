from datetime import UTC, datetime, timedelta

import pytest

from src.services.plan_intelligence import estimate_workload
from src.services.planning import build_plan_draft
from src.services.study_rhythm import compare_rhythm_trial, propose_rhythm, summarize_independent_assessment
from src.services.study_sessions import advance_timer

NOW = datetime(2026, 10, 10, 8, tzinfo=UTC)


def timer():
    return {"status": "running", "observed_seconds": 120, "checkpoint_at": NOW.isoformat(),
            "unobserved_gap": False, "interruption_reason": "none"}


def observation(index, **patch):
    return {"session_id": f"s{index}", "task_id": "1:a", "course_id": 1, "activity_type": "concept",
            "planned_minutes": 60, "actual_minutes": 90, "completion_percent": 100,
            "time_source": "timer", "interruption_reason": "none", "unobserved_gap": False,
            "length_feeling": "too_long", "rhythm": {"sessionMinutes": 60, "breakMinutes": 10},
            "readiness_key": "application-v1", "recorded_at": str(index), **patch}


def test_reload_does_not_count_absence_even_for_short_gap():
    result = advance_timer(timer(), {"action": "recover"}, NOW + timedelta(seconds=10))
    assert result["observed_seconds"] == 120
    assert result["status"] == "paused"
    assert result["unobserved_gap"]


def test_network_gap_never_adds_absence_and_does_not_infer_misunderstanding():
    result = advance_timer(timer(), {"action": "checkpoint"}, NOW + timedelta(hours=8))
    assert result["observed_seconds"] == 120
    assert result["interruption_reason"] == "unknown"
    assert "mastery" not in result


def test_reading_pdf_without_clicks_is_not_automatically_interrupted():
    result = advance_timer(timer(), {"action": "checkpoint"}, NOW + timedelta(seconds=20))
    assert result["observed_seconds"] == 140
    assert result["status"] == "running"
    assert result["interruption_reason"] == "none"


@pytest.mark.parametrize("reason", ["unexpected", "unknown", "outside", "difficulty"])
def test_unsuitable_sessions_do_not_propose_rhythm(reason):
    result = propose_rhythm([observation(i, interruption_reason=reason) for i in range(5)],
                            {"sessionMinutes": 60, "breakMinutes": 10})
    assert result["proposal"] is None


def test_no_cross_course_task_readiness_or_missing_evidence_inference():
    prefs = {"sessionMinutes": 60, "breakMinutes": 10}
    assert propose_rhythm([], prefs)["proposal"] is None
    cases = [observation(1), observation(2, task_id="1:b"), observation(3, course_id=2),
             observation(4, readiness_key="recognition-v1")]
    assert propose_rhythm(cases, prefs)["proposal"] is None


def test_proposal_is_small_traceable_and_not_a_claim_of_learning_quality():
    prefs = {"sessionMinutes": 60, "breakMinutes": 10}
    result = propose_rhythm([observation(i) for i in range(3)], prefs)
    proposal = result["proposal"]
    assert proposal["preferences"] == {"sessionMinutes": 45, "breakMinutes": 10}
    assert proposal["sourceRefs"] == ["do:s0", "do:s1", "do:s2"]
    assert proposal["learningQuality"] == "not_comparatively_validated"
    assert proposal["requiresConfirmation"]
    assert prefs["sessionMinutes"] == 60


def test_sparse_interrupted_other_task_or_duplicate_history_preserves_baseline():
    for history in [[observation(1)], [observation(1)] * 5,
                    [observation(i, task_id="2:b") for i in range(5)],
                    [observation(i, interruption_reason="unexpected") for i in range(5)]]:
        estimate = estimate_workload(30, task_id="1:a", learner_profile={"do_history": history})
        assert estimate.p50_minutes == 30


@pytest.mark.parametrize("patch", [{"time_source": "self_report"}, {"time_source": None},
                                  {"checkpoint_minutes": 5}, {"readiness_key": None}])
def test_uninstrumented_or_mixed_work_and_checkpoint_time_is_not_calibration(patch):
    estimate = estimate_workload(30, task_id="1:a", learner_profile={"do_history": [observation(i, **patch) for i in range(3)]})
    assert estimate.p50_minutes == 30 and estimate.evidence_count == 0


def test_new_readiness_or_rhythm_requires_its_own_duration_evidence():
    old = [observation(i) for i in range(3)]
    for last in [observation(3, readiness_key="new-level"),
                 observation(3, rhythm={"sessionMinutes": 45, "breakMinutes": 10})]:
        assert estimate_workload(30, task_id="1:a", learner_profile={"do_history": old + [last]}).p50_minutes == 30


def test_latest_five_rhythm_sources_are_chronological_unique_and_identifiable():
    prefs = {"sessionMinutes": 60, "breakMinutes": 10}
    rows = [observation(i) for i in range(8, -1, -1)]
    proposal = propose_rhythm(rows + [rows[0]], prefs)["proposal"]
    assert proposal["sourceRefs"] == [f"do:s{i}" for i in range(4, 9)]
    assert propose_rhythm([observation(i, task_id=None) for i in range(3)], prefs)["proposal"] is None


def test_assisted_pending_and_missing_assessment_are_not_independence_evidence():
    def evidence(identifier, kc, outcome, **patch):
        return {"id": identifier, "valid": True, "confidence": "high", "review_status": "accepted",
                "knowledge_component_ids": [kc], "dimensions": {"application": outcome}, **patch}
    rows = [evidence("e1", "kc1", "failed"), evidence("e2", "kc2", "passed"),
            evidence("e3", "kc1", "passed", review_status="pending_review"),
            evidence("e4", "kc1", "passed", hint_level=2)]
    summary, refs = summarize_independent_assessment(rows)
    assert summary["application"] == "failed" and refs == ["e1", "e2"]
    assert summarize_independent_assessment([]) == ({}, [])
    # A later independent re-test can resolve the failure of that same KC.
    assert summarize_independent_assessment(rows + [evidence("e5", "kc1", "passed")])[0]["application"] == "passed"


def test_unscoped_or_interruption_reflect_does_not_multiply_every_task():
    for signal in [{"duration_factor": 1.5, "follow_up_minutes": 30},
                   {"task_id": "1:a", "cause": "interruption", "duration_factor": 1.5}]:
        estimate = estimate_workload(30, task_id="1:a", learner_profile={"last_reflection": {"planning_signal": signal}})
        assert estimate.p50_minutes == 30


def test_shorter_rhythm_keeps_work_and_breaks_do_not_cross_deadline():
    assignments = [{"id": "1:a", "deadline": "2026-10-10T17:00:00+07:00"}]
    base = {"weekStart": "2026-10-05", "tasks": [{"taskId": "1:a", "remainingMin": 90}],
            "availability": [{"weekday": 5, "enabled": True, "start": "15:00", "end": "17:00"}]}
    draft = build_plan_draft({**base, "studyPreferences": {"sessionMinutes": 30, "breakMinutes": 10}},
                            assignments, now=NOW - timedelta(hours=1))
    assert draft["planningTargets"][0]["targetMin"] == 90
    assert draft["feasibility"]["feasible"]
    assert all(block["end"] <= "17:00" for block in draft["blocks"])
    assert sum((int(b["end"][:2]) * 60 + int(b["end"][3:])) -
               (int(b["start"][:2]) * 60 + int(b["start"][3:])) for b in draft["blocks"]) == 90


def test_checkpoint_is_extra_capacity_not_stolen_work_and_can_make_deadline_infeasible():
    base = {"weekStart": "2026-10-05", "tasks": [{"taskId": "1:a", "remainingMin": 60}],
            "availability": [{"weekday": 5, "enabled": True, "start": "15:00", "end": "16:00"}],
            "studyPreferences": {"sessionMinutes": 45, "breakMinutes": 10, "checkpointMinutes": 5}}
    assignments = [{"id": "1:a", "deadline": "2026-10-10T16:00:00+07:00"}]
    draft = build_plan_draft(base, assignments, now=NOW - timedelta(hours=1))
    assert draft["planningTargets"][0]["targetMin"] == 60
    assert not draft["feasibility"]["feasible"]
    assert draft["feasibility"]["checkpointReservedMin"] == 5
    assert all(b["end"] <= "16:00" for b in draft["blocks"])
    assert all(b["workMinutes"] + b["checkpointMinutes"] <= 45 for b in draft["blocks"])
    base["availability"][0]["end"] = "17:00"
    assignments[0]["deadline"] = "2026-10-10T17:00:00+07:00"
    feasible = build_plan_draft(base, assignments, now=NOW - timedelta(hours=1))
    assert feasible["feasibility"]["feasible"]
    assert sum(b["workMinutes"] for b in feasible["blocks"]) == 60
    assert sum(b["checkpointMinutes"] for b in feasible["blocks"]) == 10


def test_pilot_comparison_reports_missing_assessment_as_unknown_not_zero():
    old = [observation(i) for i in range(3)]
    trial = {"sourceRefs": [f"do:s{i}" for i in range(3)], "taskId": "1:a", "courseId": 1, "activityType": "concept",
             "preferences": {"sessionMinutes": 45, "breakMinutes": 10}, "accepted_at": "2026-10-10"}
    assert compare_rhythm_trial(old, trial)["status"] == "collecting"
    new = [observation(i, rhythm=trial["preferences"], actual_minutes=45, length_feeling="comfortable",
                       recorded_at="2026-10-11") for i in range(3, 6)]
    result = compare_rhythm_trial(old + new, trial)
    assert result["status"] == "descriptive_not_causal"
    assert result["before"]["longSessionRate"] == 1
    assert result["after"]["longSessionRate"] == 0
    assert result["after"]["assessment"]["application"]["passRate"] is None
    assert "optimal" not in result


def test_pilot_does_not_compare_other_tasks_or_changed_knowledge_baseline():
    old = [observation(i) for i in range(3)]
    trial = {"sourceRefs": [f"do:s{i}" for i in range(3)], "taskId": "1:a", "courseId": 1, "activityType": "concept",
             "preferences": {"sessionMinutes": 45, "breakMinutes": 10}, "accepted_at": "2026-10-10"}
    mismatched = [observation(i, rhythm=trial["preferences"], readiness_key="changed", recorded_at="2026-10-11") for i in range(3, 6)]
    result = compare_rhythm_trial(old + mismatched, trial)
    assert result["status"] == "collecting"
    assert result["after"]["sessions"] == 0
