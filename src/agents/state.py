import operator
from typing import Annotated, Any, TypedDict


class LearningGraphState(TypedDict, total=False):
    """
    Trạng thái trung tâm (State) của hệ thống Multi-Agent LMS Canvas.
    Được thiết kế dựa trên đặc tả trong specs/detail.md.
    """

    # --- 1. Định danh và định tuyến (Routing & ID) ---
    institution_id: str
    run_id: str
    request_id: str
    student_id: str
    course_id: str
    course_code: str
    role: str
    week_id: str
    workflow: str  # plan | do | tracking | qa | understanding | recover | reflect
    current_node: str
    messages: Annotated[list[dict[str, Any]], operator.add]
    request: dict[str, Any]

    # Các trường tương thích nhanh với API endpoint (/api/v1/chat) và Terminal CLI
    query: str
    qa_history: list[dict[str, str]]
    response: str
    analysis: str
    mode: str  # grounded | abstained | integrity | conversation | out_of_scope

    # --- 2. Dữ liệu đầu vào (Context) ---
    goals: list[dict[str, Any]]
    planning_stage: str
    assignments: list[dict[str, Any]]
    modules: list[dict[str, Any]]
    planner_items: list[dict[str, Any]]
    priority_weights: dict[str, Any]
    availability: list[dict[str, Any]]
    unavailable_slots: list[dict[str, Any]]
    current_plan: dict[str, Any] | None
    learning_resources: list[dict[str, Any]]
    authorized_file_versions: dict[str, str]
    allowed_resource_ids: list[str] | None
    preferred_resource_ids: list[str]
    do_scope: dict[str, Any]
    lms_files: list[dict[str, Any]]
    approved_rubric: list[dict[str, Any]] | dict[str, Any] | None
    learner_profile: dict[str, Any]
    mastery_profile: dict[str, Any]
    misconceptions: list[dict[str, Any]]

    # --- 3. Trạng thái trung gian & Đầu ra của Agent ---
    proposed_milestones: list[dict[str, Any]]
    candidate_schedules: list[dict[str, Any]]
    retrieved_passages: list[dict[str, Any]]
    assessment_result: dict[str, Any] | None
    progress_metrics: dict[str, Any]
    # Snapshot fields describe the latest calculation. They replace values
    # from the previous turn so resolved risks/errors do not remain visible.
    risk_signals: list[dict[str, Any]]
    recovery_snapshot: dict[str, Any] | None
    recovery_options: list[dict[str, Any]]
    reflection_draft: dict[str, Any] | None
    do_session: dict[str, Any] | None

    # --- 4. Cờ kiểm duyệt & Bất định (Guardrails) ---
    security_flags: dict[str, Any]
    validation_errors: list[dict[str, Any]]
    uncertainties: list[dict[str, Any]]
    disputed_evidence: list[dict[str, Any]]

    # --- 5. Trạng thái luồng điều khiển (Control Flow) ---
    status: str  # running | awaiting_student | awaiting_teacher | completed | failed
    pending_action: dict[str, Any] | None
    student_decision: dict[str, Any] | None

    # --- 6. Truy vết (Tracing & Observability) ---
    source_refs: list[dict[str, Any]]
    audit_events: Annotated[list[dict[str, Any]], operator.add]
    output: dict[str, Any] | None
    quality_review: dict[str, Any]
    quality_repair_count: int
