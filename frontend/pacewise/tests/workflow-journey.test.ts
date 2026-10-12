import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  assessUnderstanding,
  confirmPlan,
  confirmRecovery,
  confirmReflection,
  createReflection,
  evaluateDoSession,
  generatePlan,
  generateRecoveryOptions,
  prepareDoSession,
  saveInstructorAction,
  trackProgress,
} from '../src/services/api';
import type { AssessmentItem, Plan, PlanInput, Task } from '../src/types';

const jsonResponse = (payload: unknown) => Promise.resolve(new Response(JSON.stringify(payload), {
  status: 200,
  headers: { 'Content-Type': 'application/json' },
}));

const agentResponse = (workflow: string, extra: Record<string, unknown> = {}) => ({
  response: `${workflow} completed`,
  workflow,
  status: 'completed',
  source_refs: [],
  ...extra,
});

describe('Plan → Do → Check → Recover → Reflect → teacher review', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('uses the authenticated backend contract for the complete role journey', async () => {
    const input: PlanInput = {
      goal: 'Hoàn thành bài đúng hạn',
      tasks: [{ taskId: '1:10', remainingMin: 60 }],
      availability: [{ weekday: 4, enabled: true, start: '08:00', end: '10:00' }],
      unavailable: [],
      preferred: 'morning',
    };
    const task: Task = {
      id: '1:10',
      courseId: '1',
      title: 'Assignment',
      deadline: '2026-10-09',
      estimateMin: 60,
      loggedMin: 0,
      status: 'todo',
      priority: 'high',
      objective: 'Understand the topic',
    };
    const block = { id: 'b-1', taskId: task.id, date: '2026-10-02', start: '08:00', end: '09:00' } as const;
    const plan: Plan = { id: 'p-1', weekStart: '2026-09-28', blocks: [block], savedAt: '2026-10-02T08:00:00Z', version: 1 };
    const assessment: AssessmentItem = {
      id: 'Q-10',
      topic: 'Topic',
      question: 'Explain the concept',
      rubric: ['Correct concept', 'Clear reasoning'],
      status: 'approved',
      version: 3,
    };
    const calls: RequestInit[] = [];
    const responses = [
      { id: 'ia-1', createdAt: '2026-10-02T07:00:00Z', payload: { status: 'approved', version: 3 } },
      agentResponse('plan', {
        output: {
          plan_validation: { valid: true, errors: [] },
          plan_draft: {
            input,
            blocks: [block],
            feasibility: { availableMin: 120, requiredMin: 60, remainingMin: 60, feasible: true, deficitMin: 0, shortfalls: [] },
            reasons: [],
            assumptions: [],
            createdAt: '2026-10-02T08:00:00Z',
          },
        },
      }),
      agentResponse('plan', { output: { confirmed_plan: {
        input, blocks: [block], reasons: [], assumptions: [], createdAt: '2026-10-02T08:00:00Z',
        feasibility: { availableMin: 120, requiredMin: 60, remainingMin: 60, feasible: true, deficitMin: 0, shortfalls: [] },
      } } }),
      {
        action: 'prepare', status: 'ready', block_id: block.id, task_id: task.id, title: task.title,
        objective: task.objective, planned_minutes: 60, recommended_resources: [], opening_prompt: 'Bắt đầu học.',
      },
      agentResponse('do', { output: { do_session: {
        action: 'complete', status: 'needs_more_time', block_id: block.id, task_id: task.id,
        planned_minutes: 60, actual_minutes: 70, variance_minutes: 10, completion_percent: 50,
        remaining_minutes: 30, blocker: 'knowledge', blocker_note: 'Chưa hiểu phần khó', needs_recovery: true,
        needs_understanding_check: true, next_action: 'Kiểm tra nhanh rồi Recover.',
      } } }),
      agentResponse('tracking', { progress_metrics: { completion: 0.5 }, risk_signals: [] }),
      agentResponse('understanding', {
        status: 'awaiting_teacher',
        review_case_id: 'AR-journey',
        assessment_result: { status: 'đang hình thành', confidence: 'thấp', rubric_version: 3 },
      }),
      agentResponse('recover', {
        recovery_options: [{
          id: 'A', title: 'Move block', summary: 'Protect deadline', changes: [], impact: '', time: '1 giờ', tradeoff: '',
          new_blocks: [block], assumptions: [], fully_recovers: true,
        }],
      }),
      agentResponse('recover'),
      agentResponse('reflect', { reflection_draft: { scope: 'activity', next_step: 'Review the difficult concept' } }),
      agentResponse('reflect'),
      agentResponse('reflect', { reflection_draft: { scope: 'weekly', adjustment: 'Start earlier' } }),
      agentResponse('reflect'),
      { id: 'ia-2', createdAt: '2026-10-02T09:00:00Z', payload: { status: 'edited' } },
    ];
    vi.stubGlobal('fetch', vi.fn((_url: string | URL | Request, init?: RequestInit) => {
      calls.push(init ?? {});
      return jsonResponse(responses.shift());
    }));

    await saveInstructorAction('assessment', assessment.id, { status: 'approved', rubric: assessment.rubric });
    await generatePlan(input, [task]);
    await confirmPlan();
    const prepared = await prepareDoSession({
      courseId: task.courseId, blockId: block.id,
    });
    const doEvaluation = await evaluateDoSession({
      courseId: task.courseId, blockId: block.id, taskId: task.id, plannedMinutes: 60,
      actualMinutes: 70, completionPercent: 50, blocker: 'knowledge', blockerNote: 'Chưa hiểu phần khó',
    });
    await trackProgress(plan, input.availability, []);
    const check = await assessUnderstanding(assessment, 'Student answer');
    const recovery = await generateRecoveryOptions(plan, [task], {
      taskId: task.id, expectedMin: 60, loggedMin: 0, deficitMin: 60, deadline: task.deadline,
    }, input.availability, []);
    await confirmRecovery(recovery[0].id);
    await createReflection(
      ['Understood the basics', 'Difficult concept', 'Review the concept'],
      { reflection_scope: 'activity', activity: { id: `study:${block.id}`, task_id: task.id } },
    );
    await confirmReflection('activity');
    await createReflection(['Worked', 'Started late', 'Start earlier'], { reflection_scope: 'weekly', completion: 0.5 });
    await confirmReflection();
    await saveInstructorAction('review', check.reviewCaseId!, {
      status: 'edited',
      note: 'Teacher verified evidence',
      edited_result: { status: 'thể hiện hiểu biết' },
    });

    const bodies = calls.map((call) => JSON.parse(String(call.body)) as Record<string, unknown>);
    expect(bodies.filter((body) => body.workflow).map((body) => body.workflow)).toEqual([
      'plan', 'plan', 'do', 'tracking', 'understanding', 'recover', 'recover',
      'reflect', 'reflect', 'reflect', 'reflect',
    ]);
    expect(prepared).toMatchObject({ action: 'prepare', block_id: block.id });
    expect(bodies[3]).toEqual({ courseId: 1, blockId: block.id });
    expect(doEvaluation).toMatchObject({ status: 'needs_more_time', needs_recovery: true, needs_understanding_check: true });
    expect(check).toMatchObject({
      evidenceState: 'abstained',
      requiresInstructorReview: true,
      reviewCaseId: 'AR-journey',
      rubricVersion: 3,
    });
    expect(bodies.at(-1)).toMatchObject({
      actionType: 'review',
      entityId: 'AR-journey',
      payload: { status: 'edited' },
    });
  });
});
