/** One compact hour cell; rendering and interactions share the same minute scale. */
export const CALENDAR_HOUR_HEIGHT = 80;
export const calendarMinuteTop = (minute: number, startHour = 0) => (minute - startHour * 60) * CALENDAR_HOUR_HEIGHT / 60;
export const calendarDurationHeight = (minutes: number) => minutes * CALENDAR_HOUR_HEIGHT / 60;

/** Preserve where the event was grabbed; hour-cell boundaries do not round the time. */
export function calendarDropMinute(clientY: number, columnTop: number, startHour: number, grabOffsetMin = 0) {
  const minute = (clientY - columnTop) * 60 / CALENDAR_HOUR_HEIGHT + startHour * 60 - grabOffsetMin;
  return Math.max(0, Math.min(24 * 60 - 1, Math.round(minute)));
}
