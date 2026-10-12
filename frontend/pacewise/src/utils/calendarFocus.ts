import type { PlanTimelineItem } from './planTimeline';
import { toMin } from './time';

/** Preserve sleep blocks, but initially reveal a learning activity rather than midnight. */
export function calendarFocusMinute(items: PlanTimelineItem[], dates: string[], today: string, nowMinute: number) {
  const activities = items.filter((item) => dates.includes(item.date) && item.source !== 'busy' && item.durationMin > 0)
    .sort((left, right) => left.date.localeCompare(right.date) || left.start.localeCompare(right.start));
  const next = activities.find((item) => item.date > today || (item.date === today && toMin(item.end ?? item.start) > nowMinute));
  const chosen = next ?? activities[0];
  return Math.max(0, Math.min(23 * 60, (chosen ? toMin(chosen.start) : dates.includes(today) ? nowMinute : 8 * 60) - 30));
}
