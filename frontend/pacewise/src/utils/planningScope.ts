import type { PlanDraft, StudySession, Task } from '../types';
import { addDays } from './time';

export function taskDeadlineTimestamp(task: Task): number {
  if (!task.dueAt) return Date.parse(`${addDays(task.deadline, 1)}T00:00:00+07:00`);
  return Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(task.dueAt) ? task.dueAt : `${task.dueAt}+07:00`);
}

export const isExpiredTask = (task: Task, now = Date.now()) => taskDeadlineTimestamp(task) <= now;
export const isOpenPlanningTask = (task: Task, now = Date.now()) => task.status !== 'done' && taskDeadlineTimestamp(task) > now;

/** Reconcile remaining work from structured Do outcomes, not timer minutes. */
export function remainingTaskMinutes(task: Task, sessions: StudySession[]): number {
  if (task.status === 'done') return 0;
  const latestByBlock = new Map<string, StudySession>();
  sessions.forEach((session) => {
    if (session.taskId === task.id && session.blockId && session.workResult) {
      const current = latestByBlock.get(session.blockId);
      const currentAt = Date.parse(current?.completedAt ?? '');
      const candidateAt = Date.parse(session.completedAt ?? '');
      if (!current || (Number.isFinite(candidateAt) && (!Number.isFinite(currentAt) || candidateAt > currentAt))) {
        latestByBlock.set(session.blockId, session);
      }
    }
  });
  const structured = [...latestByBlock.values()];
  if (structured.length === 0) return Math.max(0, task.estimateMin - task.loggedMin);
  const structuredActual = structured.reduce((total, session) => total + Math.max(0, session.minutes), 0);
  const unstructuredCredit = Math.max(0, task.loggedMin - structuredActual);
  const structuredCredit = structured.reduce((total, session) => {
    const planned = Math.max(0, session.plannedMin ?? session.minutes);
    if (session.workResult === 'planned_part_done') return total + planned;
    return total + planned - Math.max(0, session.remainingMinutes ?? planned);
  }, 0);
  return Math.max(0, task.estimateMin - unstructuredCredit - structuredCredit);
}

/** Old cached capacity cannot be relabelled feasible after hiding its expired work. */
export function hasExpiredDraftWork(draft: PlanDraft | null | undefined, tasks: Task[], now = Date.now()): boolean {
  if (!draft) return false;
  const ids = new Set(tasks.filter(t => isExpiredTask(t, now)).map(t => t.id));
  return draft.feasibility.shortfalls.some(s => ids.has(s.taskId))
    || draft.blocks.some(b => b.status !== 'history' && ids.has(b.taskId))
    || Boolean(draft.planningTargets?.some(t => ids.has(t.taskId)));
}
