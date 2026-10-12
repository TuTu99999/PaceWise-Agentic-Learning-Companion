import type {
  AvailabilityDay,
  TimeBlock,
  UnavailableSlot,
} from '../types';
import {
  DEMO_NOW,
  DEMO_TODAY,
  diffDays,
  toMin,
  weekdayOf,
} from './time';

export interface Interval {
  date: string;
  start: number;
  end: number;
}

function subtract(list: [number, number][], s: number, e: number): [number, number][] {
  const out: [number, number][] = [];
  for (const [a, b] of list) {
    if (e <= a || s >= b) {
      out.push([a, b]);
      continue;
    }
    if (s > a) out.push([a, s]);
    if (e < b) out.push([e, b]);
  }
  return out;
}

/** Free study intervals on a date: availability − unavailable − already planned blocks − past time. */
export function freeIntervals(
  date: string,
  availability: AvailabilityDay[],
  unavailable: UnavailableSlot[],
  taken: TimeBlock[],
  minLength = 1,
): Interval[] {
  const w = weekdayOf(date);
  const day = availability.find((a) => a.weekday === w);
  if (!day || !day.enabled || toMin(day.end) <= toMin(day.start)) return [];
  let list: [number, number][] = [[toMin(day.start), toMin(day.end)]];
  for (const u of unavailable.filter((x) => x.weekday === w)) list = subtract(list, toMin(u.start), toMin(u.end));
  for (const b of taken.filter((x) => x.date === date)) list = subtract(list, toMin(b.start), toMin(b.end));
  if (date === DEMO_TODAY) list = subtract(list, 0, toMin(DEMO_NOW));
  if (diffDays(DEMO_TODAY, date) < 0) return [];
  return list.filter(([a, b]) => b - a >= minLength).map(([start, end]) => ({ date, start, end }));
}

export function validateBlockEdit(
  block: TimeBlock,
  others: TimeBlock[],
  availability: AvailabilityDay[],
): { error?: string; warning?: string } {
  const s = toMin(block.start);
  const e = toMin(block.end);
  if (!block.start || !block.end) return { error: 'Nhập đủ giờ bắt đầu và kết thúc.' };
  if (e <= s) return { error: 'Giờ kết thúc phải sau giờ bắt đầu.' };
  const clash = others.find((o) => o.id !== block.id && o.date === block.date && toMin(o.start) < e && s < toMin(o.end));
  if (clash) return { error: `Khung giờ này trùng với buổi ${clash.start}–${clash.end}.` };
  const day = availability.find((a) => a.weekday === weekdayOf(block.date));
  if (!day?.enabled || s < toMin(day.start) || e > toMin(day.end)) {
    return { warning: 'Khung giờ này nằm ngoài thời gian rảnh bạn đã khai báo.' };
  }
  return {};
}
