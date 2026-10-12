from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.services.plan_confirmation import confirm_partial_plan, confirmation_constraints
from src.services.plan_intelligence import evaluate_plan_quality

NOW = datetime(2026, 10, 10, 8, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
ASSIGNMENTS = [{"id": "a", "deadline": "2026-10-10T22:00:00+07:00"}]


def block(identifier, start="15:00", end="16:00", **extra):
    return {"id": identifier, "taskId": "a", "date": "2026-10-10", "start": start, "end": end, **extra}


def draft(blocks, **extra):
    return {"createdAt": NOW.isoformat(), "input": {"unavailable": []}, "blocks": blocks,
            "feasibility": {"feasible": False, "deficitMin": 540, "shortfalls": [{"taskId": "a", "missingMin": 540}]},
            **extra}


def preview(value):
    return evaluate_plan_quality(value, ASSIGNMENTS, now=NOW)["partialConfirmation"]


def test_capacity_shortfall_allows_explicit_subset_without_claiming_feasibility():
    value = draft([block("safe")])
    original = deepcopy(value)
    quality = evaluate_plan_quality(value, ASSIGNMENTS, now=NOW)
    assert not quality["canConfirm"] and not quality["releaseReady"]
    partial = quality["partialConfirmation"]
    assert partial["canConfirm"] and partial["blockIds"] == ["safe"]
    confirmed = confirm_partial_plan(value, partial)
    assert confirmed["confirmation"]["acknowledgedShortfall"]
    assert not confirmed["feasibility"]["feasible"]
    assert confirmed["feasibility"]["deficitMin"] == 540
    assert value == original


@pytest.mark.parametrize("bad", [block("bad", "23:00", "24:00"), block("bad", "07:00", "08:00"),
                                     block("bad", end="14:00"), block("bad", taskId="missing")])
def test_excludes_invalid_block_but_does_not_discard_its_work(bad):
    partial = preview(draft([block("safe"), bad]))
    assert partial["canConfirm"] and partial["blockIds"] == ["safe"]
    assert partial["excludedBlocks"][0]["blockId"] == "bad"
    assert sum(s["missingMin"] for s in partial["shortfalls"]) >= 540


def test_overlap_rejects_both_competing_blocks_conservatively():
    partial = preview(draft([block("safe", "18:00", "19:00"), block("one"), block("two", "15:30", "16:30")]))
    assert partial["blockIds"] == ["safe"]
    assert partial["shortfalls"] == [{"taskId": "a", "missingMin": 660}]


@pytest.mark.parametrize("required", [60, 120])
def test_dependency_missing_or_incomplete_cannot_unlock_successor(required):
    milestones = [{"milestoneId": "m1", "targetMin": required}, {"milestoneId": "m2", "dependsOn": ["m1"]}]
    blocks = [block("safe", "18:00", "19:00"), block("dependent", "16:00", "17:00", milestoneId="m2")]
    if required == 120:
        blocks.append(block("prerequisite", milestoneId="m1"))
    partial = preview(draft(blocks, milestones=milestones))
    assert "dependent" not in partial["blockIds"]
    assert "safe" in partial["blockIds"]


def test_rejected_prerequisite_propagates_through_entire_dependency_chain():
    milestones = [{"milestoneId": "m1"}, {"milestoneId": "m2", "dependsOn": ["m1"]},
                  {"milestoneId": "m3", "dependsOn": ["m2"]}]
    partial = preview(draft([block("bad", "07:00", "08:00", milestoneId="m1"),
                            block("child", milestoneId="m2"), block("grandchild", "16:00", "17:00", milestoneId="m3"),
                            block("safe", "18:00", "19:00")], milestones=milestones))
    assert partial["blockIds"] == ["safe"]


def test_dependency_cycles_cannot_be_confirmed():
    partial = preview(draft([block("first", milestoneId="m1"), block("second", "16:00", "17:00", milestoneId="m2")],
                            milestones=[{"milestoneId": "m1", "dependsOn": ["m2"]}, {"milestoneId": "m2", "dependsOn": ["m1"]}]))
    assert not partial["canConfirm"] and not partial["blockIds"]


def test_forecast_and_history_are_not_new_executable_work():
    partial = preview(draft([block("past", "07:00", "08:00", status="history"), block("forecast", status="tentative")]))
    assert not partial["canConfirm"]
    with pytest.raises(ValueError):
        confirm_partial_plan(draft([]), partial)


def test_latest_calendar_sleep_and_personal_constraints_are_rechecked():
    value = draft([block("busy"), block("safe", "18:00", "19:00")])
    current = confirmation_constraints(value, {"routineProfile": {"sleepTime": "23:00", "wakeTime": "07:00"}, "unavailable": []},
        [{"type": "event", "starts_at": "2026-10-10T08:00:00Z", "ends_at": "2026-10-10T09:00:00Z"}])
    assert preview(current)["blockIds"] == ["safe"]
    assert preview(value)["blockIds"] == ["busy", "safe"]


def test_completed_tasks_are_not_executable():
    quality = evaluate_plan_quality(draft([block("safe")]),
        [{**ASSIGNMENTS[0], "submission": {"workflow_state": "submitted"}}], now=NOW)
    assert not quality["partialConfirmation"]["canConfirm"]


def test_latest_availability_excludes_outside_blocks_and_keeps_preferred_windows():
    value = draft([block("outside"), block("inside", "18:00", "19:00"),
                   block("preferred", "20:00", "21:00")])
    current = confirmation_constraints(value, {
        "availability": [{"weekday": 5, "start": "18:00", "end": "19:00", "enabled": True}],
        "unavailable": [{"date": "2026-10-10", "start": "20:00", "end": "21:00", "category": "self_study"}],
    }, [])
    partial = preview(current)
    assert partial["blockIds"] == ["inside", "preferred"]
    assert partial["excludedBlocks"][0]["reasons"][0]["code"] == "OUTSIDE_AVAILABILITY"
    assert partial["shortfalls"] == [{"taskId": "a", "missingMin": 600}]


def test_disabled_availability_cannot_authorize_confirmation():
    value = draft([block("outside")], input={"unavailable": [], "availability": [
        {"weekday": 5, "start": "09:00", "end": "22:00", "enabled": False}]})
    assert not preview(value)["canConfirm"]
