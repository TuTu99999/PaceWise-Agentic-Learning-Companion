import { describe, expect, it } from 'vitest';
import { calendarDayCount, visibleCalendarDates } from './responsiveCalendar';

const dates = ['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-10', '2026-10-11'];
describe('responsive calendar windows', () => {
  it.each([[294, 1], [359, 1], [360, 2], [559, 2], [560, 3], [839, 3], [840, 7], [1400, 7]])('fits %i pixels into %i readable days', (width, count) => {
    expect(calendarDayCount(width, 7)).toBe(count);
  });
  it('does not add nonexistent days for shorter date ranges', () => {
    expect(calendarDayCount(1400, 1)).toBe(1);
    expect(calendarDayCount(600, 2)).toBe(2);
  });
  it('keeps the selected date visible including Sunday and across month boundaries', () => {
    expect(visibleCalendarDates(dates, dates[4], 2)).toEqual(dates.slice(4, 6));
    expect(visibleCalendarDates(dates, dates[6], 2)).toEqual(dates.slice(5, 7));
    expect(visibleCalendarDates(['2026-10-31', '2026-11-01'], '2026-11-01', 1)).toEqual(['2026-11-01']);
  });
  it('falls back to the beginning when changing weeks and never mutates the input', () => {
    expect(visibleCalendarDates(dates, '2026-09-01', 3)).toEqual(dates.slice(0, 3));
    expect(dates).toHaveLength(7);
  });
});
