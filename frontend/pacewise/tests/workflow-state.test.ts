import { describe, expect, it } from 'vitest';

import { initialState, reducer } from '../src/store/AppStore';
import type { Task, PlanDraft, PlanImpact } from '../src/types';
import { addDays, DEMO_TODAY, weekdayOf } from '../src/utils/time';

const task = (overrides: Partial<Task> = {}): Task => ({
  id: '1:10',
  courseId: '1',
  title: 'Assignment',
  deadline: '2026-10-10',
  estimateMin: 60,
  loggedMin: 0,
  status: 'todo',
  priority: 'medium',
  objective: 'Test persistence',
  ...overrides,
});

describe('durable learner workflow state', () => {
  it.each([true, false])('retires an addressed LMS impact only after confirming a fully feasible plan (%s)', feasible => {
    const impact: PlanImpact = { id: 'lms-change', kind: 'assignment_added', title: '', message: '',
      taskId: '1:10', deficitMin: 60, affectedBlockIds: [], detectedAt: '' };
    const draft: PlanDraft = { createdAt: 'canonical-draft', input: { goal: '', tasks: [],
      availability: [], unavailable: [], preferred: 'evening' }, reasons: [], assumptions: [],
      blocks: [{ id: 'b1', taskId: '1:10', date: '2026-10-10', start: '16:00', end: '17:00' }],
      feasibility: { feasible, availableMin: 60, requiredMin: 60, remainingMin: 0, deficitMin: feasible ? 0 : 60, shortfalls: [] },
      replan: { contextKey: 'lms-snapshot', impactIds: [impact.id] } };
    const before = { ...initialState, tasks: [task()], planDraft: draft, planImpacts: [impact] };
    expect(reducer(before, { type: 'SET_DRAFT', draft }).planImpacts).toEqual([impact]);
    // A different canonical confirmation cannot claim this draft's hand-off.
    expect(reducer(before, { type: 'SAVE_PLAN', confirmedDraft: { ...draft, createdAt: 'other-draft' } }).planImpacts).toEqual([impact]);
    const changed = reducer(before, { type: 'SAVE_PLAN', confirmedDraft: { ...draft, replan: undefined } });
    expect(changed.planImpacts).toEqual(feasible ? [] : [impact]);
  });
  it('round-trips personal schedule slots through workspace hydration after reload', () => {
    const date = '2026-10-06';
    const personalSlots = [
      { id: 'meal-1', label: 'Ăn tối', date, weekday: weekdayOf(date), start: '18:00', end: '18:45', source: 'manual' as const, category: 'meal' as const },
      { id: 'sleep-1', label: 'Ngủ', date, weekday: weekdayOf(date), start: '23:00', end: '24:00', source: 'manual' as const, category: 'sleep' as const },
    ];

    const saved = reducer(initialState, {
      type: 'SAVE_AVAILABILITY',
      availability: initialState.availability,
      unavailable: personalSlots,
    });
    const reloaded = reducer(initialState, {
      type: 'HYDRATE_WORKSPACE',
      state: { unavailable: saved.unavailable },
    });

    expect(reloaded.unavailable).toEqual(personalSlots);
    expect(reloaded.workspaceReady).toBe(true);
  });

  it('reapplies saved progress to a fresh LMS task snapshot', () => {
    const hydrated = reducer(initialState, {
      type: 'HYDRATE_WORKSPACE',
      state: {
        taskProgress: {
          '1:10': {
            estimateMin: 120,
            loggedMin: 45,
            status: 'in_progress',
            updatedAt: '2026-10-02T08:00:00Z',
          },
        },
      },
    });

    const synced = reducer(hydrated, { type: 'SYNC_CANVAS', tasks: [task()] });

    expect(synced.tasks[0]).toMatchObject({
      estimateMin: 120,
      loggedMin: 45,
      status: 'in_progress',
    });
  });

  it('keeps reflections isolated by course and calendar week', () => {
    const first = reducer(initialState, {
      type: 'SAVE_REFLECTION',
      courseId: '1',
      weekStart: '2026-09-28',
      effectiveWeekStart: '2026-10-05',
      answers: ['A', 'B', 'C'],
    });
    const second = reducer(first, {
      type: 'SAVE_REFLECTION',
      courseId: '2',
      weekStart: '2026-09-28',
      effectiveWeekStart: '2026-10-05',
      answers: ['D', 'E', 'F'],
    });

    expect(second.reflections['1:2026-09-28'].answers).toEqual(['A', 'B', 'C']);
    expect(second.reflections['2:2026-09-28'].answers).toEqual(['D', 'E', 'F']);
  });

  it('carries a completed Do result into activity and weekly reflection state', () => {
    const withTask = { ...initialState, tasks: [task()] };
    const running = reducer(withTask, { type: 'START_SESSION', taskId: '1:10' });
    const completed = reducer(running, {
      type: 'COMPLETE_SESSION',
      minutes: 75,
      blockId: 'block-1',
      plannedMin: 60,
      evaluation: {
        action: 'complete', status: 'needs_more_time', block_id: 'block-1', task_id: '1:10',
        planned_minutes: 60, actual_minutes: 75, variance_minutes: 15, completion_percent: 50,
        remaining_minutes: 30, blocker: 'knowledge', blocker_note: 'Chưa hiểu phần khó',
        needs_recovery: true, needs_understanding_check: true, next_action: 'Kiểm tra nhanh.',
      },
    });
    const withActivityReflect = reducer(completed, {
      type: 'SAVE_REFLECTION', reflectionKey: 'activity:study:block-1', scope: 'activity',
      courseId: '1', weekStart: '2026-09-28', activityId: 'study:block-1', activityTitle: 'Assignment',
      activityKind: 'self_study', answers: ['Đã hiểu cơ bản', 'Vướng phần khó', 'Ôn lại ví dụ'],
    });
    const withWeeklyReflect = reducer(withActivityReflect, {
      type: 'SAVE_REFLECTION', reflectionKey: 'all:2026-09-28', scope: 'weekly',
      courseId: 'all', weekStart: '2026-09-28', effectiveWeekStart: '2026-10-05',
      answers: ['Đã học 75 phút', 'Estimate thấp', 'Tăng thời lượng'],
    });

    expect(completed.sessions[0]).toMatchObject({
      blockId: 'block-1', plannedMin: 60, minutes: 75, completionPercent: 50,
      blocker: 'knowledge', needsRecovery: true,
    });
    expect(withWeeklyReflect.reflections['activity:study:block-1']).toMatchObject({ scope: 'activity', activityKind: 'self_study' });
    expect(withWeeklyReflect.reflections['all:2026-09-28']).toMatchObject({ scope: 'weekly', effectiveWeekStart: '2026-10-05' });
  });

  it('applies the teacher resolution returned by synchronization', () => {
    const state = {
      ...initialState,
      quickChecks: [{
        id: 'qc-1',
        topic: 'Regression',
        question: 'Explain overfitting',
        answer: 'Answer',
        evidenceState: 'abstained' as const,
        confidence: 'low' as const,
        feedback: 'Waiting for review',
        submittedAt: '08:00',
        reviewItemId: 'AR-1',
      }],
    };

    const synced = reducer(state, {
      type: 'SYNC_CANVAS',
      tasks: [],
      reviewResolutions: {
        'AR-1': {
          status: 'edited',
          note: 'Đã đối chiếu bằng chứng.',
          resolvedStatus: 'thể hiện hiểu biết',
        },
      },
    });

    expect(synced.quickChecks[0]).toMatchObject({
      evidenceState: 'demonstrated',
      instructorNote: 'Đã đối chiếu bằng chứng.',
    });
  });

  it('creates a reviewable impact only when a later LMS snapshot changes the plan', () => {
    const baselineTask = task({ deadline: addDays(DEMO_TODAY, 5) });
    const stateWithPlan = {
      ...initialState,
      plan: {
        id: 'plan-1',
        weekStart: DEMO_TODAY,
        savedAt: '',
        version: 1,
        blocks: [{ id: 'block-1', taskId: baselineTask.id, date: addDays(DEMO_TODAY, 4), start: '18:00', end: '19:00' }],
      },
    };
    const baseline = reducer(stateWithPlan, { type: 'SYNC_CANVAS', tasks: [baselineTask], courseData: {} });
    expect(baseline.planImpacts).toEqual([]);

    const changed = reducer(baseline, {
      type: 'SYNC_CANVAS',
      tasks: [task({ deadline: addDays(DEMO_TODAY, 1) })],
      courseData: {},
    });
    expect(changed.planImpacts[0]).toMatchObject({
      kind: 'deadline_earlier',
      taskId: baselineTask.id,
      affectedBlockIds: ['block-1'],
    });
    expect(changed.plan?.blocks).toHaveLength(1);
  });

  it('reconciles legacy DS201 milestone titles with the current LMS assignment title', () => {
    const oldTask = task({ title: 'BTVN 2026 T10.1: Làm sạch dữ liệu' });
    const currentTask = task({ title: 'BTVN 2026 T10.1: 3.1 Khái niệm quan hệ hai ngôi và tính chất' });
    const synced = reducer({
      ...initialState,
      tasks: [oldTask],
      plan: {
        id: 'plan-ds201',
        weekStart: '2026-10-05',
        savedAt: '',
        version: 1,
        blocks: [{
          id: 'block-ds201',
          taskId: oldTask.id,
          date: '2026-10-07',
          start: '20:10',
          end: '21:30',
          milestoneTitle: 'Thực hiện bản nháp: BTVN 2026 T10.1: Làm sạch dữ liệu',
        }],
      },
    }, {
      type: 'SYNC_CANVAS',
      tasks: [currentTask],
      courseData: {},
    });

    expect(synced.plan?.blocks[0].milestoneTitle).toBe(
      'Thực hiện bản nháp: BTVN 2026 T10.1: 3.1 Khái niệm quan hệ hai ngôi và tính chất',
    );
  });

  it('detects an LMS deadline change against the persisted baseline after reopening', () => {
    const baselineTask = task({ deadline: addDays(DEMO_TODAY, 5) });
    const hydrated = reducer({
      ...initialState,
      plan: {
        id: 'plan-1',
        weekStart: DEMO_TODAY,
        savedAt: '',
        version: 1,
        blocks: [{ id: 'block-1', taskId: baselineTask.id, date: addDays(DEMO_TODAY, 4), start: '18:00', end: '19:00' }],
      },
    }, {
      type: 'HYDRATE_WORKSPACE',
      state: {
        lmsBaseline: { tasks: [baselineTask], courseData: {}, syncedAt: '2026-10-01T08:00:00Z' },
      },
    });

    const changed = reducer(hydrated, {
      type: 'SYNC_CANVAS',
      tasks: [task({ deadline: addDays(DEMO_TODAY, 1) })],
      courseData: {},
    });

    expect(changed.planImpacts[0]).toMatchObject({ kind: 'deadline_earlier', taskId: baselineTask.id });
    expect(changed.lmsBaseline?.tasks[0].deadline).toBe(addDays(DEMO_TODAY, 1));
  });

  it('keeps the plan unchanged when new personal busy time creates a conflict', () => {
    const date = addDays(DEMO_TODAY, 1);
    const currentTask = task({ deadline: addDays(DEMO_TODAY, 4) });
    const state = {
      ...initialState,
      tasks: [currentTask],
      plan: {
        id: 'plan-1',
        weekStart: DEMO_TODAY,
        savedAt: '',
        version: 1,
        blocks: [{ id: 'block-1', taskId: currentTask.id, date, start: '18:00', end: '19:00' }],
      },
    };

    const changed = reducer(state, {
      type: 'SAVE_AVAILABILITY',
      availability: state.availability,
      unavailable: [{ id: 'busy-1', label: 'Có việc đột xuất', date, weekday: weekdayOf(date), start: '18:30', end: '20:00', source: 'manual' }],
    });

    expect(changed.plan?.blocks).toEqual(state.plan.blocks);
    expect(changed.planImpacts[0]).toMatchObject({
      kind: 'schedule_conflict',
      taskId: currentTask.id,
      affectedBlockIds: ['block-1'],
    });
  });

  it('keeps confirmed plan/history and creates a reviewable impact when LMS removes a task', () => {
    const currentTask = task();
    const removedTask = task({ id: 't-draft', title: 'Removed assignment' });
    const synced = reducer({
      ...initialState,
      tasks: [currentTask, removedTask],
      plan: {
        id: 'legacy-plan',
        weekStart: '2026-09-28',
        savedAt: '',
        version: 1,
        blocks: [
          { id: 'legacy', taskId: 't-draft', date: '2026-10-01', start: '18:00', end: '19:00' },
          { id: 'current', taskId: currentTask.id, date: '2026-10-02', start: '18:00', end: '19:00' },
        ],
      },
      sessions: [
        { id: 'legacy', taskId: 't-quiz', date: '2026-10-01', minutes: 60, source: 'manual' },
        { id: 'current', taskId: currentTask.id, date: '2026-10-02', minutes: 30, source: 'manual' },
      ],
      taskProgress: {
        't-draft': { estimateMin: 60, loggedMin: 0, status: 'todo', updatedAt: '' },
      },
    }, {
      type: 'SYNC_CANVAS',
      tasks: [currentTask],
      courseData: {},
    });

    expect(synced.plan?.blocks.map((block) => block.id)).toEqual(['legacy', 'current']);
    expect(synced.sessions.map((session) => session.id)).toEqual(['legacy', 'current']);
    expect(Object.keys(synced.taskProgress)).toEqual([currentTask.id]);
    expect(synced.planImpacts).toContainEqual(expect.objectContaining({
      kind: 'assignment_removed',
      taskId: removedTask.id,
      affectedBlockIds: ['legacy'],
    }));
  });

  it('refreshes pilot metrics immediately after confirming a plan', () => {
    const currentTask = task();
    const next = reducer({
      ...initialState,
      tasks: [currentTask],
      planDraft: {
        input: {
          goal: 'Finish assignment',
          weekStart: '2026-10-05',
          tasks: [{ taskId: currentTask.id, remainingMin: 60 }],
          availability: initialState.availability,
          unavailable: [],
          preferred: ['evening'],
        },
        blocks: [
          { id: 'block', taskId: currentTask.id, date: '2026-10-06', start: '18:00', end: '19:00' },
        ],
        milestones: [],
        feasibility: {
          availableMin: 420,
          requiredMin: 60,
          remainingMin: 360,
          feasible: true,
          deficitMin: 0,
          shortfalls: [],
        },
        reasons: [],
        assumptions: [],
        createdAt: '2026-10-03T08:00:00Z',
        weekStart: '2026-10-05',
      },
    }, { type: 'SAVE_PLAN' });

    expect(next.pilotMetricsHistory[0].planCoverageRate).toBe(1);
    expect(next.pilotMetricsHistory[0].plannedDeadlineCount).toBe(1);
  });

  it('confirms a partial plan so capacity shortfalls can enter Progress and Recover', () => {
    const currentTask = task({ estimateMin: 120 });
    const next = reducer({
      ...initialState,
      tasks: [currentTask],
      planDraft: {
        input: {
          goal: 'Protect the nearest deadline',
          weekStart: '2026-10-05',
          tasks: [{ taskId: currentTask.id, remainingMin: 120 }],
          availability: initialState.availability,
          unavailable: [],
          preferred: ['evening'],
        },
        blocks: [
          { id: 'partial-block', taskId: currentTask.id, date: '2026-10-06', start: '18:00', end: '19:00' },
        ],
        milestones: [],
        feasibility: {
          availableMin: 60,
          requiredMin: 120,
          remainingMin: 0,
          feasible: false,
          deficitMin: 60,
          shortfalls: [{ taskId: currentTask.id, missingMin: 60 }],
        },
        reasons: [],
        assumptions: [],
        createdAt: '2026-10-03T08:00:00Z',
        weekStart: '2026-10-05',
      },
    }, { type: 'SAVE_PLAN' });

    expect(next.plan?.blocks).toHaveLength(1);
    expect(next.planDraft).toBeNull();
    expect(next.pilotMetricsHistory[0].planCoverageRate).toBe(1);
  });

  it('binds recovery options to their drift context for the two-week diff route', () => {
    const options = [{
      id: 'A',
      title: 'Protect nearest deadline',
      summary: 'Move one study block',
      changes: ['Move block'],
      impact: 'Deadline remains protected',
      time: 'This week',
      tradeoff: 'Less buffer',
      newBlocks: [],
      fullyRecovers: true,
    }];

    const cached = reducer(initialState, {
      type: 'SET_RECOVERY_OPTIONS',
      options,
      key: 'drift:1:10:60:plan-1',
    });

    expect(cached.recoveryOptions).toEqual(options);
    expect(cached.recoveryOptionsKey).toBe('drift:1:10:60:plan-1');
  });

  it('commits only the current week and keeps next-week recovery blocks provisional', () => {
    const weekStart = '2026-09-28';
    const current = { id: 'current', taskId: task().id, date: '2026-10-02', start: '18:00', end: '19:00' };
    const nextWeek = { id: 'next', taskId: task().id, date: '2026-10-06', start: '18:00', end: '19:00' };
    const recovered = reducer({
      ...initialState,
      tasks: [task()],
      plan: { id: 'plan-1', weekStart, savedAt: '', version: 1, blocks: [current] },
    }, {
      type: 'APPLY_RECOVERY',
      blocks: [current, nextWeek],
    });

    expect(recovered.plan?.blocks).toEqual([current]);
    expect(recovered.provisionalBlocks).toEqual([nextWeek]);
    expect(recovered.plan?.version).toBe(2);
  });
});
