"""Deterministic, server-side study scheduling.

The LLM may propose milestones and explain trade-offs, but this module is the
single source of truth for positioned study blocks and feasibility numbers.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from math import ceil
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.services.deadline_risk import cumulative_deadline_risks
from src.services.notification_policy import StudyPreferences
from src.services.plan_intelligence import (
    apply_estimate,
    build_template_milestones,
    enrich_task_milestones,
    evaluate_plan_quality,
    normalize_reflection_feedback,
    planning_mastery_risk,
)
from src.services.plan_progress import observed_plan_progress
from src.services.planning_time import (
    assignment_available_at,
    block_at,
    deadline_at,
    partition_open_assignments,
)
from src.services.study_activity import activity_context, effective_rhythm

MIN_SLOT_MINUTES = 30
MAX_BLOCK_MINUTES = 90
BREAK_MINUTES = 10
PRIORITY_WEIGHT = {"high": 0, "medium": 1, "low": 2}
DEFAULT_PERSONAL_PRIORITY = 2
SCHEDULING_BUFFER_MINUTES = 15


def _clock_to_minutes(value: str) -> int:
    hours, minutes = str(value).split(":", 1)
    return int(hours) * 60 + int(minutes)


def _minutes_to_clock(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def _ceil_minutes(value: int, increment: int = 15) -> int:
    """Round a minute-of-day value up to a calendar-friendly boundary."""
    return min(24 * 60, ((value + increment - 1) // increment) * increment)


def _fallback_milestones(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Create task-aware safe milestones when the LLM is unavailable.

    These are intentionally based on the assignment type/title and never
    invent subject-matter content or solve graded work.
    """
    assignment = item["assignment"]
    task_id = item["task_id"]
    target = max(MIN_SLOT_MINUTES, int(item["target"]))
    # Use the same evidence-aware decomposition as Plan Agent.  The previous
    # fallback collapsed every <=90-minute assignment into one generic
    # "Hoàn thành..." milestone, which discarded parsed assignment questions
    # and made the calendar look no smarter than manual scheduling.
    assignment_parts = [
        part
        for part in assignment.get("assignment_parts") or []
        if isinstance(part, dict) and part.get("partId") and part.get("content")
    ]
    if len(assignment_parts) >= 2:
        return [
            {
                "milestoneId": str(milestone["milestone_id"]),
                "title": str(milestone["title"]),
                "deliverable": str(milestone.get("deliverable") or ""),
                "estimatedMin": int(milestone.get("estimated_minutes") or target),
                "dependsOn": [str(value) for value in milestone.get("depends_on") or []],
                "sourceRefs": [str(value) for value in milestone.get("source_refs") or []],
                "rubricCriteria": [str(value) for value in milestone.get("rubric_criteria") or []],
                "assignmentPartIds": [str(value) for value in milestone.get("assignment_part_ids") or []],
                "decompositionSource": str(milestone.get("decomposition_source") or "template"),
                "difficulty": milestone.get("difficulty"),
                "allocationBasis": milestone.get("allocation_basis"),
            }
            for milestone in build_template_milestones(assignment, target_minutes=target)
            if str(milestone.get("task_id") or task_id) == task_id
        ]

    title = str(assignment.get("title") or "nhiệm vụ")
    folded = title.casefold()
    rubric = assignment.get("rubric") or {}
    source_refs = [f"assignment:{task_id}"]
    if isinstance(rubric, dict) and rubric.get("id"):
        source_refs.append(f"rubric:{rubric['id']}")
    elif rubric:
        source_refs.append(f"rubric:{task_id}")

    if any(value in folded for value in ("quiz", "kiểm tra", "giữa kỳ", "cuối kỳ", "exam")):
        steps = [
            ("Xác định phạm vi cần ôn", "Danh sách chủ đề và tiêu chí cần đạt", 25),
            ("Ôn học liệu liên quan", "Ghi chú ngắn cho từng chủ đề", 45),
            ("Tự kiểm tra và rà soát", "Danh sách phần còn chưa chắc", 30),
        ]
    elif any(value in folded for value in ("video", "bài giảng", "lecture")):
        steps = [
            ("Xem học liệu và ghi chú", "Ghi chú các ý chính", 70),
            ("Tóm tắt và xác định câu hỏi", "Bản tóm tắt cùng câu hỏi cần làm rõ", 30),
        ]
    elif any(value in folded for value in ("project", "dự án", "lập trình", "code", "dashboard")):
        steps = [
            ("Đọc yêu cầu và rubric", "Checklist yêu cầu cần đáp ứng", 15),
            ("Thiết kế phương án thực hiện", "Bản thiết kế hoặc danh sách bước triển khai", 20),
            ("Thực hiện phần chính", "Bản nháp sản phẩm có thể kiểm tra", 40),
            ("Kiểm thử và đối chiếu rubric", "Sản phẩm đã rà soát, sẵn sàng nộp", 25),
        ]
    else:
        steps = [
            ("Đọc yêu cầu và tiêu chí", "Checklist yêu cầu cần hoàn thành", 20),
            ("Thực hiện bản nháp", "Bản nháp có thể kiểm tra", 55),
            ("Rà soát và chuẩn bị nộp", "Nhiệm vụ sẵn sàng nộp", 25),
        ]

    if target <= MAX_BLOCK_MINUTES:
        return [
            {
                "milestoneId": f"{task_id}:complete",
                "title": f"Hoàn thành {title}",
                "deliverable": "Nhiệm vụ sẵn sàng nộp",
                "estimatedMin": target,
                "dependsOn": [],
                "sourceRefs": source_refs,
                "decompositionSource": "template",
            }
        ]
    milestones: list[dict[str, Any]] = []
    allocated = 0
    for index, (step_title, deliverable, percentage) in enumerate(steps):
        remaining = target - allocated
        minutes = remaining if index == len(steps) - 1 else max(60, round(target * percentage / 100 / 15) * 15)
        minutes = min(remaining, minutes)
        if minutes <= 0:
            continue
        milestone_id = f"{task_id}:step-{index + 1}"
        milestones.append(
            {
                "milestoneId": milestone_id,
                "title": f"{step_title}: {title}",
                "deliverable": deliverable,
                "estimatedMin": minutes,
                "dependsOn": [milestones[-1]["milestoneId"]] if milestones else [],
                "sourceRefs": source_refs,
                "decompositionSource": "template",
            }
        )
        allocated += minutes
    return milestones


def _subtract(
    intervals: list[tuple[int, int]],
    blocked_start: int,
    blocked_end: int,
) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for start, end in intervals:
        if blocked_end <= start or blocked_start >= end:
            result.append((start, end))
            continue
        if blocked_start > start:
            result.append((start, blocked_start))
        if blocked_end < end:
            result.append((blocked_end, end))
    return result


def _parse_deadline(value: Any, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return fallback


def _ordered_intervals(
    intervals: list[tuple[int, int]],
    preferred: str | list[str],
    preferred_ranges: list[tuple[int, int]] | None = None,
) -> list[list[int]]:
    windows = {
        "late_night": (0, 5 * 60),
        "morning": (5 * 60, 12 * 60),
        "afternoon": (12 * 60, 17 * 60),
        "evening": (17 * 60, 24 * 60),
    }
    raw_values = preferred if isinstance(preferred, list) else [preferred]
    preferred_values = {value for value in raw_values if value in windows}
    if not preferred_values:
        preferred_values = {"evening"}
    parts: list[list[int]] = []
    exact_ranges = preferred_ranges or []
    for start, end in intervals:
        cursor = start
        cuts = sorted(
            {
                5 * 60,
                12 * 60,
                17 * 60,
                end,
                *(value for pair in exact_ranges for value in pair),
            }
        )
        for cut in cuts:
            if cursor < cut <= end:
                parts.append([cursor, cut])
                cursor = cut
    return sorted(
        parts,
        key=lambda item: (
            0 if any(start <= item[0] and item[1] <= end for start, end in exact_ranges) else 1,
            0
            if any(start <= item[0] < end for value, (start, end) in windows.items() if value in preferred_values)
            else 1,
            item[0],
        ),
    )


def _self_study_ranges(
    current: date,
    slots: list[dict[str, Any]],
) -> list[tuple[int, int]]:
    """Return learner-declared study windows that apply to one calendar day."""
    ranges: list[tuple[int, int]] = []
    for item in slots:
        if str(item.get("category") or "") != "self_study":
            continue
        exact_date = str(item.get("date") or "")[:10]
        if exact_date and exact_date != current.isoformat():
            continue
        if int(item.get("weekday", -1)) != current.weekday():
            continue
        try:
            start = _clock_to_minutes(str(item["start"]))
            end = _clock_to_minutes(str(item["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        if end - start >= MIN_SLOT_MINUTES:
            ranges.append((start, end))
    return ranges


def _merge_ranges(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def _inside_self_study_window(
    current: date,
    interval: list[int],
    slots: list[dict[str, Any]],
) -> bool:
    return any(start <= interval[0] and interval[1] <= end for start, end in _self_study_ranges(current, slots))


def _inside_preferred_window(
    current: date,
    interval: list[int],
    slots: list[dict[str, Any]],
    preferred: str | list[str],
) -> bool:
    """Whether a block fits any learner preference (never a hard constraint)."""
    if _inside_self_study_window(current, interval, slots):
        return True
    windows = {
        "late_night": (0, 5 * 60),
        "morning": (5 * 60, 12 * 60),
        "afternoon": (12 * 60, 17 * 60),
        "evening": (17 * 60, 24 * 60),
    }
    values = preferred if isinstance(preferred, list) else [preferred]
    return any(
        value in windows
        and windows[value][0] <= interval[0]
        and interval[1] <= windows[value][1]
        for value in values
    )


def _free_intervals(
    current: date,
    availability: list[dict[str, Any]],
    unavailable: list[dict[str, Any]],
    preferred: str | list[str],
) -> list[list[int]]:
    weekday = current.weekday()
    preferred_ranges = _self_study_ranges(current, unavailable)
    available = next(
        (item for item in availability if int(item.get("weekday", -1)) == weekday and item.get("enabled", True)),
        None,
    )
    intervals: list[tuple[int, int]] = []
    if available:
        try:
            intervals.append(
                (
                    _clock_to_minutes(str(available["start"])),
                    _clock_to_minutes(str(available["end"])),
                )
            )
        except (KeyError, TypeError, ValueError):
            pass
    # A positioned self-study slot is an explicit declaration that the learner
    # can study then. It therefore extends general availability, including on a
    # weekend that is disabled in the recurring weekly profile.
    intervals = _merge_ranges([*intervals, *preferred_ranges])
    if not intervals:
        return []
    for item in unavailable:
        exact_date = str(item.get("date") or "")[:10]
        if exact_date and exact_date != current.isoformat():
            continue
        if int(item.get("weekday", -1)) != weekday:
            continue
        try:
            if str(item.get("category") or "") == "self_study":
                continue
            intervals = _subtract(
                intervals,
                _clock_to_minutes(str(item["start"])),
                _clock_to_minutes(str(item["end"])),
            )
        except (KeyError, TypeError, ValueError):
            continue
    intervals = [item for item in intervals if item[1] - item[0] >= MIN_SLOT_MINUTES]
    return _ordered_intervals(intervals, preferred, preferred_ranges)


def _next_study_window(
    current: date,
    start: int,
    end: int,
    minimum_span: int,
    break_minutes: int,
    blocks: list[dict[str, Any]],
    fallback_break_minutes: int,
) -> tuple[int, int] | None:
    """Find the earliest window that keeps the requested inter-session break.

    Availability ranges are ordered independently. Without this day-wide check,
    a block placed in one preferred range can be followed too closely by a block
    selected from another range.
    """

    positioned: list[tuple[int, int, int]] = []
    for block in blocks:
        if block.get("status") == "history" or str(block.get("date") or "")[:10] != current.isoformat():
            continue
        try:
            block_start = _clock_to_minutes(str(block.get("start")))
            block_end = _clock_to_minutes(str(block.get("end")))
            rhythm = block.get("rhythm") if isinstance(block.get("rhythm"), dict) else {}
            block_break = int(rhythm.get("breakMinutes", fallback_break_minutes))
        except (TypeError, ValueError):
            continue
        if block_end > block_start:
            positioned.append((block_start, block_end, max(0, block_break)))

    cursor = start
    for block_start, block_end, block_break in sorted(positioned):
        required_break = max(0, break_minutes, block_break)
        latest_end_before_block = block_start - required_break
        if cursor + minimum_span <= latest_end_before_block:
            return cursor, min(end, latest_end_before_block)
        if cursor < block_end + required_break:
            cursor = block_end + required_break
        if cursor + minimum_span > end:
            return None
    return (cursor, end) if cursor + minimum_span <= end else None


def build_plan_draft(
    plan_input: dict[str, Any],
    assignments: list[dict[str, Any]],
    *,
    proposed_milestones: list[dict[str, Any]] | None = None,
    learner_profile: dict[str, Any] | None = None,
    mastery_profile: dict[str, Any] | None = None,
    timezone_name: str = "Asia/Ho_Chi_Minh",
    today: date | None = None,
    now: datetime | None = None,
    window_days: int = 7,
) -> dict[str, Any]:
    """Create a canonical plan with deterministic risk-aware scheduling.

    The LLM may decompose work into milestones, but only this function positions
    blocks on the calendar. This keeps feasibility and deadline rules stable.
    """
    timezone = ZoneInfo(timezone_name)
    rhythm = StudyPreferences.model_validate(plan_input.get("studyPreferences") or {})
    session_minutes, break_minutes = rhythm.session_minutes, rhythm.break_minutes
    checkpoint_minutes = rhythm.checkpoint_minutes
    current_time = now.astimezone(timezone) if now else datetime.now(timezone)
    current = today or current_time.date()
    schedule_floor_minute = (
        _ceil_minutes(current_time.hour * 60 + current_time.minute + SCHEDULING_BUFFER_MINUTES)
        if now is not None or today is None
        else 0
    )
    planning_window_days = max(1, int(window_days))
    requested_week_start = _parse_deadline(plan_input.get("weekStart"), current)
    has_calendar_week = bool(plan_input.get("weekStart"))
    week_start = requested_week_start if has_calendar_week else current
    commitment_end = week_start + timedelta(days=planning_window_days - 1)
    requested_horizon_end = _parse_deadline(plan_input.get("horizonEnd"), commitment_end)
    horizon_end = max(commitment_end, requested_horizon_end)
    schedule_start = max(current, week_start)
    # Explicit date-only callers (offline evaluations) mean start of that day;
    # live requests and callers passing now use the exact, server-owned instant.
    planning_now = current_time if now is not None or today is None else datetime.combine(current, time.min, timezone)
    active_assignments, expired_assignments = partition_open_assignments(
        assignments, now=planning_now, timezone_name=timezone_name, fallback=horizon_end)
    assignments_by_id = {str(item.get("id")): item for item in active_assignments}
    requested_minutes = {str(item.get("taskId")): max(0, int(item.get("remainingMin") or 0))
                         for item in plan_input.get("tasks") or []}
    expired_tasks = [{"taskId": str(item.get("id")), "title": str(item.get("title") or item.get("id")),
                      "deadline": deadline_at(item.get("deadline") or item.get("due_at"), horizon_end, timezone_name).isoformat(),
                      "remainingMin": requested_minutes.get(str(item.get("id"))), "status": "overdue_unresolved"}
                     for item in expired_assignments]
    weekly_goals = [
        {
            "id": str(item.get("id") or f"goal-{index + 1}"),
            "title": str(item.get("title") or "").strip(),
            "taskIds": [str(value) for value in item.get("taskIds") or [] if str(value) in assignments_by_id],
            "confirmed": bool(item.get("confirmed", True)),
            "rationale": str(item.get("rationale") or "").strip(),
            "sourceRefs": [str(value) for value in item.get("sourceRefs") or [] if str(value).strip()],
            "analysisSource": str(item.get("analysisSource") or "assignment_rule"),
        }
        for index, item in enumerate(plan_input.get("weeklyGoals") or [])
        if str(item.get("title") or "").strip()
        and (not item.get("taskIds") or any(str(value) in assignments_by_id for value in item["taskIds"]))
    ]
    goal_by_task = {task_id: goal["id"] for goal in weekly_goals for task_id in goal["taskIds"]}
    selected: list[dict[str, Any]] = []
    replan_adjustments: list[dict[str, Any]] = []
    proposals = [
        item
        for item in (learner_profile or {}).get("replan_proposals") or []
        if isinstance(item, dict) and item.get("action") == "propose_draft"
    ]
    fallback_proposal = (learner_profile or {}).get("last_replan_proposal") or {}
    if fallback_proposal and fallback_proposal not in proposals:
        proposals.append(fallback_proposal)
    requested_repair_ids = {
        str(value)
        for value in ((plan_input.get("replanContext") or {}).get("taskIds") or [])
        if str(value)
    }
    replan_proposal = next(
        (
            proposal
            for proposal in reversed(proposals)
            if not requested_repair_ids
            or requested_repair_ids
            & {str(value) for value in (proposal.get("repair_context") or {}).get("affected_task_ids") or []}
        ),
        {},
    )
    repair_context = replan_proposal.get("repair_context") or {}
    repair_task_ids = {str(value) for value in repair_context.get("affected_task_ids") or [] if str(value)}
    matching_do = [
        item
        for item in (learner_profile or {}).get("do_history") or []
        if isinstance(item, dict) and str(item.get("task_id") or "") in repair_task_ids
    ]
    last_do = matching_do[-1] if matching_do else (learner_profile or {}).get("last_do_session") or {}

    def scoped_mastery(assignment: dict[str, Any]) -> dict[str, Any]:
        profiles = (mastery_profile or {}).get("__by_course__")
        if not isinstance(profiles, dict):
            return mastery_profile or {}
        course_id = str(assignment.get("course_id") or assignment.get("courseId") or "")
        value = profiles.get(course_id, {})
        return value if isinstance(value, dict) else {}
    observed_progress = observed_plan_progress(learner_profile)
    for item in plan_input.get("tasks") or []:
        task_id = str(item.get("taskId") or "")
        assignment = assignments_by_id.get(task_id)
        remaining = max(0, int(item.get("remainingMin") or 0))
        if task_id in observed_progress:
            remaining = int(observed_progress[task_id]["remaining_minutes"])
        if assignment:
            reflection_signals = normalize_reflection_feedback(learner_profile, task_id=task_id)
            assignment_mastery = scoped_mastery(assignment)
            mastery_risk = planning_mastery_risk(assignment, assignment_mastery)
            adaptive_review = max(
                int(reflection_signals["followUpMinutes"]),
                MIN_SLOT_MINUTES if mastery_risk > 0.5 else 0,
            )
            # Completing the original Do work closes that work; a confirmed
            # Reflect follow-up is separate new review work and must survive a
            # zero remaining baseline.
            if remaining <= 0 and adaptive_review <= 0:
                continue
            reported_remaining = remaining
            if (
                replan_proposal.get("action") == "propose_draft"
                and task_id in repair_task_ids
                and str(last_do.get("task_id") or "") == task_id
                and str(last_do.get("status") or "") in {"missed", "blocked", "needs_more_time"}
            ):
                planned = max(0, int(last_do.get("planned_minutes") or 0))
                actual = max(0, int(last_do.get("actual_minutes") or 0))
                completion = min(100, max(0, int(last_do.get("completion_percent") or 0)))
                # The client baseline normally subtracts actual timer minutes.
                # Add back only the observed gap between time spent and the
                # planned-work equivalent completed. Never reduce workload from
                # a self-reported completion percentage.
                reconciled = max(remaining, remaining + actual - round(planned * completion / 100))
                remaining = max(0, reconciled)
                if remaining != reported_remaining:
                    replan_adjustments.append(
                        {
                            "taskId": task_id,
                            "baselineRemainingMin": reported_remaining,
                            "reconciledRemainingMin": remaining,
                            "addedMin": remaining - reported_remaining,
                            "reason": "observed_unfinished_work",
                            "sourceRef": f"do:{last_do.get('block_id') or 'latest'}",
                        }
                    )
            deadline_value = assignment.get("deadline") or assignment.get("due_at")
            due = deadline_at(deadline_value, horizon_end, timezone_name)
            due_day = (
                due.date() if len(str(deadline_value or "")) > 10 else _parse_deadline(deadline_value, horizon_end)
            )
            selected.append(
                {
                    "task_id": task_id,
                    "remaining": remaining,
                    "assignment": assignment,
                    "deadline": due_day,
                    "deadline_at": due,
                    "deadline_minute": due.hour * 60 + due.minute if due.date() == due_day else 1440,
                    "available_at": assignment_available_at(assignment, timezone_name),
                    "priority": str(assignment.get("priority") or "medium"),
                    # Legacy workspace values remain readable, but the removed
                    # manual-priority control must not silently affect new plans.
                    "personal_priority": DEFAULT_PERSONAL_PRIORITY,
                    "mastery_risk": mastery_risk,
                    "mastery_profile": assignment_mastery,
                    "reflect_follow_up": reflection_signals["followUpMinutes"],
                    "adaptive_review": adaptive_review,
                    "weekly_goal_id": str(item.get("weeklyGoalId") or goal_by_task.get(task_id) or ""),
                }
            )
    selected.sort(
        key=lambda item: (
            item["deadline_at"],
            -item["mastery_risk"],
            PRIORITY_WEIGHT.get(item["priority"], PRIORITY_WEIGHT["medium"]),
            -float((item["assignment"].get("assignment_group") or {}).get("weight") or 0),
            -float(item["assignment"].get("points_possible") or 0),
        )
    )
    horizon_days = max(1, (horizon_end - schedule_start).days + 1)
    for item in selected:
        days_until_deadline = max(0, (item["deadline"] - schedule_start).days)
        if item["deadline"] <= horizon_end:
            target = item["remaining"]
        else:
            # The look-ahead horizon may include work due after this planning
            # window. Schedule only a fair share instead of forcing the whole
            # assignment into the current window.
            proportional = ceil(item["remaining"] * horizon_days / (days_until_deadline + 1))
            target = min(item["remaining"], max(MIN_SLOT_MINUTES, ceil(proportional / 15) * 15))
        item["target"] = target + item["adaptive_review"]

    selected_ids = {item["task_id"] for item in selected}
    milestones_by_task: dict[str, list[dict[str, Any]]] = {task_id: [] for task_id in selected_ids}
    generic_milestones: list[dict[str, Any]] = []
    for raw in proposed_milestones or []:
        milestone_id = str(raw.get("milestone_id") or raw.get("id") or "").strip()
        if not milestone_id:
            continue
        task_id = str(raw.get("task_id") or raw.get("taskId") or raw.get("assignment_id") or "").strip()
        completed = observed_progress.get(task_id, {})
        completed_milestones = set(completed.get("completed_milestone_ids") or [])
        completed_parts = set(completed.get("completed_assignment_part_ids") or [])
        raw_parts = {
            str(value)
            for value in (raw.get("assignment_part_ids") or raw.get("assignmentPartIds") or [])
            if str(value)
        }
        if milestone_id in completed_milestones or (raw_parts and raw_parts <= completed_parts):
            continue
        normalized = {
            "milestoneId": milestone_id,
            "title": str(raw.get("title") or milestone_id),
            "deliverable": str(raw.get("deliverable") or ""),
            "estimatedMin": max(15, int(raw.get("estimated_minutes") or raw.get("estimatedMin") or 60)),
            "dependsOn": [
                str(value)
                for value in (raw.get("depends_on") or raw.get("dependsOn") or [])
                if str(value) not in completed_milestones
            ],
            "sourceRefs": [
                str(value) for value in (raw.get("source_refs") or raw.get("sourceRefs") or []) if str(value).strip()
            ],
            "rubricCriteria": [
                str(value)
                for value in (raw.get("rubric_criteria") or raw.get("rubricCriteria") or [])
                if str(value).strip()
            ],
            "knowledgeComponents": list(raw.get("knowledge_components") or raw.get("knowledgeComponents") or []),
            "assignmentPartIds": [
                str(value)
                for value in (raw.get("assignment_part_ids") or raw.get("assignmentPartIds") or [])
                if str(value).strip()
            ],
            "mappingConfidence": raw.get("mapping_confidence") or raw.get("mappingConfidence"),
            "decompositionSource": str(raw.get("decomposition_source") or raw.get("decompositionSource") or "llm"),
            "difficulty": raw.get("difficulty"),
            "allocationBasis": raw.get("allocation_basis") or raw.get("allocationBasis"),
        }
        if task_id in milestones_by_task:
            milestones_by_task[task_id].append(normalized)
        elif not task_id:
            generic_milestones.append(normalized)

    # Old agent responses did not carry task_id. They are still useful when a
    # student is planning one assignment; otherwise deterministic task-level
    # milestones avoid attaching AI output to the wrong course.
    if len(selected) == 1 and generic_milestones:
        milestones_by_task[selected[0]["task_id"]].extend(generic_milestones)

    planning_milestones: list[dict[str, Any]] = []
    rubric_coverage: list[dict[str, Any]] = []
    for item in selected:
        task_milestones = milestones_by_task[item["task_id"]]
        if not task_milestones:
            task_milestones = _fallback_milestones(item)
        task_milestones, coverage = enrich_task_milestones(
            task_id=item["task_id"],
            assignment=item["assignment"],
            milestones=task_milestones,
            learner_profile=learner_profile,
            mastery_profile=item["mastery_profile"],
        )
        rubric_coverage.append(coverage)
        remaining_target = item["target"]
        for index, milestone in enumerate(task_milestones):
            milestone = {**milestone, **activity_context(milestone, item["assignment"], item["task_id"])}
            if remaining_target <= 0:
                break
            requested = milestone["estimatedMin"]
            allocated = remaining_target if index == len(task_milestones) - 1 else min(remaining_target, requested)
            planning_milestones.append(
                apply_estimate(
                    {
                        **milestone,
                        "taskId": item["task_id"],
                        "weeklyGoalId": item["weekly_goal_id"] or None,
                        "targetMin": allocated,
                        "deadline": item["deadline"].isoformat(),
                    },
                    allocated_minutes=allocated,
                    learner_profile=learner_profile,
                    task_id=item["task_id"],
                )
            )
            remaining_target -= allocated
        if remaining_target > 0:
            planning_milestones.append(
                apply_estimate(
                    {
                        "milestoneId": f"{item['task_id']}:finish",
                        "taskId": item["task_id"],
                        "weeklyGoalId": item["weekly_goal_id"] or None,
                        "title": f"Hoàn thiện {item['assignment'].get('title', 'nhiệm vụ')}",
                        "deliverable": "Nhiệm vụ sẵn sàng nộp",
                        "estimatedMin": remaining_target,
                        "targetMin": remaining_target,
                        "dependsOn": [planning_milestones[-1]["milestoneId"]] if planning_milestones else [],
                        "sourceRefs": [f"assignment:{item['task_id']}"],
                        "rubricCriteria": [],
                        "knowledgeComponents": [],
                        "mappingConfidence": 1.0,
                        "decompositionSource": "capacity_fill",
                        "masteryScores": {},
                        **activity_context({}, item["assignment"], item["task_id"]),
                        "deadline": item["deadline"].isoformat(),
                    },
                    allocated_minutes=remaining_target,
                    learner_profile=learner_profile,
                    task_id=item["task_id"],
                )
            )

    preferences = rhythm.model_dump(by_alias=True)
    for milestone in planning_milestones:
        milestone["rhythm"] = effective_rhythm(preferences, milestone.get("courseId"), milestone["activityType"])

    # Adapt the proposal, not the original student-entered remainingMin.
    # Estimates are computed once from baseline allocations to avoid double
    # multiplication when the adjusted draft is presented for confirmation.
    duration_adjustments = []
    for item in selected:
        task_milestones = [m for m in planning_milestones if m["taskId"] == item["task_id"]]
        base_target = item["target"]
        for milestone in task_milestones:
            baseline = milestone["targetMin"]
            milestone["baselineTargetMin"] = baseline
            milestone["targetMin"] = max(baseline, int(milestone["estimate"]["p50_minutes"]))
        item["target"] = sum(m["targetMin"] for m in task_milestones)
        if item["target"] != base_target or item["adaptive_review"]:
            duration_adjustments.append(
                {
                    "taskId": item["task_id"],
                    "studentRemainingMin": item["remaining"],
                    "baselineTargetMin": base_target - item["adaptive_review"],
                    "reviewAddedMin": item["adaptive_review"],
                    "proposedTargetMin": item["target"],
                    "reason": "history_reflect_or_knowledge_estimate",
                    "sourceRefs": sorted({ref for m in task_milestones for ref in m["estimate"].get("source_refs", [])}),
                    "evidenceCount": max((m["estimate"]["evidence_count"] for m in task_milestones), default=0),
                    "estimateStatus": "heuristic_not_calibrated",
                    "requiresConfirmation": True,
                }
            )

    availability = list(plan_input.get("availability") or [])
    unavailable = list(plan_input.get("unavailable") or [])
    preferred_raw = plan_input.get("preferred") or ["evening"]
    preferred = [str(value) for value in preferred_raw] if isinstance(preferred_raw, list) else str(preferred_raw)
    # Student-positioned blocks are explicit constraints. Preserve every valid
    # block, reserve its interval, and schedule only the remaining workload.
    selected_by_id = {item["task_id"]: item for item in selected}
    pinned_minutes: dict[str, int] = {task_id: 0 for task_id in selected_by_id}
    pinned_blocks: list[dict[str, Any]] = []
    history_blocks: list[dict[str, Any]] = []
    history_floor_by_task: dict[str, tuple[date, int]] = {}
    for raw in plan_input.get("pinnedBlocks") or []:
        task_id = str(raw.get("taskId") or "")
        selected_item = selected_by_id.get(task_id)
        try:
            block_date = date.fromisoformat(str(raw.get("date") or "")[:10])
            start_minute = _clock_to_minutes(str(raw.get("start")))
            end_minute = _clock_to_minutes(str(raw.get("end")))
        except (TypeError, ValueError):
            continue
        elapsed = block_date < schedule_start or (
            block_date == current and end_minute <= schedule_floor_minute
        )
        # Time passing is not completion evidence. Only server-protected history
        # survives re-analysis; an elapsed, unused Do block is released so its
        # work can be placed again before the assignment deadline.
        if raw.get("status") == "history":
            if week_start <= block_date <= horizon_end:
                history_block = {
                        "id": str(raw.get("id") or f"blk-{uuid4().hex[:12]}"),
                        "taskId": task_id,
                        "milestoneId": raw.get("milestoneId"),
                        "milestoneTitle": raw.get("milestoneTitle"),
                        "date": block_date.isoformat(),
                        "start": _minutes_to_clock(start_minute),
                        "end": _minutes_to_clock(end_minute),
                        "status": "history",
                        "placementSource": str(raw.get("placementSource") or "student"),
                    }
                history_blocks.append(history_block)
                if task_id:
                    previous_floor = history_floor_by_task.get(task_id)
                    next_floor = (block_date, end_minute)
                    if previous_floor is None or next_floor > previous_floor:
                        history_floor_by_task[task_id] = next_floor
                # Completed study is immutable evidence and remains occupied
                # during re-plan, even when the learner finished it early.
                unavailable.append(
                    {
                        "date": block_date.isoformat(),
                        "weekday": block_date.weekday(),
                        "start": _minutes_to_clock(start_minute),
                        "end": _minutes_to_clock(end_minute),
                        "category": "completed_study",
                    }
                )
            continue
        if elapsed:
            continue
        # Release only future AI placements. Elapsed/completed blocks above
        # survive even when their task was removed from the new selection.
        started = (
            raw.get("status") == "active"
            and
            (now is not None or today is None)
            and block_date == current
            and start_minute <= current_time.hour * 60 + current_time.minute
        )
        if str(raw.get("placementSource") or "") == "agent" and not started:
            continue
        if not selected_item:
            continue
        if (
            block_date > horizon_end
            or end_minute <= start_minute
            or block_at(block_date.isoformat(), str(raw["end"]), timezone_name) > selected_item["deadline_at"]
            or (
                selected_item["available_at"] is not None
                and block_at(block_date.isoformat(), str(raw["start"]), timezone_name)
                < selected_item["available_at"]
            )
        ):
            continue
        free_before_pin = _free_intervals(block_date, availability, unavailable, preferred)
        if not started and not any(
            start_minute >= free_start and end_minute <= free_end for free_start, free_end in free_before_pin
        ):
            continue
        normalized = {
            "id": str(raw.get("id") or f"blk-{uuid4().hex[:12]}"),
            "taskId": task_id,
            "milestoneId": raw.get("milestoneId"),
            "milestoneTitle": raw.get("milestoneTitle"),
            "date": block_date.isoformat(),
            "start": _minutes_to_clock(start_minute),
            "end": _minutes_to_clock(end_minute),
            "status": "confirmed" if block_date <= commitment_end else "tentative",
            "placementSource": "student",
            "lockedOngoing": started,
            **(
                {"earliestStartAt": selected_item["available_at"].isoformat()}
                if selected_item["available_at"]
                else {}
            ),
            "checkpointMinutes": max(0, min(int(raw.get("checkpointMinutes") or 0), end_minute - start_minute)),
            "activityType": raw.get("activityType", "unknown"),
            "activitySource": raw.get("activitySource", "unmapped"),
            "rhythm": raw.get("rhythm") or effective_rhythm(preferences, activity_context({}, selected_item["assignment"], task_id)["courseId"], raw.get("activityType", "unknown")),
        }
        pinned_blocks.append(normalized)
        pinned_minutes[task_id] += end_minute - start_minute - normalized["checkpointMinutes"]
        unavailable.append(
            {
                "date": block_date.isoformat(),
                "weekday": block_date.weekday(),
                "start": normalized["start"],
                "end": normalized["end"],
            }
        )
    free_by_day: dict[date, list[list[int]]] = {}
    planning_day_count = max(0, (horizon_end - schedule_start).days + 1)
    for offset in range(planning_day_count):
        day = schedule_start + timedelta(days=offset)
        free_by_day[day] = _free_intervals(day, availability, unavailable, preferred)
    # In production the current day starts after "now" plus a small preparation
    # buffer. Tests that pass only ``today`` keep the full deterministic day.
    if schedule_floor_minute:
        free_by_day[current] = [
            [max(start, schedule_floor_minute), end]
            for start, end in free_by_day.get(current, [])
            if end - max(start, schedule_floor_minute) >= MIN_SLOT_MINUTES
        ]
    capacity_intervals = {day: [tuple(interval) for interval in intervals] for day, intervals in free_by_day.items()}

    available_minutes = sum(end - start for intervals in free_by_day.values() for start, end in intervals) + sum(
        pinned_minutes.values()
    )
    blocks: list[dict[str, Any]] = [*history_blocks, *pinned_blocks]

    def scheduled_day_minutes(day: date) -> int:
        """Balance new work across the rolling window instead of filling today first."""

        return sum(
            max(0, _clock_to_minutes(str(block.get("end"))) - _clock_to_minutes(str(block.get("start"))))
            for block in blocks
            if str(block.get("date") or "") == day.isoformat()
            and block.get("start")
            and block.get("end")
        )

    shortfalls: list[dict[str, Any]] = []
    for item in selected:
        task_milestones = [value for value in planning_milestones if value["taskId"] == item["task_id"]]
        remaining = max(0, item["target"] - pinned_minutes.get(item["task_id"], 0))
        last_day = min(item["deadline"], horizon_end)
        milestone_index = 0
        milestone_remaining = task_milestones[0]["targetMin"] if task_milestones else remaining
        candidate_intervals = [
            (day, interval_order, interval)
            for day, intervals in free_by_day.items()
            if schedule_start <= day <= last_day
            and (item["available_at"] is None or day >= item["available_at"].date())
            for interval_order, interval in enumerate(intervals)
        ]
        # Explicit self-study windows are learner intent, not busy time. A
        # future preferred window may jump ahead of earlier generic capacity,
        # but only when one such interval can contain the task's complete
        # dependency chain. Otherwise use chronological order so a later
        # milestone can never be placed before its prerequisite.
        required_span = 0
        last_segment_break = 0
        span_remaining = remaining
        for milestone in task_milestones:
            target = min(span_remaining, int(milestone.get("targetMin") or 0))
            if target <= 0:
                continue
            rhythm = milestone["rhythm"]
            work_limit = max(1, rhythm["sessionMinutes"] - checkpoint_minutes)
            segment_count = ceil(target / work_limit)
            required_span += target + segment_count * (checkpoint_minutes + rhythm["breakMinutes"])
            last_segment_break = rhythm["breakMinutes"]
            span_remaining -= target
        if span_remaining > 0:
            work_limit = max(1, session_minutes - checkpoint_minutes)
            segment_count = ceil(span_remaining / work_limit)
            required_span += span_remaining + segment_count * (checkpoint_minutes + break_minutes)
            last_segment_break = break_minutes
        required_span = max(0, required_span - last_segment_break)

        fitting_candidates = [
            value
            for value in candidate_intervals
            if min(value[2][1], item["deadline_minute"] if value[0] == item["deadline"] else 1440)
            - max(
                value[2][0],
                item["available_at"].hour * 60 + item["available_at"].minute
                if item["available_at"] is not None and value[0] == item["available_at"].date()
                else value[2][0],
            )
            >= required_span
        ]
        fitting_self_study = [
            value for value in fitting_candidates if _inside_self_study_window(value[0], value[2], unavailable)
        ]
        if fitting_self_study:
            chosen = min(
                fitting_self_study,
                key=lambda value: (scheduled_day_minutes(value[0]), value[0], value[2][0]),
            )
        elif fitting_candidates:
            # Balance work across the rolling planning window. Within equally
            # loaded days, keep chronological order and the learner's preferred
            # period ordering produced by _free_intervals.
            chosen = min(
                fitting_candidates,
                key=lambda value: (scheduled_day_minutes(value[0]), value[0], value[1]),
            )
        else:
            chosen = None
        if chosen is not None:
            candidate_intervals.sort(
                key=lambda value: (
                    0 if value is chosen else 1,
                    value[0],
                    value[2][0],
                )
            )
        else:
            candidate_intervals.sort(key=lambda value: (value[0], value[2][0]))
        history_floor = history_floor_by_task.get(item["task_id"])
        task_floor_day: date | None = history_floor[0] if history_floor else None
        task_floor_minute = (history_floor[1] + break_minutes) if history_floor else 0
        for day, _, interval in candidate_intervals:
            if task_floor_day is not None and day < task_floor_day:
                continue
            cutoff = item["deadline_minute"] if day == item["deadline"] else 1440
            effective_end = min(interval[1], cutoff)
            while remaining > 0:
                while milestone_index < len(task_milestones) and milestone_remaining <= 0:
                    milestone_index += 1
                    milestone_remaining = (
                        task_milestones[milestone_index]["targetMin"]
                        if milestone_index < len(task_milestones)
                        else remaining
                    )
                milestone = task_milestones[milestone_index] if milestone_index < len(task_milestones) else None
                block_rhythm = milestone["rhythm"] if milestone else effective_rhythm(preferences, None, "unknown")
                work_limit = block_rhythm["sessionMinutes"] - checkpoint_minutes
                minimum_work = min(MIN_SLOT_MINUTES, remaining, milestone_remaining, work_limit)
                candidate_start = max(
                    interval[0],
                    task_floor_minute if task_floor_day == day else interval[0],
                    item["available_at"].hour * 60 + item["available_at"].minute
                    if item["available_at"] is not None and day == item["available_at"].date()
                    else interval[0],
                )
                window = _next_study_window(
                    day,
                    candidate_start,
                    effective_end,
                    minimum_work + checkpoint_minutes,
                    block_rhythm["breakMinutes"],
                    blocks,
                    break_minutes,
                )
                if window is None:
                    break
                start, window_end = window
                duration = min(remaining, milestone_remaining, work_limit, window_end - start - checkpoint_minutes)
                blocks.append(
                    {
                        "id": f"blk-{uuid4().hex[:12]}",
                        "taskId": item["task_id"],
                        "milestoneId": milestone["milestoneId"] if milestone else None,
                        "milestoneTitle": milestone["title"] if milestone else None,
                        "date": day.isoformat(),
                        "start": _minutes_to_clock(start),
                        "end": _minutes_to_clock(start + duration + checkpoint_minutes),
                        **({"earliestStartAt": item["available_at"].isoformat()} if item["available_at"] else {}),
                        "workMinutes": duration,
                        "checkpointMinutes": checkpoint_minutes,
                        "activityType": milestone["activityType"] if milestone else "unknown",
                        "activitySource": milestone["activitySource"] if milestone else "unmapped",
                        "rhythm": block_rhythm,
                        "status": "confirmed" if day <= commitment_end else "tentative",
                        "placementSource": "agent",
                        "outsidePreferred": not _inside_preferred_window(
                            day,
                            [start, start + duration + checkpoint_minutes],
                            unavailable,
                            preferred,
                        ),
                    }
                )
                remaining -= duration
                milestone_remaining -= duration
                task_floor_day = day
                task_floor_minute = start + duration + checkpoint_minutes + block_rhythm["breakMinutes"]
                interval[0] = min(
                    interval[1],
                    task_floor_minute,
                )
            if remaining <= 0:
                break
        if remaining:
            shortfalls.append({"taskId": item["task_id"], "missingMin": remaining})

    checkpoint_reserved = sum(int(block.get("checkpointMinutes") or 0) for block in blocks if block.get("status") != "history")
    required_minutes = sum(item["target"] for item in selected) + checkpoint_reserved
    deficit_minutes = sum(item["missingMin"] for item in shortfalls)
    p50_required_by_task: dict[str, int] = {}
    p80_required_by_task: dict[str, int] = {}
    for item in selected:
        task_milestones = [m for m in planning_milestones if m["taskId"] == item["task_id"]]

        def required(field: str, fallback: int) -> int:
            work = sum(int((m.get("estimate") or {}).get(field) or m["targetMin"]) for m in task_milestones)
            work = max(fallback, work)
            segments = [
                (
                    ceil(int((m.get("estimate") or {}).get(field) or m["targetMin"])
                         / max(1, m["rhythm"]["sessionMinutes"] - checkpoint_minutes)),
                    m["rhythm"]["breakMinutes"],
                )
                for m in task_milestones
            ]
            overhead = sum(count * (checkpoint_minutes + pause) for count, pause in segments)
            if segments:
                overhead -= segments[-1][1]
            return work + overhead

        p50_required_by_task[item["task_id"]] = required("p50_minutes", item["target"])
        p80_required_by_task[item["task_id"]] = required("p80_minutes", item["target"])
    robust_required_minutes = sum(p80_required_by_task.values())
    deadline_risks = cumulative_deadline_risks(
        selected,
        capacity_intervals,
        p50_required_by_task=p50_required_by_task,
        p80_required_by_task=p80_required_by_task,
        pinned_capacity=[
            {
                "date": date.fromisoformat(block["date"]),
                "task_id": block["taskId"],
                "start_minute": _clock_to_minutes(block["start"]),
                "end_minute": _clock_to_minutes(block["end"]),
            }
            for block in pinned_blocks
        ],
    )
    robust_shortfalls = [
        {
            "taskId": risk["taskIds"][-1],
            "missingMin": -risk["slackP80Min"],
            "deadline": risk["deadline"],
        }
        for risk in deadline_risks
        if risk["slackP80Min"] < 0
    ]
    uncovered_tasks = []
    for assignment in active_assignments:
        task_id = str(assignment.get("id") or "")
        submission_state = str((assignment.get("submission") or {}).get("workflow_state") or "").lower()
        deadline = _parse_deadline(assignment.get("deadline"), horizon_end)
        if (
            task_id
            and task_id not in selected_ids
            and submission_state not in {"submitted", "graded", "pending_review", "excused"}
            and schedule_start <= deadline <= horizon_end
        ):
            uncovered_tasks.append(
                {
                    "taskId": task_id,
                    "title": str(assignment.get("title") or task_id),
                    "deadline": deadline.isoformat(),
                }
            )
    first_assignment = selected[0]["assignment"] if selected else None
    reasons = [
        "Backend ưu tiên deadline gần, mức độ quan trọng và trọng số bài; không đặt study block sau hạn nộp.",
        "Mọi study block nằm trong quỹ thời gian rảnh và tránh các khoảng bận đã khai báo.",
        f"Mỗi ca tối đa {session_minutes} phút, nghỉ {break_minutes} phút; ca cuối hoặc khung rảnh ngắn có thể ít hơn mà không làm giảm tổng công việc. Dùng nhịp riêng đã chọn nếu đúng môn/loại hoạt động, vẫn ưu tiên deadline.",
    ]
    if first_assignment:
        reasons.insert(0, f"Ưu tiên “{first_assignment.get('title', 'nhiệm vụ gần nhất')}” vì có deadline gần nhất.")
    assumptions = [
        (
            f"Lịch cam kết được tính đến {commitment_end.isoformat()}; "
            f"các block đến {horizon_end.isoformat()} là dự kiến và không có block nào nằm trong quá khứ."
        ),
        "Thời lượng còn lại do sinh viên xác nhận; hệ thống không tự thay đổi con số này.",
    ]
    draft = {
        "input": plan_input,
        "weekStart": week_start.isoformat(),
        "weekEnd": commitment_end.isoformat(),
        "horizonEnd": horizon_end.isoformat(),
        "scheduleStart": schedule_start.isoformat(),
        "timezone": timezone_name,
        "enforceCurrentTime": now is not None or today is None,
        "durationAdjustments": duration_adjustments,
        "replanAdjustments": replan_adjustments,
        "replanContext": repair_context if replan_proposal.get("action") == "propose_draft" else {},
        "expiredTasks": expired_tasks,
        "weeklyGoals": weekly_goals,
        "planningTargets": [
            {
                "taskId": item["task_id"],
                "targetMin": item["target"],
                "remainingMin": item["remaining"],
                "reflectFollowUpMin": item["reflect_follow_up"],
                "adaptiveReviewMin": item["adaptive_review"],
                "estimateStatus": "insufficient_evidence" if all(m["estimate"].get("data_status") == "insufficient_evidence" for m in planning_milestones if m["taskId"] == item["task_id"]) else "supported_heuristic",
            }
            for item in selected
        ],
        "priorityOrder": [
            {
                "rank": index + 1,
                "taskId": item["task_id"],
                "title": str(item["assignment"].get("title") or item["task_id"]),
                "deadline": item["deadline"].isoformat(),
                "priority": item["priority"],
                "personalPriority": item["personal_priority"],
                "assignmentGroupWeight": float((item["assignment"].get("assignment_group") or {}).get("weight") or 0),
                "pointsPossible": float(item["assignment"].get("points_possible") or 0),
                "masteryRisk": item["mastery_risk"],
            }
            for index, item in enumerate(selected)
        ],
        "milestones": planning_milestones,
        "rubricCoverage": rubric_coverage,
        "blocks": sorted(blocks, key=lambda item: (item["date"], item["start"])),
        "feasibility": {
            "availableMin": available_minutes,
            "requiredMin": required_minutes,
            "workRequiredMin": sum(item["target"] for item in selected),
            "checkpointReservedMin": checkpoint_reserved,
            "robustRequiredMin": robust_required_minutes,
            "remainingMin": available_minutes - required_minutes,
            "feasible": deficit_minutes == 0,
            "robustFeasible": deficit_minutes == 0 and not robust_shortfalls,
            "robustShortfalls": robust_shortfalls,
            "deadlineRisks": deadline_risks,
            "deficitMin": deficit_minutes,
            "shortfalls": shortfalls,
            "uncoveredTasks": uncovered_tasks,
        },
        "reasons": reasons,
        "assumptions": assumptions,
        "createdAt": current_time.isoformat(),
    }
    draft["qualityEvaluation"] = evaluate_plan_quality(draft, assignments)
    return draft
