import { describe, expect, it } from 'vitest';
import type { PlanDraft, Task } from '../types';
import { hasExpiredDraftWork, isOpenPlanningTask } from './planningScope';

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
});
