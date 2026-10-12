import { describe, expect, it } from 'vitest';
import { visibleTeacherLessons } from './TeacherLessonManager';
import type { TeacherLesson } from '../../types/teacherManagement';

const lesson = (id: number, start: string, end: string, cancelled = false): TeacherLesson => ({ id, starts_at: start, ends_at: end,
  title: `Lesson ${id}`, cancelled, version: 'v1', mode: 'offline', description: '', location: '', meeting_url: '', resource_ids: [] });

describe('teacher lesson view', () => {
  const now = Date.parse('2026-10-10T09:30:00Z');
  const lessons = [lesson(1, '2026-01-01T08:00:00Z', '2026-01-01T09:00:00Z'),
    lesson(2, '2026-10-10T09:00:00Z', '2026-10-10T10:00:00Z'),
    lesson(3, '2026-10-12T09:00:00Z', '2026-10-12T10:00:00Z'),
    lesson(4, '2026-10-12T09:00:00Z', '2026-10-12T10:00:00Z', true)];
  it('opens with upcoming and ongoing, not January history', () => {
    expect(visibleTeacherLessons(lessons, 'upcoming', now).map((item) => item.id)).toEqual([2, 3]);
  });
  it('keeps old and cancelled records in separate views', () => {
    expect(visibleTeacherLessons(lessons, 'past', now).map((item) => item.id)).toEqual([1]);
    expect(visibleTeacherLessons(lessons, 'cancelled', now).map((item) => item.id)).toEqual([4]);
  });
  it('does not redisplay removed commitments even if cached data contains them', () => {
    const removed = { ...lessons[0], removed: true };
    expect(visibleTeacherLessons([removed], 'past', now)).toEqual([]);
  });
});
