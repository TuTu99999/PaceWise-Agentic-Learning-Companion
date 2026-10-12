import { describe, expect, it } from 'vitest';

import { buildCourseScope } from '../src/hooks/useDerived';
import type { Plan, StudySession, Task } from '../src/types';

const task = (id: string, courseId: string): Task => ({
  id,
  courseId,
  title: id,
  deadline: '2026-10-02',
  estimateMin: 60,
  loggedMin: 0,
  status: 'todo',
  priority: 'medium',
  objective: 'Test',
});

describe('course-scoped PaceWise data', () => {
  it('keeps only tasks, sessions and plan blocks of the selected course', () => {
    const tasks = [task('cs-task', '1'), task('ds-task', '2')];
    const sessions: StudySession[] = [
      { id: 's1', taskId: 'cs-task', date: '2026-10-01', minutes: 30, source: 'timer' },
      { id: 's2', taskId: 'ds-task', date: '2026-10-01', minutes: 45, source: 'manual' },
    ];
    const plan: Plan = {
      id: 'plan-1',
      weekStart: '2026-09-28',
      savedAt: '2026-09-28T00:00:00Z',
      version: 1,
      blocks: [
        { id: 'b1', taskId: 'cs-task', date: '2026-10-01', start: '08:00', end: '09:00' },
        { id: 'b2', taskId: 'ds-task', date: '2026-10-01', start: '09:00', end: '10:00' },
      ],
    };

    const result = buildCourseScope('2', tasks, sessions, plan);

    expect(result.activeTasks.map((item) => item.id)).toEqual(['ds-task']);
    expect(result.activeSessions.map((item) => item.id)).toEqual(['s2']);
    expect(result.activePlan?.blocks.map((item) => item.id)).toEqual(['b2']);
  });

  it('preserves the aggregate view when no course is selected', () => {
    const tasks = [task('cs-task', '1'), task('ds-task', '2')];
    const result = buildCourseScope(undefined, tasks, [], null);

    expect(result.activeTasks).toEqual(tasks);
  });
});
