from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.services.planning import build_plan_draft


def test_scheduler_respects_busy_time_and_deadline():
    result = build_plan_draft(
        {
            "goal": "Finish assignment",
            "tasks": [{"taskId": "a1", "remainingMin": 120}],
            "availability": [{"weekday": 0, "enabled": True, "start": "18:00", "end": "21:30"}],
            "unavailable": [{"weekday": 0, "start": "18:00", "end": "19:00", "label": "Class"}],
            "preferred": "evening",
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-09-28T23:59:00+07:00"}],
        today=date(2026, 9, 28),
    )
    assert result["feasibility"]["feasible"] is True
    assert result["blocks"][0]["start"] == "19:00"
    assert all(block["date"] == "2026-09-28" for block in result["blocks"])


def test_elapsed_unused_do_block_is_rescheduled_instead_of_marked_complete():
    current = datetime(2026, 9, 28, 12, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    result = build_plan_draft(
        {
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [{"weekday": 0, "enabled": True, "start": "08:00", "end": "20:00"}],
            "unavailable": [],
            "pinnedBlocks": [
                {"id": "unused", "taskId": "a1", "date": "2026-09-28", "start": "09:00", "end": "10:00", "placementSource": "agent"},
            ],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-09-28T20:00:00+07:00"}],
        now=current,
    )

    assert all(block["id"] != "unused" for block in result["blocks"])
    replacement = [block for block in result["blocks"] if block["taskId"] == "a1"]
    assert replacement
    assert min(block["start"] for block in replacement) >= "12:15"
    assert result["planningTargets"][0]["remainingMin"] == 60


def test_only_completed_do_evidence_survives_as_history():
    current = datetime(2026, 9, 28, 12, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    result = build_plan_draft(
        {
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [{"weekday": 0, "enabled": True, "start": "08:00", "end": "20:00"}],
            "unavailable": [],
            "pinnedBlocks": [
                {"id": "completed", "taskId": "a1", "date": "2026-09-28", "start": "09:00", "end": "10:00", "status": "history", "placementSource": "agent"},
            ],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-09-28T20:00:00+07:00"}],
        now=current,
    )

    assert next(block for block in result["blocks"] if block["id"] == "completed")["status"] == "history"


def test_not_yet_taught_assignment_is_planned_for_after_learning_release():
    before_class = datetime(2026, 9, 28, 12, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    assignment = {
        "id": "a1",
        "title": "Chapter exercise",
        "learning_available_at": "2026-09-28T14:00:00+07:00",
        "deadline": "2026-09-28T20:00:00+07:00",
    }
    plan_input = {
        "tasks": [{"taskId": "a1", "remainingMin": 60}],
        "availability": [{"weekday": 0, "enabled": True, "start": "08:00", "end": "20:00"}],
        "unavailable": [],
    }

    planned = build_plan_draft(plan_input, [assignment], now=before_class)
    assert planned["planningTargets"][0]["taskId"] == "a1"
    assert planned["blocks"]
    assert min(block["start"] for block in planned["blocks"]) >= "14:00"
    assert {block["earliestStartAt"] for block in planned["blocks"]} == {
        "2026-09-28T14:00:00+07:00"
    }

    after_class = build_plan_draft(
        plan_input,
        [assignment],
        now=datetime(2026, 9, 28, 14, 1, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
    )
    assert after_class["planningTargets"][0]["taskId"] == "a1"
    assert min(block["start"] for block in after_class["blocks"]) >= "14:15"


def test_scheduler_places_each_grounded_assignment_part_in_dependency_order():
    proposed = [
        {
            "milestone_id": f"M{index}",
            "task_id": "db:a1",
            "title": f"Làm câu {index}",
            "deliverable": f"Lời giải câu {index}",
            "estimated_minutes": 40,
            "depends_on": [] if index == 1 else [f"M{index - 1}"],
            "assignment_part_ids": [f"S1-P{index}"],
            "source_refs": [f"file:7#exercise=1&part=S1-P{index}"],
        }
        for index in range(1, 4)
    ]
    result = build_plan_draft(
        {
            "goal": "Hoàn thành bài SQL theo từng câu",
            "tasks": [{"taskId": "db:a1", "remainingMin": 120}],
            "availability": [{"weekday": 0, "enabled": True, "start": "18:00", "end": "22:00"}],
            "unavailable": [],
            "preferred": "evening",
            "studyPreferences": {"sessionMinutes": 60, "breakMinutes": 10, "checkpointMinutes": 0},
        },
        [{"id": "db:a1", "title": "Bài SQL", "deadline": "2026-09-28T23:59:00+07:00"}],
        proposed_milestones=proposed,
        today=date(2026, 9, 28),
    )

    assert result["feasibility"]["feasible"] is True
    assert [item["assignmentPartIds"] for item in result["milestones"]] == [
        ["S1-P1"], ["S1-P2"], ["S1-P3"],
    ]
    starts = {
        milestone_id: min(f"{item['date']}T{item['start']}" for item in result["blocks"] if item["milestoneId"] == milestone_id)
        for milestone_id in ("M1", "M2", "M3")
    }
    assert starts["M1"] < starts["M2"] < starts["M3"]


def test_scheduler_fallback_preserves_assignment_parts_as_separate_do_blocks():
    assignment = {
        "id": "db:a2",
        "title": "Bài tập Chương 2: Mô hình cơ sở dữ liệu",
        "deadline": "2026-09-28T23:59:00+07:00",
        "assignment_parts": [
            {
                "partId": "S2-P1",
                "label": "Thiết kế ERD",
                "content": "Xác định thực thể, thuộc tính, khóa và quan hệ.",
                "sourceRef": "file:118#exercise=2&part=S2-P1",
            },
            {
                "partId": "S2-P2",
                "label": "Kiểm tra và giải thích",
                "content": "Kiểm tra lực lượng quan hệ và giải thích quyết định.",
                "sourceRef": "file:118#exercise=2&part=S2-P2",
            },
        ],
    }
    result = build_plan_draft(
        {
            "tasks": [{"taskId": "db:a2", "remainingMin": 70}],
            "availability": [{"weekday": 0, "enabled": True, "start": "18:00", "end": "21:00"}],
            "unavailable": [],
            "preferred": "evening",
            "studyPreferences": {"sessionMinutes": 90, "breakMinutes": 10, "checkpointMinutes": 0},
        },
        [assignment],
        proposed_milestones=[],
        today=date(2026, 9, 28),
    )

    assert [item["assignmentPartIds"] for item in result["milestones"]] == [["S2-P1"], ["S2-P2"]]
    assert len({item["milestoneId"] for item in result["blocks"]}) == 2
    assert all("Hoàn thành Bài tập" not in item["milestoneTitle"] for item in result["blocks"])


def test_scheduler_accepts_multiple_preferred_study_periods():
    result = build_plan_draft(
        {
            "goal": "Study outside the morning",
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [{"weekday": 0, "enabled": True, "start": "08:00", "end": "20:00"}],
            "unavailable": [],
            "preferred": ["afternoon", "evening"],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-09-28T23:59:00+07:00"}],
        today=date(2026, 9, 28),
    )

    assert result["feasibility"]["feasible"] is True
    assert result["blocks"][0]["start"] == "12:00"
    assert result["blocks"][0]["outsidePreferred"] is False


def test_scheduler_labels_valid_fallback_outside_soft_preferences():
    result = build_plan_draft(
        {
            "goal": "Use a free fallback when preferred time is busy",
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [{"weekday": 0, "enabled": True, "start": "00:00", "end": "24:00"}],
            "unavailable": [
                {"weekday": 0, "start": "17:00", "end": "24:00", "category": "personal"},
            ],
            "preferred": ["evening"],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-09-28T23:59:00+07:00"}],
        today=date(2026, 9, 28),
    )

    assert result["feasibility"]["feasible"] is True
    assert result["blocks"][0]["start"] == "00:00"
    assert result["blocks"][0]["outsidePreferred"] is True


def test_scheduler_uses_student_break_between_different_tasks():
    result = build_plan_draft(
        {
            "goal": "Study two courses with a real break",
            "tasks": [
                {"taskId": "dsa", "remainingMin": 70},
                {"taskId": "db", "remainingMin": 70},
            ],
            "availability": [{"weekday": 3, "enabled": True, "start": "15:38", "end": "19:00"}],
            "unavailable": [],
            "preferred": ["afternoon", "evening"],
            "studyPreferences": {"sessionMinutes": 90, "breakMinutes": 20, "checkpointMinutes": 0},
        },
        [
            {"id": "dsa", "title": "DSA task", "deadline": "2026-10-15T23:59:00+07:00"},
            {"id": "db", "title": "DB task", "deadline": "2026-10-15T23:59:00+07:00"},
        ],
        today=date(2026, 10, 15),
    )

    assert len(result["blocks"]) == 2
    first, second = result["blocks"]
    first_end = int(first["end"][:2]) * 60 + int(first["end"][3:])
    second_start = int(second["start"][:2]) * 60 + int(second["start"][3:])
    assert second_start - first_end >= 20


def test_scheduler_prioritizes_student_defined_self_study_window():
    result = build_plan_draft(
        {
            "goal": "Use my protected study habit",
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [{"weekday": 0, "enabled": True, "start": "08:00", "end": "22:00"}],
            "unavailable": [
                {
                    "weekday": 0,
                    "date": "2026-09-28",
                    "start": "20:00",
                    "end": "21:30",
                    "category": "self_study",
                }
            ],
            "preferred": ["morning", "evening"],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-09-28T23:59:00+07:00"}],
        today=date(2026, 9, 28),
    )

    assert result["blocks"][0]["start"] == "20:00"


def test_scheduler_uses_explicit_weekend_self_study_before_generic_weekday_time():
    result = build_plan_draft(
        {
            "goal": "Use the study windows I placed on the calendar",
            "weekStart": "2026-10-05",
            "horizonEnd": "2026-10-11",
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [
                {"weekday": weekday, "enabled": weekday < 5, "start": "08:00", "end": "20:00"}
                for weekday in range(7)
            ],
            "unavailable": [
                {
                    "weekday": 6,
                    "date": "2026-10-11",
                    "start": "20:00",
                    "end": "22:00",
                    "category": "self_study",
                }
            ],
            "preferred": ["morning", "afternoon"],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-10-11T23:59:00+07:00"}],
        today=date(2026, 10, 5),
    )

    assert result["feasibility"]["feasible"] is True
    assert result["blocks"][0]["date"] == "2026-10-11"
    assert result["blocks"][0]["start"] == "20:00"
    assert result["blocks"][0]["end"] == "21:00"


def test_self_study_priority_never_reverses_milestone_dependencies():
    result = build_plan_draft(
        {
            "weekStart": "2026-10-05",
            "horizonEnd": "2026-10-11",
            "tasks": [{"taskId": "a1", "remainingMin": 120}],
            "availability": [
                {"weekday": weekday, "enabled": True, "start": "08:00", "end": "20:00"}
                for weekday in range(7)
            ],
            "unavailable": [
                {
                    "weekday": 6,
                    "date": "2026-10-11",
                    "start": "20:00",
                    "end": "21:00",
                    "category": "self_study",
                }
            ],
            "preferred": ["morning", "evening"],
            "studyPreferences": {"sessionMinutes": 30, "breakMinutes": 15, "checkpointMinutes": 5},
        },
        [{"id": "a1", "title": "Dependency-heavy task", "deadline": "2026-10-11T23:59:00+07:00"}],
        today=date(2026, 10, 5),
    )

    assert result["feasibility"]["feasible"] is True
    assert not [
        item for item in result["qualityEvaluation"]["violations"]
        if item["code"].startswith("DEPENDENCY_")
    ]


def test_reanalysis_releases_old_agent_block_for_new_self_study_window():
    result = build_plan_draft(
        {
            "goal": "Replan around my new preferred study time",
            "weekStart": "2026-10-05",
            "horizonEnd": "2026-10-11",
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [
                {"weekday": weekday, "enabled": True, "start": "08:00", "end": "22:00"}
                for weekday in range(7)
            ],
            "unavailable": [
                {
                    "weekday": 5,
                    "date": "2026-10-10",
                    "start": "20:00",
                    "end": "22:00",
                    "category": "self_study",
                }
            ],
            "preferred": ["morning", "evening"],
            "pinnedBlocks": [
                {
                    "id": "old-ai-monday",
                    "taskId": "a1",
                    "date": "2026-10-05",
                    "start": "08:00",
                    "end": "09:00",
                    "placementSource": "agent",
                }
            ],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-10-11T23:59:00+07:00"}],
        today=date(2026, 10, 5),
    )

    assert len(result["blocks"]) == 1
    assert result["blocks"][0]["date"] == "2026-10-10"
    assert result["blocks"][0]["start"] == "20:00"
    assert result["blocks"][0]["placementSource"] == "agent"


def test_scheduler_supports_explicit_late_night_preference_and_sleep_constraint():
    result = build_plan_draft(
        {
            "goal": "Study before my 02:00 bedtime",
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [{"weekday": 0, "enabled": True, "start": "00:00", "end": "24:00"}],
            "unavailable": [
                {"weekday": 0, "start": "02:00", "end": "10:00", "category": "sleep"}
            ],
            "preferred": ["late_night"],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-09-28T23:59:00+07:00"}],
        today=date(2026, 9, 28),
    )

    assert result["blocks"][0]["start"] == "00:00"
    assert result["blocks"][0]["end"] == "01:00"


def test_scheduler_places_blocks_in_the_selected_next_calendar_week():
    result = build_plan_draft(
        {
            "goal": "Prepare next week",
            "weekStart": "2026-10-05",
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [
                {"weekday": weekday, "enabled": True, "start": "18:00", "end": "20:00"}
                for weekday in range(7)
            ],
            "unavailable": [],
            "preferred": ["evening"],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-10-06T23:59:00+07:00"}],
        today=date(2026, 10, 3),
    )

    assert result["weekStart"] == "2026-10-05"
    assert result["weekEnd"] == "2026-10-11"
    assert result["blocks"][0]["date"] == "2026-10-05"


def test_scheduler_supports_a_two_week_window_for_recovery_only():
    result = build_plan_draft(
        {
            "goal": "Recover across current and following week",
            "weekStart": "2026-09-28",
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [
                {"weekday": 0, "enabled": True, "start": "18:00", "end": "19:00"}
            ],
            "unavailable": [],
            "preferred": ["evening"],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-10-11"}],
        today=date(2026, 10, 3),
        window_days=14,
    )

    assert result["weekStart"] == "2026-09-28"
    assert result["weekEnd"] == "2026-10-11"
    assert result["blocks"][0]["date"] == "2026-10-05"


def test_scheduler_does_not_place_current_week_blocks_in_past_days():
    result = build_plan_draft(
        {
            "goal": "Finish the current week",
            "weekStart": "2026-09-28",
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [
                {"weekday": weekday, "enabled": True, "start": "18:00", "end": "20:00"}
                for weekday in range(7)
            ],
            "unavailable": [],
            "preferred": ["evening"],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-10-04T23:59:00+07:00"}],
        today=date(2026, 10, 3),
    )

    assert result["blocks"][0]["date"] == "2026-10-03"


def test_scheduler_reports_shortfall_instead_of_crossing_deadline():
    result = build_plan_draft(
        {
            "goal": "Finish assignment",
            "tasks": [{"taskId": "a1", "remainingMin": 180}],
            "availability": [{"weekday": 0, "enabled": True, "start": "18:00", "end": "19:00"}],
            "unavailable": [],
            "preferred": "evening",
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-09-28T23:59:00+07:00"}],
        today=date(2026, 9, 28),
    )
    assert result["feasibility"]["feasible"] is False
    assert result["feasibility"]["shortfalls"] == [{"taskId": "a1", "missingMin": 120}]


def test_scheduler_uses_weekly_target_for_deadline_beyond_window():
    result = build_plan_draft(
        {
            "goal": "Make progress without overloading this week",
            "tasks": [{"taskId": "a1", "remainingMin": 600}],
            "availability": [
                {"weekday": weekday, "enabled": True, "start": "18:00", "end": "20:00"}
                for weekday in range(7)
            ],
            "unavailable": [],
            "preferred": "evening",
        },
        [{"id": "a1", "title": "Large assignment", "deadline": "2026-10-10T23:59:00+07:00"}],
        today=date(2026, 9, 28),
    )
    target = result["planningTargets"][0]
    assert target["remainingMin"] == 600
    assert target["targetMin"] == 330
    assert result["feasibility"]["requiredMin"] == 330
    assert result["feasibility"]["feasible"] is True


def test_scheduler_respects_exact_date_busy_slot_only_once():
    result = build_plan_draft(
        {
            "goal": "Avoid an LMS exam",
            "tasks": [{"taskId": "a1", "remainingMin": 120}],
            "availability": [{"weekday": 0, "enabled": True, "start": "18:00", "end": "21:00"}],
            "unavailable": [{"weekday": 0, "date": "2026-09-28", "start": "18:00", "end": "19:00"}],
            "preferred": "evening",
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-10-05T23:59:00+07:00"}],
        today=date(2026, 9, 28),
    )
    assert result["blocks"][0]["start"] == "19:00"


def test_scheduler_turns_agent_milestones_into_canonical_blocks():
    result = build_plan_draft(
        {
            "goal": "Complete the report",
            "tasks": [{"taskId": "a1", "remainingMin": 120}],
            "availability": [{"weekday": 0, "enabled": True, "start": "18:00", "end": "21:00"}],
            "unavailable": [],
            "preferred": "evening",
        },
        [{"id": "a1", "title": "Report", "deadline": "2026-09-28T23:59:00+07:00"}],
        proposed_milestones=[
            {"milestone_id": "M1", "title": "Outline", "estimated_minutes": 45},
            {"milestone_id": "M2", "title": "Draft", "estimated_minutes": 75, "depends_on": ["M1"]},
        ],
        today=date(2026, 9, 28),
    )

    assert [item["title"] for item in result["milestones"]] == ["Outline", "Draft"]
    assert {block["milestoneTitle"] for block in result["blocks"]} == {"Outline", "Draft"}
    assert sum(item["targetMin"] for item in result["milestones"]) == 120


def test_scheduler_reports_near_deadlines_omitted_from_the_draft():
    result = build_plan_draft(
        {
            "goal": "Plan selected work",
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [{"weekday": 0, "enabled": True, "start": "18:00", "end": "20:00"}],
            "unavailable": [],
            "preferred": "evening",
        },
        [
            {"id": "a1", "title": "Selected", "deadline": "2026-09-28T23:59:00+07:00"},
            {"id": "a2", "title": "Not selected", "deadline": "2026-10-02T23:59:00+07:00"},
        ],
        today=date(2026, 9, 28),
    )

    assert result["feasibility"]["feasible"] is True
    assert result["feasibility"]["uncoveredTasks"] == [
        {"taskId": "a2", "title": "Not selected", "deadline": "2026-10-02"}
    ]


def test_scheduler_uses_priority_when_deadlines_are_equal():
    result = build_plan_draft(
        {
            "goal": "Protect the highest-risk work",
            "tasks": [
                {"taskId": "low", "remainingMin": 60},
                {"taskId": "high", "remainingMin": 60},
            ],
            "availability": [{"weekday": 0, "enabled": True, "start": "18:00", "end": "20:30"}],
            "unavailable": [],
            "preferred": "evening",
        },
        [
            {"id": "low", "title": "Low priority", "priority": "low", "deadline": "2026-09-28"},
            {"id": "high", "title": "High priority", "priority": "high", "deadline": "2026-09-28"},
        ],
        today=date(2026, 9, 28),
    )

    assert result["blocks"][0]["taskId"] == "high"
    assert [item["taskId"] for item in result["priorityOrder"]] == ["high", "low"]


def test_scheduler_preserves_valid_pinned_block_and_schedules_remainder():
    result = build_plan_draft(
        {
            "goal": "Keep my chosen study time",
            "weekStart": "2026-09-28",
            "tasks": [{"taskId": "a1", "remainingMin": 120}],
            "availability": [{"weekday": 0, "enabled": True, "start": "18:00", "end": "21:00"}],
            "unavailable": [],
            "preferred": "evening",
            "pinnedBlocks": [
                {
                    "id": "student-choice",
                    "taskId": "a1",
                    "date": "2026-09-28",
                    "start": "18:00",
                    "end": "19:00",
                }
            ],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-09-28T23:59:00+07:00"}],
        today=date(2026, 9, 28),
    )

    assert result["feasibility"]["feasible"] is True
    assert result["blocks"][0]["id"] == "student-choice"
    assert result["blocks"][0]["start"] == "18:00"
    assert result["blocks"][1]["start"] == "19:10"
    assert sum(
        int(block["end"].split(":")[0]) * 60
        + int(block["end"].split(":")[1])
        - int(block["start"].split(":")[0]) * 60
        - int(block["start"].split(":")[1])
        for block in result["blocks"]
    ) == 120


def test_scheduler_starts_after_current_time_with_preparation_buffer():
    result = build_plan_draft(
        {
            "goal": "Continue the current week",
            "weekStart": "2026-09-28",
            "horizonEnd": "2026-10-11",
            "tasks": [{"taskId": "a1", "remainingMin": 60, "personalPriority": 3}],
            "availability": [
                {"weekday": weekday, "enabled": True, "start": "08:00", "end": "20:00"}
                for weekday in range(7)
            ],
            "unavailable": [],
            "preferred": ["afternoon", "evening"],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-10-04T23:59:00+07:00"}],
        now=datetime(2026, 10, 2, 16, 7, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
    )

    assert result["scheduleStart"] == "2026-10-02"
    assert result["blocks"][0]["date"] == "2026-10-02"
    assert result["blocks"][0]["start"] >= "16:30"
    assert result["blocks"][0]["status"] == "confirmed"


def test_replanning_keeps_completed_past_blocks_as_read_only_history():
    result = build_plan_draft(
        {
            "goal": "Replan without rewriting history",
            "weekStart": "2026-09-28",
            "horizonEnd": "2026-10-11",
            "tasks": [{"taskId": "a1", "remainingMin": 60}],
            "availability": [
                {"weekday": weekday, "enabled": True, "start": "08:00", "end": "20:00"}
                for weekday in range(7)
            ],
            "unavailable": [],
            "preferred": "afternoon",
            "pinnedBlocks": [
                {"id": "past", "taskId": "a1", "date": "2026-09-30", "start": "09:00", "end": "10:00", "status": "history"}
            ],
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-10-04"}],
        now=datetime(2026, 10, 2, 16, 7, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
    )

    history = next(block for block in result["blocks"] if block["id"] == "past")
    future = [block for block in result["blocks"] if block["id"] != "past"]
    assert history["status"] == "history"
    assert all(block["date"] >= "2026-10-02" for block in future)


def test_scheduler_spreads_new_work_into_future_days_when_today_already_has_history():
    result = build_plan_draft(
        {
            "goal": "Plan the next seven days without cramming today",
            "weekStart": "2026-10-18",
            "horizonEnd": "2026-10-25",
            "tasks": [{"taskId": "future", "remainingMin": 60}],
            "availability": [
                {"weekday": weekday, "enabled": True, "start": "18:00", "end": "22:00"}
                for weekday in range(7)
            ],
            "unavailable": [],
            "preferred": ["evening"],
            "pinnedBlocks": [
                {
                    "id": "completed-today",
                    "taskId": "done",
                    "date": "2026-10-18",
                    "start": "18:00",
                    "end": "20:00",
                    "status": "history",
                }
            ],
        },
        [{"id": "future", "title": "Future assignment", "deadline": "2026-11-01"}],
        today=date(2026, 10, 18),
    )

    planned = [block for block in result["blocks"] if block["taskId"] == "future"]
    assert planned
    assert planned[0]["date"] == "2026-10-19"


def test_reflection_follow_up_is_scheduled_after_completed_block_not_on_top_of_it():
    result = build_plan_draft(
        {
            "weekStart": "2026-10-12",
            "horizonEnd": "2026-10-18",
            "tasks": [{"taskId": "cs101", "remainingMin": 0}],
            "availability": [
                {"weekday": weekday, "enabled": True, "start": "08:00", "end": "22:00"}
                for weekday in range(7)
            ],
            "unavailable": [],
            "preferred": ["afternoon", "evening"],
            "pinnedBlocks": [{
                "id": "completed-cs101", "taskId": "cs101", "date": "2026-10-16",
                "start": "18:00", "end": "19:10", "status": "history",
            }],
        },
        [{"id": "cs101", "title": "Ôn lại Python", "deadline": "2026-10-18T23:59:00+07:00"}],
        learner_profile={"activity_reflections": [{
            "activity": {"task_id": "cs101"},
            "planning_signal": {"task_id": "cs101", "cause": "knowledge_gap", "follow_up_minutes": 30},
        }]},
        now=datetime(2026, 10, 16, 17, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
    )

    follow_up = next(block for block in result["blocks"] if block["id"] != "completed-cs101")
    assert follow_up["date"] > "2026-10-16" or follow_up["start"] >= "19:20"
    assert not (follow_up["date"] == "2026-10-16" and follow_up["start"] < "19:10" and follow_up["end"] > "18:00")


def test_reanalysis_does_not_schedule_completed_do_parts_again():
    proposed = [
        {
            "milestone_id": f"M{index}", "task_id": "db:a3", "title": f"Làm phần {index}",
            "estimated_minutes": 60, "depends_on": [] if index == 1 else ["M1"],
            "assignment_part_ids": [f"S1-P{index}"], "source_refs": [f"file:7#part=S1-P{index}"],
        }
        for index in (1, 2)
    ]
    learner_profile = {
        "last_confirmed_plan": {
            "planningTargets": [{"taskId": "db:a3", "targetMin": 120, "remainingMin": 120}],
            "milestones": [
                {"taskId": "db:a3", "milestoneId": "M1", "assignmentPartIds": ["S1-P1"]},
                {"taskId": "db:a3", "milestoneId": "M2", "assignmentPartIds": ["S1-P2"]},
            ],
            "blocks": [
                {"id": "B1", "taskId": "db:a3", "milestoneId": "M1", "workMinutes": 60},
                {"id": "B2", "taskId": "db:a3", "milestoneId": "M2", "workMinutes": 60},
            ],
        },
        "do_history": [{"block_id": "B1", "task_id": "db:a3", "work_result": "planned_part_done"}],
    }
    result = build_plan_draft(
        {
            "tasks": [{"taskId": "db:a3", "remainingMin": 120}],
            "availability": [{"weekday": 0, "enabled": True, "start": "18:00", "end": "21:00"}],
            "unavailable": [],
            "studyPreferences": {"sessionMinutes": 90, "breakMinutes": 10, "checkpointMinutes": 0},
        },
        [{"id": "db:a3", "title": "Bài SQL hai phần", "deadline": "2026-09-28T23:59:00+07:00"}],
        learner_profile=learner_profile,
        proposed_milestones=proposed,
        today=date(2026, 9, 28),
    )
    assert result["planningTargets"][0]["remainingMin"] == 60
    assert [item["milestoneId"] for item in result["milestones"]] == ["M2"]
    assert result["milestones"][0]["dependsOn"] == []
    assert {item["milestoneId"] for item in result["blocks"]} == {"M2"}


def test_scheduler_marks_next_week_blocks_as_tentative():
    result = build_plan_draft(
        {
            "goal": "Use the two-week forecast",
            "weekStart": "2026-09-28",
            "horizonEnd": "2026-10-11",
            "tasks": [{"taskId": "a1", "remainingMin": 180}],
            "availability": [
                {"weekday": 0, "enabled": True, "start": "18:00", "end": "20:00"},
                {"weekday": 6, "enabled": True, "start": "18:00", "end": "19:00"},
            ],
            "unavailable": [],
            "preferred": "evening",
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-10-11"}],
        today=date(2026, 10, 4),
    )

    assert result["weekEnd"] == "2026-10-04"
    assert result["horizonEnd"] == "2026-10-11"
    assert {block["status"] for block in result["blocks"]} == {"confirmed", "tentative"}


def test_scheduler_ignores_removed_personal_priority_and_uses_academic_weight():
    result = build_plan_draft(
        {
            "goal": "Prioritize from LMS evidence, not the removed control",
            "tasks": [
                {"taskId": "academic", "remainingMin": 60, "personalPriority": 1},
                {"taskId": "personal", "remainingMin": 60, "personalPriority": 4},
            ],
            "availability": [{"weekday": 0, "enabled": True, "start": "18:00", "end": "21:00"}],
            "unavailable": [],
            "preferred": "evening",
        },
        [
            {"id": "academic", "title": "Heavy group", "priority": "medium", "deadline": "2026-09-28", "assignment_group": {"weight": 60}},
            {"id": "personal", "title": "Learner focus", "priority": "medium", "deadline": "2026-09-28", "assignment_group": {"weight": 20}},
        ],
        today=date(2026, 9, 28),
    )

    assert [item["taskId"] for item in result["priorityOrder"]] == ["academic", "personal"]
    assert all(item["personalPriority"] == 2 for item in result["priorityOrder"])
    assert result["priorityOrder"][0]["assignmentGroupWeight"] == 60


def test_scheduler_preserves_confirmed_goals_and_grounding_refs():
    result = build_plan_draft(
        {
            "goal": "Finish the project",
            "weeklyGoals": [{"id": "goal-1", "title": "Finish CS101", "taskIds": ["a1"], "confirmed": True}],
            "tasks": [{"taskId": "a1", "remainingMin": 60, "weeklyGoalId": "goal-1"}],
            "availability": [{"weekday": 0, "enabled": True, "start": "18:00", "end": "20:00"}],
            "unavailable": [],
            "preferred": "evening",
        },
        [{"id": "a1", "title": "Mini project", "deadline": "2026-09-28", "rubric": {"id": 7}}],
        today=date(2026, 9, 28),
    )

    assert result["weeklyGoals"][0]["confirmed"] is True
    assert result["milestones"][0]["weeklyGoalId"] == "goal-1"
    assert result["milestones"][0]["sourceRefs"] == ["assignment:a1", "rubric:7"]


def test_plan_draft_exposes_rubric_kc_uncertainty_and_quality_evidence():
    assignment = {
        "id": "a1",
        "title": "Equivalence relation report",
        "deadline": "2026-09-28",
        "knowledge_components": [
            {"id": "transitive", "name": "Transitive relation"},
        ],
        "rubric": {
            "id": 9,
            "criteria": [
                {"id": "R1", "description": "Correct transitivity proof", "points": 10},
            ],
        },
    }
    result = build_plan_draft(
        {
            "tasks": [{"taskId": "a1", "remainingMin": 90}],
            "availability": [{"weekday": 0, "enabled": True, "start": "17:00", "end": "22:00"}],
            "unavailable": [],
            "preferred": "evening",
        },
        [assignment],
        proposed_milestones=[
            {
                "milestone_id": "M1",
                "task_id": "a1",
                "title": "Prove transitivity",
                "deliverable": "A justified proof",
                "estimated_minutes": 90,
                "knowledge_components": ["transitive"],
                "rubric_criteria": ["R1"],
                "source_refs": ["assignment:a1", "rubric:9#criterion=R1"],
            }
        ],
        learner_profile={
            "do_history": [
                {"task_id": "a1", "planned_minutes": 60, "actual_minutes": 75}
            ]
        },
        mastery_profile={"transitive": {"level": "recognition", "source_evidence_ids": ["LE-transitivity"]}},
        today=date(2026, 9, 28),
    )

    assert result["rubricCoverage"][0]["missingCriterionIds"] == []
    assert result["rubricCoverage"][0]["weakKnowledgeComponents"][0]["componentId"] == "transitive"
    assert result["milestones"][0]["decompositionSource"] == "mastery_rule"
    assert result["planningTargets"][0]["adaptiveReviewMin"] == 30
    assert result["durationAdjustments"][0]["baselineTargetMin"] == 90
    assert result["durationAdjustments"][0]["reviewAddedMin"] == 30
    assert "LE-transitivity" in result["durationAdjustments"][0]["sourceRefs"]
    assert result["planningTargets"][0]["targetMin"] == sum(
        milestone["estimate"]["p50_minutes"] for milestone in result["milestones"]
    )
    assert result["milestones"][0]["estimate"]["p80_minutes"] >= result["milestones"][0]["estimate"]["p50_minutes"]
    assert result["feasibility"]["robustRequiredMin"] >= result["feasibility"]["requiredMin"]
    assert result["qualityEvaluation"]["metrics"]["rubricCoverage"] == 1.0


def test_mastery_risk_breaks_ties_without_overriding_an_earlier_deadline():
    result = build_plan_draft(
        {
            "tasks": [
                {"taskId": "early", "remainingMin": 30},
                {"taskId": "weak", "remainingMin": 30},
                {"taskId": "strong", "remainingMin": 30},
            ],
            "availability": [
                {"weekday": day, "enabled": True, "start": "18:00", "end": "22:00"}
                for day in range(2)
            ],
            "unavailable": [],
        },
        [
            {"id": "early", "title": "Earlier", "deadline": "2026-09-28", "knowledge_components": ["known"]},
            {"id": "weak", "title": "Weak KC", "deadline": "2026-09-29", "knowledge_components": ["weak-kc"]},
            {"id": "strong", "title": "Strong KC", "deadline": "2026-09-29", "knowledge_components": ["strong-kc"]},
        ],
        mastery_profile={"known": {"level": "transfer", "source_evidence_ids": ["LE-known"]},
                         "weak-kc": {"level": "recognition", "source_evidence_ids": ["LE-weak"]},
                         "strong-kc": {"level": "transfer", "source_evidence_ids": ["LE-strong"]}},
        today=date(2026, 9, 28),
    )

    assert [item["taskId"] for item in result["priorityOrder"]] == ["early", "weak", "strong"]


def test_multi_course_mastery_is_scoped_before_it_breaks_a_deadline_tie():
    result = build_plan_draft(
        {
            "tasks": [
                {"taskId": "1:a", "remainingMin": 30},
                {"taskId": "2:b", "remainingMin": 30},
            ],
            "availability": [
                {"weekday": 0, "enabled": True, "start": "18:00", "end": "22:00"}
            ],
            "unavailable": [],
        },
        [
            {"id": "1:a", "course_id": 1, "deadline": "2026-09-28", "knowledge_components": ["shared-name"]},
            {"id": "2:b", "course_id": 2, "deadline": "2026-09-28", "knowledge_components": ["shared-name"]},
        ],
        mastery_profile={
            "__by_course__": {
                "1": {"shared-name": {"level": "transfer", "source_evidence_ids": ["course-1"]}},
                "2": {"shared-name": {"level": "recognition", "source_evidence_ids": ["course-2"]}},
            }
        },
        today=date(2026, 9, 28),
    )

    assert [item["taskId"] for item in result["priorityOrder"]] == ["2:b", "1:a"]
