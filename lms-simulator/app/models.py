from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), index=True)
    avatar_color: Mapped[str] = mapped_column(String(16), default="#2563eb")

    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="user")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    term: Mapped[str] = mapped_column(String(128))
    color: Mapped[str] = mapped_column(String(16))
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)

    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="course")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="course")
    resources: Mapped[list["Resource"]] = relationship(back_populates="course")


class CourseLifecycle(Base):
    """Additive lifecycle metadata; existing course/history tables are untouched."""
    __tablename__ = "course_lifecycle"
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class TeacherScheduleBatch(Base):
    __tablename__ = "teacher_schedule_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    preview_json: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("user_id", "fingerprint", name="uq_teacher_schedule_batch"),)


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_enrollment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(32))
    progress: Mapped[float] = mapped_column(Float, default=0)

    user: Mapped[User] = relationship(back_populates="enrollments")
    course: Mapped[Course] = relationship(back_populates="enrollments")


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    points_possible: Mapped[float] = mapped_column(Float, default=10)
    submission_types: Mapped[str] = mapped_column(String(255), default="online_text_entry")
    published: Mapped[bool] = mapped_column(Boolean, default=True)

    course: Mapped[Course] = relationship(back_populates="assignments")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="assignment")


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "user_id", name="uq_submission"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    workflow_state: Mapped[str] = mapped_column(String(32), default="unsubmitted")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    late: Mapped[bool] = mapped_column(Boolean, default=False)

    assignment: Mapped[Assignment] = relationship(back_populates="submissions")


class SubmissionDetail(Base):
    __tablename__ = "submission_details"
    __table_args__ = (UniqueConstraint("submission_id", name="uq_submission_detail"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    text_entry: Mapped[str] = mapped_column(Text, default="")
    website_url: Mapped[str] = mapped_column(String(1000), default="")
    file_name: Mapped[str] = mapped_column(String(255), default="")
    file_url: Mapped[str] = mapped_column(String(1000), default="")
    instructor_comment: Mapped[str] = mapped_column(Text, default="")
    rubric_json: Mapped[str] = mapped_column(Text, default="{}")


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32))
    source_url: Mapped[str] = mapped_column(String(500))

    course: Mapped[Course] = relationship(back_populates="resources")


class CourseModule(Base):
    __tablename__ = "course_modules"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=1)
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class ModuleItem(Base):
    __tablename__ = "module_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("course_modules.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    item_type: Mapped[str] = mapped_column(String(32), default="resource")
    content_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_url: Mapped[str] = mapped_column(String(1000), default="")
    position: Mapped[int] = mapped_column(Integer, default=1)
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class CourseContent(Base):
    __tablename__ = "course_content"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    points_possible: Mapped[float | None] = mapped_column(Float, nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


class DiscussionReply(Base):
    __tablename__ = "discussion_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    discussion_id: Mapped[int] = mapped_column(ForeignKey("course_content.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("discussion_replies.id", ondelete="CASCADE"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class DiscussionLike(Base):
    __tablename__ = "discussion_likes"
    __table_args__ = (UniqueConstraint("reply_id", "user_id", name="uq_discussion_like"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reply_id: Mapped[int] = mapped_column(ForeignKey("discussion_replies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class TeachingEventLink(Base):
    __tablename__ = "teaching_event_links"

    calendar_event_id: Mapped[int] = mapped_column(ForeignKey("calendar_events.id", ondelete="CASCADE"), primary_key=True)
    occurrence_key: Mapped[str] = mapped_column(String(36), index=True)


class QuizAssignmentLink(Base):
    """Canonical assignment backing a dated graded quiz, as in Canvas."""
    __tablename__ = "quiz_assignment_links"
    quiz_id: Mapped[int] = mapped_column(ForeignKey("course_content.id", ondelete="CASCADE"), primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), unique=True, index=True)


class TeacherTaskMetadata(Base):
    __tablename__ = "teacher_task_metadata"
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), default="assignment")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    resource_ids_json: Mapped[str] = mapped_column(Text, default="[]")


class TeacherProfile(Base):
    __tablename__ = "teacher_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    profile_json: Mapped[str] = mapped_column(Text, default="{}")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("course_content.id", ondelete="CASCADE"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    options_json: Mapped[str] = mapped_column(Text, default="[]")
    correct_answer: Mapped[str] = mapped_column(Text)
    points: Mapped[float] = mapped_column(Float, default=1)
    position: Mapped[int] = mapped_column(Integer, default=1)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (UniqueConstraint("quiz_id", "user_id", name="uq_quiz_attempt"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("course_content.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    answers_json: Mapped[str] = mapped_column(Text, default="{}")
    score: Mapped[float] = mapped_column(Float, default=0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class OutcomeAlignment(Base):
    __tablename__ = "outcome_alignments"
    __table_args__ = (UniqueConstraint("outcome_id", "assignment_id", name="uq_outcome_assignment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    outcome_id: Mapped[int] = mapped_column(ForeignKey("course_content.id", ondelete="CASCADE"), index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_kind: Mapped[str] = mapped_column(String(50), default="personal")
    join_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attendance_status: Mapped[str | None] = mapped_column(String(20), nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"
    __table_args__ = (UniqueConstraint("conversation_id", "user_id", name="uq_conversation_participant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


class ConversationState(Base):
    __tablename__ = "conversation_states"
    __table_args__ = (UniqueConstraint("conversation_id", "user_id", name="uq_conversation_state"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    unread: Mapped[bool] = mapped_column(Boolean, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("conversation_messages.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_url: Mapped[str] = mapped_column(String(1000))


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BrowserBridgeTicket(Base):
    __tablename__ = "browser_bridge_tickets"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(32))
    session_reference: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BrowserBridgeSession(Base):
    __tablename__ = "browser_bridge_sessions"

    auth_session_id: Mapped[int] = mapped_column(ForeignKey("auth_sessions.id", ondelete="CASCADE"), primary_key=True)
    session_reference: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    pronouns: Mapped[str] = mapped_column(String(64), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh")
    language: Mapped[str] = mapped_column(String(32), default="en")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_user_notification_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(64))
    frequency: Mapped[str] = mapped_column(String(16), default="daily")


class PersonalFile(Base):
    __tablename__ = "personal_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(128), default="")
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    request_id: Mapped[str] = mapped_column(String(64), default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class IntegrationEvent(Base):
    __tablename__ = "integration_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(128), default="")
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class GradeHistory(Base):
    __tablename__ = "grade_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    grader_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    rubric_json: Mapped[str] = mapped_column(Text, default="{}")
    graded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class LearningEvidence(Base):
    __tablename__ = "learning_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str] = mapped_column(String(128), default="")
    competency_key: Mapped[str] = mapped_column(String(128), index=True)
    score: Mapped[float] = mapped_column(Float, default=0)
    max_score: Mapped[float] = mapped_column(Float, default=1)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class LaunchNonce(Base):
    __tablename__ = "launch_nonces"

    id: Mapped[int] = mapped_column(primary_key=True)
    nonce: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# Canvas-compatible learning structures used by PaceWise. These are separate
# extension tables so existing simulator databases can be upgraded with
# create_all instead of destructive column migrations.


class AssignmentGroup(Base):
    __tablename__ = "assignment_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=1)
    group_weight: Mapped[float] = mapped_column(Float, default=0)
    drop_lowest: Mapped[int] = mapped_column(Integer, default=0)
    drop_highest: Mapped[int] = mapped_column(Integer, default=0)


class AssignmentConfiguration(Base):
    __tablename__ = "assignment_configurations"

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), unique=True, index=True
    )
    assignment_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("assignment_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    unlock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grading_type: Mapped[str] = mapped_column(String(32), default="points")
    peer_reviews: Mapped[bool] = mapped_column(Boolean, default=False)
    group_category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AssignmentOverride(Base):
    __tablename__ = "assignment_overrides"
    __table_args__ = (
        UniqueConstraint("assignment_id", "target_type", "target_id", name="uq_assignment_override_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    target_type: Mapped[str] = mapped_column(String(32), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unlock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CourseSection(Base):
    __tablename__ = "course_sections"
    __table_args__ = (UniqueConstraint("course_id", "name", name="uq_course_section_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))


class SectionMembership(Base):
    __tablename__ = "section_memberships"
    __table_args__ = (UniqueConstraint("section_id", "user_id", name="uq_section_membership"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("course_sections.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


class GroupCategory(Base):
    __tablename__ = "group_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    self_signup: Mapped[bool] = mapped_column(Boolean, default=False)


class CourseGroup(Base):
    __tablename__ = "course_groups"
    __table_args__ = (UniqueConstraint("category_id", "name", name="uq_course_group_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("group_categories.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))


class GroupMembership(Base):
    __tablename__ = "group_memberships"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_membership"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("course_groups.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


class ModulePrerequisite(Base):
    __tablename__ = "module_prerequisites"
    __table_args__ = (UniqueConstraint("module_id", "prerequisite_module_id", name="uq_module_prerequisite"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("course_modules.id", ondelete="CASCADE"), index=True)
    prerequisite_module_id: Mapped[int] = mapped_column(
        ForeignKey("course_modules.id", ondelete="CASCADE"), index=True
    )


class ModulePolicy(Base):
    __tablename__ = "module_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int] = mapped_column(
        ForeignKey("course_modules.id", ondelete="CASCADE"), unique=True, index=True
    )
    sequential_progress: Mapped[bool] = mapped_column(Boolean, default=False)


class ModuleRequirement(Base):
    __tablename__ = "module_requirements"
    __table_args__ = (UniqueConstraint("module_item_id", name="uq_module_item_requirement"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    module_item_id: Mapped[int] = mapped_column(ForeignKey("module_items.id", ondelete="CASCADE"), index=True)
    requirement_type: Mapped[str] = mapped_column(String(32), default="must_view")
    min_score: Mapped[float | None] = mapped_column(Float, nullable=True)


class ModuleItemProgress(Base):
    __tablename__ = "module_item_progress"
    __table_args__ = (UniqueConstraint("module_item_id", "user_id", name="uq_module_item_progress"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    module_item_id: Mapped[int] = mapped_column(ForeignKey("module_items.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="unlocked")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SubmissionAttempt(Base):
    __tablename__ = "submission_attempts"
    __table_args__ = (UniqueConstraint("submission_id", "attempt_number", name="uq_submission_attempt"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    text_entry: Mapped[str] = mapped_column(Text, default="")
    website_url: Mapped[str] = mapped_column(String(1000), default="")


class SubmissionAttachment(Base):
    __tablename__ = "submission_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("submission_attempts.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_url: Mapped[str] = mapped_column(String(1000))


class SubmissionComment(Base):
    __tablename__ = "submission_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class SubmissionWorkflow(Base):
    __tablename__ = "submission_workflows"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), unique=True, index=True
    )
    excused: Mapped[bool] = mapped_column(Boolean, default=False)
    reassigned: Mapped[bool] = mapped_column(Boolean, default=False)


class Rubric(Base):
    __tablename__ = "rubrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    points_possible: Mapped[float] = mapped_column(Float, default=0)


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    rubric_id: Mapped[int] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(String(500))
    long_description: Mapped[str] = mapped_column(Text, default="")
    points: Mapped[float] = mapped_column(Float, default=0)
    position: Mapped[int] = mapped_column(Integer, default=1)


class RubricRating(Base):
    __tablename__ = "rubric_ratings"

    id: Mapped[int] = mapped_column(primary_key=True)
    criterion_id: Mapped[int] = mapped_column(ForeignKey("rubric_criteria.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(String(255))
    points: Mapped[float] = mapped_column(Float)


class AssignmentRubric(Base):
    __tablename__ = "assignment_rubrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), unique=True, index=True
    )
    rubric_id: Mapped[int] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"), index=True)


class RubricAssessment(Base):
    __tablename__ = "rubric_assessments"
    __table_args__ = (UniqueConstraint("submission_id", "criterion_id", name="uq_rubric_assessment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    criterion_id: Mapped[int] = mapped_column(ForeignKey("rubric_criteria.id", ondelete="CASCADE"), index=True)
    assessor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    points: Mapped[float] = mapped_column(Float)
    comments: Mapped[str] = mapped_column(Text, default="")


class ResourceFolder(Base):
    __tablename__ = "resource_folders"
    __table_args__ = (UniqueConstraint("course_id", "parent_id", "name", name="uq_resource_folder_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("resource_folders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))


class ResourceVersion(Base):
    __tablename__ = "resource_versions"
    __table_args__ = (UniqueConstraint("resource_id", "version", name="uq_resource_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), index=True)
    folder_id: Mapped[int | None] = mapped_column(
        ForeignKey("resource_folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    source_url: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ResourceAccess(Base):
    __tablename__ = "resource_access"
    __table_args__ = (UniqueConstraint("resource_id", "scope_type", "scope_id", name="uq_resource_access"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), default="course")
    scope_id: Mapped[int] = mapped_column(Integer)
    permission: Mapped[str] = mapped_column(String(16), default="read")


class LearningActivity(Base):
    __tablename__ = "learning_activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    activity_type: Mapped[str] = mapped_column(String(64), index=True)
    object_type: Mapped[str] = mapped_column(String(64), default="")
    object_id: Mapped[str] = mapped_column(String(128), default="")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class PlannerItem(Base):
    __tablename__ = "planner_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True
    )
    assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class AppointmentGroup(Base):
    __tablename__ = "appointment_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    slot_minutes: Mapped[int] = mapped_column(Integer, default=30)
    participants_per_slot: Mapped[int] = mapped_column(Integer, default=1)


class AppointmentReservation(Base):
    __tablename__ = "appointment_reservations"
    __table_args__ = (UniqueConstraint("appointment_group_id", "user_id", name="uq_appointment_reservation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_group_id: Mapped[int] = mapped_column(
        ForeignKey("appointment_groups.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
