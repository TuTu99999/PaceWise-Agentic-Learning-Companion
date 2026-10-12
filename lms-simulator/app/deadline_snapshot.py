"""Batch effective due dates for the privileged aggregate service, without N+1."""

from collections import defaultdict
from datetime import UTC

from sqlalchemy import select

from app.models import Assignment, AssignmentOverride, GroupMembership, SectionMembership


def course_due_overrides(db, course_id):
    overrides = db.scalars(
        select(AssignmentOverride)
        .join(Assignment, Assignment.id == AssignmentOverride.assignment_id)
        .where(Assignment.course_id == course_id, AssignmentOverride.due_at.is_not(None))
    ).all()
    if not overrides:
        return {}
    targets = {"student": defaultdict(set), "group": defaultdict(set), "section": defaultdict(set)}
    for item in overrides:
        if item.target_type == "student":
            targets["student"][item.target_id].add(item.target_id)
    for kind, model, column in (
        ("group", GroupMembership, GroupMembership.group_id),
        ("section", SectionMembership, SectionMembership.section_id),
    ):
        ids = {item.target_id for item in overrides if item.target_type == kind}
        for target, user in db.execute(select(column, model.user_id).where(column.in_(ids))).all():
            targets[kind][target].add(user)
    grouped, individual = {}, {}
    for item in overrides:
        due = item.due_at.replace(tzinfo=UTC) if item.due_at.tzinfo is None else item.due_at.astimezone(UTC)
        bucket = individual if item.target_type == "student" else grouped
        for user in targets.get(item.target_type, {}).get(item.target_id, ()):
            key = (item.assignment_id, str(user))
            bucket[key] = max(due, bucket.get(key, due))
    result = defaultdict(dict)
    for (assignment_id, user), due in {**grouped, **individual}.items():
        result[assignment_id][user] = due.isoformat()
    return dict(result)
