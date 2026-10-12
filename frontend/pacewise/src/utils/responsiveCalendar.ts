/** Keep day columns readable rather than shrinking a seven-day grid indefinitely. */
export function calendarDayCount(width: number | undefined, total: number) {
  if (width === undefined || width >= 840) return total;
  return Math.min(total, width >= 560 ? 3 : width >= 360 ? 2 : 1);
}

export function visibleCalendarDates(dates: string[], selected: string, count: number) {
  const index = Math.max(0, dates.indexOf(selected));
  const start = Math.min(index, Math.max(0, dates.length - count));
  return dates.slice(start, start + count);
}
