"""Browser and push reminders must hand off to the same confirmed Plan flow."""
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

from src.services.reminder_schedule import LOCAL, candidates, replan_href


def test_plan_handoff_url_encodes_context_without_exposing_another_workflow():
    url = replan_href("lms", impactId="deadline:1:10?next=/recover", taskId="1:10", courseId="1")
    parts = urlsplit(url)
    assert parts.path == "/plan"
    assert parse_qs(parts.query) == {"reanalyze": ["lms"], "impactId": ["deadline:1:10?next=/recover"],
                                    "taskId": ["1:10"], "courseId": ["1"]}


def test_push_jobs_use_plan_for_lms_change_missed_block_and_urgent_deadline():
    now = datetime(2026, 10, 10, 10, tzinfo=LOCAL)
    state = {"plan": {"blocks": [{"id": "b1", "taskId": "1:10", "date": "2026-10-10", "start": "08:00", "end": "09:00"}]},
        "lmsBaseline": {"tasks": [{"id": "1:10", "courseId": "1", "title": "Task", "status": "todo",
            "dueAt": "2026-10-10T12:00:00+07:00", "estimateMin": 60, "loggedMin": 0}]},
        "planImpacts": [{"id": "new-task", "kind": "assignment_added", "taskId": "1:10", "courseId": "1",
            "detectedAt": "2026-10-10T09:59:00+07:00"}]}
    jobs = {job["kind"]: job for job in candidates(state, now)}
    for kind, trigger in [("deadline_2h", "deadline"), ("missed_block", "progress"), ("lms_change", "lms")]:
        parts = urlsplit(jobs[kind]["href"])
        assert parts.path == "/plan"
        assert parse_qs(parts.query)["reanalyze"] == [trigger]
        assert parse_qs(parts.query)["taskId"] == ["1:10"]
    assert parse_qs(urlsplit(jobs["lms_change"]["href"]).query)["impactId"] == ["new-task"]
