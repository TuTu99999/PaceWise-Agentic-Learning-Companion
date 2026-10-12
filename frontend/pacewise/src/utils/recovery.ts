import type { DiffItem, TimeBlock } from '../types';
import { diffDays } from './time';

/** Presentation-only diff. Recovery decisions and schedule patches come from the backend agent. */
export function diffBlocks(before: TimeBlock[], after: TimeBlock[]): DiffItem[] {
  const out: DiffItem[] = [];
  const afterById = new Map(after.map((block) => [block.id, block]));
  const beforeIds = new Set(before.map((block) => block.id));
  for (const block of before) {
    const next = afterById.get(block.id);
    const snapshot = { date: block.date, start: block.start, end: block.end };
    if (!next) out.push({ type: 'removed', taskId: block.taskId, before: snapshot });
    else if (next.date !== block.date || next.start !== block.start || next.end !== block.end) {
      out.push({
        type: 'moved',
        taskId: block.taskId,
        before: snapshot,
        after: { date: next.date, start: next.start, end: next.end },
      });
    } else out.push({ type: 'unchanged', taskId: block.taskId, before: snapshot, after: snapshot });
  }
  for (const block of after) {
    if (!beforeIds.has(block.id)) {
      out.push({ type: 'added', taskId: block.taskId, after: { date: block.date, start: block.start, end: block.end } });
    }
  }
  const key = (item: DiffItem) => (item.after ?? item.before)!;
  return out.sort((left, right) => diffDays(key(right).date, key(left).date) || key(left).start.localeCompare(key(right).start));
}
