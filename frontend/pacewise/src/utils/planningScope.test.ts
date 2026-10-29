import { describe, expect, it } from 'vitest';
import type { PlanDraft, StudySession, Task } from '../types';
import { hasExpiredDraftWork, isOpenPlanningTask, remainingTaskMinutes } from './planningScope';

const now = Date.parse('2026-10-10T11:00:00+07:00');
const task = { id: 'a', status: 'todo', deadline: '2026-10-10', dueAt: '2026-10-10T10:45:00+07:00' } as Task;
describe('rolling planning scope', () => {
  it('excludes earlier deadlines today, including the exact due instant', () => {
    expect(isOpenPlanningTask(task, now)).toBe(false);
    expect(isOpenPlanningTask({ ...task, dueAt: '2026-10-10T11:00:00+07:00' }, now)).toBe(false);
    expect(isOpenPlanningTask({ ...task, dueAt: '2026-10-10T11:01:00+07:00' }, now)).toBe(true);
  });
  it('preserves date-only work until local midnight and respects timezone offsets', () => {
    expect(isOpenPlanningTask({ ...task, dueAt: undefined }, now)).toBe(true);
    expect(isOpenPlanningTask({ ...task, dueAt: undefined }, Date.parse('2026-10-10T17:00:00Z'))).toBe(false);
    expect(isOpenPlanningTask({ ...task, dueAt: '2026-10-10T03:45:00Z' }, now)).toBe(false);
  });
  it('never interprets a historical block by itself as stale future work', () => {
    const draft = { blocks: [{ id: 'history', taskId: 'a', status: 'history' }], feasibility: { shortfalls: [] } } as unknown as PlanDraft;
    expect(hasExpiredDraftWork(draft, [task], now)).toBe(false);
    expect(hasExpiredDraftWork({ ...draft, feasibility: { ...draft.feasibility, shortfalls: [{ taskId: 'a', missingMin: 60 }] } }, [task], now)).toBe(true);
    expect(isOpenPlanningTask({ ...task, dueAt: '2026-10-12T11:00:00+07:00', status: 'done' }, now)).toBe(false);
  });
  it('does not re-plan a Do part that was completed early', () => {
    const assignment = { ...task, estimateMin: 120, loggedMin: 7, status: 'in_progress' } as Task;
    const session = { id: 's1', taskId: 'a', blockId: 'b1', date: '2026-10-10', minutes: 7, source: 'timer',
      plannedMin: 70, workResult: 'planned_part_done', remainingMinutes: 0 } as StudySession;
    expect(remainingTaskMinutes(assignment, [session])).toBe(50);
  });
  it('keeps the explicit residual from an unfinished Do part', () => {
    const assignment = { ...task, estimateMin: 120, loggedMin: 20, status: 'in_progress' } as Task;
    const session = { id: 's1', taskId: 'a', blockId: 'b1', date: '2026-10-10', minutes: 20, source: 'timer',
      plannedMin: 60, workResult: 'needs_more_time', remainingMinutes: 25 } as StudySession;
    expect(remainingTaskMinutes(assignment, [session])).toBe(85);
  });
});
