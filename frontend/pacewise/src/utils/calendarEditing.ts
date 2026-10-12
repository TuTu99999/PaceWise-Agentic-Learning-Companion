import type { Task, TimeBlock, UnavailableSlot } from '../types';
import { weekdayOf } from './time';

export const blockTimestamp = (date: string, clock: string) => Date.parse(`${date}T${clock}:00+07:00`);
const timestamp = (value: string) => Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}+07:00`);

/** Personal planning is prospective; elapsed calendar time is read-only history. */
export function personalSlotTimeError(
  slot: Pick<UnavailableSlot, 'date' | 'start' | 'end'>,
  now = Date.now(),
): string | undefined {
  if (!slot.date) return 'Ngày của hoạt động không hợp lệ.';
  const start = blockTimestamp(slot.date, slot.start);
  const end = blockTimestamp(slot.date, slot.end);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 'Ngày hoặc giờ của hoạt động không hợp lệ.';
  if (end <= start) return 'Hoạt động phải kết thúc sau giờ bắt đầu.';
  if (start < now) return 'Không thể thêm hoặc dời hoạt động vào thời gian đã qua. Lịch quá khứ chỉ để xem.';
}

/** Exact Canvas due time wins over the date-only, end-of-day fallback. */
export function blockDeadlineError(block: Pick<TimeBlock, 'date' | 'end'>, task: Task): string | undefined {
  const deadline = task.dueAt ? timestamp(task.dueAt) : blockTimestamp(task.deadline, '23:59');
  if (!Number.isFinite(deadline)) return 'Deadline của nhiệm vụ không hợp lệ; hãy đồng bộ LMS lại.';
  const end = blockTimestamp(block.date, block.end);
  if (!Number.isFinite(end)) return 'Ngày hoặc giờ kết thúc ca tự học không hợp lệ.';
  if (end > deadline) return 'Ca tự học phải kết thúc trước hoặc đúng giờ deadline.';
}

export const sameBlockPlacement = (left: TimeBlock, right: TimeBlock) =>
  left.id === right.id && left.taskId === right.taskId && left.date === right.date
  && left.start === right.start && left.end === right.end
  && (left.milestoneId ?? '') === (right.milestoneId ?? '') && (left.milestoneTitle ?? '') === (right.milestoneTitle ?? '');

/** A global draft flag must not block a confirmed, unchanged, conflict-free session. */
export function confirmedBlockIssue(block: TimeBlock, confirmed: TimeBlock[], tasks: Task[], constraints: UnavailableSlot[]) {
  const original = confirmed.find((item) => item.id === block.id);
  if (!original || !sameBlockPlacement(block, original)) return 'Ca này chưa được xác nhận hoặc vừa đổi giờ. Hãy phân tích và áp dụng lại trước khi bắt đầu Do.';
  if (block.status === 'history' || block.status === 'tentative') return 'Ca này là lịch sử hoặc dự kiến, chưa thể bắt đầu Do.';
  const task = tasks.find((item) => item.id === block.taskId);
  if (!task || task.status === 'done') return 'Nhiệm vụ đã hoàn thành hoặc không còn tồn tại.';
  const deadlineError = blockDeadlineError(block, task);
  if (deadlineError) return deadlineError;
  if (constraints.some((slot) => slot.category !== 'self_study'
    && (slot.date ? slot.date === block.date : slot.weekday === weekdayOf(block.date))
    && block.start < slot.end && slot.start < block.end)) return 'Ca này trùng lịch LMS hoặc lịch cá nhân mới. Hãy điều chỉnh và xác nhận lại.';
}
