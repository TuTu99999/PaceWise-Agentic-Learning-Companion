from datetime import UTC, datetime

from app.deadline_snapshot import course_due_overrides
from app.models import AssignmentOverride, CourseSection, SectionMembership
from test_pacewise_contracts import env  # noqa: F401


def test_batched_due_overrides_match_student_precedence_and_stay_service_only(env):
    client, factory, _, student, headers = env
    with factory() as db:
        db.add(CourseSection(id=4, course_id=1, name="A"))
        db.flush()
        db.add(SectionMembership(section_id=4, user_id=2))
        db.add_all([
            AssignmentOverride(assignment_id=1, title="section", target_type="section", target_id=4,
                               due_at=datetime(2026, 10, 10, 12, tzinfo=UTC)),
            AssignmentOverride(assignment_id=1, title="individual", target_type="student", target_id=2,
                               due_at=datetime(2026, 10, 9, 12, tzinfo=UTC)),
        ])
        db.commit()
        assert course_due_overrides(db, 1)[1]["2"] == "2026-10-09T12:00:00+00:00"
    all_assignments = client.get("/api/pacewise/v1/courses/1/assignments", headers=headers).json()
    assert all_assignments[0]["student_due_dates"]["2"] == "2026-10-09T12:00:00+00:00"
    student_view = client.get("/api/pacewise/v1/courses/1/assignments?user_id=2", headers=headers).json()
    assert "student_due_dates" not in student_view[0]
"""Deadline snapshot contract tests."""

# Imported fixtures are intentionally re-exported for pytest discovery.
# ruff: noqa: F811

