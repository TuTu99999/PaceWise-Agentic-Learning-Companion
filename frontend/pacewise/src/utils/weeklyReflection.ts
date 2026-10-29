import type { Clock, Plan } from '../types';
import { addDays, calendarWeekStart, currentAppDateTime, toMin, weekdayOf } from './time';

export const WEEKLY_REFLECT_GRACE_END: Clock = '09:00';

export interface WeeklyReflectionCycle {
  weekStart: string;
  weekEnd: string;
  effectiveWeekStart: string;
  isOpen: boolean;
  isGracePeriod: boolean;
  isPastPeriod: boolean;
  periodComplete: boolean;
}

/** Resolve the fixed Monday-Sunday reflection period in Asia/Ho_Chi_Minh UI time. */
export function weeklyReflectionCycle(
  _plan: Plan | null,
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
  const isPastPeriod = weekEnd < resolvedDate;
  const isSelectedGracePeriod = inMondayGrace && weekEnd === addDays(resolvedDate, -1);
  const isSundayWindow = weekday === 6 && resolvedDate === weekEnd;

  return {
    weekStart,
    weekEnd,
    effectiveWeekStart: addDays(weekStart, 7),
    isOpen: isPastPeriod || isSelectedGracePeriod || isSundayWindow,
    isGracePeriod: isSelectedGracePeriod,
    isPastPeriod,
    periodComplete: isPastPeriod || isSelectedGracePeriod || isSundayWindow,
  };
}

/** Reflect opens on the calendar week that contains the requested/current day. */
export function defaultWeeklyReflectionWeekStart(
  _plan: Plan | null,
  date?: string,
  _time?: Clock,
) {
  const current = currentAppDateTime();
  const resolvedDate = date ?? current.date;
  return calendarWeekStart(resolvedDate);
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
