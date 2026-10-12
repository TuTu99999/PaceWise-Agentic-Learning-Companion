from datetime import UTC, datetime

from src.api.lms_integration import _assignment_risk_summary
from src.services.instructor_metrics import completion_metrics, topic_metrics


def test_completion_excludes_drafts_exemptions_future_extensions_and_duplicates():
    assignments = [
        {"id": 1, "due_at": "2026-10-09T10:00:00Z", "student_due_dates": {"3": "2026-10-15T10:00:00Z"}},
        {"id": 2, "due_at": "2026-10-01T10:00:00Z", "published": False},
    ]
    assignments.append(assignments[0])
    submissions = [
        {
            "assignment_id": 1,
            "user_id": 1,
            "workflow_state": "graded",
            "late": True,
            "first_submitted_at": "2026-10-09T09:00:00Z",
            "submitted_at": "2026-10-09T11:00:00Z",
        },
        {"assignment_id": 1, "user_id": 2, "workflow_state": "excused"},
        {"assignment_id": 1, "user_id": 4, "workflow_state": "submitted", "late": False},
        {"assignment_id": 1, "user_id": 5, "workflow_state": "submitted"},
    ]
    result = completion_metrics(assignments, submissions, {1, 2, 3, 4, 5}, as_of=datetime(2026, 10, 10, tzinfo=UTC))
    assert result["count"] == 2 and result["total"] == 2 and result["unknown"] == 1
    assert result["rate"] == 1 and result["weekly"][0]["total"] == 2


def test_completion_uses_vietnam_due_week_and_handles_naive_missing_dates():
    result = completion_metrics(
        [
            {"id": 1, "due_at": "2026-10-04T18:30:00Z"},
            {"id": 2, "due_at": None},
            {"id": 3, "due_at": "2026-10-05T00:00:00"},
        ],
        [],
        {1},
        as_of=datetime(2026, 10, 6, tzinfo=UTC),
    )
    assert result["total"] == 2
    assert [item["week"] for item in result["weekly"]] == ["05/10"]
    assert completion_metrics([], [], {1}, as_of=datetime.now(UTC))["weekly"] == []


def test_topics_use_latest_evidence_and_observed_cohort_not_whole_class():
    evidence = [
        {
            "user_id": student,
            "score": 4 if student == 1 else 9,
            "max_score": 10,
            "competency_key": "kc",
            "observed_at": "2026-10-08T10:00:00Z",
        }
        for student in range(1, 6)
    ]
    assert topic_metrics(evidence, set(range(1, 20)), str, minimum_group_size=5) == [
        {"topic": "kc", "needsSupport": 1, "n": 5}
    ]
    evidence.append({**evidence[0], "score": 9, "observed_at": "2026-10-09T10:00:00Z"})
    assert topic_metrics(evidence, set(range(1, 20)), str, minimum_group_size=5) == []


def test_topics_suppress_small_observed_cohort_invalid_and_unenrolled_evidence():
    evidence = [
        {"user_id": 1, "score": 2, "max_score": 10, "competency_key": "kc"},
        {"user_id": 2, "score": None, "max_score": 10, "competency_key": "kc"},
        {"user_id": 3, "score": "NaN", "max_score": 10, "competency_key": "kc"},
        {"user_id": 99, "score": 1, "max_score": 10, "competency_key": "kc"},
    ]
    assert topic_metrics(evidence, {1, 2, 3, 4, 5}, str, minimum_group_size=5) == []


def test_risk_respects_personal_extensions_and_never_estimates_work_from_points():
    rows, students = _assignment_risk_summary(
        [
            {
                "id": 1,
                "due_at": "2026-10-10T10:00:00Z",
                "points_possible": 100,
                "student_due_dates": {"2": "2026-10-20T10:00:00Z"},
            },
            {"id": 2, "due_at": "2026-10-10T10:00:00Z", "published": False},
        ],
        [{"assignment_id": 1, "user_id": 3, "workflow_state": "excused"}],
        {1, 2, 3},
        as_of=datetime(2026, 10, 9, tzinfo=UTC),
    )
    assert students == {1} and len(rows) == 1 and rows[0]["atRiskCount"] == 1
    assert "missingMinutes" not in rows[0]
