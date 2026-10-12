import { describe, expect, it } from 'vitest';
import type { Course, LMSCalendarItem, LMSCourseData } from '../types';
import { buildTeachingCalendar } from './teachingCalendar';

const courses: Course[] = [
  { id: '1', code: 'CS101', name: 'Python', tone: 'primary' },
  { id: '2', code: 'TRR', name: 'Toán rời rạc', tone: 'accent' },
];
const event = (courseId: number | null, overrides: Partial<LMSCalendarItem> = {}): LMSCalendarItem => ({
  id: 'same-id', source_id: 1, type: 'event', course_id: courseId, course_code: null,
  title: `Buổi học ${courseId}`, starts_at: '2026-10-05T09:07:00+07:00', ends_at: '2026-10-05T10:22:00+07:00',
  duration_minutes: 75, event_kind: 'class', editable: true, ...overrides,
});
const snapshot = (courseId: string, calendarItems: LMSCalendarItem[]): LMSCourseData => ({
  courseId, calendarItems, modules: [], resources: [], plannerItems: [], appointmentGroups: [],
});
const input = {
  courses, courseData: { '1': snapshot('1', [event(1)]), '2': snapshot('2', [event(2)]) },
  from: '2026-10-05', to: '2026-10-11',
};

describe('teaching calendar read model', () => {
  it('shows every authorized course without collapsing identical IDs across courses', () => {
    const items = buildTeachingCalendar(input);
    expect(items).toHaveLength(2);
    expect(items.map((item) => item.courseCode)).toEqual(['CS101', 'TRR']);
    expect(items.every((item) => item.readOnly)).toBe(true);
    expect(items[0]).toMatchObject({ start: '09:07', end: '10:22', durationMin: 75 });
  });

  it('filters by course without mutating the source snapshots', () => {
    const before = JSON.stringify(input);
    expect(buildTeachingCalendar({ ...input, courseId: '2' }).map((item) => item.courseId)).toEqual(['2']);
    expect(JSON.stringify(input)).toBe(before);
    expect(buildTeachingCalendar({ ...input, courseId: 'unauthorized' })).toEqual([]);
  });

  it('excludes private and unauthorized events and deduplicates copied events', () => {
    const items = buildTeachingCalendar({ ...input, courseData: {
      '1': snapshot('1', [event(1), event(1), event(null), event(999)]),
      '999': snapshot('999', [event(999)]),
    } });
    expect(items).toHaveLength(1);
    expect(items[0].courseId).toBe('1');
  });

  it('keeps existing PaceWise teacher schedules visible as read-only course commitments', () => {
    const items = buildTeachingCalendar({ ...input, courseData: {
      '1': snapshot('1', [event(1, { source: 'pacewise_instructor', event_kind: 'teaching_online' })]),
    } });
    expect(items[0]).toMatchObject({ kindLabel: 'Học online', readOnly: true });
    expect(items[0].details.source).toBe('pacewise_instructor');
  });

  it('converts UTC to GMT+7 and uses end timestamps rather than an inconsistent duration hint', () => {
    const items = buildTeachingCalendar({ ...input, courseData: {
      '1': snapshot('1', [event(1, { starts_at: '2026-10-05T02:07:00Z', ends_at: '2026-10-05T03:22:00Z', duration_minutes: 999 })]),
    } });
    expect(items[0]).toMatchObject({ date: '2026-10-05', start: '09:07', end: '10:22', durationMin: 75 });
  });

  it('splits overnight events at midnight with exact durations, including starts before the range', () => {
    const courseData = { '1': snapshot('1', [event(1, {
      starts_at: '2026-10-04T23:45:00+07:00', ends_at: '2026-10-05T00:35:00+07:00', duration_minutes: 50,
    })]) };
    const items = buildTeachingCalendar({ ...input, courseData, from: '2026-10-04' });
    expect(items.map(({ date, start, end, durationMin }) => ({ date, start, end, durationMin }))).toEqual([
      { date: '2026-10-04', start: '23:45', end: '24:00', durationMin: 15 },
      { date: '2026-10-05', start: '00:00', end: '00:35', durationMin: 35 },
    ]);
    expect(buildTeachingCalendar({ ...input, courseData })).toHaveLength(1);
  });

  it('retains point markers while ignoring malformed timestamps and events outside the range', () => {
    const items = buildTeachingCalendar({ ...input, courseData: { '1': snapshot('1', [
      event(1, { id: 'bad', starts_at: 'invalid' }),
      event(1, { id: 'old', starts_at: '2026-10-01T09:00:00+07:00', ends_at: '2026-10-01T10:00:00+07:00' }),
      event(1, { id: 'quiz', type: 'assignment', event_kind: 'quiz', ends_at: null, duration_minutes: null }),
    ]) } });
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ kind: 'quiz', durationMin: 0, readOnly: true });
  });
});
