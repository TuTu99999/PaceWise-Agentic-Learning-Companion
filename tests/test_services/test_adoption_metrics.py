from datetime import UTC, datetime

from src.services.adoption_metrics import adoption_comparison


def data():
    students = set(range(1, 6))
    assignments = [{"id": 1, "due_at": "2026-10-01T12:00:00Z"}, {"id": 2, "due_at": "2026-10-08T12:00:00Z"}]
    adoption = {user: datetime(2026, 10, 5, tzinfo=UTC) for user in students}
    submissions = [
        {"user_id": user, "assignment_id": task, "submitted_at": f"2026-10-{day}T11:00:00Z"}
        for task, day in [(1, "01"), (2, "08")]
        for user in students
    ]
    return assignments, submissions, students, adoption


def compare(assignments, submissions, students, adoption):
    return adoption_comparison(assignments, submissions, students, adoption, as_of=datetime(2026, 10, 20, tzinfo=UTC))


def test_paired_on_time_kpi_deduplicates_and_checks_exact_deadline():
    assignments, submissions, students, adoption = data()
    submissions[0]["submitted_at"] = "2026-10-01T12:01:00Z"
    submissions.append(dict(submissions[0]))
    result = compare(assignments, submissions, students, adoption)
    assert result["status"] == "available"
    assert result["before"] == {"count": 4, "total": 5, "rate": 0.8}
    assert result["after"]["rate"] == 1
    assert result["deltaPercentagePoints"] == 20 and result["causalClaim"] is False
    assert "user_id" not in str(result)


def test_student_override_and_first_submission_are_authoritative():
    assignments, submissions, students, adoption = data()
    assignments[1]["student_due_dates"] = {"1": "2026-10-08T11:30:00Z"}
    submissions[5]["submitted_at"] = "2026-10-08T13:00:00Z"
    submissions[5]["first_submitted_at"] = "2026-10-08T11:20:00Z"
    assert compare(assignments, submissions, students, adoption)["after"]["rate"] == 1
    submissions[5].pop("first_submitted_at")
    assert compare(assignments, submissions, students, adoption)["after"]["rate"] == 0.8


def test_small_cohort_unknown_timestamps_excused_and_no_usage_do_not_create_fake_improvement():
    assignments, submissions, students, adoption = data()
    assert compare(assignments, submissions, students, {})["status"] == "insufficient_data"
    submissions[0]["submitted_at"] = None
    result = compare(assignments, submissions, students, adoption)
    assert result["status"] == "insufficient_data" and result["before"] is None
    assert result["unknownTimestampCount"] == 1
    submissions[0]["workflow_state"] = "excused"
    assert compare(assignments, submissions, students, adoption)["status"] == "insufficient_data"


def test_incomplete_after_window_and_old_assignments_do_not_create_comparison():
    assignments, submissions, students, adoption = data()
    result = adoption_comparison(assignments, submissions, students, adoption, as_of=datetime(2026, 10, 9, tzinfo=UTC))
    assert result["status"] == "insufficient_data"
    assignments[0]["due_at"] = "2026-08-01T12:00:00Z"
    assert compare(assignments, submissions, students, adoption)["status"] == "insufficient_data"


def test_equal_windows_and_duplicate_assignments():
    assignments, submissions, students, adoption = data()
    assignments.append(dict(assignments[0]))
    result = compare(assignments, submissions, students, adoption)
    assert result["before"]["total"] == 5
    assert result["method"] == "paired_observational_first_plan_confirmation_v2"
    assert result["windowDays"] == 14 and result["adoptionEvent"] == "PLAN_CONFIRMED"
