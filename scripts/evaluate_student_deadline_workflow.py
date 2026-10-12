"""Exercise the live student deadline workflow against the running API.

This is intentionally an API-level manual evaluation: it uses the same
authenticated contracts as the web app without mutating the learner workspace.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

BASE_URL = os.getenv("PACEWISE_API_URL", "http://localhost:8000/api/v1").rstrip("/")
EMAIL = os.getenv("PACEWISE_EVAL_EMAIL", "student@canvas.local")
PASSWORD = os.getenv("PACEWISE_EVAL_PASSWORD", "demo123")
ZONE = ZoneInfo("Asia/Ho_Chi_Minh")
FIXED_EVENT_KINDS = {
    "class",
    "class_session",
    "online_class",
    "exam",
    "quiz",
    "midterm",
    "final_exam",
    "video",
    "lecture_video",
}


def minutes(block: dict[str, Any]) -> int:
    start_hour, start_minute = map(int, block["start"].split(":"))
    end_hour, end_minute = map(int, block["end"].split(":"))
    return end_hour * 60 + end_minute - start_hour * 60 - start_minute


def overlaps(block: dict[str, Any], slot: dict[str, Any]) -> bool:
    if slot.get("date") and slot["date"] != block["date"]:
        return False
    if int(slot["weekday"]) != date.fromisoformat(block["date"]).weekday():
        return False
    block_start = int(block["start"][:2]) * 60 + int(block["start"][3:])
    block_end = int(block["end"][:2]) * 60 + int(block["end"][3:])
    slot_start = int(slot["start"][:2]) * 60 + int(slot["start"][3:])
    slot_end = int(slot["end"][:2]) * 60 + int(slot["end"][3:])
    return block_start < slot_end and slot_start < block_end


def lms_busy_slots(course_data: dict[str, Any], today: date) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for course in course_data.values():
        for item in course.get("calendarItems") or []:
            if item["id"] in seen or item.get("type") != "event":
                continue
            seen.add(item["id"])
            if item.get("event_kind") not in FIXED_EVENT_KINDS or not item.get("ends_at"):
                continue
            starts_at = datetime.fromisoformat(item["starts_at"].replace("Z", "+00:00")).astimezone(ZONE)
            ends_at = datetime.fromisoformat(item["ends_at"].replace("Z", "+00:00")).astimezone(ZONE)
            if not 0 <= (starts_at.date() - today).days <= 13:
                continue
            result.append(
                {
                    "id": f"lms-{item['id']}",
                    "label": item["title"],
                    "date": starts_at.date().isoformat(),
                    "weekday": starts_at.weekday(),
                    "start": starts_at.strftime("%H:%M"),
                    "end": ends_at.strftime("%H:%M"),
                    "source": "lms",
                    "readOnly": True,
                }
            )
    return result


def choose_tasks(tasks: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    candidates = sorted(
        (
            task
            for task in tasks
            if task.get("status") != "done"
            and 0 <= (date.fromisoformat(task["deadline"]) - today).days <= 14
        ),
        key=lambda task: (task["deadline"], task["courseId"]),
    )
    selected: list[dict[str, Any]] = []
    courses: set[str] = set()
    for task in candidates:
        if task["courseId"] in courses:
            continue
        selected.append(task)
        courses.add(task["courseId"])
        if len(selected) == 3:
            break
    if len(selected) < 3:
        raise RuntimeError("Evaluation needs one open deadline from each of three courses")
    return selected


def post_chat(client: httpx.Client, csrf: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/chat", json=payload, headers={"X-CSRF-Token": csrf})
    response.raise_for_status()
    return response.json()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    today = datetime.now(ZONE).date()
    week_start = today - timedelta(days=today.weekday())
    with httpx.Client(base_url=BASE_URL, timeout=120) as client:
        login = client.post("/auth/lms-login", json={"email": EMAIL, "password": PASSWORD})
        login.raise_for_status()
        csrf = client.cookies.get("pacewise_csrf")
        if not csrf:
            raise RuntimeError("Login did not issue a CSRF cookie")
        sync = client.get("/lms/sync")
        sync.raise_for_status()
        snapshot = sync.json()
        selected = choose_tasks(snapshot["tasks"], today)

        availability = [
            {"weekday": weekday, "enabled": True, "start": "08:00", "end": "23:00"}
            for weekday in range(7)
        ]
        manual_busy = [
            {
                "id": "eval-family",
                "label": "Việc gia đình",
                "date": today.isoformat(),
                "weekday": today.weekday(),
                "start": "16:00",
                "end": "18:00",
                "source": "manual",
            },
            {
                "id": "eval-sport",
                "label": "Thể thao",
                "date": (today + timedelta(days=1)).isoformat(),
                "weekday": (today + timedelta(days=1)).weekday(),
                "start": "19:00",
                "end": "20:30",
                "source": "manual",
            },
        ]
        unavailable = [*manual_busy, *lms_busy_slots(snapshot["courseData"], today)]
        plan_input = {
            "goal": "Bảo vệ ba deadline gần nhất của ba môn",
            "weekStart": week_start.isoformat(),
            "tasks": [
                {
                    "taskId": task["id"],
                    "remainingMin": max(0, task["estimateMin"] - task["loggedMin"]),
                }
                for task in selected
            ],
            "availability": availability,
            "unavailable": unavailable,
            "preferred": ["afternoon", "evening"],
        }
        plan_response = post_chat(
            client,
            csrf,
            {
                "message": "Lập kế hoạch học cho ba deadline gần nhất, không làm hộ bài tập.",
                "workflow": "plan",
                "context": {
                    "availability": availability,
                    "unavailable_slots": unavailable,
                    "goals": [
                        {
                            "task_id": task["id"],
                            "title": task["title"],
                            "course_id": task["courseId"],
                            "deadline": task["deadline"],
                            "remaining_minutes": max(0, task["estimateMin"] - task["loggedMin"]),
                            "weekly_goal": plan_input["goal"],
                        }
                        for task in selected
                    ],
                    "plan_input": plan_input,
                },
            },
        )
        draft = plan_response.get("output", {}).get("plan_draft")
        if not draft:
            raise RuntimeError("Plan workflow returned no canonical draft")
        blocks = draft["blocks"]
        tasks_by_id = {task["id"]: task for task in selected}

        planned_by_task = {
            task["id"]: sum(minutes(block) for block in blocks if block["taskId"] == task["id"])
            for task in selected
        }
        deadline_safe = all(
            date.fromisoformat(block["date"]) <= date.fromisoformat(tasks_by_id[block["taskId"]]["deadline"])
            for block in blocks
        )
        conflict_free = all(not overlaps(block, slot) for block in blocks for slot in unavailable)
        preferred_minutes = sum(
            minutes(block)
            for block in blocks
            if int(block["start"][:2]) >= 12
        )
        total_minutes = sum(minutes(block) for block in blocks)
        first_block_by_task = {
            task["id"]: min(
                (block for block in blocks if block["taskId"] == task["id"]),
                key=lambda block: (block["date"], block["start"]),
            )
            for task in selected
        }
        chronological_task_order = [
            task_id
            for task_id, _ in sorted(
                first_block_by_task.items(),
                key=lambda item: (item[1]["date"], item[1]["start"]),
            )
        ]
        deadline_task_order = [task["id"] for task in sorted(selected, key=lambda task: task["deadline"])]
        canonical_priority_order = [
            str(item.get("taskId")) for item in draft.get("priorityOrder", [])
        ]

        confirmation = post_chat(
            client,
            csrf,
            {
                "message": "Tôi xác nhận kế hoạch này.",
                "workflow": "plan",
                "context": {"current_plan": draft},
            },
        )

        progress_tasks = [
            {
                "id": task["id"],
                "estimate_min": task["estimateMin"],
                "logged_min": 30 if index == 0 else 0,
                "status": "in_progress" if index == 0 else "todo",
            }
            for index, task in enumerate(selected)
        ]
        tracking = post_chat(
            client,
            csrf,
            {
                "message": "Kiểm tra tiến độ và nguy cơ deadline hiện tại.",
                "workflow": "tracking",
                "context": {
                    "current_plan": draft,
                    "availability": availability,
                    "unavailable_slots": unavailable,
                    "progress_metrics": {
                        "tasks": progress_tasks,
                        "session_count": 1,
                        "studied_minutes": 30,
                    },
                },
            },
        )

        target_task = selected[0]
        target_blocks = [block for block in blocks if block["taskId"] == target_task["id"]]
        conflicted_block = target_blocks[0]
        unexpected_busy = {
            "id": "eval-unexpected-busy",
            "label": "Đi bệnh viện đột xuất",
            "date": conflicted_block["date"],
            "weekday": date.fromisoformat(conflicted_block["date"]).weekday(),
            "start": conflicted_block["start"],
            "end": conflicted_block["end"],
            "source": "manual",
        }
        recovery_unavailable = [*unavailable, unexpected_busy]
        affected = [
            block["id"]
            for block in blocks
            if overlaps(block, unexpected_busy)
        ]
        remaining = max(0, target_task["estimateMin"] - 30)
        valid_future = sum(
            minutes(block)
            for block in target_blocks
            if not overlaps(block, unexpected_busy)
        )
        deficit = max(0, remaining - valid_future)
        drift = {
            "taskId": target_task["id"],
            "courseId": target_task["courseId"],
            "kind": "capacity_gap",
            "expectedMin": planned_by_task[target_task["id"]],
            "loggedMin": 30,
            "deficitMin": deficit,
            "deadline": target_task["deadline"],
        }
        impact = {
            "id": "eval-schedule-conflict",
            "kind": "schedule_conflict",
            "constraintId": unexpected_busy["id"],
            "title": "Việc đột xuất trùng study block",
            "message": "Khoảng bận mới làm một study block không còn khả thi.",
            "courseId": target_task["courseId"],
            "taskId": target_task["id"],
            "deadline": target_task["deadline"],
            "deficitMin": deficit,
            "affectedBlockIds": affected,
            "detectedAt": datetime.now(ZONE).isoformat(),
        }
        tracking_after_change = post_chat(
            client,
            csrf,
            {
                "message": "Kiểm tra lại tiến độ sau khi xuất hiện khoảng bận đột xuất.",
                "workflow": "tracking",
                "context": {
                    "current_plan": draft,
                    "availability": availability,
                    "unavailable_slots": recovery_unavailable,
                    "progress_metrics": {
                        "tasks": progress_tasks,
                        "session_count": 1,
                        "studied_minutes": 30,
                    },
                },
            },
        )
        recovery = post_chat(
            client,
            csrf,
            {
                "message": f"Kế hoạch thiếu {deficit} phút vì có việc đột xuất. Hãy xếp lại nhưng không đổi deadline.",
                "workflow": "recover",
                "context": {
                    "current_plan": draft,
                    "progress_metrics": {"drift": drift, "plan_impact": impact},
                    "availability": availability,
                    "unavailable_slots": recovery_unavailable,
                    "proposed_milestones": [
                        {
                            "milestone_id": task["id"],
                            "title": task["title"],
                            "course_id": task["courseId"],
                            "priority": task["priority"],
                            "assignment_group": task.get("assignmentGroup"),
                            "points_possible": task.get("pointsPossible", 0),
                            "estimated_minutes": max(0, task["estimateMin"] - (30 if index == 0 else 0)),
                            "deadline": task["deadline"],
                        }
                        for index, task in enumerate(selected)
                    ],
                },
            },
        )
        options = recovery.get("recovery_options") or []
        executable_checks = []
        for option in options:
            option_blocks = option.get("new_blocks") or []
            option_deadline_safe = all(
                str(block.get("taskId")) in tasks_by_id
                and date.fromisoformat(block["date"])
                <= date.fromisoformat(tasks_by_id[str(block["taskId"])]["deadline"])
                for block in option_blocks
            )
            executable_checks.append(
                {
                    "id": option.get("id"),
                    "title": option.get("title"),
                    "fullyRecovers": bool(option.get("fully_recovers")),
                    "blockCount": len(option_blocks),
                    "conflictFree": all(
                        not overlaps(block, slot)
                        for block in option_blocks
                        for slot in recovery_unavailable
                    ),
                    "futureOnly": all(date.fromisoformat(block["date"]) >= today for block in option_blocks),
                    "deadlineSafe": option_deadline_safe,
                    "keepsTaskIds": sorted({str(block.get("taskId")) for block in option_blocks}),
                    "firstBlocks": [
                        {
                            "taskId": block.get("taskId"),
                            "date": block.get("date"),
                            "start": block.get("start"),
                            "end": block.get("end"),
                        }
                        for block in option_blocks[:3]
                    ],
                }
            )
        selected_option = next((option for option in options if option.get("fully_recovers")), None)
        recovery_confirmation = None
        if selected_option:
            recovery_confirmation = post_chat(
                client,
                csrf,
                {
                    "message": f"Tôi xác nhận phương án {selected_option.get('id', 'A')}.",
                    "workflow": "recover",
                    "context": {},
                },
            )

        report = {
            "scenario": {
                "student": login.json()["user"]["email"],
                "courses": sorted({task["courseId"] for task in selected}),
                "selectedTasks": [
                    {
                        "id": task["id"],
                        "title": task["title"],
                        "courseId": task["courseId"],
                        "deadline": task["deadline"],
                        "remainingMin": max(0, task["estimateMin"] - task["loggedMin"]),
                        "weight": (task.get("assignmentGroup") or {}).get("weight"),
                    }
                    for task in selected
                ],
                "preferred": plan_input["preferred"],
                "manualBusy": manual_busy,
                "lmsBusyCount": len(unavailable) - len(manual_busy),
            },
            "plan": {
                "agentStatus": plan_response.get("status"),
                "agentMessage": plan_response.get("response"),
                "safety": (plan_response.get("output") or {}).get("safety"),
                "feasibility": draft["feasibility"],
                "blockCount": len(blocks),
                "plannedByTask": planned_by_task,
                "deadlineSafe": deadline_safe,
                "conflictFree": conflict_free,
                "preferredTimeRate": round(preferred_minutes / total_minutes, 3) if total_minutes else 0,
                "deadlineOrder": deadline_task_order,
                "canonicalPriorityOrder": canonical_priority_order,
                "priorityOrderExposed": canonical_priority_order == deadline_task_order,
                "chronologicalFirstBlockOrder": chronological_task_order,
                "calendarOrderNote": (
                    "Calendar stays chronological; the UI shows canonical priority separately."
                ),
                "confirmationStatus": confirmation.get("status"),
                "confirmationMessage": confirmation.get("response"),
                "confirmationQuality": (confirmation.get("output") or {}).get("quality_review"),
            },
            "progress": {
                "loggedMinutes": 30,
                "agentMetrics": tracking.get("progress_metrics"),
                "riskSignals": tracking.get("risk_signals"),
                "recoverRecommended": (tracking.get("output") or {}).get("recover_recommended"),
            },
            "unexpectedChange": {
                "slot": unexpected_busy,
                "affectedBlockIds": affected,
                "derivedDrift": drift,
                "trackingRiskSignals": tracking_after_change.get("risk_signals"),
                "trackingRecoverRecommended": (tracking_after_change.get("output") or {}).get("recover_recommended"),
            },
            "recovery": {
                "agentStatus": recovery.get("status"),
                "agentMessage": recovery.get("response"),
                "safety": (recovery.get("output") or {}).get("safety"),
                "optionCount": len(options),
                "options": executable_checks,
                "confirmationStatus": recovery_confirmation.get("status") if recovery_confirmation else None,
            },
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
