from src.services.reflection_policy import (
    recommend_reflection,
    route_reflection,
    validate_hypothesis,
    verified_assessment_kcs,
)


def _session(course="DB201", **overrides):
    value = {
        "course_code": course,
        "task_id": f"{course}:1",
        "planned_minutes": 60,
        "actual_minutes": 90,
        "completion_percent": 100,
    }
    value.update(overrides)
    return value


def test_reflection_router_keeps_activity_and_low_evidence_week_on_luna():
    assert route_reflection("activity", {"sessions": [_session()] * 5}, "khó hiểu")["model_tier"] == "luna"
    assert route_reflection("weekly", {"sessions": [_session()] * 2}, "khó hiểu")["model_tier"] == "luna"


def test_reflection_router_uses_sol_only_for_evidence_rich_complex_week():
    metrics = {
        "session_count": 3,
        "sessions": [_session("DB201"), _session("WEB201"), _session("DB201")],
    }
    route = route_reflection("weekly", metrics, "Tuần này em học bình thường")
    assert route["model_tier"] == "sol"
    assert route["complexity"] == "complex"
    assert "multiple_courses" in route["reasons"]


def test_validator_downgrades_single_session_causality_and_ignores_model_planning():
    hypothesis, warnings = validate_hypothesis(
        {
            "effective": "đã thử làm bài",
            "difficulty": "còn khó",
            "cause": "estimate_error",
            "confidence": 0.9,
            "recommended_action": "split_task",
            "task_id": "DB201:1",
            "duration_factor": 1.5,
            "follow_up_minutes": 180,
        },
        metrics={"session_count": 1, "sessions": [_session()]},
        trusted_task_ids={"DB201:1"},
        trusted_kcs=set(),
    )
    assert hypothesis["cause"] == "unknown"
    assert hypothesis["confidence"] == 0.49
    assert "INSUFFICIENT_CAUSAL_EVIDENCE" in warnings
    assert "MODEL_PLANNING_FIELDS_IGNORED" in warnings


def test_validator_rejects_unobserved_numeric_claim_but_keeps_observed_number():
    hypothesis, warnings = validate_hypothesis(
        {
            "effective": "đã học 999 phút",
            "difficulty": "còn 35 phút",
            "cause": "unknown",
            "confidence": 0.2,
        },
        metrics={"sessions": [_session(remaining_minutes=35)]},
        trusted_task_ids={"DB201:1"},
        trusted_kcs=set(),
    )
    assert hypothesis["effective"] == ""
    assert hypothesis["difficulty"] == "còn 35 phút"
    assert "UNSUPPORTED_NUMERIC_CLAIM" in warnings


def test_remaining_work_has_exact_backend_minutes_and_recover_handoff():
    recommendation, signal = recommend_reflection(
        {"cause": "unknown", "task_id": "DB201:1", "affected_kcs": []},
        metrics={"sessions": [_session(remaining_minutes=35, completion_percent=50)]},
        calibration_count=0,
        calibration_factor=1.0,
        trusted_task_ids={"DB201:1"},
    )
    assert recommendation == {
        "action": "complete_remaining_work",
        "minutes": 35,
        "duration_factor": 1.0,
        "requires_recover": True,
        "reason": "observed_remaining_work",
        "affected_kcs": [],
        "task_id": "DB201:1",
    }
    assert signal["follow_up_minutes"] == 0


def test_verified_assessment_can_create_bounded_kc_review_but_model_cannot_set_minutes():
    metrics = {
        "assessment_evidence": [
            {
                "valid": True,
                "knowledge_component_ids": ["JOIN"],
                "dimensions": {"application": "failed"},
            }
        ]
    }
    assert verified_assessment_kcs(metrics) == {"JOIN"}
    recommendation, signal = recommend_reflection(
        {"cause": "knowledge_gap", "task_id": "DB201:1", "affected_kcs": ["JOIN"]},
        metrics=metrics,
        calibration_count=0,
        calibration_factor=1.0,
        trusted_task_ids={"DB201:1"},
    )
    assert recommendation["action"] == "review_verified_kc"
    assert recommendation["minutes"] == 15
    assert signal["follow_up_minutes"] == 15
    assert signal["affected_kcs"] == ["JOIN"]


def test_duration_factor_requires_three_homogeneous_calibration_sessions():
    hypothesis = {"cause": "estimate_error", "task_id": "DB201:1", "affected_kcs": []}
    low, low_signal = recommend_reflection(
        hypothesis,
        metrics={},
        calibration_count=2,
        calibration_factor=1.25,
        trusted_task_ids={"DB201:1"},
    )
    enough, enough_signal = recommend_reflection(
        hypothesis,
        metrics={},
        calibration_count=3,
        calibration_factor=1.25,
        trusted_task_ids={"DB201:1"},
    )
    assert low["duration_factor"] == low_signal["duration_factor"] == 1.0
    assert enough["duration_factor"] == enough_signal["duration_factor"] == 1.25
