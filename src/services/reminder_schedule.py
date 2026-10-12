"""Reconcile bounded, deterministic reminders from a student's saved workspace.

Only confirmed plan blocks are used. Assessment/chat text is never a push payload.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.persistence_models import NotificationJob
from src.services.notification_policy import ReminderPreferences

LOCAL = ZoneInfo("Asia/Ho_Chi_Minh")


def replan_href(trigger: str, **context: str | None) -> str:
    return "/plan?" + urlencode({"reanalyze": trigger, **{key: value for key, value in context.items() if value}})


def parse_time(value: str | None) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=LOCAL) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError):
        return None


def candidates(state: dict, now: datetime) -> list[dict]:
    preferences = ReminderPreferences.model_validate((state.get("reminders") or {}).get("preferences") or {})
    blocks = (state.get("plan") or {}).get("blocks") or []
    progress = state.get("taskProgress") or {}
    tasks = {}
    for task in (state.get("lmsBaseline") or {}).get("tasks") or []:
        if not task.get("id"):
            continue
        merged = {**task, **(progress.get(str(task["id"])) or {})}
        # A stale local progress record must never undo authoritative LMS completion.
        if task.get("status") == "done":
            merged["status"] = "done"
        merged["submission"] = task.get("submission")
        tasks[str(task["id"])] = merged
    jobs: dict[str, dict] = {}

    def add(key: str, kind: str, at: datetime | None, until: datetime | None, href: str, rank: int = 2):
        if at is None or until is None or not preferences.allows(kind):
            return
        if until < now or at > now + timedelta(days=15):
            return
        jobs[key] = {"key": key, "kind": kind, "at": at, "until": until, "href": href, "rank": rank}

    def submitted(task: dict) -> bool:
        submission = task.get("submission") or {}
        return (
            task.get("status") == "done"
            or bool(submission.get("submittedAt") or submission.get("attempts"))
            or submission.get("state") in {"submitted", "graded"}
        )

    for task_id, task in tasks.items():
        if submitted(task):
            continue
        due = parse_time(task.get("dueAt") or f"{task.get('deadline')}T23:59:00+07:00")
        if not due:
            continue
        remaining = max(0, int(task.get("estimateMin") or 0) - int(task.get("loggedMin") or 0))
        future = 0
        for block in blocks:
            start = parse_time(f"{block.get('date')}T{block.get('start')}:00+07:00")
            end = parse_time(f"{block.get('date')}T{block.get('end')}:00+07:00")
            if block.get("taskId") == task_id and start and end and now <= start < due:
                future += max(0, round((end - start).total_seconds() / 60))
        for hours, next_hours in ((72, 24), (24, 2), (2, -2)):
            if hours == 72 and task.get("loggedMin") and future >= remaining:
                continue
            add(
                f"deadline-{hours}h:{task_id}:{due.astimezone(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')}",
                f"deadline_{hours}h",
                due - timedelta(hours=hours),
                due - timedelta(hours=next_hours),
                replan_href("deadline", taskId=task_id, courseId=str(task.get("courseId") or ""))
                if hours == 2 else f"/study/{quote(task_id, safe='')}",
                0 if hours == 2 else 1,
            )

    completed_blocks = {session.get("blockId") for session in state.get("sessions") or []}
    for block in blocks:
        task = tasks.get(str(block.get("taskId")))
        if not task or submitted(task):
            continue
        start = parse_time(f"{block.get('date')}T{block.get('start')}:00+07:00")
        if start and block.get("id") not in completed_blocks:
            key = f"study-block:{block['id']}:{start.astimezone(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')}"
            add(
                key,
                "study_block",
                start - timedelta(minutes=preferences.study_lead),
                start + timedelta(minutes=15),
                f"/study/{quote(str(task['id']), safe='')}/session?blockId={quote(str(block['id']), safe='')}",
            )
        end = parse_time(f"{block.get('date')}T{block.get('end')}:00+07:00")
        if end and end <= now:
            expected = 0
            for other in blocks:
                other_end = parse_time(f"{other.get('date')}T{other.get('end')}:00+07:00")
                other_start = parse_time(f"{other.get('date')}T{other.get('start')}:00+07:00")
                if other.get("taskId") == task["id"] and other_end and other_start and other_end <= end:
                    expected += max(0, round((other_end - other_start).total_seconds() / 60))
            actual = max(
                int(task.get("loggedMin") or 0),
                sum(
                    int(session.get("minutes") or 0)
                    for session in state.get("sessions") or []
                    if session.get("taskId") == task["id"]
                ),
            )
            if actual + 10 < expected:
                add(
                    f"missed-block:{block['id']}:{end.astimezone(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')}",
                    "missed_block",
                    end,
                    end + timedelta(hours=48),
                    replan_href("progress", taskId=str(task["id"]), courseId=str(task.get("courseId") or "")),
                    1,
                )

    block_by_id = {block.get("id"): block for block in blocks}
    reflected = {
        reflection.get("activityId")
        for reflection in (state.get("reflections") or {}).values()
        if reflection.get("scope") == "activity"
    }
    for session in state.get("sessions") or []:
        block = block_by_id.get(session.get("blockId"))
        activity = f"study:{block['id']}" if block else f"session:{session['id']}"
        if activity in reflected:
            continue
        completed = parse_time(session.get("completedAt"))
        if not completed and block:
            completed = parse_time(f"{block.get('date')}T{block.get('end')}:00+07:00")
        if completed:
            add(
                f"reflect-session:{session['id']}",
                "reflect_session",
                completed + timedelta(minutes=5),
                completed + timedelta(days=1),
                f"/reflect?activity={quote(activity, safe='')}",
            )

    # Course sessions/quizzes/exams also remain available after closing the tab.
    course_data = (state.get("lmsBaseline") or {}).get("courseData") or {}
    rules = {
        "class": [(10, "online_class")],
        "class_session": [(10, "online_class")],
        "quiz": [(30, "quiz")],
        "midterm": [(1440, "exam_24h"), (60, "exam_60m")],
        "final_exam": [(1440, "exam_24h"), (60, "exam_60m")],
    }
    for course in course_data.values():
        for event in course.get("calendarItems") or []:
            start = parse_time(event.get("starts_at"))
            if event.get("type") != "event" or not start:
                continue
            for lead, kind in rules.get(event.get("event_kind"), []):
                add(
                    f"{kind}:{event['id']}:{start.astimezone(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')}",
                    kind,
                    start - timedelta(minutes=lead),
                    start + timedelta(minutes=15),
                    "/plan",
                    1,
                )
    for impact in state.get("planImpacts") or []:
        if impact.get("kind") not in {"schedule_conflict", "deadline_earlier", "assignment_added"}:
            continue
        at = parse_time(impact.get("detectedAt"))
        if at:
            add(f"lms-change:{impact['id']}", "lms_change", at, at + timedelta(days=14),
                replan_href("lms", impactId=str(impact["id"]), taskId=impact.get("taskId"), courseId=impact.get("courseId")), 1)
    digest_at = now.astimezone(LOCAL).replace(hour=preferences.digest_hour, minute=0, second=0, microsecond=0)
    digest_items = [
        item
        for item in jobs.values()
        if item["rank"] == 2 and digest_at < item["at"] <= digest_at + timedelta(hours=28)
    ]
    if digest_items:
        add(
            f"evening-digest:{digest_at.date().isoformat()}",
            "evening_digest",
            digest_at,
            digest_at + timedelta(hours=4),
            "/plan",
        )
    return sorted(jobs.values(), key=lambda item: (item["rank"], item["at"]))[:256]


def reconcile_jobs(db: Session, user_id: int, state: dict, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    existing = {
        job.id: job
        for job in db.scalars(
            select(NotificationJob).where(
                NotificationJob.user_id == user_id, NotificationJob.expires_at >= now - timedelta(days=30)
            )
        )
    }
    retained = set()
    receipts = (state.get("reminders") or {}).get("deliveredAt") or {}
    for item in candidates(state, now):
        key = hashlib.sha256(f"{user_id}:{item['key']}".encode()).hexdigest()
        retained.add(key)
        job = existing.get(key) or NotificationJob(id=key, user_id=user_id, reminder_key=item["key"])
        job.idempotency_key = f"notification:{key}"
        job.kind, job.scheduled_at, job.expires_at = item["kind"], item["at"], item["until"]
        job.payload_json = json.dumps(
            {
                "title": "PaceWise · Nhắc học",
                "body": "Mở PaceWise để xem ca học, deadline hoặc phản tư cần hoàn thành.",
                "href": item["href"],
                "tag": item["key"],
            }
        )
        job.priority = item["rank"]
        if job.status in {None, "cancelled"}:
            job.status = "pending"
            job.queued_at = None
        if item["key"] in receipts:
            job.status = "delivered"
            job.delivered_at = parse_time(receipts[item["key"]])
        db.add(job)
    for key, job in existing.items():
        if key not in retained and job.status == "pending":
            job.status = "cancelled"
