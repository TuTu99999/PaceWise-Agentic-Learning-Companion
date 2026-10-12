import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Course, LMSCourseData, Plan, StudySession, Task } from '../types';
import { buildReflectionActivities, reflectionActivityWindow, reflectionNeedsPlanReview } from './reflectionActivities';

const courses: Course[] = [{ id: '1', code: 'CS101', name: 'Python', tone: 'primary' }];
const tasks: Task[] = [{
  id: '1:10', courseId: '1', title: 'Bài vòng lặp', deadline: '2026-10-05', estimateMin: 60,
  loggedMin: 0, status: 'todo', priority: 'medium', objective: 'Hiểu vòng lặp',
}];
const plan = {
  id: 'p1', weekStart: '2026-09-28', savedAt: '2026-09-28T00:00:00Z', version: 1,
  blocks: [
    { id: 'done', taskId: '1:10', date: '2026-10-02', start: '09:00', end: '10:00', milestoneTitle: 'Ôn vòng lặp' },
    { id: 'future', taskId: '1:10', date: '2026-10-04', start: '20:00', end: '21:00' },
  ],
} as Plan;
const sessions = [{ id: 's1', taskId: '1:10', blockId: 'done', date: '2026-10-02', minutes: 75, source: 'timer', completionPercent: 75 }] as StudySession[];
const courseData = {
  '1': {
    courseId: '1', modules: [], resources: [], plannerItems: [], appointmentGroups: [],
    calendarItems: [
      { id: 'class-1', source_id: 1, type: 'event', course_id: 1, course_code: 'CS101', title: 'Học vòng lặp', starts_at: '2026-10-03T09:00:00+07:00', ends_at: '2026-10-03T10:30:00+07:00', duration_minutes: 90, event_kind: 'class_session', editable: false },
      { id: 'video-1', source_id: 2, type: 'event', course_id: 1, course_code: 'CS101', title: 'Video vòng lặp', starts_at: '2026-10-03T08:00:00+07:00', ends_at: '2026-10-03T08:40:00+07:00', duration_minutes: 40, event_kind: 'lecture_video', editable: false },
    ],
  },
} as Record<string, LMSCourseData>;

describe('buildReflectionActivities', () => {
  afterEach(() => vi.useRealTimers());

  it('uses the current PaceWise clock when deciding which activities have ended', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-11T14:00:00.000Z'));
    const currentPlan = {
      ...plan,
      weekStart: '2026-10-05',
      blocks: [{ id: 'current', taskId: '1:10', date: '2026-10-10', start: '09:00', end: '10:00' }],
    } as Plan;

    const result = buildReflectionActivities({
      plan: currentPlan,
      sessions: [],
      tasks,
      courses,
      courseData: {},
      from: '2026-10-05',
      to: '2026-10-11',
    });

    expect(result).toEqual([expect.objectContaining({ id: 'study:current', missed: true })]);
  });

  it('includes observable learning activities but excludes timetable lessons', () => {
    const result = buildReflectionActivities({ plan, sessions, tasks, courses, courseData, from: '2026-09-28', to: '2026-10-04', today: '2026-10-04', now: '17:00' });
    expect(result.map((item) => item.id)).toEqual(['lms:event:video-1', 'study:done']);
    expect(result.some((item) => item.id === 'lms:event:class-1')).toBe(false);
    expect(result[1]).toMatchObject({ kind: 'review', actualMinutes: 75, completionPercent: 75, missed: false });
  });

  it('includes an ended untracked study block as a missed reflection milestone', () => {
    const result = buildReflectionActivities({ plan, sessions: [], tasks, courses, courseData: {}, from: '2026-09-28', to: '2026-10-04', today: '2026-10-04', now: '17:00' });
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ id: 'study:done', missed: true });
  });

  it('makes a completed Do session reflectable even before its reserved block ends', () => {
    const earlySession = [{ ...sessions[0], id: 's-early', blockId: 'future', date: '2026-10-04' }];
    const result = buildReflectionActivities({ plan, sessions: earlySession, tasks, courses, courseData: {}, from: '2026-09-28', to: '2026-10-04', today: '2026-10-04', now: '17:00' });
    expect(result.some((item) => item.id === 'study:future')).toBe(true);
  });
});

describe('reflectionActivityWindow', () => {
  it('uses the current demo week for an explicit post-session reflection during Monday grace', () => {
    expect(reflectionActivityWindow({
      requestedActivity: true,
      weeklyStart: '2026-09-28',
      weeklyEnd: '2026-10-04',
      today: '2026-10-05',
    })).toEqual({ from: '2026-10-05', to: '2026-10-11' });
  });

  it('keeps the weekly window when no activity is requested', () => {
    expect(reflectionActivityWindow({
      requestedActivity: false,
      weeklyStart: '2026-09-28',
      weeklyEnd: '2026-10-04',
      today: '2026-10-05',
    })).toEqual({ from: '2026-09-28', to: '2026-10-04' });
  });
});

describe('reflectionNeedsPlanReview', () => {
  it('keeps an on-track completed session without creating another draft', () => {
    expect(reflectionNeedsPlanReview('activity', {
      completionPercent: 100,
      blocker: 'none',
      outcome: 'completed',
    })).toBe(false);
  });

  it('requests a plan proposal when the activity is incomplete or blocked', () => {
    expect(reflectionNeedsPlanReview('activity', {
      completionPercent: 60,
      blocker: 'knowledge',
      outcome: 'blocked',
    })).toBe(true);
  });

  it('always reviews the next plan after weekly reflection', () => {
    expect(reflectionNeedsPlanReview('weekly')).toBe(true);
  });
});
