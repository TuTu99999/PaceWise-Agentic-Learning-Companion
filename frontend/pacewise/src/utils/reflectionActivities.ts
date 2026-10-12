import type { Course, LMSCourseData, Plan, StudySession, Task } from '../types';
import { APP_TIMEZONE, addDays, calendarWeekStart, currentAppDateTime, durationMin } from './time';

export type ReflectionActivityKind = 'class' | 'class_session' | 'lecture_video' | 'quiz' | 'exam' | 'self_study' | 'review';

export interface ReflectionActivity {
  id: string;
  taskId?: string;
  blockId?: string;
  kind: ReflectionActivityKind;
  kindLabel: string;
  title: string;
  courseId: string;
  courseCode: string;
  date: string;
  start: string;
  end: string;
  plannedMinutes: number;
  actualMinutes?: number;
  completionPercent?: number;
  blocker?: string;
  outcome?: string;
  missed?: boolean;
}

// Timetable lessons are planning constraints, not proof that the learner
// attended or learned. Reflect only exposes activities with an observable
// learner action or outcome.
const REFLECTABLE_LMS_KINDS = new Set(['lecture_video', 'quiz', 'midterm', 'final_exam']);
const KIND_LABELS: Record<string, string> = {
  lecture_video: 'Video bài giảng',
  quiz: 'Quiz',
  midterm: 'Thi giữa kỳ',
  final_exam: 'Thi cuối kỳ',
};

export function reflectionActivityWindow({
  requestedActivity,
  weeklyStart,
  weeklyEnd,
  today,
}: {
  requestedActivity: boolean;
  weeklyStart: string;
  weeklyEnd: string;
  today?: string;
}) {
  if (!requestedActivity) return { from: weeklyStart, to: weeklyEnd };
  const from = calendarWeekStart(today ?? currentAppDateTime().date);
  return { from, to: addDays(from, 6) };
}

export function reflectionNeedsPlanReview(
  scope: 'weekly' | 'activity',
  activity?: Pick<ReflectionActivity, 'missed' | 'completionPercent' | 'blocker' | 'outcome'>,
) {
  if (scope === 'weekly') return true;
  if (!activity) return false;
  return Boolean(
    activity.missed
    || (activity.completionPercent != null && activity.completionPercent < 100)
    || (activity.blocker && activity.blocker !== 'none')
    || (activity.outcome && ['missed', 'blocked', 'needs_more_time'].includes(activity.outcome)),
  );
}

const zonedFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: APP_TIMEZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

function localParts(value: string) {
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}+07:00`;
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return null;
  const parts = Object.fromEntries(
    zonedFormatter.formatToParts(parsed).filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]),
  );
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
}

function hasEnded(date: string, end: string, today: string, now: string) {
  return date < today || (date === today && end <= now);
}

function studyKind(title: string): Pick<ReflectionActivity, 'kind' | 'kindLabel'> {
  return /ôn|review|revision/i.test(title)
    ? { kind: 'review', kindLabel: 'Ôn tập' }
    : { kind: 'self_study', kindLabel: 'Tự học' };
}

export function buildReflectionActivities({
  plan,
  sessions,
  tasks,
  courses,
  courseData,
  from,
  to,
  today,
  now,
}: {
  plan: Plan | null;
  sessions: StudySession[];
  tasks: Task[];
  courses: Course[];
  courseData: Record<string, LMSCourseData>;
  from: string;
  to: string;
  today?: string;
  now?: string;
}): ReflectionActivity[] {
  const current = currentAppDateTime();
  const resolvedToday = today ?? current.date;
  const resolvedNow = now ?? current.time;
  const taskById = new Map(tasks.map((task) => [task.id, task]));
  const courseById = new Map(courses.map((course) => [course.id, course]));
  const sessionByBlock = new Map(sessions.filter((session) => session.blockId).map((session) => [session.blockId!, session]));
  const activities: ReflectionActivity[] = [];
  const representedSessions = new Set<string>();

  (plan?.blocks ?? []).forEach((block) => {
    if (block.date < from || block.date > to) return;
    const session = sessionByBlock.get(block.id);
    // A learner may finish the planned milestone before the reserved block
    // ends. The completed Do session is sufficient evidence to reflect now.
    if (!session && !hasEnded(block.date, block.end, resolvedToday, resolvedNow)) return;
    const task = taskById.get(block.taskId);
    if (!task) return;
    const course = courseById.get(task.courseId);
    if (session) representedSessions.add(session.id);
    const title = block.milestoneTitle ?? task.title;
    activities.push({
      id: `study:${block.id}`,
      taskId: task.id,
      blockId: block.id,
      ...studyKind(title),
      title,
      courseId: task.courseId,
      courseCode: course?.code ?? 'Môn học',
      date: block.date,
      start: block.start,
      end: block.end,
      plannedMinutes: Math.max(0, durationMin(block.start, block.end)),
      actualMinutes: session?.minutes,
      completionPercent: session?.completionPercent,
      blocker: session?.blocker,
      outcome: session?.outcome,
      missed: !session,
    });
  });

  sessions.forEach((session) => {
    if (representedSessions.has(session.id) || session.date < from || session.date > to || session.date > resolvedToday) return;
    const task = taskById.get(session.taskId);
    if (!task) return;
    const course = courseById.get(task.courseId);
    activities.push({
      id: `session:${session.id}`,
      taskId: session.taskId,
      blockId: session.blockId,
      ...studyKind(task.title),
      title: task.title,
      courseId: task.courseId,
      courseCode: course?.code ?? 'Môn học',
      date: session.date,
      start: '',
      end: '',
      plannedMinutes: session.plannedMin ?? task.estimateMin,
      actualMinutes: session.minutes,
      completionPercent: session.completionPercent,
      blocker: session.blocker,
      outcome: session.outcome,
    });
  });

  const seenLms = new Set<string>();
  Object.values(courseData).flatMap((data) => data.calendarItems ?? []).forEach((item) => {
    if (!REFLECTABLE_LMS_KINDS.has(item.event_kind)) return;
    const stableId = `${item.type}:${item.id}`;
    if (seenLms.has(stableId)) return;
    seenLms.add(stableId);
    const start = localParts(item.starts_at);
    if (!start || start.date < from || start.date > to) return;
    const fallbackEnd = item.ends_at ? localParts(item.ends_at) : null;
    const end = fallbackEnd?.date === start.date ? fallbackEnd.time : start.time;
    if (!hasEnded(start.date, end, resolvedToday, resolvedNow)) return;
    const courseId = String(item.course_id ?? 'all');
    const course = courseById.get(courseId);
    const kind: ReflectionActivityKind = item.event_kind === 'midterm' || item.event_kind === 'final_exam'
      ? 'exam'
      : item.event_kind as ReflectionActivityKind;
    activities.push({
      id: `lms:${stableId}`,
      kind,
      kindLabel: KIND_LABELS[item.event_kind] ?? 'Hoạt động môn học',
      title: item.title,
      courseId,
      courseCode: item.course_code ?? course?.code ?? 'Môn học',
      date: start.date,
      start: start.time,
      end,
      plannedMinutes: Math.max(0, item.duration_minutes ?? 0),
    });
  });

  return activities.sort((left, right) => (
    right.date.localeCompare(left.date)
    || right.end.localeCompare(left.end)
    || left.title.localeCompare(right.title)
  ));
}
