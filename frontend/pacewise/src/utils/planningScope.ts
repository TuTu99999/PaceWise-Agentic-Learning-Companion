import type { PlanDraft, Task } from '../types';
import { addDays } from './time';

export function taskDeadlineTimestamp(task: Task): number {
  if (!task.dueAt) return Date.parse(`${addDays(task.deadline, 1)}T00:00:00+07:00`);
  return Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(task.dueAt) ? task.dueAt : `${task.dueAt}+07:00`);
}

export const isExpiredTask = (task: Task, now = Date.now()) => taskDeadlineTimestamp(task) <= now;
export const isOpenPlanningTask = (task: Task, now = Date.now()) => task.status !== 'done' && taskDeadlineTimestamp(task) > now;

/** Old cached capacity cannot be relabelled feasible after hiding its expired work. */
export function hasExpiredDraftWork(draft: PlanDraft | null | undefined, tasks: Task[], now = Date.now()): boolean {
  if (!draft) return false;
  const ids = new Set(tasks.filter(t => isExpiredTask(t, now)).map(t => t.id));
  return draft.feasibility.shortfalls.some(s => ids.has(s.taskId))
    || draft.blocks.some(b => b.status !== 'history' && ids.has(b.taskId))
    || Boolean(draft.planningTargets?.some(t => ids.has(t.taskId)));
}
