import copy
from datetime import UTC, datetime

import pytest

from src.services.adoption_metrics import instant
from src.services.learning_cycle_metrics import cycle_metrics, freeze_plan_measurement

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)
CONFIRMED = datetime(2026, 10, 5, 4, tzinfo=UTC)
USERS = set(range(1, 6))
ASSIGNMENTS = [{"id": 1, "published": True}]


def plan(count=6, date="2026-10-06", provisional=False):
    return {
        "weekStart": "2026-10-05",
        "blocks": [
            {
                "id": f"b-{i}",
                "taskId": "1",
                "milestoneId": f"m-{i}",
                "date": date,
                "start": "17:00",
                "end": "18:00",
                "status": "confirmed",
            }
            for i in range(count)
        ],
        "milestones": [
            {
                "taskId": "1",
                "milestoneId": f"m-{i}",
                "knowledgeComponents": [
                    {"componentId": f"kc-{i}", "status": "provisional" if provisional else "approved"}
                ],
            }
            for i in range(count)
        ],
    }


def events(source=None, at=CONFIRMED):
    source = source if source is not None else plan()
    measured = {**copy.deepcopy(source), "measurement": freeze_plan_measurement(source, at, "Asia/Ho_Chi_Minh")}
    return [{"id": f"event-{user}-{at.isoformat()}", "user": user, "at": at, "plan": measured} for user in USERS]


def evidence(count=4, at="2026-10-06T08:00:00Z", level="application"):
    return [
        {
            "user": user,
            "at": instant(at),
            "block": f"b-{i}",
            "valid": True,
            "payload": {
                "valid": True,
                "confidence": "medium",
                "review_status": "accepted",
                "kc_provisional": False,
                "knowledge_component_ids": [f"kc-{i}"],
                "demonstrated_level": level,
                "dimensions": {"application": "passed"},
            },
        }
        for user in USERS
        for i in range(count)
    ]


def compute(plans=None, records=None, submissions=None, **kwargs):
    return cycle_metrics(
        plans if plans is not None else events(),
        records or [],
        [],
        ASSIGNMENTS,
        submissions or [],
        USERS,
        as_of=NOW,
        **kwargs,
    )


def test_baseline_four_of_six_is_evidence_backed_not_timer_progress():
    result = compute(records=evidence())
    assert result["originalPlan"]["count"] == 20
    assert result["originalPlan"]["total"] == 30
    assert result["originalPlan"]["rate"] == pytest.approx(4 / 6)
    assert result["learningEvidence"]["satisfied"] == 20
    assert result["learningEvidence"]["missing"] == 10
    assert result["progressBeforePaceWise"] is None and result["causalClaim"] is False
    assert "user" not in str(result)


def test_timer_self_report_and_client_workspaces_are_not_evidence():
    source = plan()
    source.update(sessions=[{"completed": True, "actualMin": 999}], taskProgress={"1": {"completed": True}})
    result = compute(plans=events(source))
    assert result["originalPlan"]["count"] == 0
    assert result["originalPlan"]["unverifiedCount"] == 30


def test_replan_removing_every_goal_does_not_erase_original_failures():
    revised = events(plan(0), datetime(2026, 10, 7, 4, tzinfo=UTC))
    result = compute(plans=[*events(), *revised])
    assert result["originalPlan"]["total"] == 30
    assert result["originalPlan"]["removedCount"] == 30
    assert result["originalPlan"]["count"] == 0
    assert result["currentPlan"]["status"] == "insufficient_data"


def test_rescheduling_changes_current_metric_not_original_target():
    revised = events(plan(date="2026-10-08"), datetime(2026, 10, 7, 4, tzinfo=UTC))
    result = compute(plans=[*events(), *revised], records=evidence(6, at="2026-10-07T08:00:00Z"))
    assert result["originalPlan"]["count"] == 0
    assert result["currentPlan"]["count"] == 30
    assert result["learningEvidence"]["satisfied"] == 30


def test_lms_delivery_proves_progress_not_understanding():
    submissions = [{"user_id": user, "assignment_id": 1, "submitted_at": "2026-10-06T08:00:00Z"} for user in USERS]
    result = compute(submissions=submissions)
    assert result["originalPlan"]["rate"] == 1
    assert result["learningEvidence"]["rate"] == 0
    submissions[0]["submitted_at"] = None
    assert compute(submissions=submissions)["originalPlan"]["count"] == 24


def test_course_qualified_planner_ids_match_bare_lms_ids_without_cross_course_leak():
    source = plan()
    for item in [*source["blocks"], *source["milestones"]]:
        item["taskId"] = "7:1"
    submissions = [{"user_id": user, "assignment_id": 1, "submitted_at": "2026-10-06T08:00:00Z"} for user in USERS]
    result = compute(plans=events(source), submissions=submissions, course_id=7)
    assert result["originalPlan"]["count"] == 30
    assert result["learningEvidence"]["satisfied"] == 0
    assert compute(plans=events(source), submissions=submissions, course_id=8)["originalPlan"]["total"] is None


def test_other_course_confirmation_cannot_be_the_original_baseline():
    source = plan()
    for item in [*source["blocks"], *source["milestones"]]:
        item["taskId"] = "8:1"
    result = compute(
        plans=[*events(source), *events(at=instant("2026-10-05T08:00:00Z"))], records=evidence(6), course_id=7
    )
    assert result["originalPlan"]["count"] == 30


@pytest.mark.parametrize("change", ["recognition", "pending_review", "invalid", "contradiction"])
def test_guessing_uncertainty_invalid_evidence_and_wrong_reasoning_do_not_pass(change):
    records = evidence(6)
    for row in records:
        if change == "recognition":
            row["payload"]["demonstrated_level"] = "recognition"
        elif change == "pending_review":
            row["payload"]["review_status"] = "pending_review"
        elif change == "invalid":
            row["valid"] = False
        else:
            row["payload"]["dimensions"]["reasoning"] = "failed"
    assert compute(records=records)["originalPlan"]["count"] == 0


def test_new_failed_observation_is_not_hidden_by_old_high_level():
    later = evidence(6, at="2026-10-07T08:00:00Z", level="no_evidence")
    result = compute(records=[*evidence(6), *later])
    assert result["learningEvidence"]["satisfied"] == 0
    assert result["originalPlan"]["count"] == 30  # A later failure does not rewrite historic attainment.


def test_provisional_mapping_and_legacy_plans_do_not_fabricate_success():
    result = compute(plans=events(plan(provisional=True)), records=evidence(6))
    assert result["learningEvidence"]["unmapped"] == 30
    old = events()
    for event in old:
        event["plan"].pop("measurement", None)
    assert compute(plans=old, records=evidence(6))["originalPlan"]["rate"] is None


def test_future_targets_and_retroactive_confirmation_are_not_due_progress():
    assert compute(plans=events(plan(date="2026-10-11")))["originalPlan"]["status"] == "insufficient_data"
    assert not freeze_plan_measurement(plan(), NOW, "Asia/Ho_Chi_Minh")["objectives"]


def test_small_cohort_suppresses_rates_and_numerators():
    result = compute(plans=events()[:4], records=evidence(6))
    assert result["originalPlan"]["status"] == "insufficient_data"
    assert result["originalPlan"]["count"] is None
    assert result["learningEvidence"]["retention"] is None


def test_multiple_blocks_form_one_goal_and_snapshot_does_not_mutate_plan():
    source = plan(1)
    source["blocks"].append({**source["blocks"][0], "id": "second", "end": "19:00"})
    before = copy.deepcopy(source)
    snapshot = freeze_plan_measurement(source, CONFIRMED, "Asia/Ho_Chi_Minh")
    assert len(snapshot["objectives"]) == 1
    assert snapshot["objectives"][0]["blockIds"] == ["b-0", "second"]
    assert instant(snapshot["objectives"][0]["targetAt"]).hour == 12
    assert source == before


def test_retention_requires_actual_checked_probe_not_due_date():
    probes = [{"user": user, "due": instant("2026-10-08T08:00:00Z"), "status": "pending"} for user in USERS]
    result = cycle_metrics(events(), evidence(6), probes, ASSIGNMENTS, [], USERS, as_of=NOW)
    assert result["learningEvidence"]["retention"] == {"due": 5, "checked": 0, "passed": 0}


def test_excused_and_unpublished_tasks_are_excluded():
    submissions = [{"user_id": user, "assignment_id": 1, "workflow_state": "excused"} for user in USERS]
    assert compute(submissions=submissions)["originalPlan"]["rate"] is None
    result = cycle_metrics(events(), evidence(6), [], [{"id": 1, "published": False}], [], USERS, as_of=NOW)
    assert result["originalPlan"]["rate"] is None


def test_missing_second_kc_is_not_covered_by_first_kc_score():
    source = plan(1)
    source["milestones"][0]["knowledgeComponents"].append({"componentId": "other-kc", "status": "approved"})
    assert compute(plans=events(source), records=evidence(1))["originalPlan"]["count"] == 0


def test_weak_transfer_does_not_erase_valid_application_but_blocks_transfer_goal():
    source = plan(1)
    records = evidence(1)
    for row in records:
        row["payload"]["dimensions"]["transfer"] = "failed"
    assert compute(plans=events(source), records=records)["learningEvidence"]["satisfied"] == 5
    source["milestones"][0]["requiredLevel"] = "transfer"
    assert compute(plans=events(source), records=records)["learningEvidence"]["satisfied"] == 0


def test_repository_projection_excludes_other_courses_institutions_and_students():
    import json
    from uuid import uuid4

    from src.db import SessionLocal
    from src.persistence_models import LearningEvent
    from src.services.learning_cycle_metrics import load_cycle_data

    with SessionLocal() as db:
        for institution, course, user in [
            ("kpi-test", 9401, 1),
            ("other", 9401, 1),
            ("kpi-test", 9402, 1),
            ("kpi-test", 9401, 99),
        ]:
            identifier = str(uuid4())
            db.add(
                LearningEvent(
                    id=identifier,
                    event_key=identifier,
                    institution_id=institution,
                    course_id=course,
                    student_user_id=user,
                    event_type="PLAN_CONFIRMED",
                    entity_id=identifier,
                    payload_json=json.dumps({"confirmed_plan": plan()}),
                    occurred_at=CONFIRMED,
                )
            )
        db.commit()
        rows, _, _ = load_cycle_data(db, "kpi-test", 9401, USERS, NOW)
        assert len(rows) == 1 and rows[0]["user"] == 1


def test_next_week_confirmation_does_not_remove_current_week_goals():
    next_week = plan(date="2026-10-13")
    next_week["weekStart"] = "2026-10-12"
    result = compute(plans=[*events(), *events(next_week, datetime(2026, 10, 8, 4, tzinfo=UTC))])
    assert result["originalPlan"]["removedCount"] == 0
