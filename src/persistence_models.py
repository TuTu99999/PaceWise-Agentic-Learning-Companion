from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, LargeBinary, String, Text, UniqueConstraint, event, false
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base
from src.services.customer_crypto import EncryptedText


def utcnow() -> datetime:
    return datetime.now(UTC)


class AiUsageBucket(Base):
    __tablename__ = "pacewise_ai_usage_buckets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    scope_hash: Mapped[str] = mapped_column(String(64), index=True)
    limit_type: Mapped[str] = mapped_column(String(48), index=True)
    window_start: Mapped[int] = mapped_column(BigInteger, index=True)
    used: Mapped[int] = mapped_column(BigInteger, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AiUsageReservation(Base):
    __tablename__ = "pacewise_ai_usage_reservations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    user_scope_hash: Mapped[str] = mapped_column(String(64), index=True)
    workflow: Mapped[str] = mapped_column(String(32), default="qa", index=True)
    request_weight: Mapped[int] = mapped_column(Integer, default=1)
    reserved_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    actual_input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    actual_output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    estimated_cost_microusd: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(24), default="reserved", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LmsFileIndex(Base):
    """Derived text only; the binary remains in the authoritative course store."""
    __tablename__ = "lms_file_indexes"
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(255), index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    file_id: Mapped[int] = mapped_column(Integer)
    resource_version: Mapped[str] = mapped_column(String(64), default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    chunks_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(255), default="")
    idempotency_key: Mapped[str] = mapped_column(String(255), default="", index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PaceWiseSession(Base):
    __tablename__ = "pacewise_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(EncryptedText("session-name"))
    email: Mapped[str] = mapped_column(EncryptedText("session-email"))
    active_course_id: Mapped[int] = mapped_column(Integer, index=True)
    course_ids_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserWorkspace(Base):
    __tablename__ = "pacewise_workspaces"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state_json: Mapped[str] = mapped_column(EncryptedText("workspace"), default="{}")
    push_opted_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


@event.listens_for(UserWorkspace, "before_insert")
@event.listens_for(UserWorkspace, "before_update")
def _workspace_notification_projection(mapper, connection, target):
    from src.services.customer_crypto import push_opted_in

    target.push_opted_in = push_opted_in(target.state_json or "{}")


class StudyTimerSession(Base):
    """One durable timer per learner/block; CAS protects concurrent tabs/retries."""
    __tablename__ = "pacewise_study_timer_sessions"
    __table_args__ = (UniqueConstraint("institution_id", "user_id", "block_id", name="uq_study_timer_block"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    block_id: Mapped[str] = mapped_column(String(128), index=True)
    task_id: Mapped[str] = mapped_column(String(160))
    active_scope: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    state_json: Mapped[str] = mapped_column(Text, default="{}")
    # Ephemeral learning-support transcript. It is encrypted at rest and
    # erased when the Do session completes, is cancelled, or expires.
    chat_json: Mapped[str] = mapped_column(EncryptedText("do-chat"), default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class InstructorAction(Base):
    __tablename__ = "pacewise_instructor_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    actor_user_id: Mapped[int] = mapped_column(Integer, index=True)
    action_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(128), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class LoginAttempt(Base):
    __tablename__ = "pacewise_login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SyncCursor(Base):
    __tablename__ = "pacewise_sync_cursors"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_event_id: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class WorkerHeartbeat(Base):
    """Durable worker health visible from a different API process."""

    __tablename__ = "pacewise_worker_heartbeats"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    worker_kind: Mapped[str] = mapped_column(String(64), index=True)
    instance_id: Mapped[str] = mapped_column(String(160), index=True)
    queue_lag: Mapped[int] = mapped_column(Integer, default=0)
    failed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class LmsEventProjection(Base):
    """Durable copy of an LMS event before downstream processing."""

    __tablename__ = "pacewise_lms_event_projections"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    source_event_id: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(128))
    course_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    occurred_at: Mapped[str] = mapped_column(String(64), default="")
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CourseProjection(Base):
    """Latest server-side LMS state used by risk and ingestion workflows."""

    __tablename__ = "pacewise_course_projections"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    assignments_json: Mapped[str] = mapped_column(Text, default="[]")
    risk_signals_json: Mapped[str] = mapped_column(Text, default="[]")
    content_version: Mapped[str] = mapped_column(String(64), default="")
    risk_refresh_required: Mapped[int] = mapped_column(Integer, default=0)
    last_event_id: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LmsCourseContextProjection(Base):
    """Read-optimized LMS context consumed by agent requests."""

    __tablename__ = "pacewise_lms_course_contexts"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    course_json: Mapped[str] = mapped_column(Text, default="{}")
    assignments_json: Mapped[str] = mapped_column(Text, default="[]")
    modules_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LearnerMemory(Base):
    """Long-lived learner profile separate from weekly LangGraph memory."""

    __tablename__ = "pacewise_learner_memories"

    id: Mapped[str] = mapped_column(String(256), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    profile_json: Mapped[str] = mapped_column(EncryptedText("learner-profile"), default="{}")
    mastery_json: Mapped[str] = mapped_column(EncryptedText("learner-mastery"), default="{}")
    misconceptions_json: Mapped[str] = mapped_column(EncryptedText("learner-misconceptions"), default="[]")
    history_json: Mapped[str] = mapped_column(EncryptedText("learner-history"), default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LearningEvidenceRecord(Base):
    """Append-only evidence emitted by an approved assessment checkpoint."""

    __tablename__ = "pacewise_learning_evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(32), default="learning-evidence-v1")
    evaluator_version: Mapped[str] = mapped_column(String(64), index=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    student_user_id: Mapped[int] = mapped_column(Integer, index=True)
    assessment_id: Mapped[str] = mapped_column(String(128), index=True)
    block_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    item_type: Mapped[str] = mapped_column(String(32), index=True)
    first_attempt: Mapped[int] = mapped_column(Integer, default=1)
    hint_level: Mapped[int] = mapped_column(Integer, default=0)
    valid: Mapped[int] = mapped_column(Integer, default=0, index=True)
    response_text: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class KnowledgeStateSnapshot(Base):
    """Explainable derived KC state; one immutable snapshot per accepted evidence."""

    __tablename__ = "pacewise_knowledge_state_snapshots"
    __table_args__ = (
        UniqueConstraint("evidence_id", "knowledge_component_id", name="uq_knowledge_snapshot_evidence_kc"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    student_user_id: Mapped[int] = mapped_column(Integer, index=True)
    knowledge_component_id: Mapped[str] = mapped_column(String(160), index=True)
    level: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[str] = mapped_column(String(16), index=True)
    retention_status: Mapped[str] = mapped_column(String(32), default="not_tested")
    evidence_id: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class LearningEvent(Base):
    """Idempotent audit event for the Plan-Do-Reflect learning cycle."""

    __tablename__ = "pacewise_learning_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    student_user_id: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(160), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AdaptiveAssessmentSession(Base):
    """Server-owned checkpoint state, including attempts and retry receipts."""

    __tablename__ = "pacewise_adaptive_assessment_sessions"
    __table_args__ = (
        UniqueConstraint("institution_id", "student_user_id", "course_id", "block_id", "kc_id",
                         "mode", name="uq_adaptive_checkpoint_scope"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    student_user_id: Mapped[int] = mapped_column(Integer, index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    block_id: Mapped[str] = mapped_column(String(128))
    kc_id: Mapped[str] = mapped_column(String(160), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="learning")
    state_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DelayedAssessmentProbe(Base):
    """A due date is not retention evidence; only a later accepted response is."""

    __tablename__ = "pacewise_delayed_assessment_probes"
    __table_args__ = (UniqueConstraint("baseline_evidence_id", name="uq_delayed_baseline"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    student_user_id: Mapped[int] = mapped_column(Integer, index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    kc_id: Mapped[str] = mapped_column(String(160), index=True)
    baseline_evidence_id: Mapped[str] = mapped_column(String(64))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")


class AgentReviewCase(Base):
    """Durable instructor queue for AI uncertainty and citation disputes."""

    __tablename__ = "pacewise_agent_review_cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    student_user_id: Mapped[int] = mapped_column(Integer, index=True)
    case_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RagIngestionJob(Base):
    """PostgreSQL-backed ingestion queue; one job represents one course snapshot."""

    __tablename__ = "pacewise_rag_ingestion_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    resource_version: Mapped[str] = mapped_column(String(64), index=True)
    resources_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, default=lambda: f"legacy:{uuid4().hex}"
    )
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    queue_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class GoogleCalendarConnection(Base):
    __tablename__ = "google_calendar_connections"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text)
    granted_scopes: Mapped[str] = mapped_column(Text)
    calendar_id: Mapped[str] = mapped_column(String(255), default="primary")
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_freebusy_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebPushSubscription(Base):
    __tablename__ = "pacewise_web_push_subscriptions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    subscription_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificationJob(Base):
    __tablename__ = "pacewise_notification_jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    reminder_key: Mapped[str] = mapped_column(String(512))
    kind: Mapped[str] = mapped_column(String(32))
    priority: Mapped[int] = mapped_column(Integer, default=2)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(128), default="")
    idempotency_key: Mapped[str] = mapped_column(String(255), default="", index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    queue_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[str] = mapped_column(String(255), default="")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationDailyBudget(Base):
    __tablename__ = "pacewise_notification_daily_budgets"
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class GoogleOAuthState(Base):
    __tablename__ = "google_oauth_states"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    encrypted_code_verifier: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GoogleCalendarEventLink(Base):
    __tablename__ = "google_calendar_event_links"
    __table_args__ = (UniqueConstraint("user_id", "block_id", name="uq_google_calendar_user_block"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    block_id: Mapped[str] = mapped_column(String(128), index=True)
    google_event_id: Mapped[str] = mapped_column(String(255))
    event_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntegrationAuditLog(Base):
    __tablename__ = "pacewise_integration_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CourseMaterial(Base):
    """Legacy material metadata; production binaries live only in private S3."""

    __tablename__ = "pacewise_course_materials"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(128), index=True)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(255))
    module_name: Mapped[str] = mapped_column(String(128), default="Chung")
    file_name: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(32), index=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    file_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    object_key: Mapped[str | None] = mapped_column(String(1000), nullable=True, unique=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    mime_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class PrivateRequestNonce(Base):
    """Replay prevention for the encrypted API, shared across replicas."""

    __tablename__ = "private_request_nonces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class GoogleQuotaState(Base):
    """One row serializes quota reservations across all application replicas."""

    __tablename__ = "google_quota_state"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state_json: Mapped[str] = mapped_column(Text, default="{}")


class GoogleReadCache(Base):
    """Encrypted, grant-scoped availability/account cache; no plain Google token."""

    __tablename__ = "google_read_cache"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    encrypted_json: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

