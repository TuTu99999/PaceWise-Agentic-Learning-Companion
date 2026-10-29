from src.services.plan_progress import observed_plan_progress


def _profile(*observations):
    return {
        "last_confirmed_plan": {
            "planningTargets": [{"taskId": "db:a1", "targetMin": 120, "remainingMin": 120}],
            "milestones": [
                {"taskId": "db:a1", "milestoneId": "M1", "assignmentPartIds": ["S1-P1"]},
                {"taskId": "db:a1", "milestoneId": "M2", "assignmentPartIds": ["S1-P2"]},
            ],
            "blocks": [
                {"id": "B1", "taskId": "db:a1", "milestoneId": "M1", "workMinutes": 60},
                {"id": "B2", "taskId": "db:a1", "milestoneId": "M2", "workMinutes": 60},
            ],
        },
        "do_history": list(observations),
    }


def test_completed_do_part_is_removed_from_remaining_plan_scope():
    progress = observed_plan_progress(
        _profile({"block_id": "B1", "work_result": "planned_part_done", "remaining_minutes": 0})
    )["db:a1"]
    assert progress["remaining_minutes"] == 60
    assert progress["completed_milestone_ids"] == ["M1"]
    assert progress["completed_assignment_part_ids"] == ["S1-P1"]


def test_all_completed_do_parts_close_the_task_for_reanalysis():
    progress = observed_plan_progress(_profile(
        {"block_id": "B1", "work_result": "planned_part_done"},
        {"block_id": "B2", "work_result": "planned_part_done"},
    ))["db:a1"]
    assert progress["remaining_minutes"] == 0
    assert progress["completed_assignment_part_ids"] == ["S1-P1", "S1-P2"]


def test_unfinished_do_keeps_only_explicit_residual_work():
    progress = observed_plan_progress(
        _profile({"block_id": "B1", "work_result": "needs_more_time", "remaining_minutes": 25})
    )["db:a1"]
    assert progress["remaining_minutes"] == 85
    assert progress["completed_milestone_ids"] == []


def test_split_milestone_is_complete_only_after_all_its_blocks_finish():
    profile = _profile({"block_id": "B1", "work_result": "planned_part_done"})
    profile["last_confirmed_plan"]["blocks"][1]["milestoneId"] = "M1"
    progress = observed_plan_progress(profile)["db:a1"]
    assert progress["remaining_minutes"] == 60
    assert progress["completed_milestone_ids"] == []


def test_malformed_block_is_ignored_and_cross_task_milestones_stay_scoped():
    profile = _profile({"block_id": "B1", "work_result": "planned_part_done"})
    plan = profile["last_confirmed_plan"]
    plan["planningTargets"].append({"taskId": "db:a2", "remainingMin": 30})
    plan["blocks"].extend([
        {"id": "missing-task", "milestoneId": "ignored", "workMinutes": 30},
        {"id": "B3", "taskId": "db:a2", "milestoneId": "M3", "workMinutes": 30},
    ])
    plan["milestones"].append(
        {"taskId": "db:a2", "milestoneId": "M3", "assignmentPartIds": ["S2-P1"]}
    )

    progress = observed_plan_progress(profile)

    assert progress["db:a1"]["completed_milestone_ids"] == ["M1"]
    assert progress["db:a2"]["completed_milestone_ids"] == []
