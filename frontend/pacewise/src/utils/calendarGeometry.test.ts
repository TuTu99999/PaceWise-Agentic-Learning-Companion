import { describe, expect, it } from 'vitest';
import { CALENDAR_HOUR_HEIGHT, calendarMinuteTop, calendarDurationHeight, calendarDropMinute } from './calendarGeometry';
describe('hourly calendar geometry', () => {
  it('maps every minute consistently across rendering and drop coordinates', () => {
    expect(CALENDAR_HOUR_HEIGHT).toBe(80);
    for (let minute = 0; minute < 24 * 60; minute++) {
      const top = calendarMinuteTop(minute);
      expect(top).toBeCloseTo(minute * 80 / 60);
      expect(calendarDropMinute(top + 100, 100, 0)).toBe(minute);
    }
  });
  it.each([1, 7, 15, 25, 30, 60, 66, 90, 125])('preserves the true duration of %i minutes', (minutes) => {
    expect(calendarDurationHeight(minutes)).toBeCloseTo(minutes * 80 / 60);
  });
  it('accounts for a hidden morning range, scrolling, and the exact grabbed position', () => {
    const minute = 19 * 60 + 7;
    const columnTop = -800;
    const grabOffsetMin = 17;
    const clientY = columnTop + calendarMinuteTop(minute + grabOffsetMin, 7);
    expect(calendarDropMinute(clientY, columnTop, 7, grabOffsetMin)).toBe(minute);
  });
  it('clamps outside-grid drops and rounds to one minute, not five or thirty', () => {
    expect(calendarDropMinute(-10, 0, 0)).toBe(0);
    expect(calendarDropMinute(4000, 0, 0)).toBe(1439);
    expect(calendarDropMinute(19 * 80 + 7.3 * 80 / 60, 0, 0)).toBe(19 * 60 + 7);
  });
});
