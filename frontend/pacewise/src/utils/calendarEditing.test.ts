import { describe, expect, it } from 'vitest';
import type { Task, TimeBlock, UnavailableSlot } from '../types';
import { blockDeadlineError, confirmedBlockIssue, personalSlotTimeError } from './calendarEditing';

const task: Task = { id: 'task', courseId: 'course', title: 'Quan hệ', deadline: '2026-10-08',
  dueAt: '2026-10-08T12:00:00+07:00', estimateMin: 180, loggedMin: 0, status: 'todo', priority: 'high', objective: 'Giải thích' };
const block: TimeBlock = { id: 'block', taskId: task.id, date: '2026-10-08', start: '10:00', end: '11:00' };
const slot = (patch: Partial<UnavailableSlot> = {}): UnavailableSlot => ({ id: 'meal', date: block.date, weekday: 4,
  start: '10:30', end: '11:30', category: 'meal', source: 'manual', label: 'Ăn', ...patch });

describe('minute-accurate calendar validation', () => {
  it.each(['2026-10-08T12:00:00+07:00', '2026-10-08T05:00:00Z', '2026-10-08T12:00:00'])('uses exact dueAt %s rather than its date', (dueAt) => {
    expect(blockDeadlineError({ date: block.date, end: '12:00' }, { ...task, dueAt })).toBeUndefined();
    expect(blockDeadlineError({ date: block.date, end: '12:01' }, { ...task, dueAt })).toMatch(/deadline/);
    expect(blockDeadlineError({ date: block.date, end: '18:00' }, { ...task, dueAt })).toMatch(/deadline/);
  });
  it('uses end of day only for date-only deadlines, including 24:00 rollover', () => {
    expect(blockDeadlineError({ date: block.date, end: '23:59' }, { ...task, dueAt: undefined })).toBeUndefined();
    expect(blockDeadlineError({ date: block.date, end: '24:00' }, { ...task, dueAt: undefined })).toMatch(/deadline/);
  });
  it('fails closed for malformed dates rather than allowing NaN comparisons', () => {
    expect(blockDeadlineError(block, { ...task, dueAt: 'invalid' })).toMatch(/không hợp lệ/);
    expect(blockDeadlineError({ date: 'invalid', end: '11:00' }, task)).toMatch(/không hợp lệ/);
  });
});

describe('personal activity time validation', () => {
  it('allows adding and moving activities anywhere in past or future calendar history', () => {
    expect(personalSlotTimeError(slot({ date: '2026-10-04', start: '20:00', end: '21:00' }))).toBeUndefined();
    expect(personalSlotTimeError(slot({ date: '2026-10-05', start: '07:00', end: '08:30' }))).toBeUndefined();
    expect(personalSlotTimeError(slot({ date: '2036-10-05', start: '07:00', end: '08:30' }))).toBeUndefined();
  });

  it('still rejects malformed or reversed activity ranges', () => {
    expect(personalSlotTimeError(slot({ date: 'invalid' }))).toMatch(/không hợp lệ/);
    expect(personalSlotTimeError(slot({ start: '09:00', end: '08:00' }))).toMatch(/kết thúc sau/);
  });
});

describe('per-session Do eligibility', () => {
  it('keeps an unchanged confirmed session usable after an unrelated calendar edit', () => {
    expect(confirmedBlockIssue(block, [block], [task], [slot({ date: '2026-10-09' })])).toBeUndefined();
    expect(confirmedBlockIssue(block, [block], [task], [slot({ start: '11:00', end: '12:00' })])).toBeUndefined();
  });
  it('blocks only an edited or unconfirmed session', () => {
    expect(confirmedBlockIssue({ ...block, start: '10:05' }, [block], [task], [])).toMatch(/xác nhận/);
    expect(confirmedBlockIssue(block, [], [task], [])).toMatch(/xác nhận/);
  });
  it.each(['manual', 'lms', 'google'] as const)('checks conflicts from %s even if hidden by a view filter', (source) => {
    expect(confirmedBlockIssue(block, [block], [task], [slot({ source })])).toMatch(/trùng lịch/);
  });
  it('does not treat preferred study availability as busy time', () => {
    expect(confirmedBlockIssue(block, [block], [task], [slot({ category: 'self_study' })])).toBeUndefined();
  });
  it('rechecks updated deadlines and completed tasks', () => {
    expect(confirmedBlockIssue(block, [block], [{ ...task, dueAt: '2026-10-08T10:59:00+07:00' }], [])).toMatch(/deadline/);
    expect(confirmedBlockIssue(block, [block], [{ ...task, status: 'done' }], [])).toMatch(/hoàn thành/);
  });
});
