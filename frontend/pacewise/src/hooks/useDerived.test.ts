import { describe, expect, it } from 'vitest';
import type { Plan, StudySession, Task } from '../types';
import { buildCourseScope } from './useDerived';

const tasks: Task[] = [
  { id: 'a', title: 'A', courseId: 'c1', deadline: '2026-10-05', estimateMin: 60, loggedMin: 0, status: 'todo', priority: 'high', objective: '' },
  { id: 'b', title: 'B', courseId: 'c2', deadline: '2026-10-06', estimateMin: 60, loggedMin: 0, status: 'todo', priority: 'medium', objective: '' },
];
const sessions: StudySession[] = [
  { id: 's1', taskId: 'a', minutes: 20, date: '2026-10-02', source: 'manual' },
  { id: 's2', taskId: 'b', minutes: 30, date: '2026-10-02', source: 'manual' },
];
const plan: Plan = {
  id: 'p1',
  weekStart: '2026-10-02',
  savedAt: '2026-10-02T08:00:00+07:00',
  version: 1,
  blocks: [
    { id: 'ba', taskId: 'a', date: '2026-10-03', start: '18:00', end: '19:00' },
    { id: 'bb', taskId: 'b', date: '2026-10-04', start: '18:00', end: '19:00' },
  ],
};

describe('buildCourseScope', () => {
  it('returns the complete cross-course view when no course filter is selected', () => {
    const scope = buildCourseScope(undefined, tasks, sessions, plan);

    expect(scope.activeTasks).toHaveLength(2);
    expect(scope.activeSessions).toHaveLength(2);
    expect(scope.activePlan?.blocks).toHaveLength(2);
  });

  it('filters tasks, sessions and plan blocks together for one course', () => {
    const scope = buildCourseScope('c1', tasks, sessions, plan);

    expect(scope.activeTasks.map((item) => item.id)).toEqual(['a']);
    expect(scope.activeSessions.map((item) => item.id)).toEqual(['s1']);
    expect(scope.activePlan?.blocks.map((item) => item.id)).toEqual(['ba']);
  });
});
