"""Observational paired before/after KPI. No causal or learning-gain claims."""

from datetime import UTC, datetime, timedelta


def instant(value):
    if not value:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, TypeError):
        return None


def adoption_comparison(assignments, submissions, student_ids, adoption_at, *, as_of, minimum_group_size=5, window_days=14):
    as_of = instant(as_of)
    window = timedelta(days=window_days)
    by_key = {}
    for item in submissions:
        key = (int(item.get("assignment_id") or 0), int(item.get("user_id") or 0))
        by_key.setdefault(key, []).append(item)
    observations = []
    unknown = 0
    for assignment in {int(item["id"]): item for item in assignments}.values():
        if not assignment.get("published", True):
            continue
        for user_id in student_ids:
            joined = instant(adoption_at.get(user_id))
            due = instant((assignment.get("student_due_dates") or {}).get(str(user_id), assignment.get("due_at")))
            # Compare complete, equal windows. Do not compare a lifetime before
            # adoption to a few days after, or call first login actual use.
            if (not joined or not due or not as_of or joined + window > as_of
                    or not joined - window <= due < joined + window):
                continue
            attempts = by_key.get((int(assignment["id"]), user_id), [])
            if any(item.get("workflow_state") == "excused" for item in attempts):
                continue
            accepted = [
                item
                for item in attempts
                if item.get("workflow_state", "submitted") in {"submitted", "graded", "pending_review"}
            ]
            times = [
                stamp
                for item in accepted
                if (stamp := instant(item.get("first_submitted_at") or item.get("submitted_at"))) is not None
            ]
            if accepted and not times:
                unknown += 1
                continue  # No fabricated success/failure when authoritative timestamps are missing.
            observations.append((user_id, "before" if due < joined else "after", bool(times) and min(times) <= due))
    before_users = {user for user, period, _ in observations if period == "before"}
    after_users = {user for user, period, _ in observations if period == "after"}
    paired = before_users & after_users
    result = {
        "status": "insufficient_data",
        "method": "paired_observational_first_plan_confirmation_v2",
        "windowDays": window_days,
        "adoptionEvent": "PLAN_CONFIRMED",
        "before": None,
        "after": None,
        "deltaPercentagePoints": None,
        "minimumGroupSize": max(5, minimum_group_size),
        "unknownTimestampCount": unknown,
        "causalClaim": False,
    }
    if len(paired) < result["minimumGroupSize"]:
        return result
    for period in ("before", "after"):
        rows = [passed for user, label, passed in observations if user in paired and label == period]
        result[period] = {"count": sum(rows), "total": len(rows), "rate": sum(rows) / len(rows)}
    result["status"] = "available"
    result["deltaPercentagePoints"] = round((result["after"]["rate"] - result["before"]["rate"]) * 100, 2)
    return result
