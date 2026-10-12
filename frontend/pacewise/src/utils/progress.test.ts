import { describe, expect, it } from 'vitest';
import type { AvailabilityDay, Plan, StudySession, Task, TimeBlock } from '../types';
import { addDays, DEMO_TODAY, weekdayOf } from './time';
import { detectDrift, weekStats } from './progress';

const task = (overrides: Partial<Task> = {}): Task => ({
  id: 'task-1',
  title: 'Deadline gần',
  courseId: 'course-1',
  deadline: addDays(DEMO_TODAY, 2),
  estimateMin: 120,
  loggedMin: 0,
  status: 'todo',
  priority: 'high',
  objective: 'Hoàn thành trước deadline',
  ...overrides,
});

const plan = (blocks: TimeBlock[]): Plan => ({
  id: 'plan-1',
  weekStart: DEMO_TODAY,
  blocks,
  savedAt: new Date().toISOString(),
  version: 1,
});

describe('detectDrift', () => {
  it('warns before the deadline when future blocks do not cover remaining work', () => {
    const risks = detectDrift(plan([
      { id: 'block-1', taskId: 'task-1', date: addDays(DEMO_TODAY, 1), start: '19:00', end: '20:00' },
    ]), [task()]);

    expect(risks).toEqual([
      expect.objectContaining({
        taskId: 'task-1',
        courseId: 'course-1',
        kind: 'capacity_gap',
        deficitMin: 60,
      }),
    ]);
  });

  it('detects a missed study block as progress drift', () => {
    const risks = detectDrift(plan([
      { id: 'block-1', taskId: 'task-1', date: addDays(DEMO_TODAY, -1), start: '18:00', end: '19:30' },
    ]), [task()]);

    expect(risks[0]).toEqual(expect.objectContaining({
      kind: 'missed_progress',
      expectedMin: 90,
      loggedMin: 0,
    }));
  });

  it('does not warn when future blocks fully cover remaining work', () => {
    const risks = detectDrift(plan([
      { id: 'block-1', taskId: 'task-1', date: addDays(DEMO_TODAY, 1), start: '18:00', end: '19:00' },
      { id: 'block-2', taskId: 'task-1', date: addDays(DEMO_TODAY, 2), start: '18:00', end: '19:00' },
    ]), [task()]);

    expect(risks).toHaveLength(0);
  });

  it('does not count a study block covered by new busy time as usable capacity', () => {
    const date = addDays(DEMO_TODAY, 1);
    const risks = detectDrift(plan([
      { id: 'block-1', taskId: 'task-1', date, start: '18:00', end: '20:00' },
    ]), [task()], [], [{
      id: 'busy-1',
      label: 'Có việc đột xuất',
      date,
      weekday: weekdayOf(date),
      start: '18:30',
      end: '19:00',
      source: 'manual',
    }]);

    expect(risks).toContainEqual(expect.objectContaining({
      taskId: 'task-1',
      kind: 'capacity_gap',
      deficitMin: 120,
    }));
  });

  it('flags an unplanned near deadline but ignores an unplanned distant task', () => {
    const risks = detectDrift(plan([]), [
      task(),
      task({ id: 'task-far', deadline: addDays(DEMO_TODAY, 10) }),
    ]);

    expect(risks.map((risk) => risk.taskId)).toEqual(['task-1']);
  });

  it('warns about cumulative capacity before a plan exists', () => {
    const availability: AvailabilityDay[] = [
      { weekday: 0, enabled: true, start: '18:00', end: '19:00' },
      { weekday: 1, enabled: true, start: '18:00', end: '19:00' },
      { weekday: 2, enabled: true, start: '18:00', end: '19:00' },
      { weekday: 3, enabled: true, start: '18:00', end: '19:00' },
      { weekday: 4, enabled: true, start: '18:00', end: '19:00' },
      { weekday: 5, enabled: true, start: '18:00', end: '19:00' },
      { weekday: 6, enabled: true, start: '18:00', end: '19:00' },
    ];
    const risks = detectDrift(null, [
      task({ id: 'a', deadline: addDays(DEMO_TODAY, 1), estimateMin: 180 }),
      task({ id: 'b', deadline: addDays(DEMO_TODAY, 1), estimateMin: 180 }),
    ], availability, []);
    expect(risks[risks.length - 1]).toEqual(expect.objectContaining({ taskId: 'b', kind: 'capacity_gap', deficitMin: 240 }));
  });
});

describe('weekStats', () => {
  it('counts only activity inside the requested Monday-Sunday week', () => {
    const weekStart = '2026-09-28';
    const sessions: StudySession[] = [
      { id: 'in-week', taskId: 'task-1', date: '2026-10-04', minutes: 60, source: 'manual' },
      { id: 'next-week', taskId: 'task-1', date: '2026-10-05', minutes: 90, source: 'manual' },
    ];
    const weeklyPlan = plan([
      { id: 'in-week', taskId: 'task-1', date: '2026-10-04', start: '18:00', end: '19:00' },
      { id: 'next-week', taskId: 'task-1', date: '2026-10-05', start: '18:00', end: '19:30' },
    ]);

    const stats = weekStats([task({ deadline: '2026-10-04' })], sessions, weeklyPlan, weekStart);

    expect(stats.studiedMin).toBe(60);
    expect(stats.plannedMin).toBe(60);
  });

  it('uses the saved plan week when no explicit week is provided', () => {
    const weeklyPlan: Plan = {
      ...plan([]),
      weekStart: '2026-10-05',
      blocks: [
        { id: 'next-week', taskId: 'task-1', date: '2026-10-06', start: '18:00', end: '19:30' },
      ],
    };

    const stats = weekStats(
      [task({ deadline: '2026-10-06' })],
      [{ id: 'session', taskId: 'task-1', date: '2026-10-06', minutes: 45, source: 'manual' }],
      weeklyPlan,
    );

    expect(stats.plannedMin).toBe(90);
    expect(stats.studiedMin).toBe(45);
  });
});
