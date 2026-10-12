import { afterEach, describe, expect, it, vi } from 'vitest';
import { generatePlan, proposeWeeklyGoals } from '../src/services/api';
import type { PlanDraft, PlanInput, Task } from '../src/types';

afterEach(() => vi.unstubAllGlobals());

describe('generatePlan', () => {
  it('returns an infeasible draft for review instead of reporting a system failure', async () => {
    const input: PlanInput = {
      goal: 'Protect the nearest deadline',
      weekStart: '2026-09-28',
      tasks: [{ taskId: '1:10', remainingMin: 180 }],
      availability: [{ weekday: 0, enabled: true, start: '18:00', end: '19:00' }],
      unavailable: [],
      preferred: ['evening'],
    };
    const task: Task = {
      id: '1:10',
      courseId: '1',
      title: 'Deadline gần',
      deadline: '2026-09-28',
      estimateMin: 180,
      loggedMin: 0,
      status: 'todo',
      priority: 'high',
      objective: 'Submit on time',
    };
    const draft: PlanDraft = {
      input,
      weekStart: '2026-09-28',
      weekEnd: '2026-10-04',
      blocks: [{ id: 'b1', taskId: task.id, date: '2026-09-28', start: '18:00', end: '19:00' }],
      feasibility: {
        availableMin: 60,
        requiredMin: 180,
        remainingMin: -120,
        feasible: false,
        deficitMin: 120,
        shortfalls: [{ taskId: task.id, missingMin: 120 }],
      },
      reasons: ['Only one hour is available.'],
      assumptions: [],
      createdAt: '2026-09-28T08:00:00+07:00',
    };
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      response: 'Bản nháp còn thiếu thời gian và cần bạn điều chỉnh.',
      workflow: 'plan',
      status: 'awaiting_student',
      source_refs: [],
      output: {
        plan_validation: { valid: false, errors: [{ code: 'DEADLINE_CAPACITY_SHORTFALL' }] },
        plan_draft: draft,
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })));

    await expect(generatePlan(input, [task])).resolves.toMatchObject({
      feasibility: { feasible: false, deficitMin: 120 },
      blocks: [{ id: 'b1' }],
    });
  });

  it('requests weekly goals as a separate student-review stage', async () => {
    const task: Task = {
      id: '1:10',
      courseId: '1',
      title: 'Mini project',
      deadline: '2026-10-06',
      estimateMin: 180,
      loggedMin: 0,
      status: 'todo',
      priority: 'high',
      personalPriority: 4,
      objective: 'Submit on time',
      assignmentGroup: { id: '3', name: 'Project', weight: 55 },
      pointsPossible: 30,
    };
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const request = JSON.parse(String(init?.body));
      expect(request.context.planning_stage).toBe('goal_proposal');
      expect(request.context.goals[0]).toMatchObject({ assignment_group_weight: 55 });
      expect(request.context.goals[0]).not.toHaveProperty('personal_priority');
      return new Response(JSON.stringify({
        response: 'Mục tiêu đề xuất',
        workflow: 'plan',
        status: 'awaiting_student',
        source_refs: [],
        output: {
          plan_validation: { valid: true, errors: [] },
          weekly_goals: [{ id: 'goal-1', title: 'Hoàn thành Mini project', taskIds: ['1:10'], confirmed: false }],
        },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(proposeWeeklyGoals([task])).resolves.toEqual([
      { id: 'goal-1', title: 'Hoàn thành Mini project', taskIds: ['1:10'], confirmed: false },
    ]);
  });
});
