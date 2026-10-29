import type { Clock, Weekday } from '../types';

export const APP_TIMEZONE = 'Asia/Ho_Chi_Minh';
/** Fixed pilot clock keeps the demo at the start of a complete learning week. */
export const DEMO_TODAY = '2026-10-05';
export const DEMO_NOW: Clock = '08:00';
export const PLANNING_WINDOW_DAYS = 7;
export const TASK_SELECTION_HORIZON_DAYS = 14;
/** Rolling planning window shared with the backend scheduler: today + six days. */
export const PLANNING_WINDOW_START = DEMO_TODAY;
export const TIMEZONE_LABEL = APP_TIMEZONE;

const APP_DATE_TIME_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: APP_TIMEZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

/** Current wall-clock date and time in PaceWise's configured timezone. */
export function currentAppDateTime(value = new Date()): { date: string; time: Clock } {
  const parts = Object.fromEntries(
    APP_DATE_TIME_FORMATTER
      .formatToParts(value)
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour}:${parts.minute}`,
  };
}

const WEEKDAY_LONG = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật'];
const WEEKDAY_SHORT = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];

export const toMin = (c: Clock) => {
  const [h, m] = c.split(':').map(Number);
  return h * 60 + m;
};
export const toClock = (min: number): Clock => {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
};
export const durationMin = (start: Clock, end: Clock) => toMin(end) - toMin(start);

function parse(date: string) {
  const [y, m, d] = date.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}
export function addDays(date: string, n: number) {
  const d = parse(date);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
export function diffDays(a: string, b: string) {
  return Math.round((parse(b).getTime() - parse(a).getTime()) / 86400000);
}
/** 0 = Monday */
export function weekdayOf(date: string): Weekday {
  return ((parse(date).getUTCDay() + 6) % 7) as Weekday;
}
/** Monday of the calendar week containing `date`. */
export const calendarWeekStart = (date: string) => addDays(date, -weekdayOf(date));
export const WEEK_START = calendarWeekStart(DEMO_TODAY);
export const NEXT_WEEK_START = addDays(WEEK_START, 7);
export const weekDates = (weekStart = PLANNING_WINDOW_START) => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));

export const weekdayName = (w: Weekday) => WEEKDAY_LONG[w];
export const weekdayShort = (w: Weekday) => WEEKDAY_SHORT[w];

export function formatDM(date: string) {
  const [, m, d] = date.split('-');
  return `${d}/${m}`;
}
export function formatDay(date: string, opts: { relative?: boolean; short?: boolean } = {}) {
  if (opts.relative) {
    const delta = diffDays(DEMO_TODAY, date);
    if (delta === 0) return 'Hôm nay';
    if (delta === 1) return 'Ngày mai';
    if (delta === -1) return 'Hôm qua';
  }
  const w = weekdayOf(date);
  return `${opts.short ? WEEKDAY_SHORT[w] : WEEKDAY_LONG[w]} ${formatDM(date)}`;
}
export const formatRange = (start: Clock, end: Clock) => `${start}–${end}`;
export const formatDeadline = (date: string) => `${formatDay(date)}, 23:59`;

export function formatDuration(min: number, locale: 'vi' | 'en' = 'vi') {
  const sign = min < 0 ? '−' : '';
  const v = Math.abs(Math.round(min));
  const h = Math.floor(v / 60);
  const m = v % 60;
  if (locale === 'en') {
    const hours = `${h} ${h === 1 ? 'hour' : 'hours'}`;
    const minutes = `${m} ${m === 1 ? 'minute' : 'minutes'}`;
    if (h === 0) return `${sign}${minutes}`;
    if (m === 0) return `${sign}${hours}`;
    return `${sign}${hours} ${minutes}`;
  }
  if (h === 0) return `${sign}${m} phút`;
  if (m === 0) return `${sign}${h} giờ`;
  return `${sign}${h} giờ ${m} phút`;
}
export const formatHours = (min: number) => {
  const h = Math.round((min / 60) * 10) / 10;
  return `${String(h).replace('.', ',')} giờ`;
};

export function daysUntil(date: string) {
  return diffDays(DEMO_TODAY, date);
}

/** Return whether the supplied date/time has passed in the user's local clock. */
export function isPast(date: string, clock: Clock) {
  const d = diffDays(DEMO_TODAY, date);
  if (d < 0) return true;
  if (d > 0) return false;
  return toMin(clock) <= toMin(DEMO_NOW);
}

export function formatTimer(ms: number) {
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((x) => String(x).padStart(2, '0')).join(':');
}

export function nowStamp() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export const uid = (prefix = 'id') => `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
