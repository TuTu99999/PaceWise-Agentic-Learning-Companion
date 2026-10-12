import type { Clock, Plan } from '../types';
import { addDays, calendarWeekStart, currentAppDateTime, toMin, weekdayOf } from './time';

export const WEEKLY_REFLECT_DEFAULT_OPEN: Clock = '20:00';
export const WEEKLY_REFLECT_GRACE_END: Clock = '09:00';

export interface WeeklyReflectionCycle {
  weekStart: string;
  weekEnd: string;
  effectiveWeekStart: string;
  opensAt: Clock;
  isOpen: boolean;
  isGracePeriod: boolean;
  isPastPeriod: boolean;
  periodComplete: boolean;
}

function latestSundayBlockEnd(plan: Plan | null, sunday: string): Clock | null {
  const ends = (plan?.blocks ?? [])
    .filter((block) => block.date === sunday)
    .map((block) => block.end)
    .sort((left, right) => toMin(right) - toMin(left));
  return ends[0] ?? null;
}

/** Resolve the fixed Monday-Sunday reflection period in Asia/Ho_Chi_Minh UI time. */
export function weeklyReflectionCycle(
  plan: Plan | null,
  date?: string,
  time?: Clock,
  selectedWeekStart?: string,
): WeeklyReflectionCycle {
  const current = currentAppDateTime();
  const resolvedDate = date ?? current.date;
  const resolvedTime = time ?? current.time;
  const weekday = weekdayOf(resolvedDate);
  const inMondayGrace = weekday === 0 && toMin(resolvedTime) < toMin(WEEKLY_REFLECT_GRACE_END);
  const automaticWeekStart = inMondayGrace ? addDays(calendarWeekStart(resolvedDate), -7) : calendarWeekStart(resolvedDate);
  const weekStart = selectedWeekStart ?? automaticWeekStart;
  const weekEnd = addDays(weekStart, 6);
  const lastBlockEnd = latestSundayBlockEnd(plan, weekEnd);
  const opensAt = lastBlockEnd && toMin(lastBlockEnd) > toMin(WEEKLY_REFLECT_DEFAULT_OPEN)
    ? lastBlockEnd
    : WEEKLY_REFLECT_DEFAULT_OPEN;
  const isPastPeriod = weekEnd < resolvedDate;
  const isSelectedGracePeriod = inMondayGrace && weekEnd === addDays(resolvedDate, -1);
  const isSundayWindow = weekday === 6 && resolvedDate === weekEnd && toMin(resolvedTime) >= toMin(opensAt);

  return {
    weekStart,
    weekEnd,
    effectiveWeekStart: addDays(weekStart, 7),
    opensAt,
    isOpen: isPastPeriod || isSelectedGracePeriod || isSundayWindow,
    isGracePeriod: isSelectedGracePeriod,
    isPastPeriod,
    periodComplete: isPastPeriod || isSelectedGracePeriod || isSundayWindow,
  };
}

/**
 * Reflect is retrospective by default. Before the current week's official
 * Sunday window opens, show the week that has actually finished instead of a
 * mostly-empty future plan. The learner can still opt into the current week.
 */
export function defaultWeeklyReflectionWeekStart(
  plan: Plan | null,
  date?: string,
  time?: Clock,
) {
  const current = currentAppDateTime();
  const resolvedDate = date ?? current.date;
  const resolvedTime = time ?? current.time;
  const automatic = weeklyReflectionCycle(plan, resolvedDate, resolvedTime);
  if (automatic.isOpen) return automatic.weekStart;
  return addDays(calendarWeekStart(resolvedDate), -7);
}

/** Return the newest saved plan snapshot that belongs to a reflection week. */
export function planForReflectionWeek(
  currentPlan: Plan | null,
  history: Plan[],
  weekStart: string,
) {
  const candidates = [currentPlan, ...history]
    .filter((plan): plan is Plan => Boolean(plan))
    .filter((plan) => plan.weekStart === weekStart || plan.blocks.some((block) => (
      block.date >= weekStart && block.date <= addDays(weekStart, 6)
    )))
    .sort((left, right) => (
      right.savedAt.localeCompare(left.savedAt) || right.version - left.version
    ));
  return candidates[0] ?? null;
}
