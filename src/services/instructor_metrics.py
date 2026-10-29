"""Deterministic, anonymous LMS projections. Scores are not knowledge mastery."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from src.services.adoption_metrics import instant

ACCEPTED_STATES = {"submitted", "graded", "pending_review"}
COURSE_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def completion_metrics(assignments, submissions, student_ids, *, as_of, limit=8):
    """Count unique, published student-task obligations at their effective due time.

    Exemptions and future extensions are not failures. An authoritative first
    submission timestamp wins over a latest-attempt `late` flag. If timestamps
    are unavailable, use only an explicit LMS boolean, not an invented success.
    """
    by_key = defaultdict(list)
    for item in submissions:
        by_key[(int(item.get("assignment_id") or 0), int(item.get("user_id") or 0))].append(item)
    weeks = defaultdict(lambda: [0, 0])
    count = total = unknown = 0
    unique_assignments = {int(item["id"]): item for item in assignments if item.get("published", True)}
    for assignment_id, assignment in unique_assignments.items():
        for student_id in student_ids:
            due = instant((assignment.get("student_due_dates") or {}).get(str(student_id), assignment.get("due_at")))
            if due is None or due > instant(as_of):
                continue
            attempts = by_key[(assignment_id, student_id)]
            if any(item.get("excused") or item.get("workflow_state") == "excused" for item in attempts):
                continue
            accepted = [item for item in attempts if item.get("workflow_state", "submitted") in ACCEPTED_STATES]
            times = [
                stamp
                for item in accepted
                if (stamp := instant(item.get("first_submitted_at") or item.get("submitted_at"))) is not None
            ]
            if accepted and not times and not any(isinstance(item.get("late"), bool) for item in accepted):
                unknown += 1
                continue  # Missing timing is unknown, not a fabricated failure.
            on_time = min(times) <= due if times else any(item.get("late") is False for item in accepted)
            year, week, _ = due.astimezone(COURSE_TIMEZONE).isocalendar()
            weeks[(year, week)][0] += int(on_time)
            weeks[(year, week)][1] += 1
            count += int(on_time)
            total += 1
    weekly = [
        {
            "week": datetime.fromisocalendar(year, week, 1).strftime("%d/%m"),
            "weekStart": datetime.fromisocalendar(year, week, 1).date().isoformat(),
            "weekEnd": datetime.fromisocalendar(year, week, 7).date().isoformat(),
            "rate": passed / opportunities,
            "count": passed,
            "total": opportunities,
        }
        for (year, week), (passed, opportunities) in sorted(weeks.items())[-limit:]
    ]
    return {"count": count, "total": total, "unknown": unknown, "rate": count / total if total else 0, "weekly": weekly}


def course_weekly_timeline(assignments, submissions, student_ids, schedule_items, *, as_of):
    """Return every calendar week in one course's real teaching/task range.

    Completion is exposed only after an obligation reaches its effective due
    time. Empty and future weeks stay visible but never become fabricated 0%.
    """
    current = instant(as_of) or datetime.now(UTC)
    completed = completion_metrics(
        assignments,
        submissions,
        student_ids,
        as_of=current,
        limit=10_000,
    )
    completed_by_week = {item["weekStart"]: item for item in completed["weekly"]}
    excused = {
        (int(item.get("assignment_id") or 0), int(item.get("user_id") or 0))
        for item in submissions
        if item.get("excused") or item.get("workflow_state") == "excused"
    }
    anchors = set()
    scheduled_totals = defaultdict(int)
    task_ids = defaultdict(set)
    lesson_counts = defaultdict(int)

    unique_assignments = {
        int(item["id"]): item
        for item in assignments
        if item.get("published", True)
    }
    for assignment_id, assignment in unique_assignments.items():
        default_due = instant(assignment.get("due_at"))
        if default_due is not None:
            default_date = default_due.astimezone(COURSE_TIMEZONE).date()
            default_week = default_date - timedelta(days=default_date.weekday())
            anchors.add(default_week)
            task_ids[default_week.isoformat()].add(assignment_id)
        for student_id in student_ids:
            if (assignment_id, student_id) in excused:
                continue
            due = instant(
                (assignment.get("student_due_dates") or {}).get(
                    str(student_id), assignment.get("due_at")
                )
            )
            if due is None:
                continue
            local_date = due.astimezone(COURSE_TIMEZONE).date()
            week_start = local_date - timedelta(days=local_date.weekday())
            key = week_start.isoformat()
            anchors.add(week_start)
            scheduled_totals[key] += 1
            task_ids[key].add(assignment_id)

    for item in schedule_items:
        starts_at = instant(item.get("starts_at"))
        if starts_at is None:
            continue
        local_date = starts_at.astimezone(COURSE_TIMEZONE).date()
        week_start = local_date - timedelta(days=local_date.weekday())
        anchors.add(week_start)
        lesson_counts[week_start.isoformat()] += 1

    if not anchors:
        return []

    current_date = current.astimezone(COURSE_TIMEZONE).date()
    current_week = current_date - timedelta(days=current_date.weekday())
    first_week, last_week = min(anchors), max(anchors)
    rows = []
    cursor = first_week
    week_number = 1
    while cursor <= last_week:
        key = cursor.isoformat()
        observed = completed_by_week.get(key)
        rows.append(
            {
                "week": cursor.strftime("%d/%m"),
                "weekNumber": week_number,
                "weekStart": key,
                "weekEnd": (cursor + timedelta(days=6)).isoformat(),
                "rate": observed["rate"] if observed else None,
                "count": int(observed["count"]) if observed else 0,
                "total": int(observed["total"]) if observed else 0,
                "scheduledTotal": scheduled_totals[key],
                "taskCount": len(task_ids[key]),
                "lessonCount": lesson_counts[key],
                "status": (
                    "current"
                    if cursor == current_week
                    else "past" if cursor < current_week else "upcoming"
                ),
            }
        )
        cursor += timedelta(days=7)
        week_number += 1
    return rows


def latest_scored_evidence(evidence, student_ids):
    """Use the latest valid observation per student/KC, not historical failures forever."""
    latest = {}
    for item in evidence:
        if int(item.get("user_id") or 0) not in student_ids:
            continue
        try:
            score, maximum = float(item.get("score")), float(item.get("max_score"))
        except (TypeError, ValueError):
            continue
        if not isfinite(score) or not isfinite(maximum) or maximum <= 0 or not 0 <= score <= maximum:
            continue
        key = (int(item["user_id"]), str(item.get("competency_key") or "unclassified"))
        stamp = instant(item.get("observed_at")) or datetime.min.replace(tzinfo=UTC)
        previous = latest.get(key)
        if previous is None or stamp > previous[0]:
            latest[key] = (stamp, item)
    return [item for _, item in latest.values()]


def topic_metrics(evidence, student_ids, label, *, minimum_group_size):
    observed, needs_support = defaultdict(set), defaultdict(set)
    for item in latest_scored_evidence(evidence, student_ids):
        topic = label(item.get("competency_key"))
        observed[topic].add(int(item["user_id"]))
        if float(item["score"]) / float(item["max_score"]) < 0.7:
            needs_support[topic].add(int(item["user_id"]))
    return sorted(
        [
            {"topic": topic, "needsSupport": len(needs_support[topic]), "n": len(users)}
            for topic, users in observed.items()
            if len(users) >= max(5, minimum_group_size) and needs_support[topic]
        ],
        key=lambda item: (-item["needsSupport"], item["topic"]),
    )[:5]
