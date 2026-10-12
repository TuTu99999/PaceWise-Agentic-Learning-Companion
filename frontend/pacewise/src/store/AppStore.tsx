import React, { createContext, useContext, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { defaultAvailability, defaultUnavailable } from '../data/plan';
import { getCurrentSession, lmsEventStreamUrl, loadWorkspace, saveWorkspace, syncCanvas } from '../services/api';
import type {
  ActiveSession,
  AssessmentItem,
  AssessmentStatus,
  AuditEntry,
  AvailabilityDay,
  CanvasSyncResult,
  ClassGuidance,
  ClassGroup,
  Course,
  DoSessionEvaluation,
  GroupStats,
  LMSCourseData,
  LMSInstructorSummary,
  InstructorWorkspace,
  Plan,
  PlanImpact,
  PilotMetrics,
  PlanDraft,
  PlanInput,
  RoutineProfile,
  QAConversation,
  QAMessage,
  QuickCheckResult,
  Reflection,
  RecoveryOption,
  ReminderState,
  ReviewItem,
  ReviewStatus,
  StudySession,
  Task,
  TaskProgress,
  EstimateProfile,
  TimeBlock,
  UnavailableSlot,
  User,
} from '../types';
import { addDays, DEMO_TODAY, PLANNING_WINDOW_START, uid } from '../utils/time';
import { detectAvailabilityPlanImpacts, detectLmsPlanImpacts, lmsUnavailableSlots, mergeUnavailable, slotOverlapsBlock } from '../utils/lmsPlanning';
import { adaptiveEstimate, calculatePilotMetrics, updateEstimateProfiles } from '../utils/pilotMetrics';
import { defaultReminderPreferences, defaultStudyPreferences, normalizeStudyPreferences } from '../utils/studyPreferences';
import type { ActivityRhythm, StudyActivity, StudyPreferences } from '../types';

export interface Settings {
  staleData: boolean;
  lastSync: string;
}

interface LMSBaseline {
  tasks: Task[];
  courseData: Record<string, LMSCourseData>;
  syncedAt: string;
}

export const emptyInstructorWorkspace: InstructorWorkspace = {
  schedule: [],
  courseStructure: { modules: [], knowledgeComponents: [] },
  feedback: [],
  settings: {
    minimumGroupSize: 5,
    allowIndividualReview: false,
    requireStudentConsent: true,
    autoPublishApprovedResources: false,
  },
};

export interface PersistenceState {
  status: 'idle' | 'saving' | 'saved' | 'error' | 'conflict';
  savedAt: string | null;
  message?: string;
}

export interface AppState {
  studyPreferences: StudyPreferences;
  user: User | null;
  /** Student-facing data filter. Authentication remains bound to user.courseId. */
  courseScope: 'all' | string;
  authReady: boolean;
  workspaceReady: boolean;
  /** Runtime course projection is loaded separately from the durable workspace. */
  courseSourceStatus: 'idle' | 'loading' | 'ready' | 'error';
  courses: Course[];
  tasks: Task[];
  taskProgress: Record<string, TaskProgress>;
  courseData: Record<string, LMSCourseData>;
  plan: Plan | null;
  /** Recover look-ahead blocks outside the committed 7-day plan. */
  provisionalBlocks: TimeBlock[];
  planHistory: Plan[];
  availability: AvailabilityDay[];
  unavailable: UnavailableSlot[];
  routineProfile: RoutineProfile | null;
  sessions: StudySession[];
  activeSession: ActiveSession | null;
  wizardInput: PlanInput | null;
  planDraft: PlanDraft | null;
  /** Learner edits are durable input, never an implicitly confirmed plan. */
  calendarDraft: { blocks: TimeBlock[]; needsAnalysis: boolean; updatedAt: string } | null;
  qaMessages: QAMessage[];
  qaHistory?: Record<string, QAMessage[]>;
  qaConversations: QAConversation[];
  activeConversationId: string | null;
  quickChecks: QuickCheckResult[];
  guidance: ClassGuidance[];
  reflections: Record<string, Reflection>;
  recoveryOptions: RecoveryOption[];
  /** Context fingerprint that owns recoveryOptions; prevents stale/cross-drift reuse. */
  recoveryOptionsKey: string | null;
  settings: Settings;
  reviewQueue: ReviewItem[];
  assessments: AssessmentItem[];
  audit: AuditEntry[];
  classGroups: ClassGroup[];
  groupStats: Record<string, GroupStats>;
  lmsInstructorSummary: LMSInstructorSummary | null;
  teacherWorkspace: InstructorWorkspace;
  /** Monotonic UI signal used to revalidate course-derived views after LMS events. */
  lmsRevision: number;
  /** Tasks whose drift warning the student chose to keep as-is (plan unchanged). */
  dismissedDrifts: string[];
  planImpacts: PlanImpact[];
  estimateProfiles: Record<string, EstimateProfile>;
  pilotMetricsHistory: PilotMetrics[];
  recoveryCount: number;
  /** Last persisted LMS projection used to detect changes after reopening. */
  lmsBaseline: LMSBaseline | null;
  reminders: ReminderState;
}

export const initialState: AppState = {
  studyPreferences: defaultStudyPreferences,
  user: null,
  courseScope: 'all',
  authReady: false,
  workspaceReady: false,
  courseSourceStatus: 'idle',
  courses: [],
  tasks: [],
  taskProgress: {},
  courseData: {},
  plan: null,
  provisionalBlocks: [],
  planHistory: [],
  availability: defaultAvailability,
  unavailable: defaultUnavailable,
  routineProfile: null,
  sessions: [],
  activeSession: null,
  wizardInput: null,
  planDraft: null,
  calendarDraft: null,
  qaMessages: [],
  qaHistory: {},
  qaConversations: [],
  activeConversationId: null,
  quickChecks: [],
  guidance: [],
  reflections: {},
  recoveryOptions: [],
  recoveryOptionsKey: null,
  settings: { staleData: false, lastSync: '' },
  reviewQueue: [],
  assessments: [],
  audit: [],
  classGroups: [],
  groupStats: {},
  lmsInstructorSummary: null,
  teacherWorkspace: emptyInstructorWorkspace,
  lmsRevision: 0,
  dismissedDrifts: [],
  planImpacts: [],
  estimateProfiles: {},
  pilotMetricsHistory: [],
  recoveryCount: 0,
  lmsBaseline: null,
  reminders: {
    preferences: defaultReminderPreferences,
    deliveredAt: {},
    readIds: [],
  },
};

export type Action =
  | { type: 'UPDATE_STUDY_PREFERENCES'; patch: Partial<StudyPreferences> }
  | { type: 'UPSERT_ACTIVITY_RHYTHM'; rhythm: ActivityRhythm }
  | { type: 'REMOVE_ACTIVITY_RHYTHM'; courseId: number; activityType: StudyActivity }
  | { type: 'LOGIN'; user: User }
  | { type: 'REFRESH_SESSION'; user: User }
  | { type: 'AUTH_READY' }
  | { type: 'HYDRATE_WORKSPACE'; state: Partial<AppState> }
  | { type: 'COURSE_SOURCE_FAILED' }
  | { type: 'SET_COURSE_SCOPE'; courseScope: 'all' | string }
  | { type: 'SET_ACTIVE_COURSE'; courseId: string }
  | { type: 'LOGOUT' }
  | { type: 'SET_WIZARD_INPUT'; input: PlanInput }
  | { type: 'SET_DRAFT'; draft: PlanDraft | null }
  | { type: 'SAVE_CALENDAR_DRAFT'; blocks: TimeBlock[] }
  | { type: 'UPDATE_DRAFT_BLOCK'; block: TimeBlock }
  | { type: 'REMOVE_DRAFT_BLOCK'; id: string }
  | { type: 'SAVE_PLAN'; confirmedDraft?: PlanDraft }
  | { type: 'CLEAR_PLAN' }
  | { type: 'START_SESSION'; taskId: string }
  | { type: 'SET_DURABLE_SESSION'; session: ActiveSession | null }
  | { type: 'RECORD_DURABLE_SESSION'; session: StudySession }
  | { type: 'PAUSE_SESSION' }
  | { type: 'RESUME_SESSION' }
  | { type: 'CANCEL_SESSION' }
  | { type: 'COMPLETE_SESSION'; minutes: number; note?: string; blockId?: string; plannedMin?: number; evaluation?: DoSessionEvaluation }
  | { type: 'ADD_MANUAL_SESSION'; session: Omit<StudySession, 'id' | 'source'> }
  | { type: 'UPDATE_TASK_ESTIMATE'; taskId: string; estimateMin: number }
  | { type: 'UPDATE_TASK_PRIORITY'; taskId: string; personalPriority: 1 | 2 | 3 | 4 }
  | { type: 'SET_TASK_DONE'; taskId: string; done: boolean }
  | { type: 'ADD_QA'; message: QAMessage }
  | { type: 'CLEAR_QA' }
  | { type: 'CREATE_QA_CONVERSATION'; title?: string }
  | { type: 'SELECT_QA_CONVERSATION'; id: string }
  | { type: 'RENAME_QA_CONVERSATION'; id: string; title: string }
  | { type: 'DELETE_QA_CONVERSATION'; id: string }
  | { type: 'SUBMIT_QUICK_CHECK'; result: QuickCheckResult; reviewItem?: ReviewItem }
  | { type: 'ADD_CLASS_GUIDANCE'; topic: string; message: string }
  | { type: 'APPLY_RECOVERY'; blocks: TimeBlock[]; impactId?: string }
  | { type: 'SAVE_REFLECTION'; reflectionKey?: string; courseId: string; weekStart: string; effectiveWeekStart?: string; scope?: 'weekly' | 'activity'; activityId?: string; activityTitle?: string; activityKind?: string; answers: [string, string, string]; aiDraft?: Record<string, unknown>; aiSummary?: string }
  | { type: 'SET_RECOVERY_OPTIONS'; options: RecoveryOption[]; key: string | null }
  | { type: 'SAVE_AVAILABILITY'; availability: AvailabilityDay[]; unavailable: UnavailableSlot[]; draftBlocks?: TimeBlock[] }
  | { type: 'UPDATE_ROUTINE_PROFILE'; profile: RoutineProfile; draftBlocks?: TimeBlock[] }
  | { type: 'UPDATE_SETTINGS'; patch: Partial<Settings> }
  | { type: 'SET_REVIEW_STATUS'; id: string; status: ReviewStatus; note?: string }
  | { type: 'SET_ASSESSMENT_STATUS'; id: string; status: AssessmentStatus; note?: string }
  | { type: 'ADD_ASSESSMENT_DRAFT'; item: AssessmentItem }
  | { type: 'UPDATE_ASSESSMENT'; item: Pick<AssessmentItem, 'id' | 'question' | 'rubric' | 'level' | 'source' | 'version'> & Partial<Pick<AssessmentItem, 'answerType' | 'knowledgeComponentIds' | 'assessmentStage' | 'questionDesign' | 'hints' | 'kcProvisional'>>; status?: AssessmentStatus; note?: string; historyText: string }
  | { type: 'DISMISS_DRIFT'; taskId: string }
  | { type: 'DISMISS_PLAN_IMPACT'; impactId: string }
  | { type: 'APPLY_PLAN_IMPACT'; impactId: string }
  | { type: 'SYNC_CANVAS'; tasks: Task[]; courses?: Course[]; guidance?: ClassGuidance[]; assessments?: AssessmentItem[]; courseData?: Record<string, LMSCourseData>; reviewResolutions?: CanvasSyncResult['reviewResolutions'] }
  | { type: 'LMS_EVENT_RECEIVED' }
  | { type: 'UPDATE_REMINDER_PREFERENCES'; patch: Partial<ReminderState['preferences']> }
  | { type: 'MARK_REMINDERS_READ'; ids: string[] }
  | { type: 'RECORD_REMINDER_DELIVERY'; ids: string[]; deliveredAt: string }
  | { type: 'SET_INSTRUCTOR_DATA'; classGroups: ClassGroup[]; groupStats: Record<string, GroupStats>; reviewQueue: ReviewItem[]; assessments: AssessmentItem[]; audit: AuditEntry[]; guidance: ClassGuidance[]; lmsSummary: LMSInstructorSummary | null; teacherWorkspace: InstructorWorkspace }
  ;

function audit(state: AppState, action: string): AuditEntry[] {
  const d = new Date();
  const at = `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(
    d.getMinutes(),
  ).padStart(2, '0')}`;
  return [{ id: uid('au'), at, actor: state.user?.name ?? 'Hệ thống', action }, ...state.audit];
}

function defaultPersonalPriority(task: Task): 1 | 2 | 3 | 4 {
  if (task.priority === 'high') return 4;
  if ((task.assignmentGroup?.weight ?? 0) >= 40 || (task.pointsPossible ?? 0) >= 30) return 3;
  if (task.priority === 'low') return 1;
  return 2;
}

function progressOf(task: Task): TaskProgress {
  return {
    estimateMin: task.estimateMin,
    estimateIsAssumption: task.estimateIsAssumption,
    loggedMin: task.loggedMin,
    status: task.status,
    personalPriority: task.personalPriority ?? defaultPersonalPriority(task),
    updatedAt: new Date().toISOString(),
  };
}

function withTaskProgress(state: AppState, tasks: Task[]): Pick<AppState, 'tasks' | 'taskProgress'> {
  return {
    tasks,
    taskProgress: {
      ...state.taskProgress,
      ...Object.fromEntries(tasks.map((task) => [task.id, progressOf(task)])),
    },
  };
}

function preserveLearningReferences(plan: Plan | null, sessions: StudySession[]) {
  // LMS synchronization must never silently rewrite a confirmed plan or erase
  // study history. Removed/renamed assignments are represented as plan impacts
  // and remain visible until the learner explicitly accepts the diff.
  return {
    plan,
    sessions,
  };
}

const LEGACY_DS201_TERMS = /làm sạch dữ liệu|phân tích mô tả|trực quan hóa|dashboard|dữ liệu bán hàng/i;
const MILESTONE_PREFIX = /^(Hoàn thành|Hoàn thiện|Đọc yêu cầu và tiêu chí|Đọc yêu cầu và rubric|Thiết kế phương án thực hiện|Thực hiện phần chính|Thực hiện bản nháp|Kiểm thử và đối chiếu rubric|Rà soát và chuẩn bị nộp):/i;

function reconcileLegacyBlockTitles(blocks: TimeBlock[], tasks: Task[]): TimeBlock[] {
  const tasksById = new Map(tasks.map((task) => [task.id, task]));
  let changed = false;
  const next = blocks.map((block) => {
    const legacyTitle = block.milestoneTitle?.trim();
    const task = tasksById.get(block.taskId);
    if (!legacyTitle || !task || !LEGACY_DS201_TERMS.test(legacyTitle)) return block;
    const prefix = legacyTitle.match(MILESTONE_PREFIX)?.[1];
    changed = true;
    return {
      ...block,
      milestoneTitle: prefix ? `${prefix}: ${task.title}` : `Hoàn thành ${task.title}`,
    };
  });
  return changed ? next : blocks;
}

function reconcilePlanTitles(plan: Plan | null, tasks: Task[]): Plan | null {
  if (!plan) return null;
  const blocks = reconcileLegacyBlockTitles(plan.blocks, tasks);
  return blocks === plan.blocks ? plan : { ...plan, blocks };
}

function withFreshPilotMetrics(state: AppState): AppState {
  const metric = calculatePilotMetrics(
    state.tasks,
    state.plan,
    state.sessions,
    state.recoveryCount,
    state.availability,
    mergeUnavailable(state.unavailable, lmsUnavailableSlots(state.courseData)),
  );
  const metricDay = metric.measuredAt.slice(0, 10);
  return {
    ...state,
    pilotMetricsHistory: [
      metric,
      ...state.pilotMetricsHistory.filter((item) => item.measuredAt.slice(0, 10) !== metricDay),
    ].slice(0, 30),
  };
}

function compactCourseData(courseData: Record<string, LMSCourseData>): Record<string, LMSCourseData> {
  return Object.fromEntries(Object.entries(courseData).map(([courseId, value]) => [courseId, {
    courseId: value.courseId,
    modules: [],
    resources: [],
    plannerItems: [],
    appointmentGroups: [],
    calendarItems: value.calendarItems ?? [],
  }]));
}

function compactTasks(tasks: Task[]): Task[] {
  return tasks.map((task) => ({
    id: task.id,
    lmsAssignmentId: task.lmsAssignmentId,
    title: task.title,
    courseId: task.courseId,
    deadline: task.deadline,
    dueAt: task.dueAt,
    estimateMin: task.estimateMin,
    loggedMin: task.loggedMin,
    status: task.status,
    priority: task.priority,
    objective: '',
    estimateIsAssumption: task.estimateIsAssumption,
    pointsPossible: task.pointsPossible,
    assignmentGroup: task.assignmentGroup,
    submission: task.submission,
  }));
}

function resolvedEvidenceState(
  status: string | undefined,
  fallback: QuickCheckResult['evidenceState'],
): QuickCheckResult['evidenceState'] {
  const normalized = (status ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  if (normalized.includes('the hien')) return 'demonstrated';
  if (normalized.includes('hinh thanh')) return 'developing';
  if (normalized.includes('nham lan')) return 'misconception';
  if (normalized.includes('chua du')) return 'abstained';
  return fallback;
}

function splitRecoveryHorizon(plan: Plan, blocks: TimeBlock[]) {
  const nextWeekStart = addDays(plan.weekStart, 7);
  return {
    committed: blocks.filter((block) => block.date < nextWeekStart),
    provisional: blocks.filter((block) => block.date >= nextWeekStart),
  };
}

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'REFRESH_SESSION':
      return state.user?.id === action.user.id && state.user.role === action.user.role ? { ...state, user: action.user } : state;
    case 'LOGIN':
      // A first-time student starts with NO tasks, NO deadlines, NO plan, and NO sessions
      if (action.user.isNew) {
        return {
          ...initialState,
          user: action.user,
          courseScope: 'all',
          authReady: true,
          workspaceReady: false,
          courseSourceStatus: 'loading',
          courses: [],
          tasks: [], // Sinh viên mới: hoàn toàn chưa có bài tập hay deadline nào
          taskProgress: {},
          plan: null,
          sessions: [],
          dismissedDrifts: [],
          reflections: {},
        };
      }
      return { ...state, user: action.user, courseScope: 'all', authReady: true, workspaceReady: false, courseSourceStatus: 'loading' };
    case 'AUTH_READY':
      return { ...state, authReady: true };
    case 'HYDRATE_WORKSPACE': {
      const legacy = action.state as Partial<AppState> & { reflection?: Omit<Reflection, 'courseId'> };
      const courseId = state.user?.courseId;
      const reflections = legacy.reflections ?? (
        legacy.reflection && courseId
          ? { [courseId]: { ...legacy.reflection, courseId } }
          : state.reflections
      );
      const { reflection: _legacyReflection, ...workspace } = legacy;
      void _legacyReflection;
      const hydratedPlan = legacy.plan ?? state.plan;
      const migrated = hydratedPlan
        ? splitRecoveryHorizon(hydratedPlan, hydratedPlan.blocks)
        : { committed: [], provisional: [] };
      const activeCourseId = courseId || 'general';
      let hydratedConvs = (legacy.qaConversations as QAConversation[]) || [];
      if (hydratedConvs.length === 0 && state.user) {
        try {
          const cached = window.localStorage.getItem(`pacewise_qa_convs_${state.user.id}`);
          if (cached) hydratedConvs = JSON.parse(cached);
        } catch {}
      }
      // Migrate legacy qaMessages to a conversation if no conversations exist
      const legacyMsgs = (legacy.qaMessages as QAMessage[]) || state.qaMessages;
      if (hydratedConvs.length === 0 && legacyMsgs.length > 0) {
        hydratedConvs = [{
          id: uid('conv'),
          courseId: activeCourseId,
          title: legacyMsgs[0]?.text?.slice(0, 35) || 'Cuộc trò chuyện đã lưu',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          messages: legacyMsgs,
        }];
      }
      const courseConvs = hydratedConvs.filter((c) => c.courseId === activeCourseId);
      const activeConvId = (legacy.activeConversationId as string) || courseConvs[0]?.id || null;
      const currentConv = hydratedConvs.find((c) => c.id === activeConvId);

      return {
        ...state,
        ...workspace,
        studyPreferences: normalizeStudyPreferences(legacy.studyPreferences),
        reminders: {
          ...state.reminders, ...legacy.reminders,
          preferences: { ...defaultReminderPreferences, ...legacy.reminders?.preferences },
        },
        // The student dashboard always reopens in the cross-course view.
        courseScope: 'all',
        reflections,
        qaMessages: currentConv?.messages || [],
        qaHistory: (legacy.qaHistory as Record<string, QAMessage[]>) || {},
        qaConversations: hydratedConvs,
        activeConversationId: activeConvId,
        plan: hydratedPlan ? { ...hydratedPlan, blocks: migrated.committed } : null,
        provisionalBlocks: [
          ...(legacy.provisionalBlocks ?? []),
          ...migrated.provisional,
        ].filter((block, index, blocks) => blocks.findIndex((item) => item.id === block.id) === index),
        taskProgress: legacy.taskProgress ?? state.taskProgress,
        user: state.user,
        authReady: true,
        workspaceReady: true,
        courseSourceStatus: 'loading',
      };
    }
    case 'SET_COURSE_SCOPE':
      return { ...state, courseScope: action.courseScope };
    case 'SET_ACTIVE_COURSE': {
      const targetCourseConvs = state.qaConversations.filter((c) => c.courseId === action.courseId);
      const nextActiveId = targetCourseConvs[0]?.id || null;
      const nextMessages = targetCourseConvs[0]?.messages || [];

      return {
        ...state,
        user: state.user ? { ...state.user, courseId: action.courseId } : null,
        activeConversationId: nextActiveId,
        qaMessages: nextMessages,
        assessments: [],
        classGroups: [],
        groupStats: {},
        reviewQueue: [],
        audit: [],
        guidance: [],
        lmsInstructorSummary: null,
        teacherWorkspace: emptyInstructorWorkspace,
      };
    }
    case 'SYNC_CANVAS': {
      const courses = action.courses ?? state.courses;
      const courseScope = state.courseScope === 'all' || courses.some((course) => course.id === state.courseScope)
        ? state.courseScope
        : 'all';
      const comparisonTasks = state.tasks.length ? state.tasks : state.lmsBaseline?.tasks ?? [];
      const comparisonCourseData = Object.keys(state.courseData).length
        ? state.courseData
        : state.lmsBaseline?.courseData ?? {};
      const estimateProfiles = updateEstimateProfiles(state.estimateProfiles, comparisonTasks, action.tasks);
      const incomingTasks = action.tasks.map((task) => {
        const current = comparisonTasks.find((item) => item.id === task.id);
        const saved = state.taskProgress[task.id];
        const progress = saved ?? (current ? progressOf(current) : undefined);
        if (!progress) return {
          ...task,
          estimateMin: adaptiveEstimate(task, estimateProfiles),
          personalPriority: task.personalPriority ?? defaultPersonalPriority(task),
        };
        return {
          ...task,
          estimateMin: progress.estimateIsAssumption ? adaptiveEstimate(task, estimateProfiles) : progress.estimateMin,
          estimateIsAssumption: progress.estimateIsAssumption,
          loggedMin: progress.loggedMin,
          status: task.status === 'done' ? 'done' as const : progress.status,
          personalPriority: progress.personalPriority ?? 2,
        };
      });
      const reconciled = preserveLearningReferences(state.plan, state.sessions);
      const currentPlan = reconcilePlanTitles(reconciled.plan, incomingTasks);
      const currentDraft = state.planDraft
        ? {
            ...state.planDraft,
            blocks: reconcileLegacyBlockTitles(state.planDraft.blocks, incomingTasks),
          }
        : null;
      const provisionalBlocks = reconcileLegacyBlockTitles(state.provisionalBlocks, incomingTasks);
      const hasComparableSnapshot = comparisonTasks.length > 0 || Object.keys(comparisonCourseData).length > 0;
      const detectedImpacts = hasComparableSnapshot
        ? detectLmsPlanImpacts(
            currentPlan,
            comparisonTasks,
            incomingTasks,
            comparisonCourseData,
            action.courseData ?? state.courseData,
          )
        : [];
      const existingImpactIds = new Set(state.planImpacts.map((impact) => impact.id));
      const planImpacts = [
        ...state.planImpacts,
        ...detectedImpacts.filter((impact) => !existingImpactIds.has(impact.id)),
      ].slice(-50);
      const pilotMetric = calculatePilotMetrics(
        incomingTasks,
        currentPlan,
        reconciled.sessions,
        state.recoveryCount,
        state.availability,
        mergeUnavailable(state.unavailable, lmsUnavailableSlots(action.courseData ?? state.courseData)),
      );
      const metricDay = pilotMetric.measuredAt.slice(0, 10);
      const quickChecks = state.quickChecks.map((result) => {
        const resolution = result.reviewItemId
          ? action.reviewResolutions?.[result.reviewItemId]
          : undefined;
        if (!resolution || !['approved', 'edited', 'rejected', 'needs_evidence'].includes(resolution.status)) {
          return result;
        }
        return {
          ...result,
          evidenceState: resolution.status === 'approved' || resolution.status === 'edited'
            ? resolvedEvidenceState(resolution.resolvedStatus, result.evidenceState)
            : 'abstained' as const,
          instructorNote: resolution.note ?? (
            resolution.status === 'rejected'
              ? 'Giảng viên chưa chấp nhận kết luận tự động.'
              : resolution.status === 'needs_evidence'
                ? 'Giảng viên yêu cầu thêm bằng chứng trước khi kết luận.'
                : 'Giảng viên đã xác nhận kết luận.'
          ),
        };
      });
      return {
        ...state,
        ...withTaskProgress(state, incomingTasks),
        taskProgress: Object.fromEntries(incomingTasks.map((task) => [task.id, progressOf(task)])),
        plan: currentPlan,
        planDraft: currentDraft,
        calendarDraft: state.calendarDraft ? { ...state.calendarDraft, blocks: reconcileLegacyBlockTitles(state.calendarDraft.blocks, incomingTasks) } : null,
        provisionalBlocks,
        sessions: reconciled.sessions,
        quickChecks,
        estimateProfiles,
        planImpacts,
        pilotMetricsHistory: [
          pilotMetric,
          ...state.pilotMetricsHistory.filter((item) => item.measuredAt.slice(0, 10) !== metricDay),
        ].slice(0, 30),
        courses,
        courseScope,
        courseData: action.courseData ?? state.courseData,
        guidance: action.guidance ?? state.guidance,
        assessments: action.assessments ?? state.assessments,
        settings: { ...state.settings, staleData: false, lastSync: new Date().toISOString() },
        courseSourceStatus: 'ready',
        lmsBaseline: {
          tasks: compactTasks(action.tasks),
          courseData: compactCourseData(action.courseData ?? state.courseData),
          syncedAt: new Date().toISOString(),
        },
      };
    }
    case 'LMS_EVENT_RECEIVED':
      return { ...state, lmsRevision: state.lmsRevision + 1 };
    case 'COURSE_SOURCE_FAILED':
      return { ...state, courseSourceStatus: 'error', settings: { ...state.settings, staleData: true } };
    case 'UPDATE_STUDY_PREFERENCES':
      return { ...state, studyPreferences: normalizeStudyPreferences({ ...state.studyPreferences, ...action.patch }) };
    case 'UPSERT_ACTIVITY_RHYTHM':
      return { ...state, studyPreferences: normalizeStudyPreferences({ ...state.studyPreferences,
        activityRhythms: [...(state.studyPreferences.activityRhythms ?? []).filter((item) =>
          item.courseId !== action.rhythm.courseId || item.activityType !== action.rhythm.activityType), action.rhythm] }) };
    case 'REMOVE_ACTIVITY_RHYTHM':
      return { ...state, studyPreferences: normalizeStudyPreferences({ ...state.studyPreferences,
        activityRhythms: (state.studyPreferences.activityRhythms ?? []).filter((item) =>
          item.courseId !== action.courseId || item.activityType !== action.activityType) }) };
    case 'UPDATE_REMINDER_PREFERENCES':
      return {
        ...state,
        reminders: {
          ...state.reminders,
          preferences: { ...state.reminders.preferences, ...action.patch },
        },
      };
    case 'MARK_REMINDERS_READ':
      return {
        ...state,
        reminders: {
          ...state.reminders,
          readIds: [...new Set([...state.reminders.readIds, ...action.ids])].slice(-300),
        },
      };
    case 'RECORD_REMINDER_DELIVERY': {
      const deliveredAt = Object.fromEntries(
        Object.entries({
          ...state.reminders.deliveredAt,
          ...Object.fromEntries(action.ids.map((id) => [id, action.deliveredAt])),
        })
          .sort(([, left], [, right]) => left.localeCompare(right))
          .slice(-300),
      );
      return { ...state, reminders: { ...state.reminders, deliveredAt } };
    }
    case 'LOGOUT':
      return { ...initialState, user: null, authReady: true, workspaceReady: false, activeSession: null };
    case 'SET_INSTRUCTOR_DATA':
      return {
        ...state,
        classGroups: action.classGroups,
        groupStats: action.groupStats,
        reviewQueue: action.reviewQueue,
        assessments: action.assessments,
        audit: action.audit,
        guidance: action.guidance,
        lmsInstructorSummary: action.lmsSummary,
        teacherWorkspace: action.teacherWorkspace,
      };
    case 'SET_WIZARD_INPUT':
      return { ...state, wizardInput: action.input };
    case 'SET_DRAFT':
      return { ...state, planDraft: action.draft, calendarDraft: null };
    case 'SAVE_CALENDAR_DRAFT':
      return { ...state, calendarDraft: { blocks: action.blocks, needsAnalysis: true, updatedAt: new Date().toISOString() } };
    case 'UPDATE_DRAFT_BLOCK':
      if (!state.planDraft) return state;
      return {
        ...state,
        planDraft: { ...state.planDraft, blocks: state.planDraft.blocks.map((b) => (b.id === action.block.id ? action.block : b)) },
      };
    case 'REMOVE_DRAFT_BLOCK':
      if (!state.planDraft) return state;
      return { ...state, planDraft: { ...state.planDraft, blocks: state.planDraft.blocks.filter((b) => b.id !== action.id) } };
    case 'SAVE_PLAN': {
      // API confirmations use the canonical backend subset, never a possibly
      // stale client draft. The fallback preserves existing reducer callers.
      const confirmedDraft = action.confirmedDraft ?? state.planDraft;
      if (!confirmedDraft || confirmedDraft.blocks.length === 0) return state;
      const handledImpactIds = new Set(confirmedDraft.feasibility.feasible
        && confirmedDraft.createdAt === state.planDraft?.createdAt ? state.planDraft?.replan?.impactIds ?? [] : []);
      // A confirmed plan replaces the remaining week; the previous version stays in history.
      const plan: Plan = {
        id: uid('plan'),
        weekStart: confirmedDraft.weekStart ?? confirmedDraft.input.weekStart ?? PLANNING_WINDOW_START,
        blocks: confirmedDraft.blocks.filter((block) => block.status !== 'tentative'),
        savedAt: new Date().toISOString(),
        version: (state.plan?.version ?? 0) + 1,
        feasibility: confirmedDraft.feasibility,
        confirmation: confirmedDraft.confirmation,
      };
      return withFreshPilotMetrics({
        ...state,
        plan,
        provisionalBlocks: confirmedDraft.blocks.filter((block) => block.status === 'tentative'),
        planHistory: state.plan ? [state.plan, ...state.planHistory] : state.planHistory,
        availability: state.routineProfile ? state.availability : confirmedDraft.input.availability,
        unavailable: confirmedDraft.input.unavailable.filter((slot) => slot.source !== 'lms' && slot.source !== 'routine'),
        planDraft: null,
        calendarDraft: null,
        wizardInput: null,
        recoveryOptions: [],
        recoveryOptionsKey: null,
        planImpacts: state.planImpacts.filter(impact => !handledImpactIds.has(impact.id)),
      });
    }
    case 'CLEAR_PLAN':
      return withFreshPilotMetrics({ ...state, plan: null, calendarDraft: null, provisionalBlocks: [], planHistory: state.plan ? [state.plan, ...state.planHistory] : state.planHistory });
    case 'START_SESSION':
      if (state.activeSession && state.activeSession.taskId !== action.taskId) return state;
      if (state.activeSession) return state;
      return { ...state, activeSession: { taskId: action.taskId, runningSince: Date.now(), accumulatedMs: 0 } };
    case 'SET_DURABLE_SESSION':
      return { ...state, activeSession: action.session };
    case 'RECORD_DURABLE_SESSION': {
      if (state.sessions.some((item) => item.id === action.session.id)) return state;
      const tasks = state.tasks.map((task) => task.id === action.session.taskId
        ? { ...task, loggedMin: task.loggedMin + action.session.minutes, status: task.status === 'done' ? 'done' as const : 'in_progress' as const }
        : task);
      return withFreshPilotMetrics({ ...state, activeSession: null, sessions: [action.session, ...state.sessions], ...withTaskProgress(state, tasks) });
    }
    case 'PAUSE_SESSION': {
      const s = state.activeSession;
      if (!s || s.runningSince === null) return state;
      return { ...state, activeSession: { ...s, runningSince: null, accumulatedMs: s.accumulatedMs + (Date.now() - s.runningSince) } };
    }
    case 'RESUME_SESSION': {
      const s = state.activeSession;
      if (!s || s.runningSince !== null) return state;
      return { ...state, activeSession: { ...s, runningSince: Date.now() } };
    }
    case 'CANCEL_SESSION':
      return { ...state, activeSession: null };
    case 'COMPLETE_SESSION': {
      const s = state.activeSession;
      if (!s) return state;
      const session: StudySession = {
        id: uid('ses'),
        taskId: s.taskId,
        date: DEMO_TODAY,
        minutes: action.minutes,
        note: action.note,
        source: 'timer',
        completedAt: new Date().toISOString(),
        blockId: action.blockId,
        plannedMin: action.plannedMin,
        completionPercent: action.evaluation?.completion_percent,
        outcome: action.evaluation?.status,
        blocker: action.evaluation?.blocker,
        blockerNote: action.evaluation?.blocker_note,
        needsRecovery: action.evaluation?.needs_recovery,
      };
      const tasks = state.tasks.map((task) =>
        task.id === s.taskId
          ? { ...task, loggedMin: task.loggedMin + action.minutes, status: task.status === 'done' ? 'done' as const : 'in_progress' as const }
          : task,
      );
      return withFreshPilotMetrics({
        ...state,
        activeSession: null,
        sessions: [session, ...state.sessions],
        ...withTaskProgress(state, tasks),
      });
    }
    case 'ADD_MANUAL_SESSION': {
      const session: StudySession = { ...action.session, id: uid('ses'), source: 'manual' };
      const tasks = state.tasks.map((task) =>
        task.id === session.taskId
          ? { ...task, loggedMin: task.loggedMin + session.minutes, status: task.status === 'done' ? 'done' as const : 'in_progress' as const }
          : task,
      );
      return withFreshPilotMetrics({
        ...state,
        sessions: [session, ...state.sessions],
        ...withTaskProgress(state, tasks),
      });
    }
    case 'UPDATE_TASK_ESTIMATE': {
      const tasks = state.tasks.map((task) => (
        task.id === action.taskId ? { ...task, estimateMin: action.estimateMin, estimateIsAssumption: false } : task
      ));
      return withFreshPilotMetrics({
        ...state,
        ...withTaskProgress(state, tasks),
      });
    }
    case 'UPDATE_TASK_PRIORITY': {
      const tasks = state.tasks.map((task) => (
        task.id === action.taskId
          ? { ...task, personalPriority: action.personalPriority }
          : task
      ));
      return {
        ...state,
        ...withTaskProgress(state, tasks),
      };
    }
    case 'SET_TASK_DONE': {
      const completedTasks = state.tasks.map((task) =>
        task.id === action.taskId
          ? { ...task, status: action.done ? 'done' as const : task.loggedMin > 0 ? 'in_progress' as const : 'todo' as const }
          : task,
      );
      const estimateProfiles = action.done
        ? updateEstimateProfiles(state.estimateProfiles, state.tasks, completedTasks)
        : state.estimateProfiles;
      const tasks = completedTasks.map((task) => (
        task.id !== action.taskId && task.estimateIsAssumption
          ? { ...task, estimateMin: adaptiveEstimate(task, estimateProfiles) }
          : task
      ));
      return withFreshPilotMetrics({
        ...state,
        estimateProfiles,
        ...withTaskProgress(state, tasks),
      });
    }
    case 'CREATE_QA_CONVERSATION': {
      const activeCourseId = state.user?.courseId || 'general';
      const newConv: QAConversation = {
        id: uid('conv'),
        courseId: activeCourseId,
        title: action.title || 'Cuộc trò chuyện mới',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: [],
      };
      const updatedConversations = [newConv, ...state.qaConversations];
      try {
        if (state.user) {
          window.localStorage.setItem(`pacewise_qa_convs_${state.user.id}`, JSON.stringify(updatedConversations));
        }
      } catch {}
      return {
        ...state,
        qaConversations: updatedConversations,
        activeConversationId: newConv.id,
        qaMessages: [],
      };
    }
    case 'SELECT_QA_CONVERSATION': {
      const conv = state.qaConversations.find((c) => c.id === action.id);
      return {
        ...state,
        activeConversationId: action.id,
        qaMessages: conv ? conv.messages : [],
      };
    }
    case 'RENAME_QA_CONVERSATION': {
      const updatedConversations = state.qaConversations.map((c) =>
        c.id === action.id ? { ...c, title: action.title.trim() || c.title, updatedAt: new Date().toISOString() } : c
      );
      try {
        if (state.user) {
          window.localStorage.setItem(`pacewise_qa_convs_${state.user.id}`, JSON.stringify(updatedConversations));
        }
      } catch {}
      return {
        ...state,
        qaConversations: updatedConversations,
      };
    }
    case 'DELETE_QA_CONVERSATION': {
      const updatedConversations = state.qaConversations.filter((c) => c.id !== action.id);
      let nextActiveId = state.activeConversationId;
      let nextMessages = state.qaMessages;
      if (state.activeConversationId === action.id) {
        const activeCourseId = state.user?.courseId || 'general';
        const remainingInCourse = updatedConversations.filter((c) => c.courseId === activeCourseId);
        nextActiveId = remainingInCourse[0]?.id ?? null;
        nextMessages = remainingInCourse[0]?.messages ?? [];
      }
      try {
        if (state.user) {
          window.localStorage.setItem(`pacewise_qa_convs_${state.user.id}`, JSON.stringify(updatedConversations));
        }
      } catch {}
      return {
        ...state,
        qaConversations: updatedConversations,
        activeConversationId: nextActiveId,
        qaMessages: nextMessages,
      };
    }
    case 'ADD_QA': {
      const activeCourseId = state.user?.courseId || 'general';
      let activeId = state.activeConversationId;
      let conversations = [...state.qaConversations];
      let activeConv = conversations.find((c) => c.id === activeId);

      if (!activeConv || activeConv.courseId !== activeCourseId) {
        const title = action.message.role === 'user'
          ? (action.message.text.slice(0, 35) + (action.message.text.length > 35 ? '...' : ''))
          : 'Cuộc trò chuyện mới';
        activeConv = {
          id: uid('conv'),
          courseId: activeCourseId,
          title,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          messages: [],
        };
        conversations.unshift(activeConv);
        activeId = activeConv.id;
      } else if (activeConv.messages.length === 0 && action.message.role === 'user' && activeConv.title === 'Cuộc trò chuyện mới') {
        activeConv.title = action.message.text.slice(0, 35) + (action.message.text.length > 35 ? '...' : '');
      }

      const updatedMessages = [...activeConv.messages, action.message].slice(-100);
      activeConv.messages = updatedMessages;
      activeConv.updatedAt = new Date().toISOString();

      try {
        if (state.user) {
          window.localStorage.setItem(`pacewise_qa_convs_${state.user.id}`, JSON.stringify(conversations));
        }
      } catch {}

      return {
        ...state,
        qaConversations: conversations,
        activeConversationId: activeId,
        qaMessages: updatedMessages,
      };
    }
    case 'CLEAR_QA': {
      if (!state.activeConversationId) return state;
      const updatedConversations = state.qaConversations.map((c) =>
        c.id === state.activeConversationId ? { ...c, messages: [], updatedAt: new Date().toISOString() } : c
      );
      try {
        if (state.user) {
          window.localStorage.setItem(`pacewise_qa_convs_${state.user.id}`, JSON.stringify(updatedConversations));
        }
      } catch {}
      return {
        ...state,
        qaConversations: updatedConversations,
        qaMessages: [],
      };
    }
    case 'SUBMIT_QUICK_CHECK':
      return {
        ...state,
        quickChecks: [action.result, ...state.quickChecks],
        reviewQueue: action.reviewItem ? [action.reviewItem, ...state.reviewQueue] : state.reviewQueue,
        audit: action.reviewItem ? audit(state, `Chuyển ca kiểm tra #${action.reviewItem.id} vào Review Queue`) : state.audit,
      };
    case 'ADD_CLASS_GUIDANCE': {
      const d = new Date();
      const at = `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(
        d.getMinutes(),
      ).padStart(2, '0')}`;
      const g: ClassGuidance = {
        id: uid('gd'),
        topic: action.topic,
        message: action.message,
        at,
        instructorName: state.user?.name ?? 'Giảng viên',
      };
      return {
        ...state,
        guidance: [g, ...state.guidance],
        audit: audit(state, `Phát gợi ý ôn tập chủ đề “${action.topic}”`),
      };
    }
    case 'APPLY_RECOVERY': {
      if (!state.plan) return state;
      const horizon = splitRecoveryHorizon(state.plan, action.blocks);
      const plan: Plan = { ...state.plan, id: uid('plan'), blocks: horizon.committed, savedAt: new Date().toISOString(), version: state.plan.version + 1 };
      const constraints = mergeUnavailable(state.unavailable, lmsUnavailableSlots(state.courseData));
      const constraintById = new Map(constraints.map((slot) => [slot.id, slot]));
      const planImpacts = state.planImpacts.filter((impact) => {
        if (impact.id === action.impactId) return false;
        if (impact.kind !== 'schedule_conflict' || !impact.constraintId) return true;
        const constraint = constraintById.get(impact.constraintId);
        if (!constraint) return false;
        return impact.affectedBlockIds.some((blockId) => {
          const block = plan.blocks.find((item) => item.id === blockId);
          return block ? slotOverlapsBlock(block, constraint) : false;
        });
      });
      return withFreshPilotMetrics({
        ...state,
        plan,
        calendarDraft: null,
        provisionalBlocks: horizon.provisional,
        planHistory: [state.plan, ...state.planHistory],
        dismissedDrifts: [],
        recoveryOptions: [],
        recoveryOptionsKey: null,
        planImpacts,
        recoveryCount: state.recoveryCount + 1,
      });
    }
    case 'SET_RECOVERY_OPTIONS':
      return { ...state, recoveryOptions: action.options, recoveryOptionsKey: action.key };
    case 'SAVE_REFLECTION':
      return {
        ...state,
        reflections: {
          ...state.reflections,
          [action.reflectionKey ?? `${action.courseId}:${action.weekStart}`]: {
            courseId: action.courseId,
            weekStart: action.weekStart,
            effectiveWeekStart: action.effectiveWeekStart,
            scope: action.scope ?? 'weekly',
            activityId: action.activityId,
            activityTitle: action.activityTitle,
            activityKind: action.activityKind,
            answers: action.answers,
            savedAt: new Date().toISOString(),
            aiDraft: action.aiDraft,
            aiSummary: action.aiSummary,
          },
        },
      };
    case 'SAVE_AVAILABILITY': {
      const detectedImpacts = detectAvailabilityPlanImpacts(
        state.plan,
        state.tasks,
        state.unavailable,
        action.unavailable,
      );
      const before = new Map(state.unavailable.map((slot) => [slot.id, slot]));
      const after = new Map(action.unavailable.map((slot) => [slot.id, slot]));
      const changedConstraintIds = new Set([...new Set([...before.keys(), ...after.keys()])].filter((id) => {
        const old = before.get(id);
        const next = after.get(id);
        return !old || !next || old.date !== next.date || old.weekday !== next.weekday || old.start !== next.start || old.end !== next.end;
      }));
      const retainedImpacts = state.planImpacts.filter((impact) => !impact.constraintId || !changedConstraintIds.has(impact.constraintId));
      const existingImpactIds = new Set(retainedImpacts.map((impact) => impact.id));
      return withFreshPilotMetrics({
        ...state,
        availability: action.availability,
        unavailable: action.unavailable,
        calendarDraft: action.draftBlocks
          ? { blocks: action.draftBlocks, needsAnalysis: true, updatedAt: new Date().toISOString() }
          : state.calendarDraft,
        planImpacts: [
          ...retainedImpacts,
          ...detectedImpacts.filter((impact) => !existingImpactIds.has(impact.id)),
        ].slice(-50),
      });
    }
    case 'UPDATE_ROUTINE_PROFILE':
      return {
        ...state,
        routineProfile: action.profile,
        calendarDraft: action.draftBlocks
          ? { blocks: action.draftBlocks, needsAnalysis: true, updatedAt: new Date().toISOString() }
          : state.calendarDraft,
      };
    case 'UPDATE_SETTINGS':
      return { ...state, settings: { ...state.settings, ...action.patch } };
    case 'SET_REVIEW_STATUS': {
      const item = state.reviewQueue.find((r) => r.id === action.id);
      const label = {
        approved: 'Duyệt kết luận',
        edited: 'Sửa và duyệt kết luận',
        rejected: 'Từ chối kết luận',
        needs_evidence: 'Yêu cầu thêm bằng chứng',
        in_review: 'Bắt đầu xem',
        pending: 'Đưa về chờ',
        superseded: 'Ca đã được giải quyết bằng bằng chứng mới',
      }[action.status];
      return {
        ...state,
        reviewQueue: state.reviewQueue.map((r) => (r.id === action.id ? { ...r, status: action.status, note: action.note ?? r.note } : r)),
        quickChecks: state.quickChecks.map((qc) =>
          qc.reviewItemId === action.id
            ? {
                ...qc,
                instructorNote: action.note ?? (
                  action.status === 'approved' || action.status === 'edited'
                    ? 'Giảng viên đã xem và xác nhận phân tích.'
                    : undefined
                ),
              }
            : qc,
        ),
        audit: audit(state, `${label} ca #${item?.id ?? action.id}`),
      };
    }
    case 'SET_ASSESSMENT_STATUS': {
      const item = state.assessments.find((a) => a.id === action.id);
      const label = { approved: 'Duyệt và xuất bản', rejected: 'Trả lại', review: 'Gửi review', draft: 'Đưa về bản nháp' }[action.status];
      return {
        ...state,
        assessments: state.assessments.map((a) => (a.id === action.id ? { ...a, status: action.status, note: action.note ?? a.note } : a)),
        audit: audit(state, `${label} câu hỏi “${item?.topic ?? ''}”`),
      };
    }
    case 'ADD_ASSESSMENT_DRAFT':
      if (state.assessments.some((item) => item.id === action.item.id)) return state;
      return {
        ...state,
        assessments: [action.item, ...state.assessments],
        audit: audit(state, `Tạo bản nháp câu kiểm tra “${action.item.topic}”`),
      };
    case 'UPDATE_ASSESSMENT': {
      const d = new Date();
      const at = `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
      return {
        ...state,
        assessments: state.assessments.map((a) =>
          a.id === action.item.id
            ? {
                ...a,
                ...action.item,
                status: action.status ?? a.status,
                note: action.note ?? a.note,
                history: [...(a.history ?? []), { at, text: action.historyText }],
              }
            : a,
        ),
        audit: audit(state, `${action.historyText}: câu hỏi “${state.assessments.find((a) => a.id === action.item.id)?.topic ?? ''}”`),
      };
    }
    case 'DISMISS_DRIFT':
      return { ...state, dismissedDrifts: [...state.dismissedDrifts, action.taskId], recoveryOptions: [], recoveryOptionsKey: null };
    case 'DISMISS_PLAN_IMPACT':
      return { ...state, planImpacts: state.planImpacts.filter((impact) => impact.id !== action.impactId) };
    case 'APPLY_PLAN_IMPACT': {
      const impact = state.planImpacts.find((item) => item.id === action.impactId);
      if (!impact || !state.plan) {
        return { ...state, planImpacts: state.planImpacts.filter((item) => item.id !== action.impactId) };
      }
      const affected = new Set(impact.affectedBlockIds);
      const nextPlan = {
        ...state.plan,
        id: uid('plan'),
        blocks: state.plan.blocks.filter((block) => !affected.has(block.id)),
        savedAt: new Date().toISOString(),
        version: state.plan.version + 1,
      };
      return withFreshPilotMetrics({
        ...state,
        plan: nextPlan,
        planHistory: [state.plan, ...state.planHistory],
        planImpacts: state.planImpacts.filter((item) => item.id !== action.impactId),
      });
    }
    default:
      return state;
  }
}

function load(): AppState {
  return initialState;
}

interface StoreValue {
  state: AppState;
  dispatch: React.Dispatch<Action>;
  persistence: PersistenceState;
  retrySave: () => void;
}
const StoreContext = createContext<StoreValue | null>(null);

export function AppStoreProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, load);
  const [persistence, setPersistence] = useState<PersistenceState>({ status: 'idle', savedAt: null });
  const [saveAttempt, setSaveAttempt] = useState(0);
  const workspaceVersion = useRef(0);
  const queuedWorkspace = useRef<Record<string, unknown> | null>(null);
  const queuedRevision = useRef(0);
  const saveInFlight = useRef(false);
  const editRevision = useRef(0);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    const refreshAuth = (event: StorageEvent) => {
      if (event.key === 'pacewise:auth-change') window.location.reload();
    };
    const restored = (event: PageTransitionEvent) => { if (event.persisted) window.location.reload(); };
    window.addEventListener('storage', refreshAuth);
    window.addEventListener('pageshow', restored);
    return () => { window.removeEventListener('storage', refreshAuth); window.removeEventListener('pageshow', restored); };
  }, []);
  useEffect(() => {
    let active = true;
    getCurrentSession()
      .then((user) => {
        if (!active) return;
        dispatch(user ? { type: 'LOGIN', user } : { type: 'AUTH_READY' });
      })
      .catch(() => active && dispatch({ type: 'AUTH_READY' }));
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!state.user) return;
    let active = true;
    workspaceVersion.current = 0;
    loadWorkspace()
      .then((workspace) => {
        if (!active) return;
        workspaceVersion.current = workspace.version;
        setPersistence({ status: 'idle', savedAt: workspace.updatedAt });
        dispatch({ type: 'HYDRATE_WORKSPACE', state: workspace.state as Partial<AppState> });
      })
      .catch(() => {
        if (!active) return;
        setPersistence({ status: 'error', savedAt: null, message: 'Không tải được dữ liệu PaceWise đã lưu.' });
        dispatch({ type: 'HYDRATE_WORKSPACE', state: {} });
      });
    return () => { active = false; };
  }, [state.user?.id]);

  useEffect(() => {
    if (!state.user || !state.workspaceReady) return;
    let active = true;
    let refreshInFlight = false;
    let refreshQueued = false;
    let lastRefreshAt = 0;
    const refresh = async () => {
      if (refreshInFlight) {
        refreshQueued = true;
        return;
      }
      refreshInFlight = true;
      lastRefreshAt = Date.now();
      try {
        const result = await syncCanvas();
        const user = await getCurrentSession();
        if (active && user) dispatch({ type: 'REFRESH_SESSION', user });
        if (active) dispatch({
          type: 'SYNC_CANVAS',
          courses: result.courses,
          tasks: result.tasks,
          guidance: result.guidance,
          assessments: result.assessments,
          courseData: result.courseData,
          reviewResolutions: result.reviewResolutions,
        });
      } catch {
        if (active) dispatch({ type: 'COURSE_SOURCE_FAILED' });
      } finally {
        refreshInFlight = false;
        if (active && refreshQueued) {
          refreshQueued = false;
          void refresh();
        }
      }
    };
    void refresh();

    const stream = typeof EventSource === 'undefined'
      ? null
      : new EventSource(lmsEventStreamUrl(), { withCredentials: true });
    const handleLmsChange = () => {
      if (!active) return;
      dispatch({ type: 'LMS_EVENT_RECEIVED' });
      void refresh();
      window.dispatchEvent(new Event('pacewise:source-change'));
    };
    stream?.addEventListener('lms.changed', handleLmsChange);

    const refreshWhenVisible = () => {
      if (
        document.visibilityState === 'visible'
        && Date.now() - lastRefreshAt >= 30_000
      ) void refresh();
    };
    document.addEventListener('visibilitychange', refreshWhenVisible);
    window.addEventListener('online', refreshWhenVisible);
    window.addEventListener('pacewise:membership-change', handleLmsChange);
    // Safety net only. Normal updates arrive through the event stream.
    const fallbackTimer = window.setInterval(() => void refresh(), 5 * 60_000);
    return () => {
      active = false;
      stream?.removeEventListener('lms.changed', handleLmsChange);
      stream?.close();
      document.removeEventListener('visibilitychange', refreshWhenVisible);
      window.removeEventListener('online', refreshWhenVisible);
      window.removeEventListener('pacewise:membership-change', handleLmsChange);
      window.clearInterval(fallbackTimer);
    };
  }, [state.user?.id, state.workspaceReady]);
  useEffect(() => {
    if (!state.user || !state.workspaceReady) return;
    const revision = ++editRevision.current;
    setPersistence((current) => ({ ...current, status: 'saving', message: undefined }));
    const timer = window.setTimeout(() => {
      queuedWorkspace.current = state as unknown as Record<string, unknown>;
      queuedRevision.current = revision;
      if (saveInFlight.current) return;
      const drain = async () => {
        saveInFlight.current = true;
        while (queuedWorkspace.current) {
          const snapshot = queuedWorkspace.current;
          const savingRevision = queuedRevision.current;
          queuedWorkspace.current = null;
          if (mounted.current) setPersistence((current) => ({ ...current, status: 'saving', message: undefined }));
          try {
            const saved = await saveWorkspace(snapshot, workspaceVersion.current);
            workspaceVersion.current = saved.version;
            if (mounted.current) setPersistence({ status: savingRevision === editRevision.current ? 'saved' : 'saving', savedAt: saved.updatedAt });
          } catch (error) {
            // Keep a newer edit queued; never discard it because an older save failed.
            if (mounted.current) setPersistence((current) => ({
              status: error instanceof Error && 'code' in error && error.code === 'CONFLICT' ? 'conflict' : 'error',
              savedAt: current.savedAt,
              message: error instanceof Error ? error.message : 'Không lưu được dữ liệu PaceWise.',
            }));
            break;
          }
        }
        saveInFlight.current = false;
      };
      void drain();
    }, state.calendarDraft ? 0 : 750);
    return () => window.clearTimeout(timer);
  }, [state, saveAttempt]);
  useEffect(() => {
    if (!state.calendarDraft || persistence.status === 'saved') return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [state.calendarDraft, persistence.status]);
  const value = useMemo(() => ({ state, dispatch, persistence, retrySave: () => setSaveAttempt((attempt) => attempt + 1) }), [state, persistence]);
  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useAppStore() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error('useAppStore must be used inside AppStoreProvider');
  return ctx;
}
