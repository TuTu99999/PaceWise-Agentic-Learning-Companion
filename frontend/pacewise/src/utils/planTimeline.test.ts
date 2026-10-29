import { describe, expect, it } from 'vitest';
import type { Course, LMSCalendarItem, Task, TimeBlock } from '../types';
import { buildPlanTimeline } from './planTimeline';
import { weekdayOf } from './time';

const courses: Course[] = [{ id: '1', code: 'CS101', name: 'Computer Science', tone: 'primary' }];
const tasks: Task[] = [{
  id: 'task-1',
  title: 'Bài tập thuật toán',
  courseId: '1',
  deadline: '2026-10-05',
  estimateMin: 120,
  loggedMin: 0,
  status: 'todo',
  priority: 'high',
  objective: 'Hoàn thành bài tập',
}];
const blocks: TimeBlock[] = [{ id: 'block-1', taskId: 'task-1', date: '2026-10-03', start: '19:00', end: '20:00' }];
const event: LMSCalendarItem = {
  id: 'event-1',
  source_id: 1,
  type: 'event',
  course_id: 1,
  course_code: 'CS101',
  title: 'Buổi học online',
  starts_at: '2026-10-03T18:00:00+07:00',
  ends_at: '2026-10-03T19:00:00+07:00',
  duration_minutes: 60,
  event_kind: 'class_session',
  editable: false,
};

describe('buildPlanTimeline', () => {
  it('keeps the informational outside-preference flag from an AI block', () => {
    const result = buildPlanTimeline({
      blocks: [{ ...blocks[0], outsidePreferred: true }],
      calendarItems: [],
      tasks,
      courses,
      from: '2026-10-02',
      to: '2026-10-08',
    });

    expect(result[0].outsidePreferred).toBe(true);
  });

  it('merges LMS events and PaceWise blocks in chronological order', () => {
    const result = buildPlanTimeline({ blocks, calendarItems: [event], tasks, courses, from: '2026-10-02', to: '2026-10-08' });

    expect(result.map((item) => item.source)).toEqual(['lms', 'pacewise', 'lms']);
    expect(result[0]).toMatchObject({ start: '18:00', end: '19:00', readOnly: true, kindLabel: 'Buổi học online' });
    expect(result[1]).toMatchObject({ title: 'Bài tập thuật toán', courseCode: 'CS101', deadline: '2026-10-05', readOnly: false });
    expect(result[2]).toMatchObject({ title: 'Deadline · Bài tập thuật toán', start: '23:59', kindLabel: 'Deadline' });
  });

  it('deduplicates LMS items copied into multiple course snapshots', () => {
    const result = buildPlanTimeline({ blocks: [], calendarItems: [event, { ...event }], tasks, courses, from: '2026-10-02', to: '2026-10-08' });

    expect(result).toHaveLength(2);
    expect(result.filter((item) => item.id === 'lms:event:event-1')).toHaveLength(1);
  });

  it('shows assignments as deadline markers and excludes items outside the week', () => {
    const assignment = {
      ...event,
      id: 'assignment-1',
      type: 'assignment' as const,
      title: 'Deadline báo cáo',
      starts_at: '2026-10-05T23:59:00+07:00',
      ends_at: null,
      duration_minutes: null,
      event_kind: 'assignment',
    };
    const outside = { ...event, id: 'outside', starts_at: '2026-10-12T08:00:00+07:00' };
    const result = buildPlanTimeline({ blocks: [], calendarItems: [assignment, outside], tasks, courses, from: '2026-10-02', to: '2026-10-08' });

    expect(result).toHaveLength(1);
    expect(result.find((item) => item.id === 'lms:assignment:assignment-1')).toMatchObject({ title: 'Deadline báo cáo', start: '23:59', end: undefined, durationMin: 0, kindLabel: 'Deadline' });
  });

  it('uses the milestone title for a PaceWise study block', () => {
    const result = buildPlanTimeline({
      blocks: [{ ...blocks[0], milestoneId: 'M1', milestoneTitle: 'Lập dàn ý' }],
      calendarItems: [],
      tasks,
      courses,
      from: '2026-10-02',
      to: '2026-10-08',
    });

    expect(result.find((item) => item.source === 'pacewise')?.title).toBe('Lập dàn ý');
  });

  it('includes personal busy time as a hard-constraint calendar item', () => {
    const date = '2026-10-04';
    const result = buildPlanTimeline({
      blocks: [],
      calendarItems: [],
      tasks,
      courses,
      unavailable: [{ id: 'busy-1', label: 'Việc cá nhân', date, weekday: weekdayOf(date), start: '18:00', end: '19:30', source: 'manual' }],
      from: '2026-10-02',
      to: '2026-10-08',
    });

    expect(result).toContainEqual(expect.objectContaining({
      source: 'busy',
      title: 'Việc cá nhân',
      date,
      durationMin: 90,
    }));
  });

  it('keeps past student-created items visible when browsing calendar history', () => {
    const timeline = buildPlanTimeline({
      blocks: [blocks[0], { ...blocks[0], id: 'future-block', date: '2026-10-05' }],
      calendarItems: [event],
      tasks,
      courses,
      unavailable: [
        { id: 'past-personal', label: 'Việc cá nhân', date: '2026-10-03', weekday: weekdayOf('2026-10-03'), start: '20:00', end: '21:00', source: 'manual' },
        { id: 'future-personal', label: 'Việc cá nhân', date: '2026-10-05', weekday: weekdayOf('2026-10-05'), start: '20:00', end: '21:00', source: 'manual' },
      ],
      from: '2026-10-02',
      to: '2026-10-08',
    });

    expect(timeline).toContainEqual(expect.objectContaining({ id: 'lms:event:event-1', date: '2026-10-03' }));
    expect(timeline).toContainEqual(expect.objectContaining({ id: 'pacewise:block-1' }));
    expect(timeline).toContainEqual(expect.objectContaining({ id: 'busy:past-personal:2026-10-03' }));
    expect(timeline).toContainEqual(expect.objectContaining({ id: 'pacewise:future-block' }));
    expect(timeline).toContainEqual(expect.objectContaining({ id: 'busy:future-personal:2026-10-05' }));
  });
});
