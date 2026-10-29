import hashlib
import hmac
import json
from asyncio import gather
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.workspace import check_login_rate_limit, record_failed_login, revoke_session
from src.config import Settings, get_settings
from src.db import get_db
from src.persistence_models import AgentReviewCase, InstructorAction, PaceWiseSession
from src.security import (
    SessionContext,
    decode_session,
    get_current_session,
    issue_session,
    require_course,
    require_csrf,
    require_instructor,
)
from src.services.adoption_metrics import adoption_comparison, instant
from src.services.instructor_metrics import (
    completion_metrics,
    course_weekly_timeline,
    topic_metrics,
)
from src.services.instructor_workspace import (
    fold_instructor_workspace,
    pacewise_calendar_items,
)
from src.services.learning_cycle_metrics import cycle_metrics, first_plan_confirmations, load_cycle_data
from src.services.lms_client import LMSClient
from src.services.study_sessions import pause_running_session_on_logout

router = APIRouter()


class LaunchRequest(BaseModel):
    token: str = Field(min_length=20, max_length=4096)


class LMSLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)
    course_id: int | None = Field(default=None, ge=1)


class CourseSwitchRequest(BaseModel):
    course_id: int = Field(alias="courseId", ge=1)


def _client(settings: Settings) -> LMSClient:
    return LMSClient(settings)


async def _service_get_many(client, requests: list[tuple[str, dict | None]]) -> list:
    """Reuse one bounded HTTP/ASGI pool for an aggregate snapshot.

    Test doubles and external adapters only need ``service_get``; the real
    client takes the pooled fast path.
    """
    if isinstance(client, LMSClient):
        return await client.service_get_many(requests)
    return await gather(*(client.service_get(path, params) for path, params in requests))


def _parse_lms_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _weekly_completion(
    assignments: list[dict],
    submissions: list[dict],
    student_ids: set[int],
    *,
    limit: int = 8,
    as_of: datetime | None = None,
) -> list[dict]:
    return completion_metrics(assignments, submissions, student_ids,
                              as_of=as_of or datetime.now(UTC), limit=limit)["weekly"]


def _accepted_submission(item: dict | None) -> bool:
    return bool(item) and str(item.get("workflow_state") or "submitted") in {
        "submitted",
        "graded",
        "pending_review",
    }


def _display_text(value: object, fallback: str = "") -> str:
    """Repair legacy UTF-8 text that was persisted after a Latin-1 decode."""
    text = str(value or fallback).strip()
    if not any(marker in text for marker in ("Ã", "Â", "Ä", "á»", "áº")):
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _topic_catalog(outcomes: list[dict], quizzes: list[dict]) -> dict[str, str]:
    """Map stable LMS competency keys to labels an instructor can understand."""
    catalog = {
        f"outcome:{item['id']}": _display_text(
            item.get("title") or item.get("name"),
            f"Outcome {item['id']}",
        )
        for item in outcomes
        if item.get("id") is not None
    }
    for quiz in quizzes:
        quiz_title = _display_text(quiz.get("title"), f"Quiz {quiz.get('id', '')}")
        for question in quiz.get("questions") or []:
            key = f"quiz:{quiz.get('id')}:question:{question.get('id')}"
            prompt = _display_text(question.get("prompt"), "Câu hỏi chưa có tiêu đề")
            catalog[key] = f"{quiz_title}: {prompt}"
    return catalog


def _topic_label(key: object, catalog: dict[str, str]) -> str:
    value = str(key or "unclassified")
    if value in catalog:
        return catalog[value]
    if value == "unclassified":
        return "Chưa phân loại"
    return value.replace("_", " ").replace(":", " · ").strip().capitalize()


def _assignment_risk_summary(
    assignments: list[dict],
    submissions: list[dict],
    student_ids: set[int],
    *,
    as_of: datetime | None = None,
    look_ahead_days: int = 14,
    urgent_hours: int = 72,
) -> tuple[list[dict], set[int]]:
    """Return actionable near-term bottlenecks, never all future coursework.

    A student is counted only when an assignment is still unsubmitted and its
    deadline is inside the urgent part of the 14-day look-ahead window. The
    longer window is still exposed to clients so planning can inspect it, while
    the risk badge remains an actionable signal rather than an all-year count.
    """
    now = as_of or datetime.now(UTC)
    horizon = now + timedelta(days=look_ahead_days)
    urgent_until = now + timedelta(hours=urgent_hours)
    submitted = {
        (int(item.get("assignment_id") or 0), int(item.get("user_id") or 0))
        for item in submissions
        if _accepted_submission(item) or item.get("workflow_state") == "excused" or item.get("excused")
    }
    rows: list[dict] = []
    at_risk_students: set[int] = set()
    for assignment in assignments:
        if not assignment.get("published", True):
            continue
        missing = {}
        for student_id in student_ids:
            due_at = instant((assignment.get("student_due_dates") or {}).get(str(student_id), assignment.get("due_at")))
            if due_at and now <= due_at <= min(horizon, urgent_until) and (int(assignment["id"]), student_id) not in submitted:
                missing[student_id] = due_at
        if not missing:
            continue
        at_risk_students.update(missing)
        rows.append(
            {
                "assignmentId": str(assignment["id"]),
                "title": _display_text(assignment.get("title"), "Bài tập chưa đặt tên"),
                "dueAt": min(missing.values()).isoformat(),
                "atRiskCount": len(missing),
                "totalStudents": len(student_ids),
            }
        )
    rows.sort(key=lambda item: (-item["atRiskCount"], item["dueAt"], item["title"]))
    return rows[:8], at_risk_students


def _dashboard_course_summary(
    course: dict,
    enrollments: list[dict],
    assignments: list[dict],
    submissions: list[dict],
    *,
    as_of: datetime,
    schedule_items: list[dict] | None = None,
) -> tuple[dict, list[dict], list[dict]]:
    """Build teacher-authorized, per-student alerts for one selected course."""
    students = [item for item in enrollments if item.get("role") == "student"]
    student_ids = {int(item["user_id"]) for item in students}
    accepted = {
        (int(item.get("assignment_id") or 0), int(item.get("user_id") or 0))
        for item in submissions
        if _accepted_submission(item) or item.get("workflow_state") == "excused" or item.get("excused")
    }
    urgent_until = as_of + timedelta(hours=72)
    published = [item for item in assignments if item.get("published", True)]
    alerts: list[dict] = []
    overdue_students = 0

    for student in students:
        student_id = int(student["user_id"])
        overdue = upcoming = 0
        nearest_due: datetime | None = None
        for assignment in published:
            assignment_id = int(assignment.get("id") or 0)
            if (assignment_id, student_id) in accepted:
                continue
            due_at = instant(
                (assignment.get("student_due_dates") or {}).get(
                    str(student_id), assignment.get("due_at")
                )
            )
            if due_at is None:
                continue
            if due_at < as_of:
                overdue += 1
            elif due_at <= urgent_until:
                upcoming += 1
                nearest_due = min(nearest_due, due_at) if nearest_due else due_at
        if not overdue and not upcoming:
            continue
        severity = "high" if overdue >= 2 or (overdue >= 1 and upcoming >= 1) else "warning"
        overdue_students += int(overdue > 0)
        alerts.append(
            {
                "id": f"{course['id']}:{student_id}",
                "studentId": str(student_id),
                "studentName": _display_text(student.get("name"), "Sinh viên"),
                "courseId": str(course["id"]),
                "courseCode": _display_text(course.get("code"), f"Môn {course['id']}"),
                "severity": severity,
                "overdueCount": overdue,
                "upcomingCount": upcoming,
                "nearestDueAt": nearest_due.isoformat() if nearest_due else None,
            }
        )

    completion = completion_metrics(published, submissions, student_ids, as_of=as_of)
    high_risk = sum(item["severity"] == "high" for item in alerts)
    summary = {
        "id": str(course["id"]),
        "code": _display_text(course.get("code"), f"Môn {course['id']}"),
        "name": _display_text(course.get("name"), "Môn học"),
        "term": _display_text(course.get("term")),
        "studentCount": len(student_ids),
        "highRisk": high_risk,
        "openWarnings": sum(item["severity"] == "warning" for item in alerts),
        "overdue": overdue_students,
        "completionRate": completion["rate"] if completion["total"] else None,
        "completionCount": completion["count"],
        "completionTotal": completion["total"],
    }
    weeks = (
        completion["weekly"]
        if schedule_items is None
        else course_weekly_timeline(
            published,
            submissions,
            student_ids,
            schedule_items,
            as_of=as_of,
        )
    )
    return summary, alerts, weeks


def _aggregate_dashboard_weeks(course_weeks: list[list[dict]]) -> list[dict]:
    totals: dict[str, dict] = {}
    for weeks in course_weeks:
        for item in weeks:
            week_start = str(item["weekStart"])
            aggregate = totals.setdefault(
                week_start,
                {
                    "week": str(item["week"]),
                    "weekNumber": item.get("weekNumber"),
                    "weekStart": week_start,
                    "weekEnd": str(item["weekEnd"]),
                    "count": 0,
                    "total": 0,
                    "scheduledTotal": 0,
                    "taskCount": 0,
                    "lessonCount": 0,
                    "status": item.get("status"),
                },
            )
            aggregate["count"] += int(item["count"])
            aggregate["total"] += int(item["total"])
            aggregate["scheduledTotal"] += int(item.get("scheduledTotal") or 0)
            aggregate["taskCount"] += int(item.get("taskCount") or 0)
            aggregate["lessonCount"] += int(item.get("lessonCount") or 0)
    return [
        item | {"rate": item["count"] / item["total"] if item["total"] else None}
        for item in [totals[key] for key in sorted(totals)]
    ]


def _dashboard_current_week(weeks: list[dict], *, as_of: datetime) -> dict:
    local_date = as_of.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    week_start = local_date - timedelta(days=local_date.weekday())
    week_end = week_start + timedelta(days=6)
    current = next(
        (item for item in weeks if item.get("weekStart") == week_start.isoformat()),
        None,
    )
    return {
        "weekNumber": current.get("weekNumber") if current else None,
        "weekStart": week_start.isoformat(),
        "weekEnd": week_end.isoformat(),
        "rate": current["rate"] if current else None,
        "count": current["count"] if current else 0,
        "total": current["total"] if current else 0,
        "scheduledTotal": current.get("scheduledTotal", 0) if current else 0,
        "taskCount": current.get("taskCount", 0) if current else 0,
        "lessonCount": current.get("lessonCount", 0) if current else 0,
    }


def _rubric_criteria(details: dict) -> list[dict]:
    labels = {
        "understanding": "Hiểu khái niệm",
        "accuracy": "Độ chính xác",
        "process": "Quy trình và lập luận",
    }
    rubric = details.get("rubric") or {}
    if isinstance(rubric, list):
        return [item for item in rubric if isinstance(item, dict)]
    if not isinstance(rubric, dict):
        return []
    return [
        {"name": labels.get(str(key), str(key).replace("_", " ").capitalize()), "score": value}
        for key, value in rubric.items()
    ]


def _legacy_canvas_assessment(payload: dict) -> bool:
    """Hide the retired raw-quiz import path from Assessment design."""

    return str(payload.get("source") or "").strip().casefold() == "canvas quiz"


def _assessment_action_item(action: InstructorAction, payload: dict) -> dict:
    return {
        "id": action.entity_id,
        "courseId": str(action.course_id),
        "topic": payload.get("topic") or "Câu kiểm chứng",
        "question": payload.get("question") or "",
        "rubric": payload.get("rubric") or [],
        "status": payload.get("status") or "draft",
        "version": max(0, int(payload.get("version") or 0)),
        "source": payload.get("source") or "",
        "sourceResourceId": payload.get("sourceResourceId"),
        "sourceChapter": payload.get("sourceChapter"),
        "moduleId": payload.get("moduleId"),
        "answerType": payload.get("answerType") or "open",
        "knowledgeComponentIds": payload.get("knowledgeComponentIds") or [],
        "kcProvisional": bool(payload.get("kcProvisional", False)),
        "assessmentStage": payload.get("assessmentStage"),
        "assessmentSetId": payload.get("assessmentSetId"),
        "questionDesign": payload.get("questionDesign"),
        "hints": payload.get("hints") or [],
        "assignmentTitle": payload.get("assignmentTitle"),
        "weekStart": payload.get("weekStart"),
        "weekEnd": payload.get("weekEnd"),
        "aiGenerated": bool(payload.get("aiGenerated", False)),
    }


def _assessment_design_items(actions: list[InstructorAction]) -> list[dict]:
    """Fold the immutable assessment action log without touching the LMS."""

    latest: dict[str, InstructorAction] = {}
    for action in actions:
        if action.action_type == "assessment":
            latest[action.entity_id] = action
    result = []
    for action in latest.values():
        payload = json.loads(action.payload_json or "{}")
        if (
            payload.get("status") == "deleted"
            or _legacy_canvas_assessment(payload)
            or not str(payload.get("question") or "").strip()
        ):
            continue
        result.append(_assessment_action_item(action, payload))
    return result


def _evidence_details(item: dict) -> dict:
    details = item.get("details") or {}
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except json.JSONDecodeError:
            return {}
    return details if isinstance(details, dict) else {}


def _validate_claims(claims: dict, settings: Settings | None = None) -> None:
    issuer = "pacewise-native" if settings and settings.course_source_mode == "standalone" else "canvas-lms-simulator"
    if claims.get("iss") != issuer or claims.get("aud") != "pacewise":
        raise HTTPException(status_code=401, detail="Invalid LMS launch issuer or audience")
    try:
        int(claims["sub"])
        int(claims["course_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Incomplete LMS launch claims") from exc
    if claims.get("role") not in {"student", "instructor"}:
        raise HTTPException(status_code=403, detail="Unsupported LMS role")


def _set_session_cookies(
    response: Response,
    claims: dict,
    settings: Settings,
    db: Session,
    course_ids: list[int],
) -> dict:
    selected = int(claims["course_id"])
    course_ids = sorted(set(course_ids + ([selected] if selected > 0 else [])))
    token, csrf = issue_session(db, claims, settings, course_ids)
    max_age = settings.pacewise_session_minutes * 60
    secure_cookie = settings.session_cookie_secure or settings.force_https or settings.app_env == "production"
    response.set_cookie(
        settings.pacewise_session_cookie,
        token,
        max_age=max_age,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.pacewise_csrf_cookie,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=secure_cookie,
        samesite="lax",
        path="/",
    )
    return {
        "user": {
            "id": str(claims["sub"]),
            "name": claims.get("name", ""),
            "email": claims.get("email", ""),
            "role": claims["role"],
            "courseId": str(claims["course_id"]),
            "courseIds": [str(value) for value in course_ids],
        },
        "course_id": str(claims["course_id"]),
    }


@router.post("/auth/lms-launch")
async def lms_launch(
    payload: LaunchRequest,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    if settings.course_source_mode == "standalone":
        raise HTTPException(status_code=410, detail="External LMS launch is disabled")
    client = _client(settings)
    claims = await client.verify_launch(payload.token)
    _validate_claims(claims, settings)
    courses = await client.service_get("/api/pacewise/v1/courses", {"user_id": int(claims["sub"])})
    allowed = [int(item["id"]) for item in courses if item.get("enrollment_role", claims["role"]) == claims["role"]]
    # Returning from the linked LMS must not orphan the existing browser bridge.
    # Reuse only an already-authenticated session for exactly the same identity/role.
    try:
        current = decode_session(request.cookies.get(settings.pacewise_session_cookie, ""), settings, db)
    except HTTPException:
        current = None
    csrf = request.cookies.get(settings.pacewise_csrf_cookie, "")
    if (current and current.user_id == int(claims["sub"]) and current.role == claims["role"]
            and int(claims["course_id"]) in allowed and csrf
            and hmac.compare_digest(hashlib.sha256(csrf.encode()).hexdigest(), current.csrf_hash)):
        row = db.get(PaceWiseSession, current.sid)
        row.active_course_id = int(claims["course_id"])
        row.course_ids_json = json.dumps(allowed)
        db.commit()
        return {"user": current.public_user() | {"courseId": str(row.active_course_id),
                                                 "courseIds": [str(value) for value in allowed]},
                "course_id": str(row.active_course_id)}
    return _set_session_cookies(response, claims, settings, db, allowed)


@router.post("/auth/login")
@router.post("/auth/lms-login", include_in_schema=False)
async def lms_login(
    payload: LMSLoginRequest,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    """Native login in standalone mode; legacy source login only in external mode."""
    check_login_rate_limit(request, payload.email, db, settings)
    # Native auth uses the same PostgreSQL pool through another SQL namespace.
    # Release the rate-limit transaction before waiting for that operation.
    db.commit()
    client = _client(settings)
    try:
        claims = await client.login_and_create_launch(
            payload.email.strip().lower(),
            payload.password,
            payload.course_id,
        )
    except HTTPException as exc:
        if exc.status_code in {401, 403}:
            record_failed_login(request, payload.email, db)
        raise
    _validate_claims(claims, settings)
    courses = await client.service_get("/api/pacewise/v1/courses", {"user_id": int(claims["sub"])})
    allowed = [int(item["id"]) for item in courses if item.get("enrollment_role", claims["role"]) == claims["role"]]
    return _set_session_cookies(response, claims, settings, db, allowed)


@router.get("/auth/me")
async def auth_me(session: SessionContext = Depends(get_current_session)) -> dict:
    return {
        "user": session.public_user()
        | {"courseId": str(session.course_id), "courseIds": [str(value) for value in session.course_ids]}
    }


@router.post("/auth/course")
async def switch_course(
    payload: CourseSwitchRequest,
    session: SessionContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    require_course(payload.course_id, session)
    row = db.get(PaceWiseSession, session.sid)
    row.active_course_id = payload.course_id
    db.commit()
    return {"courseId": str(payload.course_id)}


@router.post("/auth/logout")
async def auth_logout(
    response: Response,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    study_session_paused = pause_running_session_on_logout(
        db,
        institution_id=settings.institution_id,
        user_id=session.user_id,
    )
    revoke_session(session, db)
    from sqlalchemy import delete

    from src.persistence_models import WebPushSubscription
    db.execute(delete(WebPushSubscription).where(WebPushSubscription.user_id == session.user_id,
                                                 WebPushSubscription.session_id == session.sid))
    db.commit()
    response.delete_cookie(settings.pacewise_session_cookie, path="/")
    response.delete_cookie(settings.pacewise_csrf_cookie, path="/")
    lms_revoked = False
    if settings.course_source_mode == "standalone":
        return {"ok": True, "linkedLmsRevoked": False, "studySessionPaused": study_session_paused}
    try:
        await _client(settings).service_post("/api/pacewise/v1/browser-bridge/revoke", {
            "user_id": session.user_id,
            "session_reference": hashlib.sha256(session.sid.encode()).hexdigest(),
        })
        lms_revoked = True
    except HTTPException:
        pass  # Local revocation is authoritative even when the LMS is offline.
    return {"ok": True, "linkedLmsRevoked": lms_revoked, "studySessionPaused": study_session_paused}


@router.post("/auth/lms-bridge")
async def lms_browser_bridge(session: SessionContext = Depends(require_csrf),
                             settings: Settings = Depends(get_settings)) -> dict:
    if settings.course_source_mode == "standalone":
        raise HTTPException(410, "PaceWise chạy độc lập; không có web LMS để chuyển sang.")
    return await _client(settings).service_post("/api/pacewise/v1/browser-bridge", {
        "user_id": session.user_id, "course_id": session.course_id, "role": session.role,
        "session_reference": hashlib.sha256(session.sid.encode()).hexdigest(),
    })


def _tone(course_id: int) -> str:
    return ("primary", "success", "accent", "warning")[course_id % 4]


def _task_status(submission: dict | None) -> str:
    return "done" if _accepted_submission(submission) or (submission or {}).get("workflow_state") == "excused" else "todo"


def _task_priority(due_at: str | None) -> str:
    if not due_at:
        return "low"
    try:
        due = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        days = (due - datetime.now(UTC)).total_seconds() / 86400
        return "high" if days <= 2 else "medium" if days <= 7 else "low"
    except ValueError:
        return "medium"


def _submission_status(submission: dict | None) -> dict:
    if not submission:
        return {
            "state": "unsubmitted",
            "attempts": 0,
            "submittedAt": None,
            "late": False,
            "score": None,
            "feedback": "",
            "rubricAssessment": {},
        }
    history = submission.get("history")
    history_attempts = history.get("attempts", []) if isinstance(history, dict) else history or []
    return {
        "state": submission.get("workflow_state") or "unsubmitted",
        "attempts": int(submission.get("attempt_count", len(history_attempts))),
        "submittedAt": submission.get("submitted_at"),
        "late": bool(submission.get("late")),
        "score": submission.get("score"),
        "feedback": submission.get("feedback") or "",
        "rubricAssessment": submission.get("rubric") or {},
    }


def _task_payload(course_id: int, assignment: dict, submission: dict | None) -> dict:
    due_at = assignment.get("due_at")
    points = float(assignment.get("points_possible") or 5)
    group = assignment.get("assignment_group") or {}
    return {
        "id": f"{course_id}:{assignment['id']}",
        "lmsAssignmentId": str(assignment["id"]),
        "title": assignment["title"],
        "courseId": str(course_id),
        "deadline": (_parse_lms_datetime(due_at) or datetime.now(UTC)).astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat(),
        "dueAt": due_at,
        "unlockAt": assignment.get("unlock_at"),
        "lockAt": assignment.get("lock_at"),
        "overrideTarget": assignment.get("override_target"),
        "estimateMin": max(30, min(240, int(points * 12))),
        "loggedMin": 0,
        "status": _task_status(submission),
        "priority": _task_priority(due_at),
        "objective": assignment.get("description") or "Hoàn thành yêu cầu của bài tập trên Canvas.",
        "estimateIsAssumption": True,
        "estimateSource": "points_heuristic",
        "pointsPossible": points,
        "assignmentGroup": {
            "id": str(group.get("id")),
            "name": group.get("name") or "",
            "weight": float(group.get("weight") or 0),
        }
        if group
        else None,
        "gradingType": assignment.get("grading_type") or "points",
        "peerReviews": bool(assignment.get("peer_reviews")),
        "groupCategoryId": str(assignment["group_category_id"])
        if assignment.get("group_category_id")
        else None,
        "rubric": assignment.get("rubric"),
        "submission": _submission_status(submission),
    }


def _shared_resource_manifest(files: list[dict]) -> list[dict]:
    """Keep sync metadata-only; binaries, extracted text and chunks stay course-owned."""

    manifests = []
    for item in files:
        latest = item.get("latest_version")
        folder = item.get("folder")
        manifests.append(
            {
                "id": item["id"],
                "title": item.get("title", ""),
                "kind": item.get("kind", "file"),
                "source_url": item.get("source_url", ""),
                "folder": ({"id": folder.get("id"), "name": folder.get("name", "")} if folder else None),
                "latest_version": (
                    {
                        "version": latest.get("version"),
                        "checksum_sha256": latest.get("checksum_sha256", ""),
                        "content_type": latest.get("content_type", ""),
                        "created_at": latest.get("created_at"),
                    }
                    if latest
                    else None
                ),
                "access_scope": [
                    {"type": scope.get("type"), "id": scope.get("id")}
                    for scope in item.get("access_scope", [])
                ],
            }
        )
    return manifests


async def _course_snapshot(
    client: LMSClient,
    course: dict,
    session: SessionContext,
    planner_items: list[dict],
    calendar_items: list[dict] | None = None,
) -> tuple[list[dict], dict]:
    course_id = int(course["id"])
    user_params = {"user_id": session.user_id}
    scoped_params = {**user_params, "summary": True} if session.role == "student" else {"summary": True}
    assignments, submissions, modules, files, appointments = await _service_get_many(client, [
        (f"/api/pacewise/v1/courses/{course_id}/assignments", scoped_params),
        (f"/api/pacewise/v1/courses/{course_id}/submissions", scoped_params),
        (f"/api/pacewise/v1/courses/{course_id}/modules", scoped_params),
        (f"/api/pacewise/v1/courses/{course_id}/files", user_params),
        (f"/api/pacewise/v1/courses/{course_id}/appointment-groups", scoped_params),
    ])
    submissions_by_assignment = {int(item["assignment_id"]): item for item in submissions}
    tasks = [
        _task_payload(
            course_id,
            {
                **item,
                # The scoped assignment endpoint is authoritative, not planner notes.
                "due_at": item.get("due_at"),
            },
            submissions_by_assignment.get(int(item["id"])),
        )
        for item in assignments
        if session.role != "student" or item.get("published", True)
    ]
    snapshot = {
        "courseId": str(course_id),
        "modules": modules,
        "resources": _shared_resource_manifest(files),
        "plannerItems": [
            item for item in planner_items if int(item.get("course_id") or 0) == course_id
        ],
        "calendarItems": [
            item
            for item in (calendar_items or [])
            if item.get("course_id") is None or int(item.get("course_id") or 0) == course_id
        ],
        "appointmentGroups": appointments,
    }
    if session.role == "instructor":
        sections, groups, analytics = await _service_get_many(client, [
            (f"/api/pacewise/v1/courses/{course_id}/sections", None),
            (f"/api/pacewise/v1/courses/{course_id}/groups", None),
            (f"/api/pacewise/v1/courses/{course_id}/analytics", None),
        ])
        snapshot.update({"sections": sections, "groups": groups, "analytics": analytics})
    return tasks, snapshot


def _guidance_payload(
    actions: list[InstructorAction],
    allowed_group_ids: set[str] | None = None,
) -> list[dict]:
    result = []
    for item in reversed(actions):
        payload = json.loads(item.payload_json or "{}")
        is_guidance = item.action_type == "guidance"
        is_class_feedback = item.action_type == "feedback" and payload.get("scope") == "class"
        is_visible_group_feedback = (
            item.action_type == "feedback"
            and payload.get("scope") == "group"
            and (
                allowed_group_ids is None
                or str(payload.get("groupId") or "") in allowed_group_ids
            )
        )
        if payload.get("message") and (
            is_guidance or is_class_feedback or is_visible_group_feedback
        ):
            result.append(
                {
                    "id": item.id,
                    "topic": payload.get("topic") or item.entity_id,
                    "message": payload["message"],
                    "at": item.created_at.isoformat(),
                    "instructorName": "Giảng viên",
                }
            )
    return result


async def _sync_payload(session: SessionContext, settings: Settings, db: Session) -> dict:
    from dataclasses import replace
    db.commit()
    client = _client(settings)
    courses = await client.service_get("/api/pacewise/v1/courses", {"user_id": session.user_id})
    # Membership is live source data, not the list frozen at first login.
    live_ids = tuple(int(item["id"]) for item in courses if item.get("enrollment_role") == session.role
                     or ("enrollment_role" not in item and int(item["id"]) in session.course_ids))
    active_id = session.course_id if session.course_id in live_ids else next(iter(live_ids), 0)
    if live_ids != session.course_ids or active_id != session.course_id:
        row = db.get(PaceWiseSession, session.sid)
        if row:
            row.course_ids_json, row.active_course_id = json.dumps(live_ids), active_id
            db.commit()
        session = replace(session, course_ids=live_ids, course_id=active_id)
    allowed_courses = [item for item in courses if int(item["id"]) in session.course_ids]
    if not allowed_courses:
        return {
            "courses": [],
            "tasks": [],
            "guidance": [],
            "assessments": [],
            "reviewResolutions": {},
            "courseData": {},
            "syncedAt": datetime.now(UTC).isoformat(),
            "source": "pacewise" if settings.course_source_mode == "standalone" else "canvas-lms-simulator",
            "activeCourseId": None,
        }
    if not any(int(item["id"]) == session.course_id for item in allowed_courses):
        raise HTTPException(status_code=403, detail="LMS enrollment no longer grants this course")
    ui_courses = [
        {
            "id": str(course["id"]),
            "code": course["code"],
            "name": course["name"],
            "tone": _tone(int(course["id"])),
        }
        for course in allowed_courses
    ]
    if session.role == "student":
        planner_items, calendar_items = await _service_get_many(
            client,
            [
                (f"/api/pacewise/v1/users/{session.user_id}/planner", None),
                (f"/api/pacewise/v1/users/{session.user_id}/calendar", None),
            ],
        )
    else:
        planner_items = []
        calendar_items = await client.service_get(
            f"/api/pacewise/v1/users/{session.user_id}/calendar"
        )
    synchronized = await gather(
        *[
            _course_snapshot(client, course, session, planner_items, calendar_items)
            for course in allowed_courses
        ]
    )
    tasks = [task for course_tasks, _snapshot in synchronized for task in course_tasks]
    course_data = {snapshot["courseId"]: snapshot for _tasks, snapshot in synchronized}
    schedule_actions = db.scalars(
        select(InstructorAction)
        .where(
            InstructorAction.course_id.in_(session.course_ids),
            InstructorAction.action_type == "schedule",
        )
        .order_by(InstructorAction.created_at)
    ).all()
    schedule_by_course: dict[int, list[InstructorAction]] = defaultdict(list)
    for action in schedule_actions:
        schedule_by_course[action.course_id].append(action)
    for course_id in session.course_ids:
        snapshot = course_data.get(str(course_id))
        if snapshot is not None:
            snapshot.setdefault("calendarItems", []).extend(
                pacewise_calendar_items(schedule_by_course.get(course_id, []), course_id)
            )
    guidance_actions = db.scalars(
        select(InstructorAction)
        .where(
            InstructorAction.course_id == session.course_id,
            InstructorAction.action_type.in_(("guidance", "feedback")),
        )
        .order_by(InstructorAction.created_at)
    ).all()
    allowed_group_ids: set[str] | None = None
    has_group_feedback = any(
        action.action_type == "feedback"
        and json.loads(action.payload_json or "{}").get("scope") == "group"
        for action in guidance_actions
    )
    db.commit()  # Do not retain a main-pool connection during native group queries.
    if session.role == "student" and has_group_feedback:
        allowed_group_ids = set()
        group_categories = await client.service_get(
            f"/api/pacewise/v1/courses/{session.course_id}/groups"
        )
        for category in group_categories:
            for group in category.get("groups") or []:
                if session.user_id in {int(value) for value in group.get("member_ids") or []}:
                    allowed_group_ids.add(str(group["id"]))
    assessment_actions = db.scalars(
        select(InstructorAction)
        .where(
            InstructorAction.course_id.in_(session.course_ids),
            InstructorAction.action_type == "assessment",
        )
        .order_by(InstructorAction.created_at)
    ).all()
    latest_assessment_actions = {
        (item.course_id, item.entity_id): item for item in assessment_actions
    }
    assessments = []
    for action in latest_assessment_actions.values():
        payload = json.loads(action.payload_json or "{}")
        if (
            payload.get("status") != "approved"
            or not str(payload.get("question") or "").strip()
            or _legacy_canvas_assessment(payload)
        ):
            continue
        item = _assessment_action_item(action, payload)
        item["version"] = max(1, int(item["version"] or 1))
        assessments.append(item)
    review_resolutions = {}
    if session.role == "student":
        review_cases = db.scalars(
            select(AgentReviewCase).where(
                AgentReviewCase.institution_id == settings.institution_id,
                AgentReviewCase.student_user_id == session.user_id,
                AgentReviewCase.course_id.in_(session.course_ids),
            )
        ).all()
        for review_case in review_cases:
            case_payload = json.loads(review_case.payload_json or "{}")
            review_resolutions[review_case.id] = {
                "status": review_case.status,
                "note": case_payload.get("instructor_note"),
                "resolvedStatus": (
                    (case_payload.get("edited_result") or {}).get("status")
                    or (case_payload.get("assessment_result") or {}).get("status")
                ),
            }
    return {
        "courses": ui_courses,
        "tasks": tasks,
        "guidance": _guidance_payload(list(guidance_actions), allowed_group_ids),
        "assessments": assessments,
        "reviewResolutions": review_resolutions,
        "courseData": course_data,
        "syncedAt": datetime.now(UTC).isoformat(),
        "source": "pacewise" if settings.course_source_mode == "standalone" else "canvas-lms-simulator",
        "activeCourseId": str(session.course_id),
    }


@router.get("/lms/sync")
async def sync_lms(
    session: SessionContext = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    return await _sync_payload(session, settings, db)


@router.get("/lms/courses/{course_id}/{resource}")
async def course_resource(
    course_id: int,
    resource: str,
    session: SessionContext = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
):
    require_course(course_id, session)
    allowed = {
        "assignments",
        "submissions",
        "modules",
        "content",
        "files",
        "grades",
        "quizzes",
        "outcomes",
        "sections",
        "groups",
        "analytics",
        "resource-folders",
        "appointment-groups",
    }
    if resource not in allowed:
        raise HTTPException(status_code=404, detail="Unsupported LMS resource")
    params = None
    if resource in {"sections", "groups", "analytics"} and session.role != "instructor":
        raise HTTPException(status_code=403, detail="Instructor role required")
    if resource in {
        "assignments",
        "submissions",
        "modules",
        "files",
        "grades",
        "quizzes",
        "outcomes",
    } and session.role == "student":
        params = {"user_id": session.user_id}
    return await _client(settings).service_get(f"/api/pacewise/v1/courses/{course_id}/{resource}", params)


@router.get("/lms/learning-evidence")
async def learning_evidence(
    session: SessionContext = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
):
    params = {"course_id": session.course_id}
    if session.role == "student":
        params["user_id"] = session.user_id
    return await _client(settings).service_get("/api/pacewise/v1/learning-evidence", params)


@router.get("/instructor/dashboard")
async def instructor_dashboard(
    session: SessionContext = Depends(require_instructor),
    settings: Settings = Depends(get_settings),
    course_id: int | None = None,
) -> dict:
    """Selected-course instructor dashboard backed only by live LMS facts."""
    now = datetime.now(UTC)
    selected_course_id = course_id or session.course_id
    if not selected_course_id:
        return {
            "summary": {"highRisk": 0, "openWarnings": 0, "overdue": 0},
            "studentAlerts": [],
            "systemNotices": [],
            "courses": [],
            "weeklyCompletion": [],
            "currentWeek": _dashboard_current_week([], as_of=now),
            "privacy": {"scope": "individual", "containsDirectIdentifiers": False},
            "generatedAt": now.isoformat(),
        }
    require_course(selected_course_id, session)

    client = _client(settings)
    all_courses, enrollments, assignments, submissions, management = await client.service_get_many(
        [
            ("/api/pacewise/v1/courses", {"user_id": session.user_id, "limit": 500}),
            (f"/api/pacewise/v1/courses/{selected_course_id}/enrollments", None),
            (f"/api/pacewise/v1/courses/{selected_course_id}/assignments", {"summary": True}),
            (f"/api/pacewise/v1/courses/{selected_course_id}/submissions", {"summary": True}),
            (
                f"/api/pacewise/v1/teacher/courses/{selected_course_id}",
                {"user_id": session.user_id},
            ),
        ]
    )
    allowed = {
        int(item["id"]): item
        for item in all_courses
        if int(item.get("id") or 0) == selected_course_id
        and item.get("enrollment_role") in {None, "instructor"}
    }
    course_ids = [selected_course_id] if selected_course_id in allowed else []
    if not course_ids:
        return {
            "summary": {"highRisk": 0, "openWarnings": 0, "overdue": 0},
            "studentAlerts": [],
            "systemNotices": [],
            "courses": [],
            "weeklyCompletion": [],
            "currentWeek": _dashboard_current_week([], as_of=now),
            "privacy": {"scope": "individual", "containsDirectIdentifiers": False},
            "generatedAt": now.isoformat(),
        }

    if not any(
        int(item.get("user_id") or 0) == session.user_id and item.get("role") == "instructor"
        for item in enrollments
    ):
        raise HTTPException(403, "Current instructor enrollment required")
    course_summaries: list[dict] = []
    student_alerts: list[dict] = []
    course_weeks: list[list[dict]] = []
    for course_id in course_ids:
        summary, alerts, weeks = _dashboard_course_summary(
            allowed[course_id],
            enrollments,
            assignments,
            submissions,
            as_of=now,
            schedule_items=management.get("lessons") or [],
        )
        course_summaries.append(summary)
        student_alerts.extend(alerts)
        course_weeks.append(weeks)

    student_alerts.sort(
        key=lambda item: (
            item["severity"] != "high",
            -int(item["overdueCount"]),
            -int(item["upcomingCount"]),
            item["studentName"],
        )
    )
    high_risk = sum(int(item["highRisk"] or 0) for item in course_summaries)
    open_warnings = sum(int(item["openWarnings"] or 0) for item in course_summaries)
    overdue = sum(int(item["overdue"] or 0) for item in course_summaries)
    system_notices = []
    for item in sorted(course_summaries, key=lambda row: (-int(row["overdue"] or 0), row["code"])):
        if item["overdue"]:
            system_notices.append(
                {
                    "id": f"overdue:{item['id']}",
                    "title": f"Rà soát deadline · {item['code']}",
                    "message": f"{item['overdue']} sinh viên đang có ít nhất một nhiệm vụ quá hạn.",
                    "at": now.isoformat(),
                    "tone": "danger",
                }
            )
        elif item["openWarnings"]:
            system_notices.append(
                {
                    "id": f"warning:{item['id']}",
                    "title": f"Theo dõi deadline · {item['code']}",
                    "message": f"{item['openWarnings']} sinh viên có deadline cần chú ý trong 72 giờ tới.",
                    "at": now.isoformat(),
                    "tone": "warning",
                }
            )

    weekly_completion = _aggregate_dashboard_weeks(course_weeks)
    return {
        "summary": {"highRisk": high_risk, "openWarnings": open_warnings, "overdue": overdue},
        "studentAlerts": student_alerts,
        "systemNotices": system_notices[:4],
        "courses": course_summaries,
        "weeklyCompletion": weekly_completion,
        "currentWeek": _dashboard_current_week(weekly_completion, as_of=now),
        "privacy": {
            "scope": "individual",
            "containsDirectIdentifiers": bool(student_alerts),
        },
        "generatedAt": now.isoformat(),
    }


@router.get("/instructor/overview")
async def instructor_overview(
    session: SessionContext = Depends(require_instructor),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    if session.course_id <= 0 or not session.course_ids:
        return {
            "classGroups": [],
            "groupStats": {},
            "reviewQueue": [],
            "assessments": [],
            "audit": [],
            "guidance": [],
            "teacherWorkspace": fold_instructor_workspace([]),
            "privacy": {
                "minimumGroupSize": 5,
                "containsDirectIdentifiers": False,
                "suppressed": True,
            },
            "lmsSummary": None,
        }
    client = _client(settings)
    course_id = session.course_id
    (
        enrollments,
        assignments,
        submissions,
        evidence,
        audits,
        outcomes,
    ) = await client.service_get_many([
        (f"/api/pacewise/v1/courses/{course_id}/enrollments", None),
        (f"/api/pacewise/v1/courses/{course_id}/assignments", {"summary": True}),
        (f"/api/pacewise/v1/courses/{course_id}/submissions", {"summary": True}),
        ("/api/pacewise/v1/learning-evidence", {"course_id": course_id, "limit": 500}),
        ("/api/pacewise/v1/audit-logs", {"course_id": course_id, "limit": 100}),
        (f"/api/pacewise/v1/courses/{course_id}/outcomes", None),
    ])
    if not any(int(item.get("user_id") or 0) == session.user_id and item.get("role") == "instructor" for item in enrollments):
        raise HTTPException(403, "Current instructor enrollment required")
    students = [item for item in enrollments if item.get("role") == "student"]
    student_ids = {int(item["user_id"]) for item in students}
    saved_actions = db.scalars(
        select(InstructorAction)
        .where(InstructorAction.course_id == course_id)
        .order_by(InstructorAction.created_at)
    ).all()
    agent_review_cases = db.scalars(
        select(AgentReviewCase)
        .where(AgentReviewCase.course_id == course_id)
        .order_by(AgentReviewCase.created_at.desc())
    ).all()
    guidance = _guidance_payload(list(saved_actions))
    teacher_workspace = fold_instructor_workspace(saved_actions)

    now = datetime.now(UTC)
    completion = completion_metrics(assignments, submissions, student_ids, as_of=now)
    on_time_count, on_time_total = completion["count"], completion["total"]
    total_students = len(student_ids)
    assignment_risks, at_risk_students = _assignment_risk_summary(
        assignments,
        submissions,
        student_ids,
        as_of=now,
    )
    topic_catalog = _topic_catalog(outcomes, [])
    group = {"id": "all", "name": "Cả lớp", "n": total_students}
    minimum_group_size = int(teacher_workspace["settings"]["minimumGroupSize"])
    if total_students < minimum_group_size:
        return {
            "classGroups": [group],
            "groupStats": {},
            "reviewQueue": [],
            "assessments": [],
            "audit": [],
            "guidance": guidance,
            "teacherWorkspace": teacher_workspace,
            "privacy": {
                "minimumGroupSize": minimum_group_size,
                "containsDirectIdentifiers": False,
                "suppressed": True,
            },
            "lmsSummary": None,
        }
    rate = on_time_count / on_time_total if on_time_total else 0
    plan_events, assessment_evidence, retention_probes = load_cycle_data(db, settings.institution_id, course_id, student_ids, now)
    adoption_at = first_plan_confirmations(db, settings.institution_id, course_id, student_ids)
    adoption = adoption_comparison(assignments, submissions, student_ids, adoption_at,
                                   as_of=now, minimum_group_size=minimum_group_size)
    weekly_completion = completion["weekly"]
    progress_improvement = (
        weekly_completion[-1]["rate"] - weekly_completion[0]["rate"]
        if len(weekly_completion) >= 2
        else None
    )
    stats = {
        "groupId": "all",
        "onTimeRate": rate,
        "onTimeCount": on_time_count,
        "onTimeTotal": on_time_total,
        "completionUnknownCount": completion["unknown"],
        "weeklyCompletion": weekly_completion,
        "topics": topic_metrics(evidence, student_ids, lambda key: _topic_label(key, topic_catalog),
                                minimum_group_size=minimum_group_size),
        "atRisk": len(at_risk_students),
        "assignmentRisks": assignment_risks,
        "riskWindowDays": 14,
        "progressImprovement": progress_improvement,
        "adoptionComparison": adoption,
        "learningCycle": cycle_metrics(plan_events, assessment_evidence, retention_probes, assignments, submissions,
                                       student_ids, as_of=now, minimum_group_size=minimum_group_size,
                                       timezone_name=settings.app_timezone, course_id=course_id),
    }
    review_queue = []
    # A low authoritative LMS grade is not an uncertain AI conclusion. Only
    # explicitly queued assessment/citation cases enter the human-review path.
    for item in agent_review_cases:
        case_payload = json.loads(item.payload_json or "{}")
        assessment_result = case_payload.get("assessment_result") or {}
        quotes = assessment_result.get("evidence_quotes") or case_payload.get("evidence_quotes") or []
        if isinstance(quotes, str):
            quotes = [quotes]
        feedback = str(assessment_result.get("feedback") or "").strip()
        review_queue.append(
            {
                "id": item.id,
                "topic": "Đánh giá hiểu bài"
                if item.case_type == "understanding_review"
                else "Khiếu nại trích dẫn",
                "question": item.entity_id,
                "responseExcerpt": str(quotes[0])
                if quotes
                else feedback or "Chưa có trích đoạn; cần yêu cầu thêm bằng chứng.",
                "confidence": "low",
                "reason": item.case_type,
                "note": case_payload.get("instructor_note"),
                "status": item.status,
                "submittedAt": item.created_at.isoformat(),
                "suggestedStatus": assessment_result.get("status"),
                "rubricVersion": case_payload.get("rubric_version"),
                "aiConclusion": feedback
                or str(assessment_result.get("status") or "Chưa đủ bằng chứng"),
                "rubricCriteria": _rubric_criteria(
                    {
                        "rubric": assessment_result.get("rubric_scores")
                        or assessment_result.get("criteria")
                        or {}
                    }
                ),
                "evidenceQuotes": [str(value) for value in quotes[:3]],
                "sourceRefs": case_payload.get("source_refs")
                or [{"label": item.entity_id, "type": item.case_type, "id": item.id}],
            }
        )
    review_by_id = {item["id"]: item for item in review_queue}
    for action in saved_actions:
        payload = json.loads(action.payload_json or "{}")
        if action.action_type == "review" and action.entity_id in review_by_id:
            if review_by_id[action.entity_id]["status"] == "superseded":
                continue  # Old teacher actions cannot reopen a resolved uncertainty.
            review_by_id[action.entity_id].update(
                {key: payload[key] for key in ("status", "note") if key in payload}
            )
    # Assessment design is authored in PaceWise. LMS quiz questions are never
    # imported into this workflow, including legacy quiz anchors.
    assessments = _assessment_design_items(saved_actions)
    audit = [
        {
            "id": str(item["id"]),
            "at": item.get("created_at", ""),
            "actor": "LMS user" if item.get("actor_user_id") else "Hệ thống",
            "action": item.get("action", "LMS event"),
        }
        for item in audits[-50:]
    ]
    audit.extend(
        {
            "id": item.id,
            "at": item.created_at.isoformat(),
            "actor": session.name,
            "action": f"{item.action_type}: {item.entity_id}",
        }
        for item in saved_actions[-50:]
    )
    return {
        "classGroups": [group],
        "groupStats": {"all": stats},
        "reviewQueue": review_queue,
        "assessments": assessments,
        "audit": audit,
        "guidance": guidance,
        "teacherWorkspace": teacher_workspace,
        "lmsSummary": None,  # LMS administration statistics do not belong to this learning dashboard.
        "privacy": {
            "minimumGroupSize": minimum_group_size,
            "containsDirectIdentifiers": False,
        },
    }


@router.get("/instructor/assessment-designs")
def instructor_assessment_designs(
    session: SessionContext = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> dict:
    """Return only the data needed by Assessment design.

    This endpoint is deliberately database-only. Opening the authoring tab must
    not wait for enrollments, submissions, outcomes, evidence, or audit APIs.
    """

    if session.course_id <= 0:
        actions: list[InstructorAction] = []
    else:
        actions = list(
            db.scalars(
                select(InstructorAction)
                .where(
                    InstructorAction.course_id == session.course_id,
                    InstructorAction.action_type.in_(("assessment", "course_structure", "settings")),
                )
                .order_by(InstructorAction.created_at)
            ).all()
        )
    workspace = fold_instructor_workspace(actions)
    minimum_group_size = int(workspace["settings"]["minimumGroupSize"])
    return {
        "classGroups": [],
        "groupStats": {},
        "reviewQueue": [],
        "assessments": _assessment_design_items(actions),
        "audit": [],
        "guidance": [],
        "teacherWorkspace": workspace,
        "privacy": {
            "minimumGroupSize": minimum_group_size,
            "containsDirectIdentifiers": False,
        },
        "lmsSummary": None,
    }
