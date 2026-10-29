import type { LMSCalendarItem, LMSCourseData, Plan, PlanImpact, Task, TimeBlock, UnavailableSlot, Weekday } from '../types';
import { durationMin, toMin, weekdayOf } from './time';
import { blockTimestamp } from './calendarEditing';
import { taskDeadlineTimestamp } from './planningScope';

const FIXED_EVENT_KINDS = new Set([
  'class',
  'class_session',
  'online_class',
  'exam',
  'quiz',
  'midterm',
  'final_exam',
  'video',
  'lecture_video',
]);

function localParts(value: string) {
  const date = new Date(value);
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  return { date: `${get('year')}-${get('month')}-${get('day')}`, clock: `${get('hour')}:${get('minute')}` };
}

export function uniqueCalendarItems(courseData: Record<string, LMSCourseData>): LMSCalendarItem[] {
  const byId = new Map<string, LMSCalendarItem>();
  Object.values(courseData).forEach((course) => {
    (course.calendarItems ?? []).forEach((item) => byId.set(item.id, item));
  });
  return [...byId.values()];
}

function isFixedCommitment(item: LMSCalendarItem) {
  return item.type === 'event'
    && Boolean(item.ends_at)
    && (FIXED_EVENT_KINDS.has(item.event_kind) || item.event_kind.startsWith('teaching_'));
}

export function lmsUnavailableSlots(
  courseData: Record<string, LMSCourseData>,
  range?: { from: string; to: string },
): UnavailableSlot[] {
  const slots = uniqueCalendarItems(courseData)
    .filter(isFixedCommitment)
    .map((item) => {
      const start = localParts(item.starts_at);
      const end = localParts(item.ends_at!);
      return {
        id: `lms-${item.id}`,
        label: item.title,
        date: start.date,
        weekday: weekdayOf(start.date) as Weekday,
        start: start.clock,
        end: end.clock,
        source: 'lms' as const,
        readOnly: true,
      };
    })
    .filter((slot) => !range || (slot.date! >= range.from && slot.date! <= range.to));
  const unique = new Map<string, UnavailableSlot>();
  slots.forEach((slot) => {
    const identity = [slot.date, slot.start, slot.end, slot.label].join('|').toLocaleLowerCase();
    if (!unique.has(identity)) unique.set(identity, slot);
  });
  return [...unique.values()];
}

export function slotOverlapsBlock(block: TimeBlock, slot: UnavailableSlot) {
  return (!slot.date || slot.date === block.date)
    && slot.weekday === weekdayOf(block.date)
    && toMin(block.start) < toMin(slot.end)
    && toMin(slot.start) < toMin(block.end);
}

function changedBusySlots(previous: Record<string, LMSCourseData>, current: Record<string, LMSCourseData>) {
  const before = new Map(lmsUnavailableSlots(previous).map((slot) => [slot.id, slot]));
  const after = new Map(lmsUnavailableSlots(current).map((slot) => [slot.id, slot]));
  return {
    addedOrChanged: [...after.values()].filter((slot) => {
      const old = before.get(slot.id);
      return !old || old.date !== slot.date || old.start !== slot.start || old.end !== slot.end;
    }),
    removedOrShortened: [...before.values()].filter((slot) => {
      const next = after.get(slot.id);
      if (!next) return true;
      if (next.date !== slot.date || next.start !== slot.start) return true;
      return toMin(next.end) < toMin(slot.end);
    }),
  };
}

export function detectLmsPlanImpacts(
  plan: Plan | null,
  previousTasks: Task[],
  currentTasks: Task[],
  previousCourseData: Record<string, LMSCourseData>,
  currentCourseData: Record<string, LMSCourseData>,
): PlanImpact[] {
  const detectedAt = new Date().toISOString();
  const impacts: PlanImpact[] = [];
  const planBlocks = plan?.blocks ?? [];
  const oldTasks = new Map(previousTasks.map((task) => [task.id, task]));
  const nextTasks = new Map(currentTasks.map((task) => [task.id, task]));
  const previousCourseIds = new Set(Object.keys(previousCourseData));

  Object.entries(currentCourseData).forEach(([key, course]) => {
    if (previousCourseIds.has(key)) return;
    const courseId = String(course.courseId || key);
    impacts.push({
      id: `course-added:${courseId}`,
      kind: 'course_added',
      title: 'Bạn được thêm vào môn học mới',
      message: 'Môn học mới đã được thêm vào phạm vi học. Bấm AI phân tích lại để đưa lịch học và nhiệm vụ của môn vào kế hoạch; lịch hiện tại chỉ đổi sau khi bạn xác nhận.',
      courseId,
      deficitMin: 0,
      affectedBlockIds: [],
      detectedAt,
    });
  });

  currentTasks.forEach((task) => {
    const old = oldTasks.get(task.id);
    if (!old) {
      impacts.push({ id: `assignment-added:${task.id}:${task.deadline}`, kind: 'assignment_added', title: 'Có deadline mới', message: `${task.title} vừa được thêm và cần được đánh giá cùng kế hoạch hiện tại.`, courseId: task.courseId, taskId: task.id, deadline: task.deadline, deficitMin: Math.max(0, task.estimateMin - task.loggedMin), affectedBlockIds: [], detectedAt });
    } else if (taskDeadlineTimestamp(old) !== taskDeadlineTimestamp(task)) {
      const earlier = taskDeadlineTimestamp(task) < taskDeadlineTimestamp(old);
      const affected = planBlocks.filter((block) => block.taskId === task.id && blockTimestamp(block.date, block.end) > taskDeadlineTimestamp(task));
      const deadlineLabel = (value: Task) => value.dueAt
        ? new Date(taskDeadlineTimestamp(value)).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' }) : value.deadline;
      impacts.push({ id: `deadline:${task.id}:${task.dueAt ?? task.deadline}`, kind: earlier ? 'deadline_earlier' : 'deadline_later', title: earlier ? 'Deadline được dời sớm' : 'Deadline được gia hạn', message: earlier ? `${task.title} chuyển từ ${deadlineLabel(old)} sang ${deadlineLabel(task)}. ${affected.length} ca tự học cần được kiểm tra lại.` : `${task.title} chuyển từ ${deadlineLabel(old)} sang ${deadlineLabel(task)}; kế hoạch có thể có thêm thời gian dự phòng.`, courseId: task.courseId, taskId: task.id, deadline: task.deadline, deficitMin: affected.reduce((sum, block) => sum + durationMin(block.start, block.end), 0), affectedBlockIds: affected.map((block) => block.id), detectedAt });
    }
  });

  previousTasks.forEach((task) => {
    if (nextTasks.has(task.id)) return;
    const affected = planBlocks.filter((block) => block.taskId === task.id);
    impacts.push({ id: `assignment-removed:${task.id}`, kind: 'assignment_removed', title: 'Assignment đã bị xóa', message: `${task.title} không còn trên LMS. ${affected.length} ca tự học chỉ được gỡ sau khi bạn xác nhận.`, courseId: task.courseId, taskId: task.id, deadline: task.deadline, deficitMin: 0, affectedBlockIds: affected.map((block) => block.id), detectedAt });
  });

  const busyChanges = changedBusySlots(previousCourseData, currentCourseData);
  busyChanges.addedOrChanged.forEach((slot) => {
    const affected = planBlocks.filter((block) => slotOverlapsBlock(block, slot));
    if (affected.length === 0) {
      impacts.push({
        id: `schedule-changed:${slot.id}:${slot.date}:${slot.start}:${slot.end}`,
        kind: 'schedule_changed',
        constraintId: slot.id,
        title: 'Giảng viên đã thay đổi lịch học',
        message: `${slot.label} chuyển sang ${slot.date} lúc ${slot.start}–${slot.end}. Lịch mới chưa trùng ca tự học đã lưu, nhưng bạn nên chạy AI phân tích lại để cập nhật toàn bộ kế hoạch.`,
        deficitMin: 0,
        affectedBlockIds: [],
        detectedAt,
      });
    }
    affected.forEach((block) => {
      const task = nextTasks.get(block.taskId) ?? oldTasks.get(block.taskId);
      impacts.push({ id: `schedule-conflict:${slot.id}:${block.id}:${slot.date}:${slot.start}`, kind: 'schedule_conflict', constraintId: slot.id, title: 'Giảng viên đổi lịch và gây trùng ca tự học', message: `${slot.label} (${slot.start}–${slot.end}) trùng một phiên học đã lưu. Bấm AI phân tích lại; PaceWise chỉ đổi lịch sau khi bạn xác nhận bản cập nhật.`, courseId: task?.courseId, taskId: block.taskId, deadline: task?.deadline, deficitMin: durationMin(block.start, block.end), affectedBlockIds: [block.id], detectedAt });
    });
  });
  busyChanges.removedOrShortened.forEach((slot) => {
    impacts.push({ id: `capacity-released:${slot.id}:${slot.date}:${slot.start}`, kind: 'capacity_released', title: 'Bạn vừa có thêm thời gian trống', message: `${slot.label} đã bị xóa hoặc rút ngắn. PaceWise không tự nhồi thêm việc; bạn có thể dùng khoảng trống này để giảm rủi ro.`, deficitMin: Math.max(0, toMin(slot.end) - toMin(slot.start)), affectedBlockIds: [], detectedAt });
  });

  return impacts;
}

function slotDuration(slot: UnavailableSlot) {
  return Math.max(0, toMin(slot.end) - toMin(slot.start));
}

function sameSlot(left: UnavailableSlot, right: UnavailableSlot) {
  return left.date === right.date
    && left.weekday === right.weekday
    && left.start === right.start
    && left.end === right.end;
}

function overlapMinutes(left: UnavailableSlot, right: UnavailableSlot) {
  const sameDate = left.date && right.date
    ? left.date === right.date
    : !left.date && !right.date && left.weekday === right.weekday;
  if (!sameDate) return 0;
  return Math.max(0, Math.min(toMin(left.end), toMin(right.end)) - Math.max(toMin(left.start), toMin(right.start)));
}

/**
 * Detect the effect of a student's changed availability without mutating the
 * saved plan. The same path is also used for imported Google busy intervals.
 */
export function detectAvailabilityPlanImpacts(
  plan: Plan | null,
  tasks: Task[],
  previous: UnavailableSlot[],
  current: UnavailableSlot[],
): PlanImpact[] {
  if (!plan) return [];
  const detectedAt = new Date().toISOString();
  const taskById = new Map(tasks.map((task) => [task.id, task]));
  const before = new Map(previous.filter((slot) => slot.source !== 'lms').map((slot) => [slot.id, slot]));
  const after = new Map(current.filter((slot) => slot.source !== 'lms').map((slot) => [slot.id, slot]));
  const impacts: PlanImpact[] = [];

  after.forEach((slot, slotId) => {
    const old = before.get(slotId);
    if (old && sameSlot(old, slot)) return;
    const affected = plan.blocks.filter((block) => slotOverlapsBlock(block, slot));
    affected.forEach((block) => {
      const task = taskById.get(block.taskId);
      impacts.push({
        id: `availability-conflict:${slotId}:${block.id}:${slot.date ?? slot.weekday}:${slot.start}:${slot.end}`,
        kind: 'schedule_conflict',
        constraintId: slotId,
        title: 'Lịch bận trùng ca tự học',
        message: `${slot.label} (${slot.start}–${slot.end}) trùng một phiên học đã lưu. Deadline không đổi; PaceWise chỉ lập lại lịch sau khi bạn xác nhận.`,
        courseId: task?.courseId,
        taskId: block.taskId,
        deadline: task?.deadline,
        deficitMin: durationMin(block.start, block.end),
        affectedBlockIds: [block.id],
        detectedAt,
      });
    });
  });

  before.forEach((slot, slotId) => {
    const next = after.get(slotId);
    const released = next ? slotDuration(slot) - overlapMinutes(slot, next) : slotDuration(slot);
    if (released <= 0) return;
    impacts.push({
      id: `availability-released:${slotId}:${next?.date ?? slot.date ?? slot.weekday}:${next?.start ?? 'removed'}:${next?.end ?? 'removed'}`,
      kind: 'capacity_released',
      title: 'Bạn vừa có thêm thời gian trống',
      message: `${slot.label} đã được rút ngắn hoặc xóa. PaceWise không tự thêm việc; bạn có thể dùng khoảng trống mới để giảm rủi ro deadline.`,
      deficitMin: released,
      affectedBlockIds: [],
      detectedAt,
    });
  });

  return impacts;
}

export function mergeUnavailable(manual: UnavailableSlot[], lms: UnavailableSlot[]) {
  const retained = manual.filter((slot) => slot.source !== 'lms');
  return [...retained, ...lms];
}
