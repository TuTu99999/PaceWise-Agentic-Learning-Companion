import type { Course, LMSCalendarItem, Task, TimeBlock, UnavailableSlot } from '../types';
import { addDays, diffDays, durationMin as clockDuration, weekdayOf } from './time';

export type PlanTimelineSource = 'lms' | 'pacewise' | 'busy';

export interface PlanTimelineItem {
  id: string;
  /** Stable domain identifier used by editable calendar views. */
  entityId?: string;
  taskId?: string;
  source: PlanTimelineSource;
  title: string;
  date: string;
  start: string;
  end?: string;
  durationMin: number;
  courseCode?: string;
  kind: string;
  kindLabel: string;
  deadline?: string;
  readOnly: boolean;
  scheduleStatus?: 'confirmed' | 'tentative' | 'history';
}

/**
 * Keep the student calendar focused on current work without deleting history.
 * Course-owned items remain visible; expired study blocks and personal slots
 * continue to exist for learning evidence, Reflect, and audit views.
 */
export function hidePastStudentCalendarItems(items: PlanTimelineItem[], today: string) {
  return items.filter((item) => item.source === 'lms' || item.date >= today);
}

const LOCAL_TIME_ZONE = 'Asia/Ho_Chi_Minh';
const zonedFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: LOCAL_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

const EVENT_KIND_LABELS: Record<string, string> = {
  assignment: 'Deadline',
  class: 'Buổi học tại lớp',
  class_session: 'Buổi học online',
  event: 'Sự kiện',
  final_exam: 'Thi cuối kỳ',
  lecture_video: 'Video bài giảng',
  midterm: 'Thi giữa kỳ',
  personal: 'Lịch cá nhân',
  quiz: 'Quiz',
};

function parseLmsDateTime(value: string) {
  // Canvas-compatible APIs may return a local timestamp without an offset.
  // The simulator and PaceWise both use GMT+7, so make that assumption explicit.
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}+07:00`;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function localParts(value: string | Date) {
  const parsed = value instanceof Date ? value : parseLmsDateTime(value);
  if (!parsed) return null;
  const parts = Object.fromEntries(
    zonedFormatter
      .formatToParts(parsed)
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour}:${parts.minute}`,
  };
}

function lmsEnd(item: LMSCalendarItem, start: Date) {
  if (item.ends_at) return parseLmsDateTime(item.ends_at);
  if (item.duration_minutes && item.duration_minutes > 0) {
    return new Date(start.getTime() + item.duration_minutes * 60_000);
  }
  return null;
}

function inRange(date: string, from: string, to: string) {
  return date >= from && date <= to;
}

interface BuildPlanTimelineInput {
  blocks: TimeBlock[];
  calendarItems: LMSCalendarItem[];
  tasks: Task[];
  courses: Course[];
  unavailable?: UnavailableSlot[];
  from: string;
  to: string;
}

/** Build one read model for the Plan timeline without changing either source. */
export function buildPlanTimeline({ blocks, calendarItems, tasks, courses, unavailable = [], from, to }: BuildPlanTimelineInput) {
  const taskById = new Map(tasks.map((task) => [task.id, task]));
  const courseById = new Map(courses.map((course) => [course.id, course]));
  const timeline: PlanTimelineItem[] = blocks
    .filter((block) => inRange(block.date, from, to))
    .map((block) => {
      const task = taskById.get(block.taskId);
      const course = task ? courseById.get(task.courseId) : undefined;
      const [startHour, startMinute] = block.start.split(':').map(Number);
      const [endHour, endMinute] = block.end.split(':').map(Number);
      return {
        id: `pacewise:${block.id}`,
        entityId: block.id,
        taskId: block.taskId,
        source: 'pacewise' as const,
        title: block.milestoneTitle ?? task?.title ?? 'Nhiệm vụ học tập',
        date: block.date,
        start: block.start,
        end: block.end,
        durationMin: Math.max(0, endHour * 60 + endMinute - startHour * 60 - startMinute),
        courseCode: course?.code,
        kind: 'study_block',
        kindLabel: 'Ca tự học',
        deadline: task?.deadline,
        readOnly: block.status === 'history',
        scheduleStatus: block.status,
      };
    });

  // Personal events are copied into every course snapshot. Deduplicate by the
  // stable LMS identity before presenting the combined schedule.
  const uniqueLmsItems = new Map<string, LMSCalendarItem>();
  calendarItems.forEach((item) => {
    const key = `${item.type}:${item.id}`;
    if (!uniqueLmsItems.has(key)) uniqueLmsItems.set(key, item);
  });

  // Assignment deadlines are task data and are not guaranteed to be emitted
  // as calendar events. Keep them visible as independent, read-only markers.
  const lmsDeadlineKeys = new Set(
    [...uniqueLmsItems.values()]
      .filter((item) => item.type === 'assignment')
      .map((item) => `${item.course_id ?? ''}:${item.source_id}`),
  );
  tasks
    .filter((task) => task.status !== 'done')
    .forEach((task) => {
      const dateTime = task.dueAt ? localParts(task.dueAt) : null;
      const date = dateTime?.date ?? task.deadline;
      if (!inRange(date, from, to)) return;
      const taskIdParts = task.id.split(/[:-]/);
      const assignmentId = task.lmsAssignmentId ?? taskIdParts[taskIdParts.length - 1] ?? task.id;
      if (lmsDeadlineKeys.has(`${task.courseId}:${assignmentId}`)) return;
      timeline.push({
        id: `lms:deadline:${task.id}`,
        source: 'lms',
        title: `Deadline · ${task.title}`,
        date,
        start: dateTime?.time ?? '23:59',
        durationMin: 0,
        courseCode: courseById.get(task.courseId)?.code,
        kind: 'assignment',
        kindLabel: 'Deadline',
        deadline: task.deadline,
        readOnly: true,
      });
    });

  uniqueLmsItems.forEach((item) => {
    const startDate = parseLmsDateTime(item.starts_at);
    const start = localParts(item.starts_at);
    if (!startDate || !start || !inRange(start.date, from, to)) return;
    const endDate = lmsEnd(item, startDate);
    const end = endDate ? localParts(endDate) : null;
    const sameDayEnd = end?.date === start.date ? end.time : undefined;
    const durationMin = endDate
      ? Math.max(0, Math.round((endDate.getTime() - startDate.getTime()) / 60_000))
      : Math.max(0, item.duration_minutes ?? 0);
    const course = item.course_id == null ? undefined : courseById.get(String(item.course_id));
    const kind = item.event_kind || item.type;
    timeline.push({
      id: `lms:${item.type}:${item.id}`,
      source: 'lms',
      title: item.title,
      date: start.date,
      start: start.time,
      end: sameDayEnd,
      durationMin,
      courseCode: item.course_code ?? course?.code,
      kind,
      kindLabel: EVENT_KIND_LABELS[kind] ?? 'Sự kiện LMS',
      readOnly: true,
    });
  });

  unavailable
    .filter((slot) => slot.source !== 'lms')
    .forEach((slot) => {
      const dates = slot.date
        ? [slot.date]
        : Array.from({ length: Math.max(0, diffDays(from, to)) + 1 }, (_, index) => addDays(from, index))
            .filter((date) => weekdayOf(date) === slot.weekday);
      dates.filter((date) => inRange(date, from, to)).forEach((date) => {
        timeline.push({
          id: `busy:${slot.id}:${date}`,
          entityId: slot.id,
          source: 'busy',
          title: slot.label,
          date,
          start: slot.start,
          end: slot.end,
          durationMin: Math.max(0, clockDuration(slot.start, slot.end)),
          kind: slot.category === 'self_study' ? 'personal_self_study' : slot.source === 'google' ? 'google_busy' : 'personal_busy',
          kindLabel: slot.category === 'self_study' ? 'Khung tự học ưu tiên' : slot.source === 'google' ? 'Google Calendar' : 'Không thể học',
          readOnly: Boolean(slot.readOnly),
        });
      });
    });

  return timeline.sort((left, right) => (
    left.date.localeCompare(right.date)
    || left.start.localeCompare(right.start)
    || (left.source === right.source ? 0 : left.source === 'lms' ? -1 : 1)
    || left.title.localeCompare(right.title)
  ));
}
