import type { Course, LMSCalendarItem, LMSCourseData } from '../types';
import { buildPlanTimeline, type PlanTimelineItem } from './planTimeline';
import { addDays, diffDays, toClock, toMin } from './time';

export interface TeachingCalendarItem extends PlanTimelineItem {
  courseId: string;
  details: LMSCalendarItem;
}

const KIND_LABELS: Record<string, string> = {
  class: 'Học offline', class_session: 'Học online',
  teaching_offline: 'Học offline', teaching_online: 'Học online',
  teaching_practice: 'Thực hành', teaching_review: 'Ôn tập',
  teaching_quiz: 'Quiz', teaching_office_hour: 'Giờ tư vấn', teaching_other: 'Buổi học',
};

/** Only course-owned commitments; never students' private schedules or study blocks. */
export function buildTeachingCalendar({ courses, courseData, courseId = 'all', from, to }: {
  courses: Course[];
  courseData: Record<string, LMSCourseData>;
  courseId?: string;
  from: string;
  to: string;
}): TeachingCalendarItem[] {
  const allowedCourses = new Set(courses.filter((course) => courseId === 'all' || course.id === courseId).map((course) => course.id));
  const events = new Map<string, LMSCalendarItem>();
  const detailsById = new Map<string, LMSCalendarItem>();
  for (const [snapshotId, snapshot] of Object.entries(courseData)) {
    if (!allowedCourses.has(snapshotId)) continue;
    for (const event of snapshot.calendarItems ?? []) {
      if (event.course_id === null || !allowedCourses.has(String(event.course_id))) continue;
      const id = `${event.course_id}:${event.id}`;
      const normalized = { ...event, id };
      events.set(`${event.type}:${id}`, normalized);
      detailsById.set(`lms:${event.type}:${id}`, normalized);
    }
  }
  // Include earlier starts so an overnight event can continue into the visible range.
  const timeline = buildPlanTimeline({
    blocks: [], tasks: [], courses, calendarItems: [...events.values()],
    from: '0000-01-01', to,
  });
  return timeline.flatMap((item): TeachingCalendarItem[] => {
    const details = detailsById.get(item.id);
    if (!details) return [];
    const base = {
      ...item, courseId: String(details.course_id), details, readOnly: true,
      kindLabel: KIND_LABELS[item.kind] ?? item.kindLabel,
    };
    if (item.durationMin <= 0) return item.date >= from ? [base] : [];
    const segments: TeachingCalendarItem[] = [];
    const startMinute = toMin(item.start);
    const dayCount = Math.ceil((startMinute + item.durationMin) / 1440);
    const firstDay = Math.max(0, diffDays(item.date, from));
    const lastDay = Math.min(dayCount - 1, diffDays(item.date, to));
    for (let day = firstDay; day <= lastDay; day += 1) {
      const start = day === 0 ? startMinute : 0;
      const end = Math.min(1440, startMinute + item.durationMin - day * 1440);
      segments.push({
        ...base, id: `${item.id}:day-${day}`, date: addDays(item.date, day),
        start: toClock(start), end: toClock(end), durationMin: end - start,
      });
    }
    return segments;
  }).sort((a, b) => a.date.localeCompare(b.date) || a.start.localeCompare(b.start) || a.id.localeCompare(b.id));
}
