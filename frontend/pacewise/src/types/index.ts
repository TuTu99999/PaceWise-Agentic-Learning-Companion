// Domain types for PaceWise. These mirror the shapes a real backend API would return.

export type Role = 'student' | 'instructor' | 'guest';

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  /** Course bound to the authenticated LMS launch/session. */
  courseId?: string;
  courseIds?: string[];
  /** Demo flag: a first-time student who has no saved plan yet. */
  isNew?: boolean;
}

export interface CanvasSyncResult {
  courses: Course[];
  tasks: Task[];
  courseData: Record<string, LMSCourseData>;
  guidance?: ClassGuidance[];
  assessments?: AssessmentItem[];
  reviewResolutions?: Record<string, {
    status: ReviewStatus;
    note?: string;
    resolvedStatus?: string;
  }>;
  syncedAt: string;
  source: string;
  activeCourseId: string;
}

export interface Course {
  id: string;
  code: string;
  name: string;
  tone: Tone;
}

export type Tone = 'primary' | 'success' | 'warning' | 'danger' | 'accent' | 'neutral';

export type Priority = 'high' | 'medium' | 'low';
export type PersonalPriority = 1 | 2 | 3 | 4;
export type TaskStatus = 'todo' | 'in_progress' | 'done';

export interface Task {
  id: string;
  lmsAssignmentId?: string;
  title: string;
  courseId: string;
  /** Local date `YYYY-MM-DD`, deadline is 23:59 GMT+7 of that day. */
  deadline: string;
  estimateMin: number;
  loggedMin: number;
  status: TaskStatus;
  priority: Priority;
  /** Learner-owned preference; independent from LMS weight and system risk. */
  personalPriority?: PersonalPriority;
  objective: string;
  /** True when the estimate came from PaceWise rather than the student. */
  estimateIsAssumption?: boolean;
  estimateSource?: string;
  dueAt?: string | null;
  unlockAt?: string | null;
  lockAt?: string | null;
  overrideTarget?: 'student' | 'group' | 'section' | null;
  pointsPossible?: number;
  assignmentGroup?: LMSAssignmentGroup | null;
  gradingType?: string;
  peerReviews?: boolean;
  groupCategoryId?: string | null;
  rubric?: LMSRubric | null;
  submission?: LMSSubmissionSummary;
}

/** User-owned fields layered on top of the latest LMS task snapshot. */
export interface TaskProgress {
  estimateMin: number;
  estimateIsAssumption?: boolean;
  loggedMin: number;
  status: TaskStatus;
  personalPriority?: PersonalPriority;
  updatedAt: string;
}

export interface LMSAssignmentGroup {
  id: string;
  name: string;
  weight: number;
}

export interface LMSRubricRating {
  id: number;
  description: string;
  points: number;
}

export interface LMSRubricCriterion {
  id: number;
  description: string;
  long_description?: string;
  points: number;
  position: number;
  ratings: LMSRubricRating[];
}

export interface LMSRubric {
  id: number;
  title: string;
  points_possible: number;
  criteria: LMSRubricCriterion[];
}

export interface LMSSubmissionSummary {
  state: string;
  attempts: number;
  submittedAt?: string | null;
  late: boolean;
  score: number | null;
  feedback: string;
  rubricAssessment: Record<string, unknown>;
}

export interface LMSModuleRequirement {
  id: number;
  module_item_id: number;
  requirement_type: string;
  min_score: number | null;
  status: string;
}

export interface LMSModule {
  id: number;
  name: string;
  position: number;
  published: boolean;
  sequential_progress: boolean;
  prerequisite_module_ids: number[];
  requirements: LMSModuleRequirement[];
  items: Array<{ id: number; title: string; type: string; published: boolean }>;
}

export interface LMSResource {
  id: number;
  title: string;
  kind: string;
  source_url: string;
  folder: { id: number; name: string } | null;
  latest_version: {
    version: number;
    checksum_sha256: string;
    content_type: string;
    created_at: string;
  } | null;
  access_scope: Array<{ type: string; id: number }>;
}

export interface LMSPlannerItem {
  id: number;
  course_id: number;
  assignment_id: number | null;
  title: string;
  due_at: string | null;
  completed: boolean;
}

export interface LMSCalendarItem {
  id: string;
  source_id: number;
  type: 'assignment' | 'event';
  course_id: number | null;
  course_code: string | null;
  title: string;
  starts_at: string;
  ends_at: string | null;
  duration_minutes: number | null;
  event_kind: string;
  editable: boolean;
  source?: 'lms' | 'pacewise_instructor';
  location?: string;
  meeting_url?: string;
  module_id?: string;
  knowledge_component_ids?: string[];
  preparation?: string;
}

export interface LMSAppointmentGroup {
  id: number;
  title: string;
  starts_at: string;
  ends_at: string;
  slot_minutes: number;
  participants_per_slot: number;
  reservations: Array<{ id: number; user_id: number; starts_at: string; ends_at: string }>;
}

export interface LMSAnalytics {
  events: number;
  active_users: number;
  duration_seconds: number;
  by_type: Record<string, number>;
}

export interface LMSCourseData {
  courseId: string;
  modules: LMSModule[];
  resources: LMSResource[];
  plannerItems: LMSPlannerItem[];
  appointmentGroups: LMSAppointmentGroup[];
  calendarItems?: LMSCalendarItem[];
  sections?: Array<{ id: number; name: string; member_ids: number[] }>;
  groups?: Array<{
    id: number;
    name: string;
    self_signup: boolean;
    groups: Array<{ id: number; name: string; member_ids: number[] }>;
  }>;
  analytics?: LMSAnalytics;
}

/** `HH:MM` 24h clock. */
export type Clock = string;

export interface TimeBlock {
  activityType?: StudyActivity | 'unknown';
  activitySource?: string;
  rhythm?: { sessionMinutes: number; breakMinutes: number };
  id: string;
  taskId: string;
  /** Optional AI decomposition; calendar placement remains deterministic. */
  milestoneId?: string | null;
  milestoneTitle?: string | null;
  /** Local date `YYYY-MM-DD`. */
  date: string;
  start: Clock;
  end: Clock;
  /** Current week is committed; next-week blocks remain a forecast. */
  status?: 'confirmed' | 'tentative' | 'history';
  /** Agent blocks may move on re-analysis; learner-positioned blocks stay pinned. */
  placementSource?: 'agent' | 'student';
  /** Work and optional extra assessment time; their sum is calendar duration. */
  workMinutes?: number;
  checkpointMinutes?: number;
}

export interface WeeklyGoal {
  id: string;
  title: string;
  taskIds: string[];
  confirmed: boolean;
  rationale?: string;
  sourceRefs?: string[];
  analysisSource?: 'model' | 'assignment_rule';
}

export interface Plan {
  id: string;
  weekStart: string;
  blocks: TimeBlock[];
  savedAt: string;
  version: number;
  feasibility?: Feasibility;
  confirmation?: PlanDraft['confirmation'];
}

/** 0 = Thứ Hai … 6 = Chủ Nhật */
export type Weekday = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export interface AvailabilityDay {
  weekday: Weekday;
  enabled: boolean;
  start: Clock;
  end: Clock;
}

export interface UnavailableSlot {
  id: string;
  label: string;
  weekday: Weekday;
  start: Clock;
  end: Clock;
  /** Exact local date for LMS/Google constraints; manual recurring slots omit it. */
  date?: string;
  source?: 'manual' | 'google' | 'lms' | 'routine';
  /** Self-study is a preferred window; the other categories are hard constraints. */
  category?: PersonalSlotCategory;
  readOnly?: boolean;
}

export type PersonalSlotCategory = 'meal' | 'self_study' | 'sleep' | 'other';
export type PreferredTime = 'late_night' | 'morning' | 'afternoon' | 'evening';

export interface RoutineProfile {
  wakeTime: Clock;
  sleepTime: Clock;
  preferred: PreferredTime[];
}

export interface PlanInput {
  studyPreferences?: StudyPreferences;
  goal: string;
  /** Monday of the selected calendar week. Optional for legacy saved drafts. */
  weekStart?: string;
  /** End of the visible forecast horizon (normally Sunday next week). */
  horizonEnd?: string;
  weeklyGoals?: WeeklyGoal[];
  tasks: {
    taskId: string;
    remainingMin: number;
    personalPriority?: PersonalPriority;
    weeklyGoalId?: string;
  }[];
  availability: AvailabilityDay[];
  unavailable: UnavailableSlot[];
  /** One or more preferred study periods. A scalar is accepted for old workspaces. */
  preferred: PreferredTime | PreferredTime[];
  /** Student-positioned blocks that the AI must preserve while scheduling the remainder. */
  pinnedBlocks?: TimeBlock[];
  /** Why an existing plan is being repaired; backend policy remains authoritative. */
  replanContext?: {
    trigger: 'reflection' | 'lms' | 'progress' | 'deadline';
    scope?: 'activity' | 'weekly';
    taskIds: string[];
  };
}

export interface Feasibility {
  availableMin: number;
  requiredMin: number;
  /** P80 workload used to expose capacity risk instead of a false precise estimate. */
  robustRequiredMin?: number;
  remainingMin: number;
  feasible: boolean;
  robustFeasible?: boolean;
  robustShortfalls?: { taskId: string; missingMin: number; deadline?: string }[];
  deadlineRisks?: Array<{
    deadline: string; deadlineMinute: number; taskIds: string[]; availableMin: number;
    requiredP50Min: number; requiredP80Min: number; slackP50Min: number; slackP80Min: number;
    risk: 'safe' | 'p80_shortage' | 'p50_shortage';
  }>;
  deficitMin: number;
  /** Tasks that could not be fully placed before their deadline. */
  shortfalls: { taskId: string; missingMin: number }[];
  /** Open 14-day deadlines intentionally left outside this draft. */
  uncoveredTasks?: { taskId: string; title: string; deadline: string }[];
}

export interface PartialPlanPreview {
  canConfirm: boolean;
  blockIds: string[];
  scheduledWorkMin: number;
  shortfalls: { taskId: string; missingMin: number }[];
  excludedBlocks: Array<{ blockId: string; taskId: string; reasons: Array<Record<string, unknown>> }>;
  errors?: Array<Record<string, unknown>>;
  requiresAcknowledgement: boolean;
}

export interface PlanDraft {
  /** UI hand-off provenance only; never an authorization to apply a schedule. */
  replan?: { contextKey: string; impactIds: string[]; trigger?: string; scope?: string; taskIds?: string[] };
  /** Unresolved expired work is separate from future capacity, not auto-completed. */
  expiredTasks?: Array<{ taskId: string; title: string; deadline: string; remainingMin?: number | null; status: 'overdue_unresolved' }>;
  confirmation?: PartialPlanPreview & { mode: 'partial'; acknowledgedShortfall: true };
  durationAdjustments?: Array<{ taskId: string; studentRemainingMin: number; baselineTargetMin: number; proposedTargetMin: number; reason: string; requiresConfirmation: boolean; sourceRefs?: string[]; evidenceCount?: number; estimateStatus?: string; reviewAddedMin?: number }>;
  replanAdjustments?: Array<{
    taskId: string; baselineRemainingMin: number; reconciledRemainingMin: number;
    addedMin: number; reason: 'observed_unfinished_work'; sourceRef: string;
  }>;
  diff?: {
    added: TimeBlock[]; removed: TimeBlock[];
    moved?: Array<{ taskId: string; before: TimeBlock; after: TimeBlock; workMinutes: number; changedDay: boolean }>;
    moved_block_count?: number; moved_work_minutes?: number; changed_day_count?: number;
    student_pinned_violations?: number; unchanged_count: number; stability: number; requires_confirmation: boolean;
  };
  input: PlanInput;
  weekStart?: string;
  weekEnd?: string;
  horizonEnd?: string;
  scheduleStart?: string;
  weeklyGoals?: WeeklyGoal[];
  decompositionAnalysis?: {
    modelOutput?: {
      valid?: boolean;
      errors?: Array<Record<string, unknown>>;
      expectedTaskIds?: string[];
      coveredTaskIds?: string[];
      fallbackApplied?: boolean;
      source?: 'model' | 'deterministic_template' | 'rule_based_fallback';
    };
    routes?: Record<string, { score?: number; maximum?: number; route?: 'template' | 'hybrid' | 'llm' }>;
    agentAnalysis?: string;
  };
  blocks: TimeBlock[];
  feasibility: Feasibility;
  reasons: string[];
  assumptions: string[];
  createdAt: string;
  /** Work that must be completed inside this 7-day window, not the whole assignment. */
  planningTargets?: Array<{
    taskId: string;
    targetMin: number;
    remainingMin: number;
    reflectFollowUpMin?: number;
    adaptiveReviewMin?: number;
    estimateStatus?: string;
  }>;
  /** Canonical task priority: deadline, priority, group weight, then points. */
  priorityOrder?: Array<{
    rank: number;
    taskId: string;
    title: string;
    deadline: string;
    priority: Priority;
    personalPriority: PersonalPriority;
    assignmentGroupWeight: number;
    pointsPossible: number;
    masteryRisk?: number;
  }>;
  milestones?: Array<{
    milestoneId: string;
    taskId: string;
    weeklyGoalId?: string | null;
    title: string;
    deliverable: string;
    estimatedMin: number;
    targetMin: number;
    dependsOn: string[];
    sourceRefs?: string[];
    rubricCriteria?: string[];
    knowledgeComponents?: Array<{
      componentId: string;
      name: string;
      status: 'approved' | 'provisional';
      sourceRef: string;
    }>;
    decompositionSource?: 'template' | 'rubric_evidence' | 'llm' | 'rule_based_fallback' | 'mastery_rule' | 'reflect_rule' | 'capacity_fill';
    difficulty?: string;
    allocationBasis?: Record<string, unknown>;
    mappingConfidence?: number;
    estimate?: {
      p50_minutes: number;
      p80_minutes: number;
      confidence: number;
      evidence_count: number;
      personal_factor: number;
      source: string;
    };
    deadline: string;
  }>;
  rubricCoverage?: Array<{
    taskId: string;
    coveredCriterionIds: string[];
    missingCriterionIds: string[];
    weakKnowledgeComponents: Array<{ componentId: string; score: number }>;
  }>;
  qualityEvaluation?: {
    partialConfirmation?: PartialPlanPreview;
    releaseReady: boolean;
    canConfirm?: boolean;
    blockingErrors?: Array<Record<string, unknown>>;
    warnings?: Array<Record<string, unknown>>;
    score: number;
    checks: Record<string, boolean>;
    metrics: {
      hardViolationCount: number;
      rubricCoverage: number;
      provenanceCoverage: number;
      robustCapacity: boolean;
    };
    violations: Array<Record<string, unknown>>;
    missingRubricCriteria: Array<{ taskId: string; criterionId: string }>;
    limitations: string[];
  };
}

export interface StudySession {
  interruptionReason?: InterruptionReason;
  lengthFeeling?: LengthFeeling;
  timeSource?: 'timer' | 'self_report';
  unobservedGap?: boolean;
  completedAt?: string;
  id: string;
  taskId: string;
  date: string;
  minutes: number;
  note?: string;
  source: 'timer' | 'manual';
  blockId?: string;
  plannedMin?: number;
  completionPercent?: number;
  outcome?: DoOutcome;
  blocker?: DoBlocker;
  blockerNote?: string;
  needsRecovery?: boolean;
}

export type DoOutcome = 'on_track' | 'completed' | 'needs_more_time' | 'blocked' | 'missed';
export type DoBlocker = 'none' | 'knowledge' | 'time' | 'interruption' | 'other';

export interface DoResource {
  id: string;
  title: string;
  kind: string;
  url?: string | null;
  module: string;
  citation: string;
  excerpt?: string;
}

export interface DoSessionPreparation {
  action: 'prepare';
  status: 'ready';
  block_id: string;
  task_id: string;
  title: string;
  objective: string;
  planned_minutes: number;
  recommended_resources: DoResource[];
  opening_prompt: string;
  resource_version?: string;
  scope?: { status: 'mapped' | 'unmapped'; module_ids: string[]; module_names: string[]; assignment_id: string };
}

export interface DoSessionEvaluation {
  assessment_summary?: Record<string, 'passed' | 'failed'>;
  interruption_reason?: InterruptionReason;
  time_source?: 'timer' | 'self_report';
  action: 'complete';
  status: DoOutcome;
  block_id: string;
  task_id: string;
  planned_minutes: number;
  actual_minutes: number;
  variance_minutes: number;
  completion_percent: number;
  remaining_minutes: number;
  blocker: DoBlocker;
  blocker_note: string;
  needs_recovery: boolean;
  needs_understanding_check: boolean;
  next_action: string;
}

export interface DoCheckpointResult {
  evidenceState: 'demonstrated' | 'developing' | 'misconception' | 'abstained';
  confidence: 'high' | 'medium' | 'low';
  feedback: string;
  evidenceQuotes: string[];
  demonstratedLevel?: string;
  knowledgeComponentIds: string[];
  evidenceIds: string[];
  provisional: boolean;
  requiresInstructorReview: boolean;
  reviewCaseId?: string;
}

export interface ActiveSession {
  id?: string;
  blockId?: string;
  version?: number;
  taskId: string;
  /** epoch ms when the current running segment started, null when paused */
  runningSince: number | null;
  accumulatedMs: number;
}

export type InterruptionReason = 'none' | 'unexpected' | 'fatigue' | 'difficulty' | 'outside' | 'unknown';
export type LengthFeeling = 'not_reported' | 'comfortable' | 'long' | 'too_long';
export interface DurableStudySession {
  activity_type?: StudyActivity | 'unknown';
  rhythm?: { sessionMinutes: number; breakMinutes: number };
  note?: string;
  id: string; courseId: string; taskId: string; blockId: string; version: number;
  status: 'running' | 'paused' | 'completed' | 'cancelled'; observed_seconds: number;
  checkpoint_at: string; date: string; planned_minutes: number; heartbeatSeconds: number;
  interruption_reason: InterruptionReason; length_feeling: LengthFeeling; unobserved_gap: boolean;
  evaluation?: DoSessionEvaluation;
}
export interface RhythmTrialSummary {
  sessions: number;
  completionRate: number | null;
  longSessionRate: number | null;
  assistedAssessmentRate?: number | null;
  assessment?: Partial<Record<'conceptual' | 'application' | 'transfer' | 'retention', { testedSessions: number; passRate: number | null }>>;
}
export interface RhythmReport {
  comparison?: { status: string; before: RhythmTrialSummary | null; after: RhythmTrialSummary | null };
  status: 'disabled' | 'insufficient_evidence' | 'trial_proposed'; excludedCount: number;
  current: { sessionMinutes: number; breakMinutes: number };
  proposal: null | { id: string; preferences: { sessionMinutes: number; breakMinutes: number }; sourceRefs: string[];
    activityType: StudyActivity;
    assessmentEvidenceIds: string[]; taskId: string; courseId: number; learningQuality: string; requiresConfirmation: true };
}

export interface Source {
  id: string;
  name: string;
  location: string;
  excerpt: string;
  context?: string;
  materialId?: string;
  downloadUrl?: string;
  previewUrl?: string;
  sectionTitle?: string;
  locationDetail?: string;
  fileName?: string;
}

export type QAKind = 'grounded' | 'abstained' | 'integrity' | 'hint' | 'conversation' | 'out_of_scope';

export interface QAMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  kind?: QAKind;
  citations?: string[];
  sources?: Source[];
  suggestions?: string[];
  createdAt: string;
}

export interface QAConversation {
  id: string;
  courseId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: QAMessage[];
}

export type DiffType = 'added' | 'removed' | 'moved' | 'unchanged';

export interface DiffItem {
  type: DiffType;
  taskId: string;
  before?: { date: string; start: Clock; end: Clock };
  after?: { date: string; start: Clock; end: Clock };
}

export interface Drift {
  taskId: string;
  courseId: string;
  kind: 'missed_progress' | 'capacity_gap';
  expectedMin: number;
  loggedMin: number;
  deficitMin: number;
  deadline: string;
}

export type PlanImpactKind =
  | 'schedule_conflict'
  | 'capacity_released'
  | 'deadline_earlier'
  | 'deadline_later'
  | 'assignment_removed'
  | 'assignment_added';

export interface PlanImpact {
  id: string;
  kind: PlanImpactKind;
  /** Constraint that caused a conflict; used to retire stale impacts after replanning. */
  constraintId?: string;
  title: string;
  message: string;
  courseId?: string;
  taskId?: string;
  deadline?: string;
  deficitMin: number;
  affectedBlockIds: string[];
  detectedAt: string;
}

export type ReminderKind =
  | 'study_block'
  | 'deadline_72h'
  | 'deadline_24h'
  | 'deadline_2h'
  | 'missed_block'
  | 'lms_change'
  | 'online_class'
  | 'quiz'
  | 'exam_24h'
  | 'exam_60m'
  | 'evening_digest'
  | 'reflect_session';
// Reflect remains part of Plan–Do–Reflect, not a fourth learning phase.

export type ReminderUrgency = 'normal' | 'urgent' | 'critical';

/** A deterministic reminder derived from the saved plan and the latest LMS projection. */
export interface Reminder {
  id: string;
  kind: ReminderKind;
  title: string;
  message: string;
  scheduledAt: string;
  expiresAt: string;
  urgency: ReminderUrgency;
  courseId?: string;
  taskId?: string;
  href?: string;
}

export interface ReminderPreferences {
  enabled: boolean;
  browserEnabled: boolean;
  dailyCap: number;
  studyBlockLeadMinutes: number;
  digestHour: number;
  pushEnabled?: boolean;
  deadlineEnabled?: boolean;
  studyEnabled?: boolean;
  reflectEnabled?: boolean;
  quietHoursEnabled?: boolean;
  quietStart?: string;
  quietEnd?: string;
}

export type StudyActivity = 'concept' | 'practice' | 'coding' | 'review';
export interface ActivityRhythm {
  courseId: number;
  activityType: StudyActivity;
  sessionMinutes: number;
  breakMinutes: number;
}
export interface StudyPreferences {
  activityRhythms?: ActivityRhythm[];
  checkpointMinutes?: number;
  adaptiveSuggestionsEnabled?: boolean;
  sessionMinutes: number;
  breakMinutes: number;
}

/** Delivery receipts are persisted to avoid duplicate notifications across reloads/devices. */
export interface ReminderState {
  preferences: ReminderPreferences;
  deliveredAt: Record<string, string>;
  readIds: string[];
}

export interface EstimateProfile {
  courseId: string;
  sampleCount: number;
  /** Exponential moving average of actual / estimated duration. */
  multiplier: number;
  updatedAt: string;
}

export interface PilotMetrics {
  measuredAt: string;
  openDeadlineCount: number;
  plannedDeadlineCount: number;
  atRiskDeadlineCount: number;
  onTimeSubmissionCount: number;
  gradedSubmissionCount: number;
  /** Submitted assignments used as the denominator, including ungraded work. */
  submittedAssignmentCount?: number;
  planCoverageRate: number;
  onTimeSubmissionRate: number | null;
  estimateMaePercent: number | null;
  recoveryCount: number;
}

export interface RecoveryOption {
  id: 'A' | 'B' | 'C';
  title: string;
  summary: string;
  changes: string[];
  impact: string;
  time: string;
  tradeoff: string;
  newBlocks: TimeBlock[];
  /** Availability assumptions the option relies on, always shown to the user. */
  assumptions: string[];
  fullyRecovers: boolean;
  /** Structured capacity evidence; optional for legacy persisted options. */
  workloadMinutes?: number;
  scheduledMinutes?: number;
  missingMinutes?: number;
  shortfalls?: Array<{ taskId: string; missingMin: number }>;
}

export interface Reflection {
  courseId: string;
  weekStart: string;
  effectiveWeekStart?: string;
  scope?: 'weekly' | 'activity';
  activityId?: string;
  activityTitle?: string;
  activityKind?: string;
  answers: [string, string, string];
  savedAt: string;
  aiDraft?: Record<string, unknown>;
  aiSummary?: string;
}

export interface Toast {
  id: string;
  tone: 'success' | 'info' | 'warning' | 'danger';
  title: string;
  description?: string;
}

/* ---------- Instructor ---------- */

export interface ClassGroup {
  id: string;
  name: string;
  n: number;
}

export interface GroupStats {
  learningCycle?: LearningCycleMetrics;
  adoptionComparison?: {
    status: 'available' | 'insufficient_data';
    before: { count: number; total: number; rate: number } | null;
    after: { count: number; total: number; rate: number } | null;
    deltaPercentagePoints: number | null;
    windowDays?: number;
    adoptionEvent?: 'PLAN_CONFIRMED';
  };
  groupId: string;
  onTimeRate: number; // 0..1
  onTimeCount: number;
  onTimeTotal: number;
    completionUnknownCount?: number;
  weeklyCompletion: { week: string; rate: number; count: number; total: number }[];
  topics: { topic: string; needsSupport: number; n: number }[];
  atRisk: number;
  riskWindowDays: number;
  progressImprovement: number | null;
  assignmentRisks: Array<{
    assignmentId: string;
    title: string;
    dueAt: string;
    atRiskCount: number;
    totalStudents: number;
      missingMinutes?: number; // Legacy only; no workload inference from points.
  }>;
}

export interface LearningCycleMetrics {
  periodStart: string;
  periodEnd: string;
  originalPlan: PlanAttainmentMetric;
  currentPlan: PlanAttainmentMetric;
  learningEvidence: {
    status: 'available' | 'insufficient_data';
    n: number;
    total: number | null;
    satisfied: number | null;
    missing: number | null;
    belowRequirement: number | null;
    unmapped: number | null;
    rate: number | null;
    retention: { due: number; checked: number; passed: number } | null;
  };
}

export interface PlanAttainmentMetric {
  status: 'available' | 'insufficient_data';
  n: number;
  count: number | null;
  total: number | null;
  rate: number | null;
  removedCount: number | null;
  unverifiedCount: number | null;
}

export interface LMSInstructorSummary {
  analytics: LMSAnalytics;
  sections: Array<{ id: string; name: string; memberCount: number }>;
  groups: Array<{ id: string; name: string; teamCount: number }>;
  modules: Array<{ id: string; name: string; requirementCount: number }>;
  weightedAssignments: number;
  rubricAssignments: number;
}

export type ReviewStatus =
  | 'pending'
  | 'in_review'
  | 'approved'
  | 'edited'
  | 'rejected'
  | 'needs_evidence'
  | 'superseded';

export interface ReviewItem {
  id: string;
  topic: string;
  question: string;
  responseExcerpt: string;
  confidence: 'low' | 'medium';
  reason: string;
  status: ReviewStatus;
  submittedAt: string;
  note?: string;
  suggestedStatus?: string;
  rubricVersion?: number;
  aiConclusion?: string;
  rubricCriteria?: Array<{ name: string; score?: number | string; maxScore?: number }>;
  evidenceQuotes?: string[];
  sourceRefs?: Array<{ label: string; type: string; id: string; url?: string }>;
}

export type AssessmentStatus = 'draft' | 'review' | 'approved' | 'rejected';

export interface AssessmentItem {
  id: string;
  /** Present for the student cross-course workspace; instructor views are already course-scoped. */
  courseId?: string;
  topic: string;
  question: string;
  rubric: string[];
  status: AssessmentStatus;
  note?: string;
  level?: string;
  source?: string;
  answerType?: 'open' | 'multiple_choice' | 'boolean' | 'numeric' | 'exact_text';
  knowledgeComponentIds?: string[];
  assessmentStage?: 'recall' | 'explain' | 'why' | 'application' | 'transfer';
  questionDesign?: {
    mode: 'fixed' | 'relation_template' | 'llm_followup';
    relation_property: 'reflexive' | 'symmetric' | 'antisymmetric' | 'transitive' | 'equivalence' | 'partial_order';
    stages: Array<'recall' | 'explain' | 'why' | 'application' | 'transfer'>;
    reference_text: string;
  };
  hints?: string[];
  kcProvisional?: boolean;
  aiGenerated?: boolean;
  history?: { at: string; text: string }[];
  version?: number;
}

export interface AuditEntry {
  id: string;
  at: string;
  actor: string;
  action: string;
}

export type EvidenceState = 'demonstrated' | 'developing' | 'misconception' | 'abstained';

export interface QuickCheckResult {
  id: string;
  topic: string;
  question: string;
  answer: string;
  evidenceState: EvidenceState;
  confidence: 'high' | 'medium' | 'low';
  feedback: string;
  submittedAt: string;
  reviewItemId?: string;
  instructorNote?: string;
  rubricVersion?: number;
}

export interface ClassGuidance {
  id: string;
  topic: string;
  message: string;
  at: string;
  instructorName: string;
}

export type TeachingEventType = 'offline' | 'online' | 'practice' | 'review' | 'quiz' | 'office_hour' | 'other';

export interface TeachingEvent {
  id: string;
  title: string;
  type: TeachingEventType;
  startAt: string;
  endAt: string;
  location: string;
  meetingUrl: string;
  moduleId: string;
  knowledgeComponentIds: string[];
  preparation: string;
  recurrence: 'none' | 'weekly';
  recurrenceCount?: number;
  status: 'scheduled' | 'cancelled';
  source: 'pacewise' | 'lms';
  updatedAt?: string;
  operation?: 'upsert' | 'delete';
}

export interface CourseModuleDefinition {
  id: string;
  title: string;
  description: string;
  position: number;
}

export interface KnowledgeComponentDefinition {
  id: string;
  moduleId: string;
  name: string;
  description: string;
  prerequisiteIds: string[];
  objectives: string[];
  misconceptions: string[];
  status: 'approved' | 'provisional';
}

export interface InstructorFeedback {
  id: string;
  scope: 'class' | 'group';
  kind: 'guidance' | 'resource' | 'reassessment' | 'intervention';
  groupId?: string | null;
  topic: string;
  message: string;
  knowledgeComponentIds: string[];
  recommendedMinutes: number;
  createdAt?: string;
}

export interface InstructorPrivacySettings {
  minimumGroupSize: number;
  allowIndividualReview: boolean;
  requireStudentConsent: boolean;
  autoPublishApprovedResources: boolean;
}

export interface InstructorWorkspace {
  schedule: TeachingEvent[];
  courseStructure: {
    modules: CourseModuleDefinition[];
    knowledgeComponents: KnowledgeComponentDefinition[];
  };
  feedback: InstructorFeedback[];
  settings: InstructorPrivacySettings;
}

export interface CourseMaterialSummary {
  id: string;
  title: string;
  moduleName: string;
  fileName: string;
  fileType: string;
  fileSize: number;
  chunkCount: number;
  uploadedBy?: number;
  createdAt: string;
  updatedAt?: string;
}

export interface MaterialPreview {
  id: string;
  title: string;
  fileName: string;
  fileType: string;
  chunkCount: number;
  preview: string;
}

