import type { AvailabilityDay, Drift, Plan, StudySession, Task, TimeBlock, UnavailableSlot } from '../types';
import { DEMO_NOW, DEMO_TODAY, PLANNING_WINDOW_DAYS, WEEK_START, addDays, daysUntil, diffDays, durationMin, formatDuration, isPast, toMin, weekdayOf } from './time';
import { slotOverlapsBlock } from './lmsPlanning';

const DRIFT_THRESHOLD_MIN = 60;

export const remainingOf = (t: Task) => Math.max(0, t.estimateMin - t.loggedMin);

export function sortBlocks(blocks: TimeBlock[]) {
  return [...blocks].sort((a, b) => diffDays(b.date, a.date) || toMin(a.start) - toMin(b.start));
}

/** Tasks whose logged time is well below what the saved plan expected by now. */
export function detectDrift(
  plan: Plan | null,
  tasks: Task[],
  availability: AvailabilityDay[] = [],
  unavailable: UnavailableSlot[] = [],
): Drift[] {
  if (!plan) return detectCapacityWithoutPlan(tasks, availability, unavailable);
  const out: Drift[] = [];
  for (const t of tasks) {
    if (t.status === 'done') continue;
    const mine = plan.blocks.filter((b) => b.taskId === t.id);
    const valid = mine.filter((block) => !unavailable.some((slot) => slotOverlapsBlock(block, slot)));
    const deadlineDistance = daysUntil(t.deadline);
    if (!mine.length && (deadlineDistance < 0 || deadlineDistance >= PLANNING_WINDOW_DAYS)) continue;
    const expected = valid.filter((b) => isPast(b.date, b.end)).reduce((s, b) => s + durationMin(b.start, b.end), 0);
    const futurePlanned = valid
      .filter((b) => !isPast(b.date, b.end) && b.date <= t.deadline)
      .reduce((s, b) => s + durationMin(b.start, b.end), 0);
    const behind = expected - t.loggedMin;
    const shortfall = remainingOf(t) - futurePlanned;
    const missedProgress = behind >= DRIFT_THRESHOLD_MIN;
    const capacityGap = deadlineDistance >= 0 && deadlineDistance < PLANNING_WINDOW_DAYS && shortfall > 0;
    if (shortfall > 0 && (missedProgress || capacityGap)) {
      out.push({
        taskId: t.id,
        courseId: t.courseId,
        kind: missedProgress ? 'missed_progress' : 'capacity_gap',
        expectedMin: expected,
        loggedMin: t.loggedMin,
        deficitMin: shortfall,
        deadline: t.deadline,
      });
    }
  }
  return out.sort((a, b) => a.deadline.localeCompare(b.deadline) || b.deficitMin - a.deficitMin);
}

function availableUntil(deadline: string, availability: AvailabilityDay[], unavailable: UnavailableSlot[]) {
  const limit = Math.min(PLANNING_WINDOW_DAYS - 1, Math.max(0, daysUntil(deadline)));
  let total = 0;
  for (let offset = 0; offset <= limit; offset += 1) {
    const date = addDays(DEMO_TODAY, offset);
    const weekday = weekdayOf(date);
    const window = availability.find((item) => item.weekday === weekday && item.enabled);
    if (!window) continue;
    let minutes = Math.max(0, toMin(window.end) - toMin(window.start));
    unavailable.filter((slot) => slot.weekday === weekday && (!slot.date || slot.date === date)).forEach((slot) => {
      const overlap = Math.max(0, Math.min(toMin(window.end), toMin(slot.end)) - Math.max(toMin(window.start), toMin(slot.start)));
      minutes -= overlap;
    });
    total += Math.max(0, minutes);
  }
  return total;
}

function detectCapacityWithoutPlan(tasks: Task[], availability: AvailabilityDay[], unavailable: UnavailableSlot[]) {
  if (!availability.length) return [];
  const upcoming = tasks
    .filter((task) => task.status !== 'done' && daysUntil(task.deadline) >= 0 && daysUntil(task.deadline) < PLANNING_WINDOW_DAYS)
    .sort((left, right) => left.deadline.localeCompare(right.deadline));
  const risks: Drift[] = [];
  let cumulativeRequired = 0;
  upcoming.forEach((task) => {
    cumulativeRequired += remainingOf(task);
    const deficit = cumulativeRequired - availableUntil(task.deadline, availability, unavailable);
    if (deficit > 0) {
      risks.push({ taskId: task.id, courseId: task.courseId, kind: 'capacity_gap', expectedMin: 0, loggedMin: task.loggedMin, deficitMin: deficit, deadline: task.deadline });
    }
  });
  return risks;
}

export interface NextAction {
  task: Task;
  block: TimeBlock;
  reason: string;
}

export function nextAction(plan: Plan | null, tasks: Task[], drifts: Drift[]): NextAction | null {
  if (!plan) return null;
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const upcoming = sortBlocks(plan.blocks).find((b) => {
    const t = byId.get(b.taskId);
    return t && t.status !== 'done' && !isPast(b.date, b.end);
  });
  if (!upcoming) return null;
  const task = byId.get(upcoming.taskId)!;
  const d = daysUntil(task.deadline);
  const first = d <= 0 ? 'Deadline là hôm nay' : `Deadline còn ${d} ngày`;
  const drift = drifts.find((x) => x.taskId === task.id);
  let second: string;
  if (task.loggedMin === 0) second = 'bạn chưa có phiên học nào cho task này';
  else if (drift) second = `task này đang trễ khoảng ${formatDuration(drift.deficitMin)} so với kế hoạch`;
  else second = `còn khoảng ${formatDuration(remainingOf(task))} cần hoàn thành`;
  return { task, block: upcoming, reason: `${first} và ${second}.` };
}

export function isInWeek(date: string, weekStart = WEEK_START) {
  const d = diffDays(weekStart, date);
  return d >= 0 && d <= 6;
}

export function weekStats(
  tasks: Task[],
  sessions: StudySession[],
  plan: Plan | null,
  weekStart = plan?.weekStart ?? WEEK_START,
) {
  const weekBlocks = plan?.blocks.filter((block) => isInWeek(block.date, weekStart)) ?? [];
  const plannedTaskIds = new Set(weekBlocks.map((block) => block.taskId));
  const weekTasks = tasks.filter((t) => isInWeek(t.deadline, weekStart) || plannedTaskIds.has(t.id));
  const done = weekTasks.filter((t) => t.status === 'done').length;
  const weekSessions = sessions.filter((s) => isInWeek(s.date, weekStart));
  const studiedMin = weekSessions.reduce((s, x) => s + x.minutes, 0);
  const plannedMin = weekBlocks.reduce((s, b) => s + durationMin(b.start, b.end), 0);
  const plannedUntilNow = weekBlocks
    .filter((b) => isPast(b.date, b.end))
    .reduce((s, b) => s + durationMin(b.start, b.end), 0);
  return {
    total: weekTasks.length,
    done,
    remaining: weekTasks.length - done,
    sessionCount: weekSessions.length,
    studiedMin,
    plannedMin,
    plannedUntilNow,
  };
}

export const todayLabel = () => ({ date: DEMO_TODAY, time: DEMO_NOW, tomorrow: addDays(DEMO_TODAY, 1) });
