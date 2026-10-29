import { describe, expect, it } from 'vitest';
import type { LMSCalendarItem, LMSCourseData, Plan, Task } from '../types';
import { initialState, reducer } from '../store/AppStore';
import { addDays, DEMO_TODAY, weekdayOf } from './time';
import { detectAvailabilityPlanImpacts, detectLmsPlanImpacts, lmsUnavailableSlots } from './lmsPlanning';

const course = (items: LMSCalendarItem[]): Record<string, LMSCourseData> => ({
  c1: { courseId: 'c1', modules: [], resources: [], plannerItems: [], appointmentGroups: [], calendarItems: items },
});
const event = (id: string, date: string, start = '19:00', end = '20:00'): LMSCalendarItem => ({
  id,
  source_id: 1,
  type: 'event',
  course_id: 1,
  course_code: 'CS101',
  title: 'Buổi học online',
  starts_at: `${date}T${start}:00+07:00`,
  ends_at: `${date}T${end}:00+07:00`,
  duration_minutes: 60,
  event_kind: 'class_session',
  editable: false,
});
const task = (deadline = addDays(DEMO_TODAY, 5)): Task => ({ id: 't1', title: 'Project', courseId: 'c1', deadline, estimateMin: 120, loggedMin: 0, status: 'todo', priority: 'high', objective: '' });
const plan = (date = addDays(DEMO_TODAY, 1)): Plan => ({ id: 'p1', weekStart: DEMO_TODAY, savedAt: '', version: 1, blocks: [{ id: 'b1', taskId: 't1', date, start: '19:00', end: '20:00' }] });

describe('LMS planning constraints', () => {
  it('keeps the first empty sync as a baseline and detects the learner first course later', () => {
    const next = reducer({
      ...initialState,
      workspaceReady: true,
      lmsBaseline: { tasks: [], courseData: {}, syncedAt: '2026-10-01T00:00:00.000Z' },
    }, {
      type: 'SYNC_CANVAS',
      courses: [{ id: 'c2', code: 'DB201', name: 'Cơ sở dữ liệu', tone: 'primary' }],
      tasks: [],
      courseData: {
        c2: { courseId: 'c2', modules: [], resources: [], plannerItems: [], appointmentGroups: [], calendarItems: [] },
      },
    });

    expect(next.planImpacts).toContainEqual(expect.objectContaining({
      id: 'course-added:c2',
      kind: 'course_added',
    }));
  });

  it('requests reanalysis when a student is added to a new course even before it has tasks', () => {
    const before = course([]);
    const after = {
      ...before,
      c2: { courseId: 'c2', modules: [], resources: [], plannerItems: [], appointmentGroups: [], calendarItems: [] },
    };
    const impacts = detectLmsPlanImpacts(plan(), [task()], [task()], before, after);
    expect(impacts).toContainEqual(expect.objectContaining({
      id: 'course-added:c2',
      kind: 'course_added',
      courseId: 'c2',
      title: 'Bạn được thêm vào môn học mới',
      affectedBlockIds: [],
    }));
  });

  it('detects a new course before the learner has created any plan', () => {
    const impacts = detectLmsPlanImpacts(null, [], [], {}, {
      c2: { courseId: 'c2', modules: [], resources: [], plannerItems: [], appointmentGroups: [], calendarItems: [] },
    });
    expect(impacts).toContainEqual(expect.objectContaining({ kind: 'course_added', courseId: 'c2' }));
  });

  it('detects a deadline moved earlier within the same date and identifies late blocks', () => {
    const date = addDays(DEMO_TODAY, 1);
    const before = { ...task(date), dueAt: `${date}T23:59:00+07:00` };
    const after = { ...before, dueAt: `${date}T12:00:00+07:00` };
    const impacts = detectLmsPlanImpacts(plan(date), [before], [after], {}, {});
    expect(impacts).toContainEqual(expect.objectContaining({ kind: 'deadline_earlier',
      id: `deadline:t1:${after.dueAt}`, affectedBlockIds: ['b1'], deficitMin: 60 }));
  });
  it('turns fixed LMS events into exact-date unavailable slots', () => {
    const date = addDays(DEMO_TODAY, 1);
    expect(lmsUnavailableSlots(course([event('e1', date)]))[0]).toMatchObject({ date, start: '19:00', end: '20:00', source: 'lms', readOnly: true });
  });

  it('keeps future class constraints beyond the old fixed demo horizon', () => {
    const date = addDays(DEMO_TODAY, 21);
    expect(lmsUnavailableSlots(course([event('future-class', date)]))).toContainEqual(
      expect.objectContaining({ date, start: '19:00', end: '20:00', source: 'lms' }),
    );
  });

  it('deduplicates repeated imports of the same class interval', () => {
    const date = addDays(DEMO_TODAY, 21);
    const first = event('first-import', date);
    const repeated = { ...first, id: 'second-import', source_id: 2 };

    expect(lmsUnavailableSlots(course([first, repeated]))).toHaveLength(1);
  });

  it('detects a newly added event that conflicts with a saved study block', () => {
    const date = addDays(DEMO_TODAY, 1);
    const impacts = detectLmsPlanImpacts(plan(date), [task()], [task()], course([]), course([event('e1', date)]));
    expect(impacts).toContainEqual(expect.objectContaining({ kind: 'schedule_conflict', taskId: 't1', deficitMin: 60, affectedBlockIds: ['b1'] }));
  });

  it('notifies the student about a teacher schedule change even when it does not conflict', () => {
    const date = addDays(DEMO_TODAY, 1);
    const impacts = detectLmsPlanImpacts(plan(date), [task()], [task()], course([]), course([event('e1', date, '15:00', '16:00')]));
    expect(impacts).toContainEqual(expect.objectContaining({
      kind: 'schedule_changed',
      title: 'Giảng viên đã thay đổi lịch học',
      deficitMin: 0,
      affectedBlockIds: [],
    }));
  });

  it('treats PaceWise instructor-authored lessons as fixed schedule constraints', () => {
    const date = addDays(DEMO_TODAY, 1);
    const authored = { ...event('teacher-1', date), event_kind: 'teaching_offline' };
    expect(lmsUnavailableSlots(course([authored]))[0]).toMatchObject({ date, start: '19:00', end: '20:00' });
  });

  it('detects released capacity without modifying the plan', () => {
    const date = addDays(DEMO_TODAY, 1);
    const original = plan(date);
    const impacts = detectLmsPlanImpacts(original, [task()], [task()], course([event('e1', date)]), course([]));
    expect(impacts[0]).toMatchObject({ kind: 'capacity_released', deficitMin: 60 });
    expect(original.blocks).toHaveLength(1);
  });

  it('detects earlier deadlines and removed assignments', () => {
    const earlier = task(addDays(DEMO_TODAY, 1));
    const impacts = detectLmsPlanImpacts(plan(addDays(DEMO_TODAY, 4)), [task()], [earlier], course([]), course([]));
    expect(impacts[0]).toMatchObject({ kind: 'deadline_earlier', taskId: 't1', affectedBlockIds: ['b1'] });
    const removed = detectLmsPlanImpacts(plan(), [task()], [], course([]), course([]));
    expect(removed[0]).toMatchObject({ kind: 'assignment_removed', affectedBlockIds: ['b1'] });
  });

  it('detects a personal busy interval that conflicts with a saved study block', () => {
    const date = addDays(DEMO_TODAY, 1);
    const impacts = detectAvailabilityPlanImpacts(plan(date), [task()], [], [{
      id: 'busy-1',
      label: 'Có việc đột xuất',
      date,
      weekday: weekdayOf(date),
      start: '18:30',
      end: '20:30',
      source: 'manual',
    }]);

    expect(impacts).toContainEqual(expect.objectContaining({
      kind: 'schedule_conflict',
      taskId: 't1',
      deficitMin: 60,
      affectedBlockIds: ['b1'],
    }));
  });

  it('reports capacity released by a shortened or removed busy interval', () => {
    const date = addDays(DEMO_TODAY, 1);
    const original = { id: 'busy-1', label: 'Việc cá nhân', date, weekday: weekdayOf(date), start: '18:00', end: '21:00', source: 'manual' as const };
    const shortened = { ...original, start: '19:00' };

    expect(detectAvailabilityPlanImpacts(plan(date), [task()], [original], [shortened]))
      .toContainEqual(expect.objectContaining({ kind: 'capacity_released', deficitMin: 60 }));
    expect(detectAvailabilityPlanImpacts(plan(date), [task()], [original], []))
      .toContainEqual(expect.objectContaining({ kind: 'capacity_released', deficitMin: 180 }));
  });
});
