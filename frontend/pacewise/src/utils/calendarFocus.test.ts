import { describe, expect, it } from 'vitest';
import { calendarFocusMinute } from './calendarFocus';
import type { PlanTimelineItem } from './planTimeline';
const item = (patch: Partial<PlanTimelineItem> = {}): PlanTimelineItem => ({ id: 'lesson', date: '2026-10-10',
  source: 'lms', start: '09:00', end: '10:00', title: 'Bài học', durationMin: 60, kind: 'class', kindLabel: 'Lớp', readOnly: true, ...patch });
describe('useful initial calendar position', () => {
  it('skips sleep and ended learning sessions, focusing the next useful hour', () => {
    expect(calendarFocusMinute([item({ source: 'busy', start: '00:00', end: '07:00' }), item(), item({ start: '19:00', end: '20:00' })], ['2026-10-10'], '2026-10-10', 12 * 60)).toBe(18 * 60 + 30);
  });
  it('falls back to current time without hiding overnight activities', () => {
    const items = [item({ source: 'busy', start: '00:00', end: '07:00' })];
    expect(calendarFocusMinute(items, ['2026-10-10'], '2026-10-10', 14 * 60)).toBe(13 * 60 + 30);
    expect(items).toHaveLength(1);
  });
  it('uses a useful hour in another week and clamps near midnight', () => {
    expect(calendarFocusMinute([], ['2026-10-12'], '2026-10-10', 20 * 60)).toBe(7 * 60 + 30);
    expect(calendarFocusMinute([item({ start: '00:10' })], ['2026-10-10'], '2026-10-10', 0)).toBe(0);
  });
});
