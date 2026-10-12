"""
Workflow Tracking: Theo dõi tiến độ học tập và phát hiện nguy cơ trễ hạn.
Sử dụng các Tool tính toán định lượng (không cần LLM agent riêng).
"""

from datetime import datetime
from typing import Any

from src.agents.state import LearningGraphState
from src.agents.tools.schedule_calculator import (
    calculate_available_hours,
    check_deadline_slack,
)


def _clock_minutes(value: Any) -> int:
    try:
        hours, minutes = str(value).split(":", maxsplit=1)
        return int(hours) * 60 + int(minutes)
    except (TypeError, ValueError):
        return 0


def _parse_current_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now().astimezone()


TRACKING_HORIZON_DAYS = 14


def _hours_until_deadline(value: Any, current: datetime) -> float | None:
    """Return deadline distance while retaining legacy numeric-hour fixtures."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        deadline = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=current.tzinfo)
    elif current.tzinfo is None:
        current = current.replace(tzinfo=deadline.tzinfo)
    return (deadline - current).total_seconds() / 3600


def _is_in_tracking_horizon(deadline: Any, current: datetime) -> bool:
    hours = _hours_until_deadline(deadline, current)
    return hours is not None and 0 <= hours <= TRACKING_HORIZON_DAYS * 24


def _block_is_actionable(
    block: dict[str, Any],
    unavailable_slots: list[dict[str, Any]],
    current: datetime,
) -> bool:
    """Return whether a saved block still represents usable future capacity."""
    block_date_raw = str(block.get("date") or "")[:10]
    if not block_date_raw:
        # Legacy plans did not persist a date. Keep those blocks countable so
        # old workspaces do not lose all capacity after an upgrade.
        return True
    try:
        block_date = datetime.fromisoformat(block_date_raw).date()
        start = _clock_minutes(block.get("start"))
        end = _clock_minutes(block.get("end"))
    except ValueError:
        return False
    if end <= start or block_date < current.date():
        return False
    if block_date == current.date() and end <= current.hour * 60 + current.minute:
        return False

    for slot in unavailable_slots:
        exact_date = str(slot.get("date") or "")[:10]
        if exact_date and exact_date != block_date_raw:
            continue
        try:
            weekday = int(slot.get("weekday", slot.get("day", -1)))
            blocked_start = _clock_minutes(slot.get("start"))
            blocked_end = _clock_minutes(slot.get("end"))
        except (TypeError, ValueError):
            continue
        if weekday != block_date.weekday():
            continue
        if max(start, blocked_start) < min(end, blocked_end):
            return False
    return True


def _planned_minutes_by_task(
    plan: dict[str, Any] | None,
    unavailable_slots: list[dict[str, Any]] | None = None,
    current_time: Any = None,
) -> tuple[dict[str, int], int]:
    planned: dict[str, int] = {}
    invalidated_count = 0
    current = _parse_current_time(current_time)
    for block in (plan or {}).get("blocks") or []:
        task_id = str(block.get("taskId") or block.get("task_id") or "")
        if not task_id:
            continue
        if not _block_is_actionable(block, unavailable_slots or [], current):
            invalidated_count += 1
            continue
        duration = max(0, _clock_minutes(block.get("end")) - _clock_minutes(block.get("start")))
        planned[task_id] = planned.get(task_id, 0) + duration
    return planned, invalidated_count


def _task_progress(state: LearningGraphState) -> dict[str, dict[str, Any]]:
    metrics = state.get("progress_metrics") or {}
    tasks = metrics.get("tasks") if isinstance(metrics, dict) else []
    return {
        str(item.get("id")): item
        for item in tasks or []
        if isinstance(item, dict) and item.get("id") is not None
    }


def tracking_node(state: LearningGraphState) -> dict:
    """Compare actual effort and saved study blocks with authorized LMS deadlines."""
    availability = state.get("availability") or []
    unavailable_slots = state.get("unavailable_slots") or []
    assignments = state.get("assignments") or []
    request = state.get("request") or {}
    client_metrics = state.get("progress_metrics") or {}
    current_time = request.get("current_time")
    current = _parse_current_time(current_time)

    available_hours = calculate_available_hours(availability, unavailable_slots)
    progress_by_task = _task_progress(state)
    planned_by_task, invalidated_block_count = _planned_minutes_by_task(
        state.get("current_plan"),
        unavailable_slots,
        current_time,
    )
    if progress_by_task:
        assignments = [
            assignment
            for assignment in assignments
            if str(assignment.get("id") or "") in progress_by_task
        ]

    risk_signals: list[dict[str, Any]] = []
    slack_results: list[dict[str, Any]] = []
    logged_minutes = 0
    planned_minutes = 0
    active_count = 0

    for assignment in assignments:
        assignment_id = str(assignment.get("id") or "")
        progress = progress_by_task.get(assignment_id, {})
        if progress.get("status") == "done":
            continue

        deadline = assignment.get("deadline") or assignment.get("due_at")
        if not _is_in_tracking_horizon(deadline, current):
            continue

        active_count += 1
        estimated_minutes = int(
            progress.get("estimate_min")
            or round(float(assignment.get("estimated_hours") or assignment.get("expected_hours") or 5.0) * 60)
        )
        task_logged = max(0, int(progress.get("logged_min") or 0))
        task_planned = max(0, planned_by_task.get(assignment_id, 0))
        remaining_minutes = max(0, estimated_minutes - task_logged)
        capacity_gap = max(0, remaining_minutes - task_planned)
        logged_minutes += task_logged
        planned_minutes += task_planned

        slack_info = check_deadline_slack(
            deadline,
            remaining_minutes / 60,
            current_time=current_time,
        )
        slack_results.append({"assignment_id": assignment_id, **slack_info})
        if capacity_gap <= 0 and not slack_info["is_at_risk"]:
            continue

        risk_signals.append(
            {
                "assignment_id": assignment_id,
                "title": assignment.get("title", "Bài tập"),
                "risk_level": "critical" if slack_info["risk_level"] == "critical" else "high",
                "slack_hours": slack_info["slack_hours"],
                "capacity_gap_minutes": capacity_gap,
                "logged_minutes": task_logged,
                "planned_minutes": task_planned,
                "message": (
                    f"Kế hoạch còn thiếu {capacity_gap} phút trước deadline."
                    if capacity_gap > 0
                    else slack_info["message"]
                ),
            }
        )

    session_count = int(client_metrics.get("session_count") or 0) if isinstance(client_metrics, dict) else 0
    studied_minutes = int(client_metrics.get("studied_minutes") or logged_minutes) if isinstance(client_metrics, dict) else logged_minutes

    progress_metrics = {
        "available_hours_remaining": available_hours,
        "active_assignments_count": active_count,
        "planned_minutes": planned_minutes,
        "logged_minutes": logged_minutes,
        "studied_minutes": studied_minutes,
        "session_count": session_count,
        "invalidated_block_count": invalidated_block_count,
        "slack_evaluations": slack_results,
        "tracking_horizon_days": TRACKING_HORIZON_DAYS,
        "at_risk_deadline_count": len(risk_signals),
    }

    if risk_signals:
        summary_resp = (
            f"PaceWise phát hiện {len(risk_signals)} deadline có rủi ro trong 14 ngày tới. "
            f"Bạn đã ghi nhận {studied_minutes} phút học; hãy mở Recover để xem lịch điều chỉnh."
        )
    else:
        summary_resp = (
            f"Tiến độ đang bám kế hoạch: {studied_minutes} phút đã học trong {session_count} phiên. "
            f"Quỹ thời gian khả dụng hiện tại khoảng {available_hours:.1f} giờ."
        )

    return {
        "current_node": "tracking",
        "progress_metrics": progress_metrics,
        "risk_signals": risk_signals,
        "response": summary_resp,
        "analysis": "Đã đối chiếu deadline LMS, thời lượng thực tế và study block đã xác nhận.",
        "status": "completed",
        "output": {"recover_recommended": bool(risk_signals)},
    }

