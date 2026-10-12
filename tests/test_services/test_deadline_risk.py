from datetime import date

from src.services.deadline_risk import cumulative_deadline_risks


def test_deadline_risk_uses_cumulative_demand_for_competing_tasks():
    tasks = [
        {"task_id": "a", "deadline": date(2026, 10, 12), "deadline_minute": 720},
        {"task_id": "b", "deadline": date(2026, 10, 12), "deadline_minute": 720},
        {"task_id": "c", "deadline": date(2026, 10, 13), "deadline_minute": 1440},
    ]
    risks = cumulative_deadline_risks(
        tasks,
        {
            date(2026, 10, 12): [(480, 720)],
            date(2026, 10, 13): [(480, 720)],
        },
        p50_required_by_task={"a": 120, "b": 120, "c": 120},
        p80_required_by_task={"a": 150, "b": 150, "c": 180},
    )

    assert risks[0] == {
        "deadline": "2026-10-12",
        "deadlineMinute": 720,
        "taskIds": ["a", "b"],
        "availableMin": 240,
        "requiredP50Min": 240,
        "requiredP80Min": 300,
        "slackP50Min": 0,
        "slackP80Min": -60,
        "risk": "p80_shortage",
    }
    assert risks[1]["taskIds"] == ["a", "b", "c"]
    assert risks[1]["risk"] == "safe"


def test_pinned_work_counts_as_committed_capacity_before_cutoff():
    risks = cumulative_deadline_risks(
        [{"task_id": "a", "deadline": date(2026, 10, 12), "deadline_minute": 600}],
        {date(2026, 10, 12): [(540, 600)]},
        p50_required_by_task={"a": 120},
        p80_required_by_task={"a": 120},
        pinned_capacity=[
            {"task_id": "a", "date": date(2026, 10, 12), "start_minute": 480, "end_minute": 540}
        ],
    )

    assert risks[0]["availableMin"] == 120
    assert risks[0]["slackP50Min"] == 0


def test_pinned_later_task_does_not_fake_capacity_for_earlier_deadline():
    risks = cumulative_deadline_risks(
        [
            {"task_id": "early", "deadline": date(2026, 10, 12), "deadline_minute": 600},
            {"task_id": "later", "deadline": date(2026, 10, 13), "deadline_minute": 600},
        ],
        {date(2026, 10, 12): [(540, 600)]},
        p50_required_by_task={"early": 120, "later": 60},
        p80_required_by_task={"early": 120, "later": 60},
        pinned_capacity=[
            {"task_id": "later", "date": date(2026, 10, 12), "start_minute": 480, "end_minute": 540}
        ],
    )

    assert risks[0]["availableMin"] == 60
    assert risks[0]["slackP50Min"] == -60
