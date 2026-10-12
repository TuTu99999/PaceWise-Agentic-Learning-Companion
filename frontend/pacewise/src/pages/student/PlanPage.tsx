import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { PlanCalendarBoard } from '../../components/domain/PlanCalendarBoard';
import { PlanDraftNotice } from '../../components/domain/PlanDraftNotice';
import { PlanMonthBoard } from '../../components/domain/PlanMonthBoard';
import { LmsCalendarNoticeDialog, PersonalSlotDialog, RoutineDialog } from '../../components/domain/PersonalScheduleDialogs';
import { ReminderCenter } from '../../components/domain/ReminderCenter';
import { StudyBlockDialog } from '../../components/domain/StudyBlockDialog';
import { PartialPlanDialog } from '../../components/domain/PartialPlanDialog';
import { Modal } from '../../components/ui/Modal';
import { Button, IconButton } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { useToast } from '../../components/ui/Toast';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { confirmPlan, generatePlan, proposeWeeklyGoals } from '../../services/api';
import { canConfirmPlan, partialPlanPreview, planBlockIssueLabel } from '../../utils/planConfirmation';
import { hasExpiredDraftWork, isExpiredTask, isOpenPlanningTask } from '../../utils/planningScope';
import { useAppStore } from '../../store/AppStore';
import type { PersonalSlotCategory, PlanInput, TimeBlock, UnavailableSlot, WeeklyGoal } from '../../types';
import { lmsUnavailableSlots, mergeUnavailable } from '../../utils/lmsPlanning';
import { pinnedBlocksForReanalysis } from '../../utils/planPins';
import { buildPlanTimeline, hidePastStudentCalendarItems, type PlanTimelineItem } from '../../utils/planTimeline';
import { routineAvailability, routineSleepSlots } from '../../utils/routine';
import { studyBlockAccess } from '../../utils/studyBlockAccess';
import { blockDeadlineError, blockTimestamp, confirmedBlockIssue, personalSlotTimeError } from '../../utils/calendarEditing';
import { calendarToday, useCalendarNow } from '../../hooks/useCalendarToday';
import { addDays, APP_TIMEZONE, calendarWeekStart, diffDays, durationMin, formatDM, formatDuration, TASK_SELECTION_HORIZON_DAYS, toClock, toMin, uid, weekdayOf, weekDates } from '../../utils/time';

type CalendarView = 'week' | 'month' | 'next7';

const monthStartOf = (date: string) => `${date.slice(0, 7)}-01`;
const addMonths = (date: string, offset: number) => {
  const [year, month] = date.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1 + offset, 1)).toISOString().slice(0, 10);
};

const overlaps = (left: { start: string; end?: string }, right: { start: string; end?: string }) => (
  Boolean(left.end && right.end) && toMin(left.start) < toMin(right.end!) && toMin(right.start) < toMin(left.end!)
);

const editablePersonalSlots = (slots: UnavailableSlot[]) => slots.filter((slot) => slot.source !== 'lms' && slot.source !== 'routine');

/** Checkpoints occupy calendar time but do not consume the task's remaining work. */
const scheduledWorkMinutes = (block: Pick<TimeBlock, 'start' | 'end' | 'checkpointMinutes'>) => (
  Math.max(0, durationMin(block.start, block.end) - Math.max(0, block.checkpointMinutes ?? 0))
);

const planErrorDescription = (error: unknown) => {
  if (!(error instanceof Error) || !('code' in error)) return 'Dữ liệu kéo thả vẫn được giữ. Hãy thử lại.';
  const apiError = error as Error & { code: string; requestId?: string; retryAfterSeconds?: number };
  if (apiError.code === 'RATE_LIMITED' && apiError.retryAfterSeconds) {
    return `${apiError.message} Thử lại sau ${apiError.retryAfterSeconds} giây. Dữ liệu kéo thả vẫn được giữ.`;
  }
  return `${apiError.message} Dữ liệu kéo thả vẫn được giữ.${apiError.requestId ? ` Mã yêu cầu: ${apiError.requestId}.` : ''}`;
};

export function PlanPage() {
  useDocumentTitle('Plan');
  const { state, dispatch, persistence, retrySave } = useAppStore();
  const now = useCalendarNow();
  const today = calendarToday(new Date(now));
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const toast = useToast();
  const reanalysisStarted = useRef(new Set<string>());
  const initialStart = calendarWeekStart(today);
  const [anchorDate, setAnchorDate] = useState(today);
  const [calendarView, setCalendarView] = useState<CalendarView>('week');
  const [calendarSource, setCalendarSource] = useState<'applied' | 'draft' | null>(null);
  const showingApplied = (calendarSource ?? (state.calendarDraft ? 'draft' : state.plan ? 'applied' : 'draft')) === 'applied' && Boolean(state.plan);
  const blocks = useMemo(() => showingApplied ? state.plan!.blocks : state.calendarDraft?.blocks ?? state.planDraft?.blocks
    ?? [...(state.plan?.blocks ?? []), ...state.provisionalBlocks], [showingApplied, state.calendarDraft, state.planDraft, state.plan, state.provisionalBlocks]);
  const [unavailable, setUnavailable] = useState<UnavailableSlot[]>(editablePersonalSlots(state.unavailable));
  const needsAnalysis = Boolean(state.calendarDraft?.needsAnalysis);
  const editBlocks = (next: TimeBlock[]) => {
    if (!generating && !saving) { dispatch({ type: 'SAVE_CALENDAR_DRAFT', blocks: next }); setCalendarSource('draft'); }
  };
  const [filterOpen, setFilterOpen] = useState(false);
  const [courseFilter, setCourseFilter] = useState('all');
  const [showPersonal, setShowPersonal] = useState(true);
  const [toolsPanel, setToolsPanel] = useState<'tasks' | 'personal' | null>(null);
  const [legendOpen, setLegendOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [goalDialogOpen, setGoalDialogOpen] = useState(false);
  const [routineDialogOpen, setRoutineDialogOpen] = useState(false);
  const [personalDialog, setPersonalDialog] = useState<{ category: PersonalSlotCategory; label: string } | null>(null);
  const [editingPersonalItem, setEditingPersonalItem] = useState<PlanTimelineItem | null>(null);
  const [lmsNoticeItem, setLmsNoticeItem] = useState<PlanTimelineItem | null>(null);
  const [pendingBlockId, setPendingBlockId] = useState<string | null>(null);
  const [partialReviewOpen, setPartialReviewOpen] = useState(false);
  const [partialStartId, setPartialStartId] = useState<string>();
  const [loadingGoals, setLoadingGoals] = useState(false);
  const [weeklyGoals, setWeeklyGoals] = useState<WeeklyGoal[]>(
    state.planDraft?.weeklyGoals ?? state.wizardInput?.weeklyGoals ?? [],
  );

  useEffect(() => {
    if (!state.planDraft) return;
    const draftStart = state.planDraft.weekStart ?? state.planDraft.input.weekStart ?? initialStart;
    setAnchorDate(today >= draftStart && today <= addDays(draftStart, 6) ? today : draftStart < initialStart ? initialStart : draftStart);
    setWeeklyGoals(state.planDraft.weeklyGoals ?? state.planDraft.input.weeklyGoals ?? []);
  }, [initialStart, state.planDraft, today]);

  useEffect(() => {
    // Personal schedule is owned by the hydrated workspace, not by an older
    // AI draft. Keep local calendar state in sync even when no draft exists.
    setUnavailable(editablePersonalSlots(state.unavailable));
  }, [state.unavailable]);

  const monthStart = monthStartOf(anchorDate);
  const monthEnd = addDays(addMonths(monthStart, 1), -1);
  const weekStart = calendarView === 'week' ? calendarWeekStart(anchorDate) : calendarView === 'next7' ? anchorDate : calendarWeekStart(monthStart);
  const weekEnd = calendarView === 'month' ? addDays(calendarWeekStart(monthEnd), 6) : addDays(weekStart, 6);
  const dates = useMemo(
    () => calendarView === 'month'
      ? Array.from({ length: diffDays(weekStart, weekEnd) + 1 }, (_, index) => addDays(weekStart, index))
      : weekDates(weekStart),
    [calendarView, weekEnd, weekStart],
  );
  const openTasks = useMemo(
    () => [...state.tasks]
      .filter((task) => isOpenPlanningTask(task, now))
      .sort((a, b) => a.deadline.localeCompare(b.deadline)),
    [state.tasks, now],
  );
  const calendarItems = useMemo(() => Object.values(state.courseData).flatMap((course) => course.calendarItems ?? []), [state.courseData]);
  const routineConstraints = useMemo(() => routineSleepSlots(state.routineProfile), [state.routineProfile]);
  const effectiveAvailability = useMemo(
    () => routineAvailability(state.routineProfile, state.availability),
    [state.availability, state.routineProfile],
  );
  const constraints = useMemo(
    () => mergeUnavailable([...unavailable, ...routineConstraints], lmsUnavailableSlots(state.courseData)),
    [routineConstraints, state.courseData, unavailable],
  );
  const visibleBlocks = useMemo(() => blocks.filter((block) => block.date >= weekStart && block.date <= weekEnd), [blocks, weekEnd, weekStart]);
  const timeline = useMemo(() => hidePastStudentCalendarItems(
    buildPlanTimeline({ blocks: visibleBlocks, calendarItems, tasks: state.tasks, courses: state.courses, unavailable: constraints, from: weekStart, to: weekEnd }),
    today,
  ), [calendarItems, constraints, state.courses, state.tasks, today, visibleBlocks, weekEnd, weekStart]);
  const filteredTimeline = useMemo(() => {
    const course = state.courses.find((item) => item.id === courseFilter);
    const taskIds = new Set(state.tasks.filter((task) => task.courseId === courseFilter).map((task) => task.id));
    return timeline.filter((item) => {
      if (item.source === 'busy') return showPersonal;
      return courseFilter === 'all' || (item.taskId ? taskIds.has(item.taskId) : item.courseCode === course?.code);
    });
  }, [timeline, courseFilter, showPersonal, state.courses, state.tasks]);
  const filteredTasks = courseFilter === 'all' ? openTasks : openTasks.filter((task) => task.courseId === courseFilter);
  const shownBlocks = filteredTimeline.filter((item) => item.source === 'pacewise' && item.scheduleStatus !== 'history' && blockTimestamp(item.date, item.end ?? item.start) > now);
  const totalMinutes = shownBlocks.reduce((total, item) => total + item.durationMin, 0);
  const expiredDraft = hasExpiredDraftWork(state.planDraft, state.tasks, now);
  const expiredAppliedRisk = state.plan?.feasibility?.shortfalls.some(s => state.tasks.some(t => t.id === s.taskId && isExpiredTask(t, now)));
  const draftReady = Boolean(state.planDraft) && !needsAnalysis && !expiredDraft;
  const draftConfirmable = draftReady && canConfirmPlan(state.planDraft);
  const partialPreview = partialPlanPreview(state.planDraft);
  const partialConfirmable = draftReady && Boolean(partialPreview?.canConfirm) && !draftConfirmable;
  const reviewPartial = (blockId?: string) => {
    setPartialStartId(blockId); setPendingBlockId(null); setPartialReviewOpen(true);
  };
  const qualityWarning = Boolean(state.planDraft?.qualityEvaluation && !state.planDraft.qualityEvaluation.releaseReady);
  const robustMissing = Math.max(0, ...(state.planDraft?.feasibility.robustShortfalls ?? []).map((item) => item.missingMin));
  const draftChecked = draftReady && !qualityWarning;

  const selectView = (view: CalendarView) => {
    setCalendarView(view);
    if (view === 'month') setAnchorDate(monthStartOf(anchorDate));
  };

  const shiftCalendar = (direction: -1 | 1) => {
    setAnchorDate((current) => calendarView === 'month' ? addMonths(current, direction) : addDays(current, direction * 7));
  };

  const validateBlock = (candidate: TimeBlock, ignoreId?: string) => {
    if (generating || saving) return 'Hãy chờ kiểm tra hoặc xác nhận kế hoạch hoàn tất trước khi chỉnh lịch.';
    const task = state.tasks.find((item) => item.id === candidate.taskId);
    if (!task) return 'Nhiệm vụ không còn tồn tại.';
    if (candidate.date < today) return 'Không thể xếp ca tự học vào thời gian đã qua.';
    if (blockTimestamp(candidate.date, candidate.start) < Date.now() + 15 * 60_000) {
      return 'Ca tự học phải bắt đầu sau thời điểm hiện tại ít nhất 15 phút.';
    }
    const deadlineError = blockDeadlineError(candidate, task);
    if (deadlineError) return deadlineError;
    if (durationMin(candidate.start, candidate.end) < 15) return 'Ca tự học phải dài ít nhất 15 phút.';
    const alreadyPlanned = blocks
      .filter((block) => block.id !== ignoreId && block.taskId === candidate.taskId)
      .filter((block) => block.status !== 'history')
      .reduce((total, block) => total + scheduledWorkMinutes(block), 0);
    const remainingWork = Math.max(30, task.estimateMin - task.loggedMin);
    if (alreadyPlanned + scheduledWorkMinutes(candidate) > remainingWork) {
      return `Nhiệm vụ này chỉ còn ${formatDuration(Math.max(0, remainingWork - alreadyPlanned))} chưa được xếp.`;
    }
    const availability = effectiveAvailability.find((day) => day.weekday === weekdayOf(candidate.date));
    const insideDeclaredStudyTime = constraints.some((slot) => (
      slot.category === 'self_study'
      && (!slot.date || slot.date === candidate.date)
      && slot.weekday === weekdayOf(candidate.date)
      && toMin(candidate.start) >= toMin(slot.start)
      && toMin(candidate.end) <= toMin(slot.end)
    ));
    if (!insideDeclaredStudyTime && (!availability?.enabled || toMin(candidate.start) < toMin(availability.start) || toMin(candidate.end) > toMin(availability.end))) return 'Khung giờ này nằm ngoài thời gian bạn có thể học.';
    if (blocks.some((block) => block.id !== ignoreId && block.date === candidate.date && overlaps(candidate, block))) return 'Ca tự học bị trùng với một ca khác.';
    const preferredSlotIds = new Set(constraints.filter((slot) => slot.category === 'self_study').map((slot) => slot.id));
    const fixed = buildPlanTimeline({ blocks: [], calendarItems, tasks: state.tasks, courses: state.courses,
      unavailable: constraints, from: candidate.date, to: candidate.date })
      .filter((item) => item.end && !(item.entityId && preferredSlotIds.has(item.entityId)));
    if (fixed.some((item) => overlaps(candidate, item))) return 'Khung giờ này trùng lịch LMS hoặc lịch cá nhân.';
    return undefined;
  };

  const moveBlock = (id: string, date: string, start: string) => {
    const current = blocks.find((block) => block.id === id);
    if (!current) return;
    const duration = Math.max(15, durationMin(current.start, current.end));
    const boundedStart = Math.min(toMin(start), 24 * 60 - duration);
    const candidate = { ...current, date, start: toClock(boundedStart), end: toClock(boundedStart + duration), placementSource: 'student' as const };
    const error = validateBlock(candidate, id);
    if (error) { toast({ tone: 'warning', title: 'Không thể dời block', description: error }); return; }
    editBlocks(blocks.map((block) => block.id === id ? candidate : block));
  };

  const resizeBlock = (id: string, edge: 'start' | 'end', clock: string) => {
    const current = blocks.find((block) => block.id === id);
    if (!current) return;
    const candidate = { ...current, [edge]: clock, placementSource: 'student' as const };
    const error = validateBlock(candidate, id);
    if (error) { toast({ tone: 'warning', title: 'Không thể đổi thời lượng', description: error }); return; }
    editBlocks(blocks.map((block) => block.id === id ? candidate : block));
  };

  const savePersonalSchedule = (next: UnavailableSlot[]) => {
    if (generating || saving) return;
    setUnavailable(next);
    dispatch({ type: 'SAVE_AVAILABILITY', availability: state.availability, unavailable: next, draftBlocks: blocks });
    setCalendarSource('draft');
  };

  const resizeBusy = (id: string, edge: 'start' | 'end', clock: string) => {
    const current = unavailable.find((slot) => slot.id === id);
    if (!current) return;
    const candidate = { ...current, [edge]: clock };
    const error = personalSlotTimeError(candidate, now);
    if (error) {
      toast({ tone: 'warning', title: 'Không thể đổi hoạt động', description: error });
      return;
    }
    savePersonalSchedule(unavailable.map((slot) => slot.id === id ? candidate : slot));
  };

  const moveBusy = (id: string, date: string, start: string) => {
    const current = unavailable.find((slot) => slot.id === id);
    if (!current) return;
    const duration = Math.max(15, durationMin(current.start, current.end));
    const boundedStart = Math.min(toMin(start), 24 * 60 - duration);
    const nextStart = toClock(boundedStart);
    const nextEnd = toClock(boundedStart + duration);
    const candidate = { ...current, date, weekday: weekdayOf(date), start: nextStart, end: nextEnd };
    const error = personalSlotTimeError(candidate, now);
    if (error) {
      toast({ tone: 'warning', title: 'Không thể dời hoạt động', description: error });
      return;
    }
    savePersonalSchedule(unavailable.map((slot) => slot.id === id ? {
      ...slot, ...candidate,
    } : slot));
    toast({
      tone: 'info',
      title: current.category === 'self_study' ? 'Đã dời khung tự học ưu tiên' : 'Đã dời lịch cá nhân',
      description: 'Bấm AI phân tích lại để cập nhật các ca tự học liên quan.',
    });
  };

  const updatePersonalSlot = (id: string, value: { date: string; start: string; end: string; label: string; category: PersonalSlotCategory }) => {
    const current = unavailable.find((slot) => slot.id === id);
    if (!current) return;
    const candidate = { ...current, ...value, weekday: weekdayOf(value.date) };
    const error = personalSlotTimeError(candidate, now);
    if (error) {
      toast({ tone: 'warning', title: 'Không thể cập nhật hoạt động', description: error });
      return;
    }
    savePersonalSchedule(unavailable.map((slot) => slot.id === id ? {
      ...slot, ...candidate,
    } : slot));
    setEditingPersonalItem(null);
    toast({
      tone: 'success',
      title: 'Đã cập nhật hoạt động',
      description: 'Ngày, giờ và độ dài block đã được cập nhật. Bấm AI phân tích lại để kiểm tra kế hoạch.',
    });
  };

  const removeBlock = (id: string) => editBlocks(blocks.filter((block) => block.id !== id));

  const openStudyBlock = (id: string) => {
    setPendingBlockId(id);
  };

  const openCalendarItem = (item: PlanTimelineItem) => {
    if (item.source === 'lms') {
      setLmsNoticeItem(item);
      return;
    }
    if (item.source === 'busy' && item.entityId && !item.readOnly) setEditingPersonalItem(item);
  };

  const startStudyBlock = (id: string) => {
    const block = blocks.find((item) => item.id === id);
    if (!block) return;
    const issue = confirmedBlockIssue(block, state.plan?.blocks ?? [], state.tasks, constraints);
    if (issue) {
      toast({ tone: 'warning', title: 'Ca tự học chưa sẵn sàng', description: issue });
      return;
    }
    const access = studyBlockAccess(block);
    if (access.state === 'ended') {
      toast({ tone: 'warning', title: 'Buổi tự học đã kết thúc', description: 'Block vẫn được giữ trên lịch sử. Hãy để Plan Agent sắp xếp lại phần chưa hoàn thành.' });
      return;
    }
    navigate(`/study/${encodeURIComponent(block.taskId)}/session?blockId=${encodeURIComponent(block.id)}`);
  };

  const updateBlockExactTime = (candidate: TimeBlock) => {
    const learnerBlock = { ...candidate, placementSource: 'student' as const };
    const error = validateBlock(learnerBlock, learnerBlock.id);
    if (error) {
      toast({ tone: 'warning', title: 'Không thể đổi thời gian', description: error });
      return false;
    }
    editBlocks(blocks.map((block) => block.id === learnerBlock.id ? learnerBlock : block));
    toast({ tone: 'info', title: 'Đã cập nhật thời gian', description: 'Bấm AI phân tích lại để kiểm tra capacity và xung đột trước khi áp dụng.' });
    return true;
  };

  const addPersonalSlot = (date: string, start: string, category: PersonalSlotCategory, label: string, end?: string) => {
    if (generating || saving) return false;
    const slot: UnavailableSlot = { id: uid('personal-slot'), label, weekday: weekdayOf(date), date, start, end: end ?? toClock(Math.min(24 * 60, toMin(start) + 60)), source: 'manual', category };
    const error = personalSlotTimeError(slot, now);
    if (error) {
      toast({ tone: 'warning', title: 'Không thể thêm hoạt động', description: error });
      return false;
    }
    savePersonalSchedule([...unavailable, slot]);
    toast({
      tone: 'info',
      title: category === 'self_study' ? 'Đã thêm giờ tự học ưu tiên' : `Đã thêm ${label.toLowerCase()}`,
      description: category === 'self_study' ? 'Plan Agent sẽ thử xếp ca tự học vào khung này trước.' : 'Plan Agent sẽ tránh khung giờ này khi xếp lịch.',
    });
    return true;
  };

  const tasksForHorizon = () => {
    const pinnedTaskIds = new Set(blocks.map((block) => block.taskId));
    const planningWeekStart = calendarWeekStart(today);
    const horizonEnd = addDays(planningWeekStart, TASK_SELECTION_HORIZON_DAYS - 1);
    return openTasks.filter((task) => isOpenPlanningTask(task) && (pinnedTaskIds.has(task.id) || task.deadline <= horizonEnd));
  };

  const analyzeWithGoals = async (requestedGoals: WeeklyGoal[], replan?: {
    contextKey: string; impactIds: string[]; trigger: 'reflection' | 'lms' | 'progress' | 'deadline';
    scope?: 'activity' | 'weekly'; taskIds: string[];
  }) => {
    const selected = tasksForHorizon();
    if (selected.length === 0) { toast({ tone: 'warning', title: 'Chưa có nhiệm vụ để lập kế hoạch', description: 'LMS chưa có deadline trong 14 ngày tới.' }); return; }
    const planningWeekStart = calendarWeekStart(today);
    const horizonEnd = addDays(planningWeekStart, TASK_SELECTION_HORIZON_DAYS - 1);
    const selectedIds = new Set(selected.map(t => t.id));
    const goals = requestedGoals.map(g => ({ ...g, taskIds: g.taskIds.filter(id => selectedIds.has(id)) })).filter(g => g.taskIds.length > 0);
    const goalByTask = new Map(goals.flatMap((goal) => goal.taskIds.map((taskId) => [taskId, goal.id] as const)));
    const input: PlanInput = {
      studyPreferences: state.studyPreferences,
      goal: goals.map((goal) => goal.title).join('; '),
      weekStart: planningWeekStart,
      horizonEnd,
      weeklyGoals: goals.map((goal) => ({ ...goal, confirmed: true })),
      tasks: selected.map((task) => ({
        taskId: task.id,
        remainingMin: Math.max(30, task.estimateMin - task.loggedMin),
        weeklyGoalId: goalByTask.get(task.id),
      })),
      availability: effectiveAvailability,
      unavailable: constraints,
      preferred: state.routineProfile?.preferred ?? state.wizardInput?.preferred ?? ['morning', 'afternoon', 'evening'],
      pinnedBlocks: pinnedBlocksForReanalysis(blocks, today,
        new Intl.DateTimeFormat('en-GB', { timeZone: APP_TIMEZONE, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date()))
        .filter(block => !replan || block.status === 'history' || blockTimestamp(block.date, block.start) <= now
          || !state.planImpacts.some(impact => replan.impactIds.includes(impact.id) && impact.affectedBlockIds.includes(block.id))),
      ...(replan ? { replanContext: { trigger: replan.trigger, scope: replan.scope, taskIds: replan.taskIds } } : {}),
    };
    setGenerating(true);
    setPendingBlockId(null);
    setPersonalDialog(null);
    setEditingPersonalItem(null);
    setRoutineDialogOpen(false);
    setToolsPanel(null);
    try {
      const draft = await generatePlan(input, state.tasks);
      dispatch({ type: 'SET_WIZARD_INPUT', input });
      dispatch({ type: 'SET_DRAFT', draft: replan ? { ...draft, replan } : draft });
      setWeeklyGoals(draft.weeklyGoals ?? goals);
      setCalendarSource('draft');
      const robust = draft.feasibility.robustFeasible !== false;
      const confirmable = canConfirmPlan(draft);
      const partialAvailable = partialPlanPreview(draft)?.canConfirm;
      toast({
        tone: confirmable && robust ? 'success' : 'warning',
        title: !confirmable ? partialAvailable ? 'Có phần lịch hợp lệ để xác nhận' : 'Bản nháp có lỗi cần xử lý' : robust ? 'AI đã tạo lịch khả thi' : 'Kế hoạch còn cảnh báo capacity',
        description: !draft.feasibility.feasible
          ? `Còn thiếu ${formatDuration(draft.feasibility.deficitMin)} trước deadline.${partialAvailable ? ' Bạn có thể xem và xác nhận các ca hợp lệ đã xếp.' : ''}`
          : !robust
            ? 'Lịch đủ theo P50 nhưng chưa đủ dự phòng P80; hãy xem cảnh báo trước khi áp dụng.'
            : 'Hãy xem lịch rồi xác nhận.',
      });
    } catch (error) {
      toast({ tone: 'danger', title: 'AI chưa thể phân tích kế hoạch', description: planErrorDescription(error) });
    } finally { setGenerating(false); }
  };

  const analyze = async () => {
    const selected = tasksForHorizon();
    if (selected.length === 0) {
      toast({ tone: 'warning', title: 'Chưa có nhiệm vụ để lập kế hoạch', description: 'LMS chưa có deadline trong 14 ngày tới.' });
      return;
    }
    setLoadingGoals(true);
    try {
      const proposed = await proposeWeeklyGoals(selected);
      setWeeklyGoals(proposed.map((goal) => ({ ...goal, confirmed: true })));
      setGoalDialogOpen(true);
    } catch {
      const fallback = selected.slice(0, 4).map((task, index) => ({
        id: `goal-${index + 1}`,
        title: `Hoàn thành phần cần thiết của ${task.title} trước hạn`,
        taskIds: [task.id],
        confirmed: true,
      }));
      setWeeklyGoals(fallback);
      setGoalDialogOpen(true);
    } finally {
      setLoadingGoals(false);
    }
  };

  useEffect(() => {
    const trigger = searchParams.get('reanalyze');
    if (!trigger || !['reflection', 'lms', 'progress', 'deadline'].includes(trigger)) return;
    // Opening a notification can mount Plan before workspace/LMS hydration.
    // Do not consume the hand-off against an empty task list.
    if (!state.workspaceReady || state.tasks.length === 0 || generating || loadingGoals || saving) return;
    const impactId = searchParams.get('impactId');
    const selected = tasksForHorizon();
    const selectedIds = new Set(selected.map(task => task.id));
    const impactIds = state.planImpacts.filter(impact => impact.id === impactId || (trigger === 'lms'
      && ['deadline_earlier', 'schedule_conflict', 'assignment_added'].includes(impact.kind)
      && impact.taskId && selectedIds.has(impact.taskId))).map(impact => impact.id).sort();
    const requestedTaskId = searchParams.get('taskId');
    const repairTaskIds = Array.from(new Set([
      ...(requestedTaskId && selectedIds.has(requestedTaskId) ? [requestedTaskId] : []),
      ...state.planImpacts.filter(impact => impactIds.includes(impact.id) && impact.taskId && selectedIds.has(impact.taskId))
        .map(impact => impact.taskId as string),
    ])).sort();
    const contextKey = JSON.stringify({ trigger, scope: searchParams.get('scope'), impactIds, taskId: searchParams.get('taskId'), planId: state.plan?.id,
      tasks: selected.map(task => [task.id, task.dueAt ?? task.deadline, task.estimateMin, task.loggedMin]),
      constraints, availability: state.availability, routine: state.routineProfile, preferences: state.studyPreferences,
      calendarDraft: state.calendarDraft?.updatedAt });
    if (reanalysisStarted.current.has(contextKey)) return;
    reanalysisStarted.current.add(contextKey);
    const nextParams = new URLSearchParams(searchParams);
    for (const name of ['reanalyze', 'scope', 'impactId', 'taskId', 'courseId']) nextParams.delete(name);
    setSearchParams(nextParams, { replace: true });
    if (!needsAnalysis && !expiredDraft && state.planDraft?.replan?.contextKey === contextKey) {
      setCalendarSource('draft');
      return;
    }
    const confirmedGoals = weeklyGoals.filter((goal) => goal.confirmed && goal.title.trim());
    const goals = confirmedGoals.length > 0
      ? confirmedGoals
      : selected.map((task, index) => ({
          id: `replan-goal-${index + 1}`,
          title: `Hoàn thành phần cần thiết của ${task.title} trước hạn`,
          taskIds: [task.id],
          confirmed: true,
        }));
    toast({
      tone: 'info',
      title: 'AI đang phân tích lại lịch',
      description: 'PaceWise sẽ tạo bản đề xuất; lịch hiện tại vẫn được giữ cho đến khi bạn áp dụng.',
    });
    void analyzeWithGoals(goals, {
      contextKey,
      impactIds,
      trigger: trigger as 'reflection' | 'lms' | 'progress' | 'deadline',
      scope: searchParams.get('scope') === 'weekly' ? 'weekly' : searchParams.get('scope') === 'activity' ? 'activity' : undefined,
      taskIds: repairTaskIds,
    });
  // One-shot hand-offs share the normal Plan draft/confirmation pipeline.
  // A ref prevents duplicate calls while the query string is being replaced.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, state.workspaceReady, state.tasks, state.planImpacts, generating, loadingGoals, saving]);

  const save = async (openAfterSaveId?: string, partial = false) => {
    if (partial ? !partialConfirmable : !draftConfirmable) return;
    setSaving(true);
    try {
      const confirmed = await confirmPlan(state.planDraft?.createdAt, partial ? partialPreview?.blockIds : undefined);
      dispatch({ type: 'SAVE_PLAN', confirmedDraft: confirmed });
      setPendingBlockId(null);
      setPartialReviewOpen(false); setCalendarSource('applied');
      toast({ tone: partial ? 'warning' : 'success', title: partial ? 'Đã xác nhận phần lịch hợp lệ' : 'Đã áp dụng kế hoạch tuần',
        ...(partial ? { description: 'Phần việc còn thiếu vẫn được giữ. Kế hoạch chưa bảo đảm hoàn thành toàn bộ trước hạn.' } : {}) });
      const block = openAfterSaveId ? confirmed.blocks.find((item) => item.id === openAfterSaveId) : undefined;
      if (block && block.status !== 'tentative' && studyBlockAccess(block).state === 'available') {
        navigate(`/study/${encodeURIComponent(block.taskId)}/session?blockId=${encodeURIComponent(block.id)}`);
      }
    }
    catch (error) { toast({ tone: 'danger', title: 'Chưa thể lưu kế hoạch', description: error instanceof Error ? error.message : 'Bản nháp vẫn được giữ.' }); }
    finally { setSaving(false); }
  };

  const pendingBlock = pendingBlockId ? blocks.find((item) => item.id === pendingBlockId) : undefined;
  const pendingIssue = pendingBlock ? (studyBlockAccess(pendingBlock).state === 'ended' ? 'Ca này đã qua giờ kết thúc. Hãy xếp lại phần việc chưa học; không ghi học mới vào lịch sử.'
    : confirmedBlockIssue(pendingBlock, state.plan?.blocks ?? [], state.tasks, constraints)) : undefined;
  const pendingEligible = Boolean(pendingBlock && partialPreview?.blockIds.includes(pendingBlock.id)
    && pendingBlock.status !== 'tentative' && studyBlockAccess(pendingBlock).state === 'available');
  const pendingExcluded = partialPreview?.excludedBlocks.find(b => b.blockId === pendingBlock?.id);

  return (
    <div className="student-calendar-page calendar-page flex min-h-0 flex-col overflow-hidden bg-canvas" tabIndex={0} aria-label="Cuộn lịch">
      <header className="calendar-toolbar z-30 shrink-0 border-b border-line bg-white px-3 py-2 sm:px-5">
        <div className="calendar-toolbar-title hidden min-w-0 sm:block">
          <h1 className="text-lg font-bold">Plan</h1>
          <p className="text-[11px] text-muted">{calendarView === 'month' ? new Intl.DateTimeFormat('vi-VN', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${monthStart}T00:00:00Z`)) : `${formatDM(weekStart)}–${formatDM(weekEnd)}`} · GMT+7</p>
        </div>
        <div className="calendar-toolbar-views hidden rounded-lg border border-line bg-white p-0.5 sm:inline-flex" role="group" aria-label="Kiểu hiển thị lịch">
          {([['week', 'Tuần'], ['month', 'Tháng'], ['next7', '7 ngày tới']] as const).map(([value, label]) => (
            <button key={value} type="button" aria-pressed={calendarView === value} onClick={() => selectView(value)} className={`min-h-8 rounded-md px-3 text-xs font-semibold ${calendarView === value ? 'bg-primary-light text-primary-ink' : 'text-muted hover:bg-slate-50'}`}>{label}</button>
          ))}
        </div>
        <div className="calendar-toolbar-dates flex min-w-0 items-center gap-1">
        <IconButton icon="chevronLeft" label="Khoảng trước" className="shrink-0" onClick={() => shiftCalendar(-1)} />
        <input type="date" value={anchorDate} onChange={(event) => setAnchorDate(event.target.value || today)} className="h-9 rounded-lg border border-line bg-white px-2 text-xs font-semibold" aria-label="Chọn ngày" />
        <Button size="sm" variant="ghost" title="Hôm nay" className="min-h-9 px-2" onClick={() => setAnchorDate(today)}>Hôm nay</Button>
        <IconButton icon="chevronRight" label="Khoảng sau" className="shrink-0" onClick={() => shiftCalendar(1)} />
        </div>
        <div className="calendar-toolbar-actions flex min-w-0 flex-wrap items-center gap-2">
          <IconButton icon="filter" label="Lọc và hiển thị lịch" onClick={() => setFilterOpen(true)} />
          <ReminderCenter compact />
          {calendarView !== 'month' && <Button size="sm" icon="sparkle" loading={generating || loadingGoals} onClick={() => void analyze()}>{state.planDraft || needsAnalysis ? 'AI phân tích lại' : 'AI lập kế hoạch'}</Button>}
          {calendarView !== 'month' && draftReady && !partialConfirmable && <Button size="sm" icon="check" loading={saving} disabled={!draftConfirmable} onClick={() => void save()}>{state.planDraft?.durationAdjustments?.length ? 'Áp dụng lịch & thời lượng đề xuất' : 'Áp dụng kế hoạch'}</Button>}
          {calendarView !== 'month' && partialConfirmable && <Button size="sm" icon="check" onClick={() => reviewPartial()}>Xác nhận phần lịch hợp lệ</Button>}
        </div>
      </header>

      <div className="calendar-status z-10 shrink-0 border-b border-line bg-white px-4 py-2 sm:px-5">
        {state.plan && (state.planDraft || state.calendarDraft) && <div role="group" aria-label="Nguồn lịch" className="mb-2 flex gap-2">
          <Button size="sm" variant={showingApplied ? 'primary' : 'secondary'} aria-pressed={showingApplied} onClick={() => setCalendarSource('applied')}>Lịch đang dùng</Button>
          <Button size="sm" variant={!showingApplied ? 'primary' : 'secondary'} aria-pressed={!showingApplied} onClick={() => setCalendarSource('draft')}>Xem bản nháp</Button>
        </div>}
        {showingApplied && state.plan?.confirmation?.mode === 'partial' && <p role="status" className="mb-2 text-warning-ink">{expiredAppliedRisk ? 'Kế hoạch đang dùng có deadline đã qua. Phân tích lại phần việc còn hạn; lịch sử học vẫn giữ nguyên.' : `Đang dùng phần lịch đã xác nhận. Còn thiếu ${formatDuration(state.plan.feasibility?.deficitMin ?? 0)}; chưa bảo đảm hoàn thành toàn bộ công việc đúng hạn.`}</p>}
        {!needsAnalysis && state.planDraft && <PlanDraftNotice draft={state.planDraft} tasks={state.tasks} now={now} />}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
          <span className="inline-flex items-center gap-1.5 font-semibold"><Icon name={draftChecked ? 'checkCircle' : 'edit'} size={15} className={draftChecked ? 'text-success-ink' : qualityWarning ? 'text-warning-ink' : 'text-primary-ink'} />{draftReady ? qualityWarning ? 'Bản nháp có cảnh báo · chưa áp dụng' : 'Bản AI đã kiểm tra · chưa áp dụng' : needsAnalysis ? 'Có thay đổi cần AI kiểm tra' : state.plan ? 'Kế hoạch đang áp dụng' : 'Kéo dữ liệu vào lịch để bắt đầu'}</span>
          <span className="text-muted">{shownBlocks.length} ca tự học · {formatDuration(totalMinutes)}</span>
          {draftReady && state.planDraft?.diff && <span className="text-muted" aria-label="Thay đổi so với lịch đã xác nhận">
            Thêm {state.planDraft.diff.added.length} · dời {state.planDraft.diff.moved_block_count ?? state.planDraft.diff.removed.length} · giữ {state.planDraft.diff.unchanged_count} block
            {(state.planDraft.diff.moved_work_minutes ?? 0) > 0 ? ` · ${formatDuration(state.planDraft.diff.moved_work_minutes ?? 0)} bị dời` : ''}
          </span>}
          {expiredDraft ? <span className="font-semibold text-warning-ink">Bản nháp cũ · cần tính lại capacity</span> : state.planDraft && !state.planDraft.feasibility.feasible && <span className="font-semibold text-warning-ink">Thiếu {formatDuration(state.planDraft.feasibility.deficitMin)} capacity</span>}
          {state.planDraft?.feasibility.feasible && state.planDraft.feasibility.robustFeasible === false && <span className="font-semibold text-warning-ink">P80 còn thiếu {formatDuration(robustMissing)}</span>}
          <button type="button" className="ml-auto inline-flex min-h-6 items-center gap-1 text-primary-ink" onClick={() => setLegendOpen(true)}><Icon name="info" size={14} />Chú giải</button>
        </div>
        {needsAnalysis && <p className="mt-1 text-[11px] text-muted" role="status">
          {persistence?.status === 'saved' ? 'Đã lưu nháp · chưa áp dụng.' : persistence?.status === 'error' || persistence?.status === 'conflict'
            ? 'Chưa lưu được nháp; đừng reload. Hãy kiểm tra kết nối.' : 'Đang lưu nháp · lịch đã xác nhận vẫn được giữ.'}
          {persistence?.status === 'error' && <button type="button" className="ml-2 font-semibold text-primary-ink underline" onClick={retrySave}>Thử lưu lại</button>}
        </p>}
        {(courseFilter !== 'all' || !showPersonal) && <p className="mt-1 text-[11px] text-muted">Đang xem: {state.courses.find((course) => course.id === courseFilter)?.code ?? 'tất cả môn'}{!showPersonal ? ' · ẩn lịch cá nhân' : ''}. Bộ lọc không thay đổi kế hoạch.</p>}
      </div>

      <div className="calendar-board-frame min-h-0 flex-1 overflow-hidden p-3 sm:p-4">
        {calendarView === 'month' ? (
          <PlanMonthBoard dates={dates} month={monthStart.slice(0, 7)} items={filteredTimeline} onSelectDate={(date) => { setAnchorDate(date); setCalendarView('week'); }} />
        ) : (
          <PlanCalendarBoard dates={dates} selectedDate={anchorDate} courses={state.courses} tasks={filteredTasks} items={filteredTimeline} draftMode={!generating && !saving} focusUsefulTime={state.workspaceReady} toolsPanel={toolsPanel} onToolsPanelChange={setToolsPanel} routineProfile={state.routineProfile} onMoveBlock={moveBlock} onMoveBusy={moveBusy} onResizeBlock={resizeBlock} onResizeBusy={resizeBusy} onAddBusy={(date, start, category, label) => addPersonalSlot(date, start, category, label)} onOpenPersonal={(category, label) => setPersonalDialog({ category, label })} onOpenRoutine={() => setRoutineDialogOpen(true)} onOpenBlock={openStudyBlock} onOpenItem={openCalendarItem} onRemoveBlock={removeBlock} onRemoveBusy={(id) => savePersonalSchedule(unavailable.filter((slot) => slot.id !== id))} />
        )}
      </div>

      <Modal open={filterOpen} onClose={() => setFilterOpen(false)} title="Lọc và hiển thị lịch">
        <div className="space-y-4">
          <label className="block text-sm font-semibold">Môn học
            <select aria-label="Lọc lịch theo môn học" value={courseFilter} onChange={(event) => setCourseFilter(event.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-line bg-white px-3">
              <option value="all">Tất cả môn</option>{state.courses.map((course) => <option key={course.id} value={course.id}>{course.code} · {course.name}</option>)}
            </select>
          </label>
          <label className="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" checked={showPersonal} onChange={(event) => setShowPersonal(event.target.checked)} />Hiện lịch cá nhân và giờ tự học ưu tiên</label>
          <div role="group" aria-label="Chế độ xem lịch" className="flex flex-wrap gap-2">{([['week', 'Tuần'], ['month', 'Tháng'], ['next7', '7 ngày tới']] as const).map(([value, label]) => <Button key={value} variant={calendarView === value ? 'primary' : 'secondary'} aria-pressed={calendarView === value} onClick={() => selectView(value)}>{label}</Button>)}</div>
          <p className="caption">Các mục ẩn vẫn được kiểm tra xung đột khi xếp lịch.</p>
        </div>
      </Modal>
      <Modal open={legendOpen} onClose={() => setLegendOpen(false)} title="Chú giải lịch học">
        <ul className="space-y-3 text-sm">
          <li className="flex gap-3"><Icon name="calendar" className="shrink-0 text-muted" /><span><strong>Lịch LMS:</strong> buổi học, quiz, deadline; chỉ xem, không kéo sửa.</span></li>
          <li className="flex gap-3"><Icon name="book" className="shrink-0 text-success-ink" /><span><strong>Giờ tự học ưu tiên:</strong> khoảng rảnh cho AI xếp việc, chưa phải nhiệm vụ để bắt đầu Do.</span></li>
          <li className="flex gap-3"><Icon name="play" className="shrink-0 text-primary-ink" /><span><strong>Ca tự học:</strong> có nhiệm vụ và mục tiêu cụ thể; ca đã xác nhận, không xung đột có thể bắt đầu Do.</span></li>
          <li className="flex gap-3"><Icon name="edit" className="shrink-0 text-warning-ink" /><span><strong>Bản nháp:</strong> được lưu riêng; phân tích và xác nhận trước khi áp dụng.</span></li>
        </ul>
      </Modal>
      <StudyBlockDialog
        block={pendingBlock ?? null}
        title={pendingBlock?.milestoneTitle ?? state.tasks.find((task) => task.id === pendingBlock?.taskId)?.title ?? 'Phiên tự học'}
        saved={Boolean(pendingBlock && !pendingIssue)}
        startIssue={pendingExcluded ? `Ca này không hợp lệ: ${[...new Set(pendingExcluded.reasons.map(r => planBlockIssueLabel(r.code)))].join('; ')}. Điều chỉnh hoặc phân tích lại; không được bắt đầu Do.` : pendingIssue}
        draftReady={pendingEligible && (draftConfirmable || partialConfirmable)}
        applyLabel={partialConfirmable ? 'Xem và xác nhận phần lịch hợp lệ' : undefined}
        saving={saving || generating}
        minDate={today}
        maxDate={addDays(calendarWeekStart(today), TASK_SELECTION_HORIZON_DAYS - 1)}
        onClose={() => !saving && setPendingBlockId(null)}
        onSave={updateBlockExactTime}
        onStart={() => pendingBlock && startStudyBlock(pendingBlock.id)}
        onApplyAndStart={() => partialConfirmable ? reviewPartial(pendingBlock?.id) : void save(pendingBlock?.id)}
      />
      <PartialPlanDialog open={partialReviewOpen} draft={state.planDraft} preview={partialPreview} tasks={state.tasks} saving={saving}
        onClose={() => setPartialReviewOpen(false)} onConfirm={() => void save(partialStartId, true)}
        onAdjust={() => { setPartialReviewOpen(false); setToolsPanel('personal'); setCalendarSource('draft'); }} />
      <PersonalSlotDialog
        open={Boolean(personalDialog)}
        category={personalDialog?.category ?? 'other'}
        initialLabel={personalDialog?.label ?? 'Bận khác'}
        initialDate={anchorDate < today ? today : anchorDate}
        minDate={today}
        maxDate={addDays(calendarWeekStart(today), TASK_SELECTION_HORIZON_DAYS - 1)}
        onClose={() => setPersonalDialog(null)}
        onSubmit={(value) => {
          if (addPersonalSlot(value.date, value.start, value.category, value.label, value.end)) setPersonalDialog(null);
        }}
      />
      <PersonalSlotDialog
        open={Boolean(editingPersonalItem)}
        mode="edit"
        category={(editingPersonalItem?.kind === 'personal_self_study' ? 'self_study' : unavailable.find((slot) => slot.id === editingPersonalItem?.entityId)?.category) ?? 'other'}
        initialLabel={editingPersonalItem?.title ?? 'Bận khác'}
        initialDate={editingPersonalItem?.date ?? today}
        initialStart={editingPersonalItem?.start ?? '18:00'}
        initialEnd={editingPersonalItem?.end ?? '19:00'}
        minDate={today}
        maxDate={addDays(calendarWeekStart(today), TASK_SELECTION_HORIZON_DAYS - 1)}
        onClose={() => setEditingPersonalItem(null)}
        onSubmit={(value) => editingPersonalItem?.entityId && updatePersonalSlot(editingPersonalItem.entityId, value)}
      />
      <LmsCalendarNoticeDialog item={lmsNoticeItem} onClose={() => setLmsNoticeItem(null)} />
      <RoutineDialog
        open={routineDialogOpen}
        value={state.routineProfile}
        onClose={() => setRoutineDialogOpen(false)}
        onSave={(profile) => {
          if (generating || saving) return;
          dispatch({ type: 'UPDATE_ROUTINE_PROFILE', profile, draftBlocks: blocks });
          setRoutineDialogOpen(false);
          setCalendarSource('draft');
          toast({ tone: 'success', title: 'Đã lưu giờ sinh hoạt', description: 'Bấm AI phân tích lại để áp dụng nhịp học mới.' });
        }}
      />
      {goalDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" role="dialog" aria-modal="true" aria-labelledby="weekly-goal-title">
          <div className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-line bg-white p-5 shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 id="weekly-goal-title" className="text-lg font-bold">Mục tiêu tuần AI đề xuất</h2>
                <p className="mt-1 text-sm text-muted">Plan Agent đọc assignment, module, rubric và tài liệu bài tập được gắn nguồn. Sửa hoặc bỏ mục tiêu trước khi chia bước và xếp lịch.</p>
              </div>
              <IconButton icon="x" label="Đóng" onClick={() => setGoalDialogOpen(false)} />
            </div>
            <div className="mt-4 space-y-3">
              {weeklyGoals.map((goal) => (
                <div key={goal.id} className="flex items-start gap-3 rounded-xl border border-line p-3">
                  <input type="checkbox" aria-label={`Chọn mục tiêu ${goal.title}`} checked={goal.confirmed} onChange={(event) => setWeeklyGoals((current) => current.map((item) => item.id === goal.id ? { ...item, confirmed: event.target.checked } : item))} className="mt-3" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <input value={goal.title} onChange={(event) => setWeeklyGoals((current) => current.map((item) => item.id === goal.id ? { ...item, title: event.target.value } : item))} className="min-h-10 min-w-0 flex-1 rounded-lg border border-line px-3 text-sm" aria-label="Nội dung mục tiêu tuần" />
                      <span className="rounded-full bg-primary-light px-2 py-1 text-[10px] font-semibold text-primary-ink">{goal.analysisSource === 'model' ? 'AI đề xuất' : 'Fallback an toàn'}</span>
                    </div>
                    {!!goal.rationale && <p className="mt-2 text-xs text-muted">{goal.rationale}</p>}
                    <p className="mt-1 text-[11px] text-muted">Bài liên quan: {goal.taskIds.map((id) => state.tasks.find((task) => task.id === id)?.title ?? id).join('; ')}</p>
                    {!!goal.sourceRefs?.length && <p className="mt-1 text-[11px] text-primary-ink">Có nguồn · {[...new Set(goal.sourceRefs.map((ref) => ref.split(':', 1)[0] === 'rubric' ? 'rubric' : ref.split(':', 1)[0] === 'module' ? 'module/chương' : ref.startsWith('file:') ? 'tài liệu bài tập' : 'assignment'))].join(' · ')}</p>}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setGoalDialogOpen(false)}>Để sau</Button>
              <Button icon="check" onClick={() => {
                const confirmed = weeklyGoals.filter((goal) => goal.confirmed && goal.title.trim()).map((goal) => ({ ...goal, confirmed: true }));
                if (!confirmed.length) { toast({ tone: 'warning', title: 'Hãy chọn ít nhất một mục tiêu tuần' }); return; }
                setWeeklyGoals(confirmed);
                setGoalDialogOpen(false);
                void analyzeWithGoals(confirmed);
              }}>Xác nhận và lập lịch</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
