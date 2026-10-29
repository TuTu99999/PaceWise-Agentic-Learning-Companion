import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.course_source.dates import as_utc
from src.course_source.db import get_db
from src.course_source.deadline_snapshot import course_due_overrides
from src.course_source.learning_api import (
    assignment_extension_payload,
    can_access_resource,
    submission_history_payload,
)
from src.course_source.models import (
    AppointmentGroup,
    AppointmentReservation,
    Assignment,
    AuditLog,
    CalendarEvent,
    Course,
    CourseContent,
    CourseGroup,
    CourseLifecycle,
    CourseModule,
    CourseSection,
    Enrollment,
    GradeHistory,
    GroupCategory,
    GroupMembership,
    IntegrationEvent,
    LaunchNonce,
    LearningActivity,
    LearningEvidence,
    ModuleItem,
    ModuleItemProgress,
    ModulePolicy,
    ModulePrerequisite,
    ModuleRequirement,
    OutcomeAlignment,
    PlannerItem,
    QuizAttempt,
    QuizQuestion,
    Resource,
    ResourceAccess,
    ResourceFolder,
    ResourceVersion,
    SectionMembership,
    Submission,
    SubmissionAttempt,
    SubmissionDetail,
    SubmissionWorkflow,
    User,
)
from src.course_source.pacewise_contracts import (
    course_actor,
    planner_payload,
    submission_contract,
    submission_rubric,
)
from src.course_source.telemetry import record_change

router = APIRouter()
service_router = APIRouter(prefix="/api/pacewise/v1")


class LaunchVerifyRequest(BaseModel):
    token: str


def _iso(value: datetime | None) -> str | None:
    return as_utc(value).isoformat() if value else None


def require_service_key(x_pacewise_key: str = Header(default="")) -> None:
    configured = os.getenv("PACEWISE_API_KEY", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="PACEWISE_API_KEY is not configured")
    if not x_pacewise_key or not hmac.compare_digest(x_pacewise_key, configured):
        raise HTTPException(status_code=401, detail="Invalid PaceWise API key")


def require_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.post("/api/pacewise/launch/{course_id}")
def create_launch(course_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    actor_id = getattr(request.state, "current_user_id", None)
    enrollment = db.scalar(
        select(Enrollment).where(Enrollment.user_id == actor_id, Enrollment.course_id == course_id)
    )
    if not enrollment:
        raise HTTPException(status_code=403, detail="Course enrollment required")
    user = db.get(User, actor_id)
    course = require_course(db, course_id)
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=5)
    nonce = secrets.token_urlsafe(24)
    db.add(
        LaunchNonce(
            nonce=nonce,
            user_id=user.id,
            course_id=course.id,
            role=enrollment.role,
            expires_at=expires_at,
        )
    )
    # Identity stays server-side; URLs must never contain readable JWT claims.
    launch_url = os.getenv("PACEWISE_URL", "http://localhost:5173").rstrip("/") + "/app#/launch?" + urlencode(
        {"token": nonce}
    )
    record_change(
        db,
        actor_user_id=user.id,
        action="pacewise.launch.created",
        entity_type="course",
        entity_id=course.id,
        course_id=course.id,
        metadata={"role": enrollment.role, "expires_at": expires_at},
    )
    db.commit()
    return {"launch_url": launch_url, "expires_at": expires_at.isoformat()}


@service_router.post("/launch/verify", dependencies=[Depends(require_service_key)])
def verify_launch(payload: LaunchVerifyRequest, db: Session = Depends(get_db)) -> dict:
    nonce = db.scalar(select(LaunchNonce).where(LaunchNonce.nonce == payload.token).with_for_update())
    now = datetime.now(UTC)
    if not nonce or nonce.used_at or (nonce.expires_at.replace(tzinfo=UTC) if nonce.expires_at.tzinfo is None else nonce.expires_at) <= now:
        raise HTTPException(status_code=401, detail="Launch token already used or expired")
    actor = course_actor(db, nonce.course_id, nonce.user_id)
    if actor.role != nonce.role:
        raise HTTPException(403, "Enrollment role changed; launch again")
    claimed = db.execute(update(LaunchNonce).where(LaunchNonce.nonce == nonce.nonce,
                         LaunchNonce.used_at.is_(None), LaunchNonce.expires_at > now).values(used_at=now).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(401, "Launch token already used or expired")
    user = db.get(User, nonce.user_id)
    claims = {"iss": "canvas-lms-simulator", "aud": "pacewise", "sub": str(user.id),
              "course_id": nonce.course_id, "role": actor.role, "name": user.full_name,
              "email": user.email, "exp": int(now.timestamp()) + 60}
    record_change(
        db,
        actor_user_id=nonce.user_id,
        action="pacewise.launch.consumed",
        entity_type="course",
        entity_id=nonce.course_id,
        course_id=nonce.course_id,
        metadata={"role": nonce.role},
        emit_event=False,
    )
    db.commit()
    return claims


@service_router.get("/courses", dependencies=[Depends(require_service_key)])
def courses(
    user_id: int | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    if user_id is not None and settings.google_signup_auto_enroll_courses:
        from src.course_source.membership import auto_enroll_google_student

        auto_enroll_google_student(db, user_id, settings.google_signup_auto_enroll_teacher_email)
        db.commit()
    query = select(Course).order_by(Course.id).offset(offset).limit(limit)
    if user_id is not None:
        query = (
            select(Course)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .where(Enrollment.user_id == user_id)
            .where((Enrollment.role == "instructor") | Course.published.is_(True))
            .order_by(Course.id)
            .offset(offset)
            .limit(limit)
        )
    query = query.where(~Course.id.in_(select(CourseLifecycle.course_id).where(CourseLifecycle.archived.is_(True))))
    roles = {row.course_id: row.role for row in db.scalars(select(Enrollment).where(Enrollment.user_id == user_id)).all()} if user_id is not None else {}
    return [
        {
            "id": course.id,
            "code": course.code,
            "name": course.name,
            "term": course.term,
            "published": course.published,
            **({"enrollment_role": roles[course.id]} if user_id is not None else {}),
        }
        for course in db.scalars(query).all()
    ]


@service_router.get("/courses/{course_id}/enrollments", dependencies=[Depends(require_service_key)])
def enrollments(course_id: int, db: Session = Depends(get_db)) -> list[dict]:
    require_course(db, course_id)
    rows = db.execute(
        select(Enrollment, User)
        .join(User, User.id == Enrollment.user_id)
        .where(Enrollment.course_id == course_id)
        .order_by(Enrollment.id)
    ).all()
    return [
        {
            "id": enrollment.id,
            "user_id": user.id,
            "name": user.full_name,
            "email": user.email,
            "role": enrollment.role,
            "progress": enrollment.progress,
        }
        for enrollment, user in rows
    ]


@service_router.get("/courses/{course_id}/assignments", dependencies=[Depends(require_service_key)])
def assignments(
    course_id: int,
    user_id: int | None = None,
    summary: bool = False,
    db: Session = Depends(get_db),
) -> list[dict]:
    require_course(db, course_id)
    actor = course_actor(db, course_id, user_id)
    items = db.scalars(select(Assignment).where(Assignment.course_id == course_id).order_by(Assignment.due_at)).all()
    due_overrides = course_due_overrides(db, course_id) if actor is None else {}
    if summary:
        return [
            {
                "id": item.id,
                "course_id": item.course_id,
                "title": item.title,
                "due_at": _iso(item.due_at),
                "published": item.published,
                "student_due_dates": due_overrides.get(item.id, {}),
            }
            for item in items
            if not actor or actor.role == "instructor" or item.published
        ]
    return [
        {
            "id": item.id,
            "course_id": item.course_id,
            "title": item.title,
            "description": item.description,
            "due_at": _iso(item.due_at),
            "points_possible": item.points_possible,
            "submission_types": item.submission_types.split(","),
            "published": item.published,
            **assignment_extension_payload(db, item, user_id),
            **({"student_due_dates": due_overrides.get(item.id, {})} if actor is None else {}),
        }
        for item in items
        if not actor or actor.role == "instructor" or item.published
    ]


@service_router.get("/courses/{course_id}/submissions", dependencies=[Depends(require_service_key)])
def submissions(
    course_id: int,
    user_id: int | None = None,
    summary: bool = False,
    db: Session = Depends(get_db),
) -> list[dict]:
    require_course(db, course_id)
    actor = course_actor(db, course_id, user_id)
    base = (
        select(Submission, Assignment)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .where(Assignment.course_id == course_id)
        .order_by(Submission.id)
    )
    if user_id is not None:
        base = base.where(Submission.user_id == user_id)
    if actor and actor.role != "instructor":
        base = base.where(Assignment.published.is_(True))
    if summary:
        rows = db.execute(base).all()
        submission_ids = [submission.id for submission, _assignment in rows]
        attempt_stats = {
            int(submission_id): (int(count), first_at)
            for submission_id, count, first_at in db.execute(
                select(
                    SubmissionAttempt.submission_id,
                    func.count(SubmissionAttempt.id),
                    func.min(SubmissionAttempt.submitted_at),
                )
                .where(SubmissionAttempt.submission_id.in_(submission_ids))
                .group_by(SubmissionAttempt.submission_id)
            ).all()
        } if submission_ids else {}
        workflows = {
            row.submission_id: row
            for row in db.scalars(
                select(SubmissionWorkflow).where(SubmissionWorkflow.submission_id.in_(submission_ids))
            ).all()
        } if submission_ids else {}
        result = []
        for submission, assignment in rows:
            workflow = workflows.get(submission.id)
            excused = bool(workflow and workflow.excused)
            reassigned = bool(workflow and workflow.reassigned)
            state = "excused" if excused else "reassigned" if reassigned else submission.workflow_state
            attempt_count, first_at = attempt_stats.get(submission.id, (0, None))
            result.append({
                "id": submission.id,
                "assignment_id": assignment.id,
                "user_id": submission.user_id,
                "submitted_at": _iso(submission.submitted_at),
                "workflow_state": state,
                "source_workflow_state": submission.workflow_state,
                "excused": excused,
                "reassigned": reassigned,
                "score": submission.score,
                "late": submission.late,
                "attempt_count": attempt_count,
                "first_submitted_at": _iso(first_at or submission.submitted_at),
            })
        return result
    query = (
        select(Submission, Assignment, SubmissionDetail)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .outerjoin(SubmissionDetail, SubmissionDetail.submission_id == Submission.id)
        .where(Assignment.course_id == course_id)
        .order_by(Submission.id)
    )
    if user_id is not None:
        query = query.where(Submission.user_id == user_id)
    if actor and actor.role != "instructor":
        query = query.where(Assignment.published.is_(True))
    rows = db.execute(query).all()
    return [
        {
            "id": submission.id,
            "assignment_id": assignment.id,
            "user_id": submission.user_id,
            "submitted_at": _iso(submission.submitted_at),
            **submission_contract(db, submission),
            "score": submission.score,
            "late": submission.late,
            "feedback": detail.instructor_comment if detail else "",
            "rubric": submission_rubric(db, submission.id, json.loads(detail.rubric_json or "{}") if detail else {}),
            "history": submission_history_payload(db, submission),
        }
        for submission, assignment, detail in rows
    ]


@service_router.get("/courses/{course_id}/modules", dependencies=[Depends(require_service_key)])
def modules(
    course_id: int,
    user_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    require_course(db, course_id)
    actor = course_actor(db, course_id, user_id)
    student_view = bool(actor and actor.role != "instructor")
    module_rows = db.scalars(
        select(CourseModule).where(CourseModule.course_id == course_id).order_by(CourseModule.position)
    ).all()
    if student_view:
        module_rows = [item for item in module_rows if item.published]
    module_ids = [item.id for item in module_rows]
    if not module_ids:
        return []

    item_rows = db.scalars(
        select(ModuleItem)
        .where(ModuleItem.module_id.in_(module_ids))
        .order_by(ModuleItem.module_id, ModuleItem.position)
    ).all()
    items_by_module: dict[int, list[ModuleItem]] = {module_id: [] for module_id in module_ids}
    for item in item_rows:
        items_by_module[item.module_id].append(item)

    policies = {
        item.module_id: item
        for item in db.scalars(select(ModulePolicy).where(ModulePolicy.module_id.in_(module_ids))).all()
    }
    prerequisites_by_module: dict[int, list[int]] = {module_id: [] for module_id in module_ids}
    for item in db.scalars(
        select(ModulePrerequisite)
        .where(ModulePrerequisite.module_id.in_(module_ids))
        .order_by(ModulePrerequisite.id)
    ).all():
        prerequisites_by_module[item.module_id].append(item.prerequisite_module_id)

    requirements = db.scalars(
        select(ModuleRequirement)
        .join(ModuleItem, ModuleItem.id == ModuleRequirement.module_item_id)
        .where(ModuleItem.module_id.in_(module_ids))
        .order_by(ModuleRequirement.id)
    ).all()
    module_id_by_item = {item.id: item.module_id for item in item_rows}
    requirements_by_module: dict[int, list[ModuleRequirement]] = {module_id: [] for module_id in module_ids}
    for requirement in requirements:
        module_id = module_id_by_item.get(requirement.module_item_id)
        if module_id is not None:
            requirements_by_module[module_id].append(requirement)
    progress_by_item: dict[int, ModuleItemProgress] = {}
    if user_id is not None and requirements:
        requirement_item_ids = [item.module_item_id for item in requirements]
        progress_by_item = {
            item.module_item_id: item
            for item in db.scalars(
                select(ModuleItemProgress).where(
                    ModuleItemProgress.user_id == user_id,
                    ModuleItemProgress.module_item_id.in_(requirement_item_ids),
                )
            ).all()
        }

    visible_target_ids: dict[str, set[int]] = {}
    if student_view:
        visible_target_ids["assignment"] = set(
            db.scalars(
                select(Assignment.id).where(Assignment.course_id == course_id, Assignment.published.is_(True))
            ).all()
        )
        visible_target_ids["content"] = set(
            db.scalars(
                select(CourseContent.id).where(
                    CourseContent.course_id == course_id,
                    CourseContent.published.is_(True),
                )
            ).all()
        )
        resources = db.scalars(select(Resource).where(Resource.course_id == course_id)).all()
        visible_target_ids["resource"] = _accessible_resource_ids(db, course_id, user_id, actor, resources)

    def visible(item: ModuleItem) -> bool:
        if not student_view:
            return True
        if not item.published:
            return False
        kind = item.item_type.lower()
        if item.content_id is None:
            return kind in {"external_url", "externalurl", "subheader"}
        if kind in {"resource", "file"}:
            return item.content_id in visible_target_ids["resource"]
        if kind == "assignment":
            return item.content_id in visible_target_ids["assignment"]
        return item.content_id in visible_target_ids["content"]

    result = []
    for module in module_rows:
        policy = policies.get(module.id)
        module_requirements = requirements_by_module[module.id]
        result.append(
            {
                "id": module.id,
                "name": module.name,
                "position": module.position,
                "published": module.published,
                "items": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "type": item.item_type,
                        "content_id": item.content_id,
                        "external_url": item.external_url,
                        "position": item.position,
                        "published": item.published,
                    }
                    for item in items_by_module[module.id]
                    if visible(item)
                ],
                "sequential_progress": policy.sequential_progress if policy else False,
                "prerequisite_module_ids": prerequisites_by_module[module.id],
                "requirements": [
                    {
                        "id": requirement.id,
                        "module_item_id": requirement.module_item_id,
                        "requirement_type": requirement.requirement_type,
                        "min_score": requirement.min_score,
                        "status": progress_by_item.get(requirement.module_item_id).status
                        if requirement.module_item_id in progress_by_item
                        else "not_started",
                    }
                    for requirement in module_requirements
                ],
            }
        )
    return result


@service_router.get("/courses/{course_id}/content", dependencies=[Depends(require_service_key)])
def content(course_id: int, kind: str | None = None, db: Session = Depends(get_db), user_id: int | None = None) -> list[dict]:
    require_course(db, course_id)
    actor = course_actor(db, course_id, user_id)
    query = select(CourseContent).where(CourseContent.course_id == course_id).order_by(CourseContent.id)
    if actor and actor.role != "instructor":
        query = query.where(CourseContent.published.is_(True))
    if kind:
        query = query.where(CourseContent.kind == kind)
    return [
        {
            "id": item.id,
            "kind": item.kind,
            "title": item.title,
            "body": item.body,
            "due_at": _iso(item.due_at),
            "points_possible": item.points_possible,
            "published": item.published,
        }
        for item in db.scalars(query).all()
    ]


def _accessible_resource_ids(
    db: Session,
    course_id: int,
    user_id: int | None,
    actor,
    resources: list[Resource],
) -> set[int]:
    """Resolve student resource ACLs in bounded bulk queries."""
    resource_ids = {item.id for item in resources if item.course_id == course_id}
    if user_id is None or (actor and actor.role == "instructor") or not resource_ids:
        return resource_ids
    access_by_resource: dict[int, list[ResourceAccess]] = {resource_id: [] for resource_id in resource_ids}
    for access in db.scalars(
        select(ResourceAccess).where(ResourceAccess.resource_id.in_(resource_ids))
    ).all():
        access_by_resource[access.resource_id].append(access)
    section_ids = set(
        db.scalars(select(SectionMembership.section_id).where(SectionMembership.user_id == user_id)).all()
    )
    group_ids = set(
        db.scalars(select(GroupMembership.group_id).where(GroupMembership.user_id == user_id)).all()
    )
    return {
        resource_id
        for resource_id, scopes in access_by_resource.items()
        if not scopes
        or any(
            access.permission == "read"
            and (
                (access.scope_type == "course" and access.scope_id == course_id)
                or (access.scope_type == "user" and access.scope_id == user_id)
                or (access.scope_type == "section" and access.scope_id in section_ids)
                or (access.scope_type == "group" and access.scope_id in group_ids)
            )
            for access in scopes
        )
    }


@service_router.get("/courses/{course_id}/files", dependencies=[Depends(require_service_key)])
def files(
    course_id: int,
    user_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    require_course(db, course_id)
    actor = course_actor(db, course_id, user_id)
    resources = db.scalars(
        select(Resource).where(Resource.course_id == course_id).order_by(Resource.id)
    ).all()
    resource_ids = [item.id for item in resources]
    if user_id is not None:
        allowed = _accessible_resource_ids(db, course_id, user_id, actor, resources)
        resources = [item for item in resources if item.id in allowed]
    if not resources:
        return []

    access_by_resource: dict[int, list[ResourceAccess]] = {item.id: [] for item in resources}
    for access in db.scalars(
        select(ResourceAccess)
        .where(ResourceAccess.resource_id.in_(resource_ids))
        .order_by(ResourceAccess.id)
    ).all():
        if access.resource_id in access_by_resource:
            access_by_resource[access.resource_id].append(access)

    latest_by_resource: dict[int, ResourceVersion] = {}
    for version in db.scalars(
        select(ResourceVersion)
        .where(ResourceVersion.resource_id.in_(resource_ids))
        .order_by(ResourceVersion.resource_id, ResourceVersion.version.desc())
    ).all():
        latest_by_resource.setdefault(version.resource_id, version)
    folder_ids = {
        version.folder_id for version in latest_by_resource.values() if version.folder_id is not None
    }
    folders = {
        folder.id: folder
        for folder in db.scalars(select(ResourceFolder).where(ResourceFolder.id.in_(folder_ids))).all()
    } if folder_ids else {}
    module_by_resource = {
        int(content_id): name
        for content_id, name in db.execute(
            select(ModuleItem.content_id, CourseModule.name)
            .join(CourseModule, CourseModule.id == ModuleItem.module_id)
            .where(
                CourseModule.course_id == course_id,
                ModuleItem.item_type == "resource",
                ModuleItem.content_id.in_(resource_ids),
            )
            .order_by(CourseModule.position, CourseModule.id)
        ).all()
        if content_id is not None
    }
    course = db.get(Course, course_id)

    return [
        {
            "id": item.id,
            "title": item.title,
            "kind": item.kind,
            "source_url": item.source_url,
            "course_code": course.code if course else str(course_id),
            "course_name": course.name if course else "",
            "planning_chapter": module_by_resource.get(item.id, ""),
            "folder": (
                {"id": folders[latest_by_resource[item.id].folder_id].id,
                 "name": folders[latest_by_resource[item.id].folder_id].name}
                if item.id in latest_by_resource
                and latest_by_resource[item.id].folder_id in folders
                else None
            ),
            "latest_version": (
                {
                    "id": latest_by_resource[item.id].id,
                    "version": latest_by_resource[item.id].version,
                    "checksum_sha256": latest_by_resource[item.id].checksum_sha256,
                    "size_bytes": latest_by_resource[item.id].size_bytes,
                    "content_type": latest_by_resource[item.id].content_type,
                    "created_at": _iso(latest_by_resource[item.id].created_at),
                }
                if item.id in latest_by_resource
                else None
            ),
            "access_scope": [
                {"type": access.scope_type, "id": access.scope_id, "permission": access.permission}
                for access in access_by_resource[item.id]
            ],
        }
        for item in resources
    ]


@service_router.get("/courses/{course_id}/files/{resource_id}/download", dependencies=[Depends(require_service_key)])
def download_resource(course_id: int, resource_id: int, user_id: int | None = None, db: Session = Depends(get_db)):
    from pathlib import Path

    from fastapi.responses import FileResponse

    from src.course_source.uploads import MAX_UPLOAD_BYTES, UPLOAD_DIR

    resource = db.get(Resource, resource_id)
    if not resource or resource.course_id != course_id:
        raise HTTPException(status_code=404, detail="Resource not found")
    if user_id is not None and not can_access_resource(db, resource, user_id):
        raise HTTPException(status_code=403, detail="You cannot access this resource")
    if resource.source_url.startswith("pacewise-object://"):
        from fastapi.responses import Response

        from src.config import get_settings
        from src.services.course_object_store import download_bytes

        settings = get_settings()
        if settings.course_storage_backend != "s3":
            raise HTTPException(status_code=503, detail="Object storage is unavailable")
        try:
            data = download_bytes(settings, resource.source_url, settings.course_pdf_max_mb * 1024 * 1024)
        except ValueError as exc:
            raise HTTPException(status_code=413, detail="File exceeds the configured limit") from exc
        return Response(data, media_type="application/octet-stream")
    # Only simulator-owned files; never follow user-controlled external URLs.
    if resource.source_url.startswith("/static/mock-files/"):
        # Bundled demo slides are simulator-owned too; no external URL fetch.
        from src.config import get_settings
        demo_root = Path(get_settings().course_mock_file_dir).resolve()
        name = resource.source_url.removeprefix("/static/mock-files/")
        path = (demo_root / name).resolve()
        if Path(name).name != name or path.parent != demo_root or not path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        if path.stat().st_size > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds 20 MB")
        return FileResponse(path, filename=resource.title)
    if not resource.source_url.startswith("/api/files/"):
        raise HTTPException(status_code=422, detail="External resources cannot be downloaded by the indexer")
    name = resource.source_url.removeprefix("/api/files/")
    if Path(name).name != name or not name.startswith(f"course-{course_id}-"):
        raise HTTPException(status_code=404, detail="File not found")
    path = (UPLOAD_DIR / name).resolve()
    if path.parent != UPLOAD_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB")
    return FileResponse(path, filename=resource.title)


@service_router.get("/courses/{course_id}/sections", dependencies=[Depends(require_service_key)])
def sections(course_id: int, db: Session = Depends(get_db)) -> list[dict]:
    require_course(db, course_id)
    result = []
    for section in db.scalars(select(CourseSection).where(CourseSection.course_id == course_id)).all():
        result.append(
            {
                "id": section.id,
                "name": section.name,
                "member_ids": db.scalars(
                    select(SectionMembership.user_id).where(SectionMembership.section_id == section.id)
                ).all(),
            }
        )
    return result


@service_router.get("/courses/{course_id}/groups", dependencies=[Depends(require_service_key)])
def groups(course_id: int, db: Session = Depends(get_db)) -> list[dict]:
    require_course(db, course_id)
    result = []
    categories = db.scalars(select(GroupCategory).where(GroupCategory.course_id == course_id)).all()
    for category in categories:
        category_groups = []
        for group in db.scalars(select(CourseGroup).where(CourseGroup.category_id == category.id)).all():
            category_groups.append(
                {
                    "id": group.id,
                    "name": group.name,
                    "member_ids": db.scalars(
                        select(GroupMembership.user_id).where(GroupMembership.group_id == group.id)
                    ).all(),
                }
            )
        result.append(
            {
                "id": category.id,
                "name": category.name,
                "self_signup": category.self_signup,
                "groups": category_groups,
            }
        )
    return result


@service_router.get("/courses/{course_id}/analytics", dependencies=[Depends(require_service_key)])
def analytics(course_id: int, db: Session = Depends(get_db)) -> dict:
    require_course(db, course_id)
    activities = db.scalars(
        select(LearningActivity).where(LearningActivity.course_id == course_id)
    ).all()
    by_type: dict[str, int] = {}
    total_duration = 0
    active_users: set[int] = set()
    for item in activities:
        by_type[item.activity_type] = by_type.get(item.activity_type, 0) + 1
        total_duration += item.duration_seconds
        active_users.add(item.user_id)
    return {
        "events": len(activities),
        "active_users": len(active_users),
        "duration_seconds": total_duration,
        "by_type": by_type,
    }


@service_router.get("/users/{user_id}/planner", dependencies=[Depends(require_service_key)])
def planner(user_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")
    items = db.scalars(
        select(PlannerItem)
        .where(PlannerItem.user_id == user_id)
        .order_by(PlannerItem.due_at)
    ).all()
    return [payload for item in items if (payload := planner_payload(db, item)) is not None]


@service_router.get("/users/{user_id}/calendar", dependencies=[Depends(require_service_key)])
def user_calendar(user_id: int, db: Session = Depends(get_db)) -> list[dict]:
    """Return fixed calendar commitments used by PaceWise planning.

    Assignment deadlines remain in the assignment API. This endpoint exposes
    events with an actual start/end range so PaceWise can treat them as dynamic
    constraints and react when an instructor moves or removes one.
    """
    from src.course_source.schedule_policy import REMOVED_SCHEDULE_KINDS
    from src.course_source.teacher_management import lesson_metadata
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    enrolled_course_ids = set(
        db.scalars(select(Enrollment.course_id).join(Course, Course.id == Enrollment.course_id)
                   .where(Enrollment.user_id == user_id, (Enrollment.role == "instructor") | Course.published.is_(True),
                          ~Course.id.in_(select(CourseLifecycle.course_id).where(CourseLifecycle.archived.is_(True))))).all()
    )
    events = db.scalars(
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user_id,
            (CalendarEvent.attendance_status.is_(None) | (CalendarEvent.attendance_status != "cancelled")),
            CalendarEvent.event_kind.not_in(REMOVED_SCHEDULE_KINDS),
            (CalendarEvent.course_id.is_(None) | CalendarEvent.course_id.in_(enrolled_course_ids)),
        )
        .order_by(CalendarEvent.starts_at)
    ).all()
    courses = {
        item.id: item
        for item in db.scalars(select(Course).where(Course.id.in_(enrolled_course_ids))).all()
    }
    fixed_events = [
        {
            "id": f"event-{item.id}",
            "source_id": item.id,
            "type": "event",
            "course_id": item.course_id,
            "course_code": courses[item.course_id].code if item.course_id in courses else None,
            "title": item.title,
            "starts_at": _iso(item.starts_at),
            "ends_at": _iso(item.ends_at),
            "duration_minutes": (
                max(0, int((item.ends_at - item.starts_at).total_seconds() // 60))
                if item.ends_at
                else None
            ),
            "event_kind": item.event_kind,
            "resource_ids": lesson_metadata(item).get("resource_ids", []),
            "attendance_status": item.attendance_status,
            "editable": not (
                item.description.startswith("pacewise-2026-v1;")
                or item.description.startswith("course-activity-v1;")
            ),
            "location": lesson_metadata(item).get("location", ""),
            "meeting_url": item.join_url,
        }
        for item in events
    ]
    reservations = db.execute(
        select(AppointmentReservation, AppointmentGroup)
        .join(AppointmentGroup, AppointmentGroup.id == AppointmentReservation.appointment_group_id)
        .where(AppointmentReservation.user_id == user_id, AppointmentGroup.course_id.in_(enrolled_course_ids))
    ).all()
    fixed_events.extend({
        "id": f"appointment-{reservation.id}", "source_id": reservation.id, "type": "event",
        "course_id": group.course_id, "course_code": courses[group.course_id].code,
        "title": group.title, "starts_at": _iso(reservation.starts_at), "ends_at": _iso(reservation.ends_at),
        "duration_minutes": group.slot_minutes, "event_kind": "appointment", "editable": False,
    } for reservation, group in reservations)
    return sorted(fixed_events, key=lambda item: item["starts_at"])


@service_router.get(
    "/courses/{course_id}/appointment-groups",
    dependencies=[Depends(require_service_key)],
)
def appointment_groups(course_id: int, db: Session = Depends(get_db), user_id: int | None = None) -> list[dict]:
    require_course(db, course_id)
    actor = course_actor(db, course_id, user_id)
    items = db.scalars(
        select(AppointmentGroup).where(AppointmentGroup.course_id == course_id)
    ).all()
    return [
        {
            "id": item.id,
            "title": item.title,
            "starts_at": _iso(item.starts_at),
            "ends_at": _iso(item.ends_at),
            "slot_minutes": item.slot_minutes,
            "participants_per_slot": item.participants_per_slot,
            "reservations": [
                {
                    "id": reservation.id,
                    "user_id": reservation.user_id,
                    "starts_at": _iso(reservation.starts_at),
                    "ends_at": _iso(reservation.ends_at),
                }
                for reservation in db.scalars(
                    select(AppointmentReservation).where(
                        AppointmentReservation.appointment_group_id == item.id
                    )
                ).all()
                if not actor or actor.role == "instructor" or reservation.user_id == user_id
            ],
        }
        for item in items
    ]


@service_router.get("/courses/{course_id}/resource-folders", dependencies=[Depends(require_service_key)])
def resource_folders(course_id: int, db: Session = Depends(get_db)) -> list[dict]:
    require_course(db, course_id)
    return [
        {
            "id": item.id,
            "parent_id": item.parent_id,
            "name": item.name,
        }
        for item in db.scalars(
            select(ResourceFolder)
            .where(ResourceFolder.course_id == course_id)
            .order_by(ResourceFolder.parent_id, ResourceFolder.name)
        ).all()
    ]


@service_router.get("/courses/{course_id}/grades", dependencies=[Depends(require_service_key)])
def grades(course_id: int, user_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    current = submissions(course_id, user_id=user_id, db=db)
    actor = course_actor(db, course_id, user_id)
    assignment_ids = select(Assignment.id).where(Assignment.course_id == course_id)
    if actor and actor.role != "instructor":
        assignment_ids = assignment_ids.where(Assignment.published.is_(True))
    history_query = select(GradeHistory).where(GradeHistory.assignment_id.in_(assignment_ids)).order_by(
        GradeHistory.graded_at
    )
    if user_id is not None:
        history_query = history_query.where(GradeHistory.user_id == user_id)
    history = db.scalars(history_query).all()
    return {
        "current": current,
        "history": [
            {
                "id": item.id,
                "submission_id": item.submission_id,
                "assignment_id": item.assignment_id,
                "user_id": item.user_id,
                "grader_id": item.grader_id,
                "score": item.score,
                "comment": item.comment,
                "rubric": json.loads(item.rubric_json or "{}"),
                "graded_at": _iso(item.graded_at),
            }
            for item in history
        ],
    }


@service_router.get("/courses/{course_id}/quizzes", dependencies=[Depends(require_service_key)])
def quizzes(
    course_id: int,
    user_id: int | None = None,
    include_answers: bool = False,
    db: Session = Depends(get_db),
) -> list[dict]:
    require_course(db, course_id)
    actor = course_actor(db, course_id, user_id)
    if include_answers and actor and actor.role != "instructor":
        raise HTTPException(403, "Quiz answer keys are instructor-only")
    quiz_items = db.scalars(
        select(CourseContent).where(CourseContent.course_id == course_id, CourseContent.kind == "quiz")
    ).all()
    result = []
    for quiz in quiz_items:
        if actor and actor.role != "instructor" and not quiz.published:
            continue
        questions = db.scalars(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id)).all()
        attempts_query = select(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id)
        if user_id is not None:
            attempts_query = attempts_query.where(QuizAttempt.user_id == user_id)
        attempts = db.scalars(attempts_query).all()
        result.append(
            {
                "id": quiz.id,
                "title": quiz.title,
                "due_at": _iso(quiz.due_at),
                "questions": [
                    {
                        "id": q.id,
                        "prompt": q.prompt,
                        "points": q.points,
                        "position": q.position,
                        "question_type": "closed" if q.correct_answer else "open",
                        **({"correct_answer": q.correct_answer} if include_answers else {}),
                    }
                    for q in questions
                ],
                "attempts": [
                    {
                        "id": attempt.id,
                        "user_id": attempt.user_id,
                        "score": attempt.score,
                        "submitted_at": _iso(attempt.submitted_at),
                    }
                    for attempt in attempts
                ],
            }
        )
    return result


@service_router.get("/courses/{course_id}/outcomes", dependencies=[Depends(require_service_key)])
def outcomes(course_id: int, user_id: int | None = None, db: Session = Depends(get_db)) -> list[dict]:
    require_course(db, course_id)
    actor = course_actor(db, course_id, user_id)
    items = db.scalars(
        select(CourseContent).where(CourseContent.course_id == course_id, CourseContent.kind == "outcome")
    ).all()
    result = []
    for item in items:
        if actor and actor.role != "instructor" and not item.published:
            continue
        alignments = db.scalars(select(OutcomeAlignment).where(OutcomeAlignment.outcome_id == item.id)).all()
        evidence_query = select(LearningEvidence).where(
            LearningEvidence.course_id == course_id,
            LearningEvidence.competency_key == f"outcome:{item.id}",
        )
        if user_id is not None:
            evidence_query = evidence_query.where(LearningEvidence.user_id == user_id)
        evidence = db.scalars(evidence_query).all()
        result.append(
            {
                "id": item.id,
                "title": item.title,
                "description": item.body,
                "mastery_points": item.points_possible,
                "assignment_ids": [alignment.assignment_id for alignment in alignments],
                "evidence_count": len(evidence),
            }
        )
    return result


@service_router.get("/learning-evidence", dependencies=[Depends(require_service_key)])
def learning_evidence(
    user_id: int | None = None,
    course_id: int | None = None,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(LearningEvidence).where(LearningEvidence.id > after_id)
    if user_id is not None:
        query = query.where(LearningEvidence.user_id == user_id)
    if course_id is not None:
        query = query.where(LearningEvidence.course_id == course_id)
    query = query.order_by(LearningEvidence.id).limit(limit)
    return [
        {
            "id": item.id,
            "user_id": item.user_id,
            "course_id": item.course_id,
            "evidence_type": item.evidence_type,
            "source_type": item.source_type,
            "source_id": item.source_id,
            "competency_key": item.competency_key,
            "score": item.score,
            "max_score": item.max_score,
            "details": json.loads(item.details_json or "{}"),
            "observed_at": _iso(item.observed_at),
        }
        for item in db.scalars(query).all()
    ]


@service_router.get("/events", dependencies=[Depends(require_service_key)])
def events(
    after_id: int = Query(default=0, ge=0),
    course_id: int | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(IntegrationEvent).where(IntegrationEvent.id > after_id)
    if course_id is not None:
        query = query.where(IntegrationEvent.course_id == course_id)
    query = query.order_by(IntegrationEvent.id).limit(limit)
    return [
        {
            "id": item.id,
            "type": item.event_type,
            "aggregate_type": item.aggregate_type,
            "aggregate_id": item.aggregate_id,
            "course_id": item.course_id,
            "actor_user_id": item.actor_user_id,
            "payload": json.loads(item.payload_json or "{}"),
            "created_at": _iso(item.created_at),
        }
        for item in db.scalars(query).all()
    ]


@service_router.get("/audit-logs", dependencies=[Depends(require_service_key)])
def audit_logs(
    after_id: int = Query(default=0, ge=0),
    course_id: int | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(AuditLog).where(AuditLog.id > after_id)
    if course_id is not None:
        query = query.where(AuditLog.course_id == course_id)
    query = query.order_by(AuditLog.id).limit(limit)
    return [
        {
            "id": item.id,
            "actor_user_id": item.actor_user_id,
            "action": item.action,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "course_id": item.course_id,
            "metadata": json.loads(item.metadata_json or "{}"),
            "created_at": _iso(item.created_at),
        }
        for item in db.scalars(query).all()
    ]


router.include_router(service_router)
