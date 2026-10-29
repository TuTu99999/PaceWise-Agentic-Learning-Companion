import hashlib
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.course_source.dates import LMSDateTime, as_utc
from src.course_source.db import get_db
from src.course_source.models import (
    AppointmentGroup,
    AppointmentReservation,
    Assignment,
    AssignmentConfiguration,
    AssignmentGroup,
    AssignmentOverride,
    AssignmentRubric,
    Course,
    CourseGroup,
    CourseLifecycle,
    CourseModule,
    CourseSection,
    Enrollment,
    GroupCategory,
    GroupMembership,
    LearningActivity,
    ModuleItem,
    ModuleItemProgress,
    ModulePolicy,
    ModulePrerequisite,
    ModuleRequirement,
    PlannerItem,
    QuizAssignmentLink,
    Resource,
    ResourceAccess,
    ResourceFolder,
    ResourceVersion,
    Rubric,
    RubricAssessment,
    RubricCriterion,
    RubricRating,
    SectionMembership,
    Submission,
    SubmissionAttachment,
    SubmissionAttempt,
    SubmissionComment,
    SubmissionWorkflow,
    TeacherTaskMetadata,
    User,
)
from src.course_source.pacewise_contracts import course_actor
from src.course_source.telemetry import record_change

router = APIRouter(prefix="/api", tags=["learning-structure"])


class AssignmentGroupPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    position: int = Field(default=1, ge=1)
    group_weight: float = Field(default=0, ge=0, le=100)
    drop_lowest: int = Field(default=0, ge=0)
    drop_highest: int = Field(default=0, ge=0)


class AssignmentPolicyPayload(BaseModel):
    assignment_group_id: int | None = None
    unlock_at: LMSDateTime | None = None
    lock_at: LMSDateTime | None = None
    grading_type: str = "points"
    peer_reviews: bool = False
    group_category_id: int | None = None


class AssignmentOverridePayload(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    target_type: str
    target_id: int
    due_at: LMSDateTime | None = None
    unlock_at: LMSDateTime | None = None
    lock_at: LMSDateTime | None = None


class NamedPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class SectionMemberPayload(BaseModel):
    member_id: int


class GroupCategoryPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    self_signup: bool = False


class ModuleRulesPayload(BaseModel):
    prerequisite_module_ids: list[int] = Field(default_factory=list)
    requirements: list[dict] = Field(default_factory=list)
    sequential_progress: bool = False


class ModuleProgressPayload(BaseModel):
    status: str


class CommentPayload(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class SubmissionWorkflowPayload(BaseModel):
    excused: bool = False
    reassigned: bool = False


class RubricRatingPayload(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    points: float = Field(ge=0)


class RubricCriterionPayload(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    long_description: str = ""
    points: float = Field(ge=0)
    ratings: list[RubricRatingPayload] = Field(default_factory=list)


class RubricPayload(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    criteria: list[RubricCriterionPayload] = Field(min_length=1)


class RubricAssessmentPayload(BaseModel):
    ratings: dict[int, float]
    comments: dict[int, str] = Field(default_factory=dict)


class ResourceVersionPayload(BaseModel):
    source_url: str = Field(min_length=1, max_length=1000)
    checksum_sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(default=0, ge=0)
    content_type: str = Field(default="application/octet-stream", max_length=128)
    folder_id: int | None = None
    access_scope: str = "course"
    access_scope_id: int | None = None


class ResourceFolderPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: int | None = None


class ActivityPayload(BaseModel):
    course_id: int
    activity_type: str = Field(min_length=1, max_length=64)
    object_type: str = Field(default="", max_length=64)
    object_id: str = Field(default="", max_length=128)
    duration_seconds: int = Field(default=0, ge=0, le=86_400)


class PlannerPayload(BaseModel):
    course_id: int | None = None
    assignment_id: int | None = None
    title: str = Field(min_length=1, max_length=255)
    due_at: LMSDateTime | None = None
    completed: bool = False


class AppointmentPayload(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    starts_at: LMSDateTime
    ends_at: LMSDateTime
    slot_minutes: int = Field(default=30, ge=5, le=240)
    participants_per_slot: int = Field(default=1, ge=1, le=100)


class ReservationPayload(BaseModel):
    starts_at: LMSDateTime


def _actor(request: Request, db: Session) -> User:
    user = db.get(User, request.state.current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _enrollment(db: Session, user_id: int, course_id: int, role: str | None = None) -> Enrollment:
    enrollment = course_actor(db, course_id, user_id)
    if not enrollment or (role and enrollment.role != role):
        raise HTTPException(status_code=403, detail=f"{role or 'Course'} enrollment required")
    return enrollment


def _teacher(request: Request, db: Session, course_id: int) -> User:
    user = _actor(request, db)
    _enrollment(db, user.id, course_id, "instructor")
    return user


def _assignment(db: Session, assignment_id: int) -> Assignment:
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


def _configuration(db: Session, assignment_id: int, create: bool = False) -> AssignmentConfiguration | None:
    config = db.scalar(
        select(AssignmentConfiguration).where(AssignmentConfiguration.assignment_id == assignment_id)
    )
    if not config and create:
        config = AssignmentConfiguration(assignment_id=assignment_id)
        db.add(config)
        db.flush()
    return config


def _iso(value: datetime | None) -> str | None:
    return as_utc(value).isoformat() if value else None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def effective_assignment_window(
    db: Session, assignment: Assignment, user_id: int | None
) -> tuple[datetime, datetime | None, datetime | None, AssignmentOverride | None]:
    config = _configuration(db, assignment.id)
    selected: AssignmentOverride | None = None
    if user_id is not None:
        candidates = db.scalars(
            select(AssignmentOverride).where(AssignmentOverride.assignment_id == assignment.id)
        ).all()
        section_ids = set(
            db.scalars(select(SectionMembership.section_id).where(SectionMembership.user_id == user_id)).all()
        )
        group_ids = set(
            db.scalars(select(GroupMembership.group_id).where(GroupMembership.user_id == user_id)).all()
        )
        applicable = [
            item
            for item in candidates
            if (item.target_type == "student" and item.target_id == user_id)
            or (item.target_type == "section" and item.target_id in section_ids)
            or (item.target_type == "group" and item.target_id in group_ids)
        ]
    else:
        applicable = []
    # Canvas collapses each overridden field independently. Student overrides
    # take precedence; otherwise use the widest applicable group/section window.
    def collapsed(field: str, fallback: datetime | None, earliest: bool = False):
        values = [item for item in applicable if getattr(item, field) is not None]
        individual = [item for item in values if item.target_type == "student"]
        values = individual or values
        if not values:
            return fallback, None
        chosen = (min if earliest else max)(values, key=lambda item: _as_utc(getattr(item, field)))
        return getattr(chosen, field), chosen
    due_at, selected = collapsed("due_at", assignment.due_at)
    unlock_at, _ = collapsed("unlock_at", config.unlock_at if config else None, earliest=True)
    lock_at, _ = collapsed("lock_at", config.lock_at if config else None)
    return due_at, unlock_at, lock_at, selected


def resolve_assignment_dates(db: Session, assignment: Assignment, user_id: int | None) -> dict:
    due_at, unlock_at, lock_at, selected = effective_assignment_window(db, assignment, user_id)
    return {
        "due_at": _iso(due_at),
        "unlock_at": _iso(unlock_at),
        "lock_at": _iso(lock_at),
        "override_id": selected.id if selected else None,
        "override_target": selected.target_type if selected else None,
    }


def assignment_extension_payload(db: Session, assignment: Assignment, user_id: int | None = None) -> dict:
    config = _configuration(db, assignment.id)
    metadata = db.get(TeacherTaskMetadata, assignment.id)
    group = db.get(AssignmentGroup, config.assignment_group_id) if config and config.assignment_group_id else None
    rubric_link = db.scalar(
        select(AssignmentRubric).where(AssignmentRubric.assignment_id == assignment.id)
    )
    rubric = db.get(Rubric, rubric_link.rubric_id) if rubric_link else None
    return {
        "assignment_group": {
            "id": group.id,
            "name": group.name,
            "weight": group.group_weight,
        }
        if group
        else None,
        "grading_type": config.grading_type if config else "points",
        "peer_reviews": config.peer_reviews if config else False,
        "group_category_id": config.group_category_id if config else None,
        "rubric": _rubric_payload(db, rubric) if rubric else None,
        "resource_ids": sorted(set(json.loads(metadata.resource_ids_json or "[]"))) if metadata else [],
        **resolve_assignment_dates(db, assignment, user_id),
    }


def module_extension_payload(db: Session, module: CourseModule, user_id: int | None = None) -> dict:
    policy = db.scalar(select(ModulePolicy).where(ModulePolicy.module_id == module.id))
    prerequisites = db.scalars(
        select(ModulePrerequisite).where(ModulePrerequisite.module_id == module.id)
    ).all()
    requirements = db.scalars(
        select(ModuleRequirement)
        .join(ModuleItem, ModuleItem.id == ModuleRequirement.module_item_id)
        .where(ModuleItem.module_id == module.id)
        .order_by(ModuleRequirement.id)
    ).all()
    progress_by_item: dict[int, ModuleItemProgress] = {}
    if user_id is not None:
        item_ids = [item.module_item_id for item in requirements if item.module_item_id]
        if item_ids:
            progress_by_item = {
                progress.module_item_id: progress
                for progress in db.scalars(
                    select(ModuleItemProgress).where(
                        ModuleItemProgress.user_id == user_id,
                        ModuleItemProgress.module_item_id.in_(item_ids),
                    )
                ).all()
            }
    return {
        "sequential_progress": policy.sequential_progress if policy else False,
        "prerequisite_module_ids": [item.prerequisite_module_id for item in prerequisites],
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
            for requirement in requirements
        ],
    }


def record_submission_attempt(
    db: Session,
    submission: Submission,
    *,
    text_entry: str = "",
    website_url: str = "",
    file_name: str = "",
    file_url: str = "",
) -> SubmissionAttempt:
    last_attempt = db.scalar(
        select(func.max(SubmissionAttempt.attempt_number)).where(SubmissionAttempt.submission_id == submission.id)
    )
    attempt = SubmissionAttempt(
        submission_id=submission.id,
        attempt_number=(last_attempt or 0) + 1,
        submitted_at=submission.submitted_at or datetime.now(UTC),
        text_entry=text_entry,
        website_url=website_url,
    )
    db.add(attempt)
    db.flush()
    if file_name and file_url:
        db.add(SubmissionAttachment(attempt_id=attempt.id, file_name=file_name, file_url=file_url))
    workflow = db.scalar(select(SubmissionWorkflow).where(SubmissionWorkflow.submission_id == submission.id))
    if workflow:
        workflow.reassigned = False
        workflow.excused = False
    return attempt


def record_resource_version(
    db: Session,
    resource: Resource,
    *,
    source_url: str | None = None,
    checksum: str | None = None,
    size_bytes: int = 0,
    content_type: str = "application/octet-stream",
    ensure_course_access: bool = True,
) -> ResourceVersion:
    last_version = db.scalar(
        select(func.max(ResourceVersion.version)).where(ResourceVersion.resource_id == resource.id)
    )
    url = source_url or resource.source_url
    version = ResourceVersion(
        resource_id=resource.id,
        version=(last_version or 0) + 1,
        checksum_sha256=checksum or hashlib.sha256(url.encode()).hexdigest(),
        size_bytes=size_bytes,
        content_type=content_type,
        source_url=url,
    )
    db.add(version)
    db.flush()
    if ensure_course_access and not db.scalar(
        select(ResourceAccess).where(ResourceAccess.resource_id == resource.id)
    ):
        db.add(ResourceAccess(resource_id=resource.id, scope_type="course", scope_id=resource.course_id))
    return version


def resource_extension_payload(db: Session, resource: Resource) -> dict:
    latest = db.scalar(
        select(ResourceVersion)
        .where(ResourceVersion.resource_id == resource.id)
        .order_by(ResourceVersion.version.desc())
    )
    access = db.scalars(
        select(ResourceAccess).where(ResourceAccess.resource_id == resource.id)
    ).all()
    folder = db.get(ResourceFolder, latest.folder_id) if latest and latest.folder_id else None
    planning_chapter = db.scalar(
        select(CourseModule.name)
        .join(ModuleItem)
        .where(
            CourseModule.course_id == resource.course_id,
            ModuleItem.item_type == "resource",
            ModuleItem.content_id == resource.id,
        )
        .order_by(CourseModule.position, CourseModule.id)
        .limit(1)
    )
    course = db.get(Course, resource.course_id)
    return {
        "course_code": course.code if course else str(resource.course_id),
        "course_name": course.name if course else "",
        "planning_chapter": planning_chapter or "",
        "folder": {"id": folder.id, "name": folder.name} if folder else None,
        "latest_version": {
            "id": latest.id,
            "version": latest.version,
            "checksum_sha256": latest.checksum_sha256,
            "size_bytes": latest.size_bytes,
            "content_type": latest.content_type,
            "created_at": _iso(latest.created_at),
        }
        if latest
        else None,
        "access_scope": [
            {"type": item.scope_type, "id": item.scope_id, "permission": item.permission} for item in access
        ],
    }


def can_access_resource(db: Session, resource: Resource, user_id: int) -> bool:
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == resource.course_id,
            Enrollment.user_id == user_id,
        )
    )
    if not enrollment:
        return False
    if enrollment.role == "instructor":
        return True
    course = db.get(Course, resource.course_id)
    lifecycle = db.get(CourseLifecycle, resource.course_id)
    if not course or not course.published or (lifecycle and lifecycle.archived):
        return False
    scopes = db.scalars(
        select(ResourceAccess).where(ResourceAccess.resource_id == resource.id)
    ).all()
    if not scopes:
        return True
    section_ids = set(
        db.scalars(
            select(SectionMembership.section_id).where(SectionMembership.user_id == user_id)
        ).all()
    )
    group_ids = set(
        db.scalars(select(GroupMembership.group_id).where(GroupMembership.user_id == user_id)).all()
    )
    return any(
        (scope.scope_type == "course" and scope.scope_id == resource.course_id)
        or (scope.scope_type == "user" and scope.scope_id == user_id)
        or (scope.scope_type == "section" and scope.scope_id in section_ids)
        or (scope.scope_type == "group" and scope.scope_id in group_ids)
        for scope in scopes if scope.permission == "read"
    )


def _folder_payload(db: Session, folder: ResourceFolder) -> dict:
    return {
        "id": folder.id,
        "course_id": folder.course_id,
        "parent_id": folder.parent_id,
        "name": folder.name,
        "resource_count": db.scalar(
            select(func.count(ResourceVersion.id)).where(ResourceVersion.folder_id == folder.id)
        )
        or 0,
    }


def submission_history_payload(db: Session, submission: Submission) -> dict:
    attempts = db.scalars(
        select(SubmissionAttempt)
        .where(SubmissionAttempt.submission_id == submission.id)
        .order_by(SubmissionAttempt.attempt_number)
    ).all()
    comments = db.execute(
        select(SubmissionComment, User)
        .join(User, User.id == SubmissionComment.author_id)
        .where(SubmissionComment.submission_id == submission.id)
        .order_by(SubmissionComment.created_at)
    ).all()
    workflow = db.scalar(
        select(SubmissionWorkflow).where(SubmissionWorkflow.submission_id == submission.id)
    )
    return {
        "submission_id": submission.id,
        "workflow": {
            "excused": workflow.excused if workflow else False,
            "reassigned": workflow.reassigned if workflow else False,
        },
        "attempts": [
            {
                "id": attempt.id,
                "attempt": attempt.attempt_number,
                "submitted_at": _iso(attempt.submitted_at),
                "text_entry": attempt.text_entry,
                "website_url": attempt.website_url,
                "attachments": [
                    {
                        "id": attachment.id,
                        "file_name": attachment.file_name,
                        "file_url": attachment.file_url,
                    }
                    for attachment in db.scalars(
                        select(SubmissionAttachment).where(
                            SubmissionAttachment.attempt_id == attempt.id
                        )
                    ).all()
                ],
            }
            for attempt in attempts
        ],
        "comments": [
            {
                "id": comment.id,
                "author": author.full_name,
                "body": comment.body,
                "created_at": _iso(comment.created_at),
            }
            for comment, author in comments
        ],
    }


def _group_payload(group: AssignmentGroup) -> dict:
    return {
        "id": group.id,
        "course_id": group.course_id,
        "name": group.name,
        "position": group.position,
        "group_weight": group.group_weight,
        "drop_lowest": group.drop_lowest,
        "drop_highest": group.drop_highest,
    }


@router.get("/courses/{course_id}/assignment-groups")
def list_assignment_groups(course_id: int, request: Request, db: Session = Depends(get_db)) -> list[dict]:
    actor = _actor(request, db)
    _enrollment(db, actor.id, course_id)
    groups = db.scalars(
        select(AssignmentGroup).where(AssignmentGroup.course_id == course_id).order_by(AssignmentGroup.position)
    ).all()
    return [_group_payload(group) for group in groups]


@router.post("/courses/{course_id}/assignment-groups", status_code=201)
def create_assignment_group(
    course_id: int, payload: AssignmentGroupPayload, request: Request, db: Session = Depends(get_db)
) -> dict:
    actor = _teacher(request, db, course_id)
    group = AssignmentGroup(course_id=course_id, **payload.model_dump())
    db.add(group)
    db.flush()
    record_change(db, actor_user_id=actor.id, action="assignment_group.created", entity_type="assignment_group", entity_id=group.id, course_id=course_id)
    db.commit()
    return _group_payload(group)


@router.put("/courses/{course_id}/assignment-groups/{group_id}")
def update_assignment_group(
    course_id: int,
    group_id: int,
    payload: AssignmentGroupPayload,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    actor = _teacher(request, db, course_id)
    group = db.get(AssignmentGroup, group_id)
    if not group or group.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment group not found")
    for key, value in payload.model_dump().items():
        setattr(group, key, value)
    record_change(db, actor_user_id=actor.id, action="assignment_group.updated", entity_type="assignment_group", entity_id=group.id, course_id=course_id)
    db.commit()
    return _group_payload(group)


@router.delete("/courses/{course_id}/assignment-groups/{group_id}")
def delete_assignment_group(course_id: int, group_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _teacher(request, db, course_id)
    group = db.get(AssignmentGroup, group_id)
    if not group or group.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment group not found")
    db.delete(group)
    record_change(db, actor_user_id=actor.id, action="assignment_group.deleted", entity_type="assignment_group", entity_id=group_id, course_id=course_id)
    db.commit()
    return {"ok": True}


@router.get("/assignments/{assignment_id}/policy")
def read_assignment_policy(assignment_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    assignment = _assignment(db, assignment_id)
    actor = _actor(request, db)
    enrollment = _enrollment(db, actor.id, assignment.course_id)
    if enrollment.role != "instructor" and not assignment.published:
        raise HTTPException(403, "Assignment is not published")
    overrides = db.scalars(
        select(AssignmentOverride).where(AssignmentOverride.assignment_id == assignment_id).order_by(AssignmentOverride.id)
    ).all()
    return {
        **assignment_extension_payload(db, assignment, actor.id),
        "overrides": [
            {"id": item.id, "title": item.title, "target_type": item.target_type, "target_id": item.target_id, "due_at": _iso(item.due_at), "unlock_at": _iso(item.unlock_at), "lock_at": _iso(item.lock_at)}
            for item in overrides
            if enrollment.role == "instructor"
        ],
    }


@router.put("/assignments/{assignment_id}/policy")
def update_assignment_policy(
    assignment_id: int, payload: AssignmentPolicyPayload, request: Request, db: Session = Depends(get_db)
) -> dict:
    assignment = _assignment(db, assignment_id)
    actor = _teacher(request, db, assignment.course_id)
    if payload.lock_at and payload.unlock_at and payload.lock_at <= payload.unlock_at:
        raise HTTPException(status_code=422, detail="lock_at must be after unlock_at")
    if payload.unlock_at and _as_utc(payload.unlock_at) >= _as_utc(assignment.due_at):
        raise HTTPException(status_code=422, detail="unlock_at must be before due_at")
    if payload.lock_at and _as_utc(payload.lock_at) <= _as_utc(assignment.due_at):
        raise HTTPException(status_code=422, detail="lock_at must be after due_at")
    allowed_grading = {"points", "percent", "pass_fail", "letter_grade", "gpa_scale", "not_graded"}
    if payload.grading_type not in allowed_grading:
        raise HTTPException(status_code=422, detail="Unsupported grading type")
    if payload.assignment_group_id:
        group = db.get(AssignmentGroup, payload.assignment_group_id)
        if not group or group.course_id != assignment.course_id:
            raise HTTPException(status_code=422, detail="Assignment group does not belong to this course")
    if payload.group_category_id:
        category = db.get(GroupCategory, payload.group_category_id)
        if not category or category.course_id != assignment.course_id:
            raise HTTPException(status_code=422, detail="Group category does not belong to this course")
    config = _configuration(db, assignment_id, create=True)
    for key, value in payload.model_dump().items():
        setattr(config, key, value)
    record_change(db, actor_user_id=actor.id, action="assignment.policy.updated", entity_type="assignment", entity_id=assignment.id, course_id=assignment.course_id, metadata=payload.model_dump())
    db.commit()
    return assignment_extension_payload(db, assignment, actor.id)


@router.post("/assignments/{assignment_id}/overrides", status_code=201)
def create_assignment_override(
    assignment_id: int, payload: AssignmentOverridePayload, request: Request, db: Session = Depends(get_db)
) -> dict:
    assignment = _assignment(db, assignment_id)
    actor = _teacher(request, db, assignment.course_id)
    if payload.target_type not in {"student", "section", "group"}:
        raise HTTPException(status_code=422, detail="target_type must be student, section, or group")
    if payload.target_type == "student":
        _enrollment(db, payload.target_id, assignment.course_id)
    elif payload.target_type == "section":
        section = db.get(CourseSection, payload.target_id)
        if not section or section.course_id != assignment.course_id:
            raise HTTPException(status_code=422, detail="Section does not belong to this course")
    else:
        group_row = db.execute(
            select(CourseGroup, GroupCategory)
            .join(GroupCategory, GroupCategory.id == CourseGroup.category_id)
            .where(CourseGroup.id == payload.target_id)
        ).first()
        if not group_row or group_row[1].course_id != assignment.course_id:
            raise HTTPException(status_code=422, detail="Group does not belong to this course")
    if payload.lock_at and payload.unlock_at and payload.lock_at <= payload.unlock_at:
        raise HTTPException(status_code=422, detail="lock_at must be after unlock_at")
    if payload.due_at and payload.unlock_at and payload.due_at <= payload.unlock_at:
        raise HTTPException(status_code=422, detail="due_at must be after unlock_at")
    if payload.due_at and payload.lock_at and payload.lock_at <= payload.due_at:
        raise HTTPException(status_code=422, detail="lock_at must be after due_at")
    item = AssignmentOverride(assignment_id=assignment_id, **payload.model_dump())
    db.add(item)
    db.flush()
    record_change(db, actor_user_id=actor.id, action="assignment.override.created", entity_type="assignment_override", entity_id=item.id, course_id=assignment.course_id, metadata=payload.model_dump())
    db.commit()
    return {"id": item.id, **payload.model_dump(mode="json")}


@router.delete("/assignments/{assignment_id}/overrides/{override_id}")
def delete_assignment_override(
    assignment_id: int, override_id: int, request: Request, db: Session = Depends(get_db)
) -> dict:
    assignment = _assignment(db, assignment_id)
    actor = _teacher(request, db, assignment.course_id)
    item = db.get(AssignmentOverride, override_id)
    if not item or item.assignment_id != assignment_id:
        raise HTTPException(status_code=404, detail="Assignment override not found")
    db.delete(item)
    record_change(db, actor_user_id=actor.id, action="assignment.override.deleted", entity_type="assignment_override", entity_id=override_id, course_id=assignment.course_id)
    db.commit()
    return {"ok": True}


@router.get("/courses/{course_id}/sections")
def list_sections(course_id: int, request: Request, db: Session = Depends(get_db)) -> list[dict]:
    actor = _actor(request, db)
    _enrollment(db, actor.id, course_id)
    sections = db.scalars(select(CourseSection).where(CourseSection.course_id == course_id)).all()
    return [
        {"id": section.id, "name": section.name, "member_ids": db.scalars(select(SectionMembership.user_id).where(SectionMembership.section_id == section.id)).all()}
        for section in sections
    ]


@router.post("/courses/{course_id}/sections", status_code=201)
def create_section(course_id: int, payload: NamedPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _teacher(request, db, course_id)
    section = CourseSection(course_id=course_id, name=payload.name.strip())
    db.add(section)
    db.flush()
    record_change(db, actor_user_id=actor.id, action="section.created", entity_type="section", entity_id=section.id, course_id=course_id)
    db.commit()
    return {"id": section.id, "name": section.name, "member_ids": []}


@router.post("/sections/{section_id}/members", status_code=201)
def add_section_member(
    section_id: int, payload: SectionMemberPayload, request: Request, db: Session = Depends(get_db)
) -> dict:
    section = db.get(CourseSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    actor = _teacher(request, db, section.course_id)
    _enrollment(db, payload.member_id, section.course_id)
    item = db.scalar(select(SectionMembership).where(SectionMembership.section_id == section_id, SectionMembership.user_id == payload.member_id))
    if not item:
        item = SectionMembership(section_id=section_id, user_id=payload.member_id)
        db.add(item)
        db.flush()
    record_change(db, actor_user_id=actor.id, action="section.member.added", entity_type="section", entity_id=section.id, course_id=section.course_id, metadata={"member_id": payload.member_id})
    db.commit()
    return {"id": item.id, "section_id": section_id, "member_id": payload.member_id}


@router.get("/courses/{course_id}/groups")
def list_course_groups(course_id: int, request: Request, db: Session = Depends(get_db)) -> list[dict]:
    actor = _actor(request, db)
    _enrollment(db, actor.id, course_id)
    categories = db.scalars(select(GroupCategory).where(GroupCategory.course_id == course_id)).all()
    result = []
    for category in categories:
        groups = db.scalars(select(CourseGroup).where(CourseGroup.category_id == category.id)).all()
        result.append({"id": category.id, "name": category.name, "self_signup": category.self_signup, "groups": [{"id": group.id, "name": group.name, "member_ids": db.scalars(select(GroupMembership.user_id).where(GroupMembership.group_id == group.id)).all()} for group in groups]})
    return result


@router.post("/courses/{course_id}/group-categories", status_code=201)
def create_group_category(
    course_id: int, payload: GroupCategoryPayload, request: Request, db: Session = Depends(get_db)
) -> dict:
    actor = _teacher(request, db, course_id)
    category = GroupCategory(course_id=course_id, name=payload.name.strip(), self_signup=payload.self_signup)
    db.add(category)
    db.flush()
    record_change(db, actor_user_id=actor.id, action="group_category.created", entity_type="group_category", entity_id=category.id, course_id=course_id)
    db.commit()
    return {"id": category.id, "name": category.name, "self_signup": category.self_signup, "groups": []}


@router.post("/group-categories/{category_id}/groups", status_code=201)
def create_course_group(category_id: int, payload: NamedPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    category = db.get(GroupCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Group category not found")
    actor = _teacher(request, db, category.course_id)
    group = CourseGroup(category_id=category_id, name=payload.name.strip())
    db.add(group)
    db.flush()
    record_change(db, actor_user_id=actor.id, action="group.created", entity_type="group", entity_id=group.id, course_id=category.course_id)
    db.commit()
    return {"id": group.id, "name": group.name, "member_ids": []}


@router.post("/groups/{group_id}/members", status_code=201)
def add_group_member(group_id: int, payload: SectionMemberPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    row = db.execute(select(CourseGroup, GroupCategory).join(GroupCategory, GroupCategory.id == CourseGroup.category_id).where(CourseGroup.id == group_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")
    group, category = row
    actor = _teacher(request, db, category.course_id)
    _enrollment(db, payload.member_id, category.course_id)
    item = db.scalar(select(GroupMembership).where(GroupMembership.group_id == group_id, GroupMembership.user_id == payload.member_id))
    if not item:
        item = GroupMembership(group_id=group_id, user_id=payload.member_id)
        db.add(item)
        db.flush()
    record_change(db, actor_user_id=actor.id, action="group.member.added", entity_type="group", entity_id=group.id, course_id=category.course_id, metadata={"member_id": payload.member_id})
    db.commit()
    return {"id": item.id, "group_id": group_id, "member_id": payload.member_id}


@router.get("/modules/{module_id}/rules")
def read_module_rules(module_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    module = db.get(CourseModule, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    actor = _actor(request, db)
    _enrollment(db, actor.id, module.course_id)
    prerequisites = db.scalars(select(ModulePrerequisite.prerequisite_module_id).where(ModulePrerequisite.module_id == module_id)).all()
    rows = db.execute(select(ModuleRequirement, ModuleItem).join(ModuleItem, ModuleItem.id == ModuleRequirement.module_item_id).where(ModuleItem.module_id == module_id)).all()
    policy = db.scalar(select(ModulePolicy).where(ModulePolicy.module_id == module_id))
    return {"module_id": module_id, "sequential_progress": policy.sequential_progress if policy else False, "prerequisite_module_ids": prerequisites, "requirements": [{"module_item_id": requirement.module_item_id, "title": item.title, "requirement_type": requirement.requirement_type, "min_score": requirement.min_score} for requirement, item in rows]}


@router.put("/modules/{module_id}/rules")
def update_module_rules(module_id: int, payload: ModuleRulesPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    module = db.get(CourseModule, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    actor = _teacher(request, db, module.course_id)
    edges = db.execute(select(ModulePrerequisite.module_id, ModulePrerequisite.prerequisite_module_id)).all()
    graph: dict[int, list[int]] = {}
    for source, target in edges:
        if source != module_id:
            graph.setdefault(source, []).append(target)
    graph[module_id] = payload.prerequisite_module_ids
    def reaches_current(start: int, visited: set[int]) -> bool:
        if start == module_id:
            return True
        if start in visited:
            return False
        visited.add(start)
        return any(reaches_current(target, visited) for target in graph.get(start, []))
    if any(reaches_current(target, set()) for target in payload.prerequisite_module_ids):
        raise HTTPException(422, "Module prerequisite cycle is not allowed")
    policy = db.scalar(select(ModulePolicy).where(ModulePolicy.module_id == module_id))
    if not policy:
        policy = ModulePolicy(module_id=module_id)
        db.add(policy)
    policy.sequential_progress = payload.sequential_progress
    db.execute(delete(ModulePrerequisite).where(ModulePrerequisite.module_id == module_id))
    for prerequisite_id in set(payload.prerequisite_module_ids):
        prerequisite = db.get(CourseModule, prerequisite_id)
        if not prerequisite or prerequisite.course_id != module.course_id or prerequisite.id == module.id:
            raise HTTPException(status_code=422, detail="Invalid prerequisite module")
        db.add(ModulePrerequisite(module_id=module_id, prerequisite_module_id=prerequisite_id))
    item_ids = set(db.scalars(select(ModuleItem.id).where(ModuleItem.module_id == module_id)).all())
    if item_ids:
        db.execute(delete(ModuleRequirement).where(ModuleRequirement.module_item_id.in_(item_ids)))
    for raw in payload.requirements:
        item_id = int(raw.get("module_item_id", 0))
        requirement_type = str(raw.get("requirement_type", "must_view"))
        if item_id not in item_ids or requirement_type not in {"must_view", "must_submit", "must_score", "must_mark_done"}:
            raise HTTPException(status_code=422, detail="Invalid module requirement")
        db.add(ModuleRequirement(module_item_id=item_id, requirement_type=requirement_type, min_score=raw.get("min_score")))
    record_change(db, actor_user_id=actor.id, action="module.rules.updated", entity_type="module", entity_id=module_id, course_id=module.course_id)
    db.commit()
    return read_module_rules(module_id, request, db)


@router.put("/module-items/{item_id}/progress")
def update_module_progress(item_id: int, payload: ModuleProgressPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    item = db.get(ModuleItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Module item not found")
    module = db.get(CourseModule, item.module_id)
    actor = _actor(request, db)
    _enrollment(db, actor.id, module.course_id)
    if not module.published or not item.published:
        raise HTTPException(403, "Module item is not published")
    if payload.status not in {"unlocked", "started", "completed"}:
        raise HTTPException(status_code=422, detail="Unsupported progress status")
    if payload.status in {"unlocked", "started", "completed"}:
        prerequisite_ids = db.scalars(
            select(ModulePrerequisite.prerequisite_module_id).where(
                ModulePrerequisite.module_id == module.id
            )
        ).all()
        prerequisite_item_ids = db.scalars(
            select(ModuleItem.id)
            .join(ModuleRequirement, ModuleRequirement.module_item_id == ModuleItem.id)
            .where(ModuleItem.module_id.in_(prerequisite_ids))
        ).all()
        completed_prerequisites = set(
            db.scalars(
                select(ModuleItemProgress.module_item_id).where(
                    ModuleItemProgress.user_id == actor.id,
                    ModuleItemProgress.status == "completed",
                    ModuleItemProgress.module_item_id.in_(prerequisite_item_ids),
                )
            ).all()
        )
        if set(prerequisite_item_ids) - completed_prerequisites:
            raise HTTPException(status_code=409, detail="Complete prerequisite modules first")

        policy = db.scalar(select(ModulePolicy).where(ModulePolicy.module_id == module.id))
        if policy and policy.sequential_progress:
            previous_item_ids = db.scalars(
                select(ModuleItem.id).where(
                    ModuleItem.module_id == module.id,
                    ModuleItem.position < item.position,
                )
            ).all()
            completed_previous = set(
                db.scalars(
                    select(ModuleItemProgress.module_item_id).where(
                        ModuleItemProgress.user_id == actor.id,
                        ModuleItemProgress.status == "completed",
                        ModuleItemProgress.module_item_id.in_(previous_item_ids),
                    )
                ).all()
            )
            if set(previous_item_ids) - completed_previous:
                raise HTTPException(status_code=409, detail="Complete earlier module items first")

        requirement = db.scalar(
            select(ModuleRequirement).where(ModuleRequirement.module_item_id == item.id)
        )
        if payload.status == "completed" and requirement and requirement.requirement_type in {"must_submit", "must_score"}:
            assignment_id = item.content_id
            if item.item_type.lower() == "quiz":
                link = db.get(QuizAssignmentLink, item.content_id)
                assignment_id = link.assignment_id if link else None
            submission = db.scalar(
                select(Submission).where(
                    Submission.assignment_id == assignment_id,
                    Submission.user_id == actor.id,
                )
            )
            if not submission or submission.workflow_state not in {"submitted", "graded", "pending_review"}:
                raise HTTPException(status_code=409, detail="Submit the linked assignment first")
            if requirement.requirement_type == "must_score" and (
                submission.score is None
                or submission.score < (requirement.min_score or 0)
            ):
                raise HTTPException(status_code=409, detail="Minimum module score not reached")
    progress = db.scalar(select(ModuleItemProgress).where(ModuleItemProgress.module_item_id == item_id, ModuleItemProgress.user_id == actor.id))
    if not progress:
        progress = ModuleItemProgress(module_item_id=item_id, user_id=actor.id)
        db.add(progress)
    progress.status = payload.status
    progress.completed_at = datetime.now(UTC) if payload.status == "completed" else None
    record_change(db, actor_user_id=actor.id, action="module.progress.updated", entity_type="module_item", entity_id=item_id, course_id=module.course_id, metadata={"status": payload.status})
    db.commit()
    return {"module_item_id": item_id, "status": progress.status, "completed_at": _iso(progress.completed_at)}


@router.get("/submissions/{submission_id}/history")
def submission_history(submission_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    submission = db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    assignment = _assignment(db, submission.assignment_id)
    actor = _actor(request, db)
    enrollment = _enrollment(db, actor.id, assignment.course_id)
    if enrollment.role != "instructor" and submission.user_id != actor.id:
        raise HTTPException(status_code=403, detail="Cannot access this submission")
    return submission_history_payload(db, submission)


@router.post("/submissions/{submission_id}/comments", status_code=201)
def add_submission_comment(submission_id: int, payload: CommentPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    submission = db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    assignment = _assignment(db, submission.assignment_id)
    actor = _actor(request, db)
    enrollment = _enrollment(db, actor.id, assignment.course_id)
    if enrollment.role != "instructor" and submission.user_id != actor.id:
        raise HTTPException(status_code=403, detail="Cannot comment on this submission")
    comment = SubmissionComment(submission_id=submission_id, author_id=actor.id, body=payload.body.strip())
    db.add(comment)
    db.flush()
    record_change(db, actor_user_id=actor.id, action="submission.comment.created", entity_type="submission", entity_id=submission_id, course_id=assignment.course_id)
    db.commit()
    return {"id": comment.id, "author": actor.full_name, "body": comment.body, "created_at": _iso(comment.created_at)}


@router.put("/submissions/{submission_id}/workflow")
def update_submission_workflow(submission_id: int, payload: SubmissionWorkflowPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    submission = db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    assignment = _assignment(db, submission.assignment_id)
    actor = _teacher(request, db, assignment.course_id)
    workflow = db.scalar(select(SubmissionWorkflow).where(SubmissionWorkflow.submission_id == submission_id))
    if not workflow:
        workflow = SubmissionWorkflow(submission_id=submission_id)
        db.add(workflow)
    workflow.excused, workflow.reassigned = payload.excused, payload.reassigned
    record_change(db, actor_user_id=actor.id, action="submission.workflow.updated", entity_type="submission", entity_id=submission_id, course_id=assignment.course_id, metadata=payload.model_dump())
    db.commit()
    return {"submission_id": submission_id, **payload.model_dump()}


def _rubric_payload(db: Session, rubric: Rubric) -> dict:
    criteria = db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_id == rubric.id).order_by(RubricCriterion.position)).all()
    return {"id": rubric.id, "course_id": rubric.course_id, "title": rubric.title, "points_possible": rubric.points_possible, "criteria": [{"id": criterion.id, "description": criterion.description, "long_description": criterion.long_description, "points": criterion.points, "position": criterion.position, "ratings": [{"id": rating.id, "description": rating.description, "points": rating.points} for rating in db.scalars(select(RubricRating).where(RubricRating.criterion_id == criterion.id).order_by(RubricRating.points.desc())).all()]} for criterion in criteria]}


@router.get("/courses/{course_id}/rubrics")
def list_rubrics(course_id: int, request: Request, db: Session = Depends(get_db)) -> list[dict]:
    actor = _actor(request, db)
    _enrollment(db, actor.id, course_id)
    return [_rubric_payload(db, item) for item in db.scalars(select(Rubric).where(Rubric.course_id == course_id)).all()]


@router.post("/courses/{course_id}/rubrics", status_code=201)
def create_rubric(course_id: int, payload: RubricPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _teacher(request, db, course_id)
    rubric = Rubric(course_id=course_id, title=payload.title.strip(), points_possible=sum(item.points for item in payload.criteria))
    db.add(rubric)
    db.flush()
    for index, raw in enumerate(payload.criteria, 1):
        if any(rating.points > raw.points for rating in raw.ratings):
            raise HTTPException(422, "Rubric rating exceeds criterion points")
        criterion = RubricCriterion(rubric_id=rubric.id, description=raw.description, long_description=raw.long_description, points=raw.points, position=index)
        db.add(criterion)
        db.flush()
        db.add_all([RubricRating(criterion_id=criterion.id, description=rating.description, points=rating.points) for rating in raw.ratings])
    record_change(db, actor_user_id=actor.id, action="rubric.created", entity_type="rubric", entity_id=rubric.id, course_id=course_id)
    db.commit()
    return _rubric_payload(db, rubric)


@router.put("/assignments/{assignment_id}/rubric/{rubric_id}")
def attach_rubric(assignment_id: int, rubric_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    assignment = _assignment(db, assignment_id)
    actor = _teacher(request, db, assignment.course_id)
    rubric = db.get(Rubric, rubric_id)
    if not rubric or rubric.course_id != assignment.course_id:
        raise HTTPException(status_code=422, detail="Rubric does not belong to this course")
    link = db.scalar(select(AssignmentRubric).where(AssignmentRubric.assignment_id == assignment_id))
    if not link:
        link = AssignmentRubric(assignment_id=assignment_id, rubric_id=rubric_id)
        db.add(link)
    else:
        link.rubric_id = rubric_id
    record_change(db, actor_user_id=actor.id, action="rubric.attached", entity_type="assignment", entity_id=assignment_id, course_id=assignment.course_id, metadata={"rubric_id": rubric_id})
    db.commit()
    return {"assignment_id": assignment_id, "rubric": _rubric_payload(db, rubric)}


@router.put("/submissions/{submission_id}/rubric-assessment")
def assess_rubric(submission_id: int, payload: RubricAssessmentPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    submission = db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    assignment = _assignment(db, submission.assignment_id)
    actor = _teacher(request, db, assignment.course_id)
    link = db.scalar(select(AssignmentRubric).where(AssignmentRubric.assignment_id == assignment.id))
    if not link:
        raise HTTPException(status_code=422, detail="Assignment has no rubric")
    criteria = {item.id: item for item in db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_id == link.rubric_id)).all()}
    if set(payload.ratings) - set(criteria):
        raise HTTPException(status_code=422, detail="Unknown rubric criterion")
    db.execute(delete(RubricAssessment).where(RubricAssessment.submission_id == submission_id))
    total = 0.0
    for criterion_id, points in payload.ratings.items():
        criterion = criteria[criterion_id]
        if points < 0 or points > criterion.points:
            raise HTTPException(status_code=422, detail="Rubric score outside criterion range")
        total += points
        db.add(RubricAssessment(submission_id=submission_id, criterion_id=criterion_id, assessor_id=actor.id, points=points, comments=payload.comments.get(criterion_id, "")))
    record_change(db, actor_user_id=actor.id, action="rubric.assessed", entity_type="submission", entity_id=submission_id, course_id=assignment.course_id, metadata={"score": total})
    db.commit()
    return {"submission_id": submission_id, "rubric_score": total}


@router.get("/resources/{resource_id}/versions")
def list_resource_versions(resource_id: int, request: Request, db: Session = Depends(get_db)) -> list[dict]:
    resource = db.get(Resource, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    actor = _actor(request, db)
    _enrollment(db, actor.id, resource.course_id)
    if not can_access_resource(db, resource, actor.id):
        raise HTTPException(status_code=403, detail="You cannot access this resource")
    return [{"id": item.id, "version": item.version, "checksum_sha256": item.checksum_sha256, "size_bytes": item.size_bytes, "content_type": item.content_type, "source_url": item.source_url, "folder_id": item.folder_id, "created_at": _iso(item.created_at)} for item in db.scalars(select(ResourceVersion).where(ResourceVersion.resource_id == resource_id).order_by(ResourceVersion.version.desc())).all()]


class ResourceAccessPayload(BaseModel):
    published: bool = True
    target_user_id: int | None = None


@router.put("/resources/{resource_id}/access")
def update_resource_access(resource_id: int, payload: ResourceAccessPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    resource = db.get(Resource, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    actor = _teacher(request, db, resource.course_id)
    if payload.target_user_id is not None:
        _enrollment(db, payload.target_user_id, resource.course_id)
    db.execute(delete(ResourceAccess).where(ResourceAccess.resource_id == resource.id))
    db.add(ResourceAccess(resource_id=resource.id, scope_type="user" if payload.target_user_id is not None else "course",
                          scope_id=payload.target_user_id if payload.target_user_id is not None else resource.course_id,
                          permission="read" if payload.published else "none"))
    record_change(db, actor_user_id=actor.id, action="resource.access.updated", entity_type="resource", entity_id=resource.id, course_id=resource.course_id)
    db.commit()
    return resource_extension_payload(db, resource)


@router.get("/courses/{course_id}/resource-folders")
def list_resource_folders(
    course_id: int, request: Request, db: Session = Depends(get_db)
) -> list[dict]:
    actor = _actor(request, db)
    _enrollment(db, actor.id, course_id)
    folders = db.scalars(
        select(ResourceFolder)
        .where(ResourceFolder.course_id == course_id)
        .order_by(ResourceFolder.parent_id, ResourceFolder.name)
    ).all()
    return [_folder_payload(db, folder) for folder in folders]


@router.post("/courses/{course_id}/resource-folders", status_code=201)
def create_resource_folder(
    course_id: int,
    payload: ResourceFolderPayload,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    actor = _teacher(request, db, course_id)
    if payload.parent_id:
        parent = db.get(ResourceFolder, payload.parent_id)
        if not parent or parent.course_id != course_id:
            raise HTTPException(status_code=422, detail="Parent folder does not belong to this course")
    folder = ResourceFolder(course_id=course_id, name=payload.name.strip(), parent_id=payload.parent_id)
    db.add(folder)
    db.flush()
    record_change(
        db,
        actor_user_id=actor.id,
        action="resource_folder.created",
        entity_type="resource_folder",
        entity_id=folder.id,
        course_id=course_id,
    )
    db.commit()
    return _folder_payload(db, folder)


@router.post("/resources/{resource_id}/versions", status_code=201)
def create_resource_version(resource_id: int, payload: ResourceVersionPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    resource = db.get(Resource, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    actor = _teacher(request, db, resource.course_id)
    if payload.folder_id:
        folder = db.get(ResourceFolder, payload.folder_id)
        if not folder or folder.course_id != resource.course_id:
            raise HTTPException(status_code=422, detail="Folder does not belong to this course")
    allowed_scopes = {"course", "section", "group", "user"}
    if payload.access_scope not in allowed_scopes:
        raise HTTPException(status_code=422, detail="Unsupported resource access scope")
    version = record_resource_version(
        db,
        resource,
        source_url=payload.source_url,
        checksum=payload.checksum_sha256.lower(),
        size_bytes=payload.size_bytes,
        content_type=payload.content_type,
        ensure_course_access=False,
    )
    version.folder_id = payload.folder_id
    db.execute(delete(ResourceAccess).where(ResourceAccess.resource_id == resource.id))
    db.add(
        ResourceAccess(
            resource_id=resource.id,
            scope_type=payload.access_scope,
            scope_id=payload.access_scope_id or resource.course_id,
        )
    )
    resource.source_url = payload.source_url
    record_change(db, actor_user_id=actor.id, action="resource.version.created", entity_type="resource", entity_id=resource.id, course_id=resource.course_id, metadata={"version": version.version, "checksum": version.checksum_sha256})
    db.commit()
    return {"id": version.id, "version": version.version, "checksum_sha256": version.checksum_sha256}


@router.post("/analytics/activities", status_code=201)
def record_activity(payload: ActivityPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _actor(request, db)
    _enrollment(db, actor.id, payload.course_id)
    item = LearningActivity(user_id=actor.id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "occurred_at": _iso(item.occurred_at)}


@router.get("/courses/{course_id}/analytics")
def course_analytics(course_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _actor(request, db)
    enrollment = _enrollment(db, actor.id, course_id)
    query = select(LearningActivity).where(LearningActivity.course_id == course_id)
    if enrollment.role != "instructor":
        query = query.where(LearningActivity.user_id == actor.id)
    rows = db.scalars(query).all()
    by_user: dict[int, dict] = {}
    by_type: dict[str, int] = {}
    total_duration = 0
    for item in rows:
        summary = by_user.setdefault(item.user_id, {"user_id": item.user_id, "participations": 0, "duration_seconds": 0, "last_activity_at": None})
        summary["participations"] += 1
        summary["duration_seconds"] += item.duration_seconds
        by_type[item.activity_type] = by_type.get(item.activity_type, 0) + 1
        total_duration += item.duration_seconds
        current = summary["last_activity_at"]
        if not current or item.occurred_at > current:
            summary["last_activity_at"] = item.occurred_at
    for summary in by_user.values():
        summary["last_activity_at"] = _iso(summary["last_activity_at"])
    submission_query = (
        select(func.count(Submission.id))
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .where(Assignment.course_id == course_id)
    )
    if enrollment.role != "instructor":
        submission_query = submission_query.where(Submission.user_id == actor.id)
    return {
        "course_id": course_id,
        "events": len(rows),
        "active_users": len(by_user),
        "duration_seconds": total_duration,
        "submissions": db.scalar(submission_query) or 0,
        "by_type": by_type,
        "users": list(by_user.values()),
    }


def _planner_payload(item: PlannerItem, db: Session) -> dict | None:
    from src.course_source.pacewise_contracts import planner_payload
    return planner_payload(db, item)


def _validate_planner(payload: PlannerPayload, actor: User, db: Session) -> None:
    if payload.course_id is not None:
        _enrollment(db, actor.id, payload.course_id)
    if payload.assignment_id is not None:
        assignment = _assignment(db, payload.assignment_id)
        if assignment.course_id != payload.course_id:
            raise HTTPException(422, "Assignment must belong to the selected course")
        enrollment = _enrollment(db, actor.id, assignment.course_id)
        if enrollment.role != "instructor" and not assignment.published:
            raise HTTPException(403, "Assignment is not published")


@router.get("/planner")
def list_planner(request: Request, db: Session = Depends(get_db)) -> list[dict]:
    actor = _actor(request, db)
    return [value for item in db.scalars(select(PlannerItem).where(PlannerItem.user_id == actor.id).order_by(PlannerItem.due_at)).all() if (value := _planner_payload(item, db)) is not None]


@router.post("/planner", status_code=201)
def create_planner_item(payload: PlannerPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _actor(request, db)
    _validate_planner(payload, actor, db)
    item = PlannerItem(user_id=actor.id, **payload.model_dump())
    db.add(item)
    db.flush()
    record_change(db, actor_user_id=actor.id, action="planner_item.created", entity_type="planner_item", entity_id=item.id, course_id=item.course_id, metadata={"title": item.title})
    db.commit()
    return _planner_payload(item, db)


@router.put("/planner/{item_id}")
def update_planner_item(item_id: int, payload: PlannerPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _actor(request, db)
    item = db.scalar(select(PlannerItem).where(PlannerItem.id == item_id, PlannerItem.user_id == actor.id))
    if not item:
        raise HTTPException(status_code=404, detail="Planner item not found")
    _validate_planner(payload, actor, db)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    record_change(db, actor_user_id=actor.id, action="planner_item.updated", entity_type="planner_item", entity_id=item.id, course_id=item.course_id, metadata={"completed": item.completed})
    db.commit()
    return _planner_payload(item, db)


@router.delete("/planner/{item_id}")
def delete_planner_item(item_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _actor(request, db)
    item = db.scalar(select(PlannerItem).where(PlannerItem.id == item_id, PlannerItem.user_id == actor.id))
    if not item:
        raise HTTPException(status_code=404, detail="Planner item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.get("/courses/{course_id}/appointment-groups")
def list_appointment_groups(course_id: int, request: Request, db: Session = Depends(get_db)) -> list[dict]:
    actor = _actor(request, db)
    _enrollment(db, actor.id, course_id)
    return [{"id": item.id, "title": item.title, "starts_at": _iso(item.starts_at), "ends_at": _iso(item.ends_at), "slot_minutes": item.slot_minutes, "participants_per_slot": item.participants_per_slot} for item in db.scalars(select(AppointmentGroup).where(AppointmentGroup.course_id == course_id)).all()]


@router.post("/courses/{course_id}/appointment-groups", status_code=201)
def create_appointment_group(course_id: int, payload: AppointmentPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _teacher(request, db, course_id)
    if payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    item = AppointmentGroup(course_id=course_id, **payload.model_dump())
    db.add(item)
    db.flush()
    record_change(db, actor_user_id=actor.id, action="appointment_group.created", entity_type="appointment_group", entity_id=item.id, course_id=course_id)
    db.commit()
    return {"id": item.id, "title": item.title}


@router.post("/appointment-groups/{group_id}/reservations", status_code=201)
def reserve_appointment(group_id: int, payload: ReservationPayload, request: Request, db: Session = Depends(get_db)) -> dict:
    # Serialize capacity checks on PostgreSQL; SQLite tests exercise validation.
    group = db.scalar(select(AppointmentGroup).where(AppointmentGroup.id == group_id).with_for_update())
    if not group:
        raise HTTPException(status_code=404, detail="Appointment group not found")
    actor = _actor(request, db)
    _enrollment(db, actor.id, group.course_id)
    ends_at = payload.starts_at + timedelta(minutes=group.slot_minutes)
    if _as_utc(payload.starts_at) < _as_utc(group.starts_at) or _as_utc(ends_at) > _as_utc(group.ends_at):
        raise HTTPException(status_code=422, detail="Reservation is outside appointment window")
    if (_as_utc(payload.starts_at) - _as_utc(group.starts_at)).total_seconds() % (group.slot_minutes * 60):
        raise HTTPException(422, "Reservation must align with an appointment slot")
    if db.scalar(select(AppointmentReservation.id).where(AppointmentReservation.appointment_group_id == group_id, AppointmentReservation.user_id == actor.id)):
        raise HTTPException(409, "You already reserved an appointment in this group")
    count = db.scalar(select(func.count(AppointmentReservation.id)).where(AppointmentReservation.appointment_group_id == group_id, AppointmentReservation.starts_at == payload.starts_at)) or 0
    if count >= group.participants_per_slot:
        raise HTTPException(status_code=409, detail="Appointment slot is full")
    item = AppointmentReservation(appointment_group_id=group_id, user_id=actor.id, starts_at=payload.starts_at, ends_at=ends_at)
    db.add(item)
    db.flush()
    record_change(db, actor_user_id=actor.id, action="appointment.reserved", entity_type="appointment_reservation", entity_id=item.id, course_id=group.course_id)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "starts_at": _iso(item.starts_at), "ends_at": _iso(item.ends_at)}
