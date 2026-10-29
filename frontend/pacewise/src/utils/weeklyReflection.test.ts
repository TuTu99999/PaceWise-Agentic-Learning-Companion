import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Plan } from '../types';
import { defaultWeeklyReflectionWeekStart, planForReflectionWeek, weeklyReflectionCycle } from './weeklyReflection';

const planWithSundayBlock = (end: string): Plan => ({
  id: 'plan-1',
  weekStart: '2026-09-28',
  savedAt: '2026-10-01T00:00:00Z',
  version: 1,
  blocks: [{ id: 'block-1', taskId: 'task-1', date: '2026-10-04', start: '19:30', end }],
});

describe('weeklyReflectionCycle', () => {
  afterEach(() => vi.useRealTimers());

  it('uses the current PaceWise timezone when no clock override is supplied', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-11T14:00:00.000Z'));

    expect(weeklyReflectionCycle(null)).toMatchObject({
      weekStart: '2026-10-05',
      weekEnd: '2026-10-11',
      isOpen: true,
      isGracePeriod: false,
    });
  });

  it('uses a fixed Monday to Sunday period', () => {
    const cycle = weeklyReflectionCycle(null, '2026-10-03', '12:00');
    expect(cycle).toMatchObject({
      weekStart: '2026-09-28',
      weekEnd: '2026-10-04',
      effectiveWeekStart: '2026-10-05',
      isOpen: false,
    });
  });

  it('opens for the whole of Sunday', () => {
    expect(weeklyReflectionCycle(null, '2026-10-03', '23:59').isOpen).toBe(false);
    expect(weeklyReflectionCycle(null, '2026-10-04', '00:00').isOpen).toBe(true);
  });

  it('does not wait for the final Sunday study block', () => {
    const plan = planWithSundayBlock('21:00');
    expect(weeklyReflectionCycle(plan, '2026-10-04', '08:00').isOpen).toBe(true);
  });

  it('keeps the previous week open until Monday 09:00', () => {
    expect(weeklyReflectionCycle(null, '2026-10-05', '08:59')).toMatchObject({
      weekStart: '2026-09-28',
      weekEnd: '2026-10-04',
      isOpen: true,
      isGracePeriod: true,
    });
    expect(weeklyReflectionCycle(null, '2026-10-05', '09:00')).toMatchObject({
      weekStart: '2026-10-05',
      isOpen: false,
    });
  });

  it('defaults to the calendar week containing the current date', () => {
    expect(defaultWeeklyReflectionWeekStart(null, '2026-10-12', '17:00')).toBe('2026-10-12');
    expect(defaultWeeklyReflectionWeekStart(null, '2026-10-18', '00:00')).toBe('2026-10-12');
  });

  it('marks an explicitly selected finished week as complete', () => {
    expect(weeklyReflectionCycle(null, '2026-10-12', '17:00', '2026-10-05')).toMatchObject({
      weekStart: '2026-10-05',
      weekEnd: '2026-10-11',
      isOpen: true,
      isPastPeriod: true,
      periodComplete: true,
    });
  });

  it('uses the latest matching historical plan for retrospective metrics', () => {
    const older = { ...planWithSundayBlock('20:00'), id: 'old', savedAt: '2026-10-01T00:00:00Z' };
    const newer = { ...older, id: 'new', savedAt: '2026-10-03T00:00:00Z', version: 2 };
    const current = { ...older, id: 'current', weekStart: '2026-10-05', blocks: [] };
    expect(planForReflectionWeek(current, [older, newer], '2026-09-28')?.id).toBe('new');
  });
});
