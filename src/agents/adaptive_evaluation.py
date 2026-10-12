"""Unique offline boundary cases; no simulated learner outcomes or SME claims."""

from datetime import UTC, datetime, timedelta

from src.services.assessment_policy import DIMENSION, STAGES, next_step
from src.services.learning_evidence import _highest_level
from src.services.misconception_diagnosis import diagnose
from src.services.replan_policy import decide_replan


def run_adaptive_evaluation() -> dict:
    cases = []
    for stage in STAGES:
        for passed, status in ((True, "completed"), (False, "completed"), (True, "awaiting_teacher")):
            for hint in (0, 1, 5):
                outcome = {
                    "status": status,
                    "assessment_result": {
                        "status": "demonstrated",
                        "dimensions": {DIMENSION[stage]: "passed" if passed else "failed"},
                    },
                }
                if status == "awaiting_teacher":
                    expected = "review_required"
                elif not passed:
                    expected = "needs_support"
                elif hint:
                    expected = "verification_required"
                else:
                    expected = "completed" if stage == "transfer" else "active"
                actual = next_step(stage, outcome, hint_level=hint, attempts=1)["status"]
                cases.append(
                    {
                        "id": f"policy:{stage}:{passed}:{status}:H{hint}",
                        "category": "policy",
                        "expected": expected,
                        "actual": actual,
                        "passed": expected == actual,
                    }
                )
    dimensions = dict.fromkeys(("conceptual", "reasoning", "application", "transfer", "retention"), "passed")
    gates = [
        ("metadata_only", {}, {}, 0, "no_evidence"),
        ("transfer_without_prerequisite", {"transfer": "passed"}, {}, 0, "no_evidence"),
        (
            "closed_correct",
            {"recall": "passed", "transfer": "passed"},
            {"answer_type": "multiple_choice"},
            0,
            "recognition",
        ),
        ("application_without_reasoning", {"conceptual": "passed", "application": "passed"}, {}, 0, "conceptual"),
        ("retention_before_probe", dimensions, {}, 0, "transfer"),
        ("hinted_transfer", dimensions, {}, 1, "application"),
        ("full_support", dimensions, {}, 5, "conceptual"),
        (
            "due_retention",
            dimensions,
            {"retention_context": {"validated": True, "baseline_evidence_id": "ev"}},
            0,
            "retained",
        ),
    ]
    for identifier, dims, trusted, hint, expected in gates:
        actual = _highest_level(
            {"status": "demonstrated", "dimensions": dims}, {"answer_type": "open", **trusted}, hint_level=hint
        )
        cases.append(
            {
                "id": identifier,
                "category": "knowledge_gate",
                "expected": expected,
                "actual": actual,
                "passed": expected == actual,
            }
        )
    instant = datetime(2026, 10, 8, tzinfo=UTC)
    drift = {"status": "missed", "block_id": "b1", "planned_minutes": 60}
    first = decide_replan(signal={}, last_do=drift, latest_evidence={}, now=instant)
    replans = [
        ("small_drift", {"planned_minutes": 60, "actual_minutes": 65, "completion_percent": 100}, None, "keep"),
        ("missed_block", drift, None, "propose_draft"),
        ("duplicate_drift", drift, first, "keep"),
        ("cooldown", {**drift, "block_id": "b2"}, first, "keep"),
    ]
    for identifier, observation, previous, expected in replans:
        result = decide_replan(
            signal={}, last_do=observation, latest_evidence={}, previous=previous, now=instant + timedelta(minutes=1)
        )
        cases.append(
            {
                "id": identifier,
                "category": "replan",
                "expected": expected,
                "actual": result["action"],
                "passed": result["action"] == expected and result["auto_apply"] is False,
            }
        )
    for identifier, hypotheses, taxonomy, expected in [
        ("taxonomy_missing", [{"label": "symmetry", "evidence_quote": "answer"}], [], "unknown"),
        ("hypothesis_ungrounded", [{"label": "symmetry", "evidence_quote": "fiction"}], ["symmetry"], "unknown"),
        ("taxonomy_grounded", [{"label": "symmetry", "evidence_quote": "answer"}], ["symmetry"], "suspected"),
    ]:
        result = diagnose(hypotheses, taxonomy, answer="answer", kc_id="kc", evidence_ids=["ev"])
        cases.append(
            {
                "id": identifier,
                "category": "misconception",
                "expected": expected,
                "actual": result["status"],
                "passed": result["status"] == expected,
            }
        )
    metrics = {
        f"{category}_accuracy": sum(case["passed"] for case in cases if case["category"] == category)
        / sum(case["category"] == category for case in cases)
        for category in sorted({case["category"] for case in cases})
    }
    return {
        "dataset_version": "adaptive-boundaries-2026-10-08-v1",
        "sample_count": len(cases),
        "unique_sample_count": len({case["id"] for case in cases}),
        "cases": cases,
        "metrics": metrics,
        "overall_pass": all(case["passed"] for case in cases),
        "validation_status": "offline_engineering_validation_only",
        "limitations": [
            "Developer-authored labels, not independent SME labels.",
            "Tests gates/policy, not real student understanding or improved learning outcomes.",
            "No Cohen kappa, probability calibration or learning gain claimed.",
        ],
    }
