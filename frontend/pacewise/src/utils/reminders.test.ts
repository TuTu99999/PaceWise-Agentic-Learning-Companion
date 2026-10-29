import { describe, expect, it } from 'vitest';
import type { LMSCalendarItem, ReminderState, Task } from '../types';
import { activeReminders, buildReminders, inQuietHours, selectBrowserDeliveries } from './reminders';
import { defaultReminderPreferences } from './studyPreferences';

const now = new Date('2026-10-03T02:00:00.000Z'); // 09:00 GMT+7

function task(patch: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    title: 'Bài tập lớn',
    courseId: '1',
    deadline: '2026-10-06',
    dueAt: '2026-10-06T02:00:00.000Z',
    estimateMin: 120,
    loggedMin: 0,
    status: 'todo',
    priority: 'high',
    objective: '',
    submission: { state: 'unsubmitted', attempts: 0, late: false, score: null, feedback: '', rubricAssessment: {} },
    ...patch,
  };
}

function build(patch: Partial<Parameters<typeof buildReminders>[0]> = {}) {
  return buildReminders({
    now,
    plan: null,
    tasks: [task()],
    courses: [{ id: '1', code: 'CS101', name: 'Lập trình', tone: 'primary' }],
    courseData: {},
    sessions: [],
    planImpacts: [],
    ...patch,
  });
}

describe('deterministic reminders', () => {
  it('honors per-kind switches without dropping unrelated reminders', () => {
    const reminders = build({ preferences: { ...defaultReminderPreferences, deadlineEnabled: false } });
    expect(reminders.some((item) => item.kind.startsWith('deadline_'))).toBe(false);
  });
  it.each([['2026-10-09T15:00:00Z', true], ['2026-10-09T23:59:00Z', true], ['2026-10-10T00:00:00Z', false]])('quiet-hour midnight boundary %s', (at, quiet) => {
    expect(inQuietHours({ ...defaultReminderPreferences, quietHoursEnabled: true }, new Date(at))).toBe(quiet);
  });
  it('creates a pending Reflect reminder then removes it after saving Reflect', () => {
    const session = { id: 's1', taskId: 'task-1', date: '2026-10-03', minutes: 30, source: 'timer' as const, completedAt: now.toISOString() };
    const reminder = build({ sessions: [session] }).find((item) => item.kind === 'reflect_session');
    expect(reminder?.scheduledAt).toBe('2026-10-03T02:05:00.000Z');
    expect(reminder?.href).toBe('/reflect?activity=session%3As1');
    expect(build({ sessions: [session], reflections: { 'activity:session:s1': { courseId: '1', weekStart: '2026-09-28', savedAt: now.toISOString(), scope: 'activity', activityId: 'session:s1', answers: ['', '', ''] } } }).some((item) => item.kind === 'reflect_session')).toBe(false);
  });
  it('raises the conditional 72-hour reminder when work has not started', () => {
    const active = activeReminders(build(), now);
    expect(active.map((item) => item.kind)).toContain('deadline_72h');
  });

  it('does not raise the 72-hour reminder when progress started and future blocks cover remaining work', () => {
    const currentTask = task({ loggedMin: 30, status: 'in_progress' });
    const reminders = build({
      tasks: [currentTask],
      plan: {
        id: 'plan-1',
        weekStart: '2026-09-28',
        savedAt: now.toISOString(),
        version: 1,
        blocks: [
          { id: 'b1', taskId: currentTask.id, date: '2026-10-03', start: '10:00', end: '11:30' },
        ],
      },
    });
    expect(reminders.map((item) => item.kind)).not.toContain('deadline_72h');
    expect(reminders.map((item) => item.kind)).toContain('deadline_24h');
  });

  it('creates study-block and missed-block reminders from the confirmed plan', () => {
    const reminders = build({
      tasks: [task({ dueAt: '2026-10-10T16:59:00.000Z' })],
      plan: {
        id: 'plan-1',
        weekStart: '2026-09-28',
        savedAt: now.toISOString(),
        version: 1,
        blocks: [
          { id: 'past', taskId: 'task-1', date: '2026-10-03', start: '07:30', end: '08:30' },
          { id: 'next', taskId: 'task-1', date: '2026-10-03', start: '09:15', end: '10:00' },
        ],
      },
    });
    const nextBlock = reminders.find((item) => item.id.startsWith('study-block:next'));
    expect(nextBlock?.scheduledAt).toBe('2026-10-03T02:00:00.000Z');
    expect(nextBlock?.href).toBe('/study/task-1/session?blockId=next');
    expect(activeReminders(reminders, now).map((item) => item.kind)).toEqual(expect.arrayContaining(['study_block', 'missed_block']));
  });

  it.each([
    ['class_session', 'online_class'],
    ['quiz', 'quiz'],
    ['midterm', 'exam_24h'],
    ['midterm', 'exam_60m'],
    ['final_exam', 'exam_24h'],
    ['final_exam', 'exam_60m'],
  ])('maps LMS %s events to %s reminders', (eventKind, expectedKind) => {
    const event: LMSCalendarItem = {
      id: `event-${eventKind}`,
      source_id: 1,
      type: 'event',
      course_id: 1,
      course_code: 'CS101',
      title: 'Sự kiện môn học',
      starts_at: '2026-10-04T02:00:00.000Z',
      ends_at: '2026-10-04T03:00:00.000Z',
      duration_minutes: 60,
      event_kind: eventKind,
      editable: false,
    };
    const reminders = build({
      tasks: [],
      courseData: { '1': { courseId: '1', modules: [], resources: [], plannerItems: [], appointmentGroups: [], calendarItems: [event] } },
    });
    expect(reminders.map((item) => item.kind)).toContain(expectedKind);
  });

  it('hands schedule-changing LMS impacts to Plan for automatic analysis, not Recover', () => {
    const reminders = build({
      tasks: [],
      planImpacts: [{
        id: 'impact-1',
        kind: 'schedule_conflict',
        title: 'Lịch học mới trùng kế hoạch',
        message: 'Một ca học mới trùng study block.',
        taskId: 'task-1',
        courseId: '1',
        deficitMin: 60,
        affectedBlockIds: ['b1'],
        detectedAt: now.toISOString(),
      }],
    });
    const item = activeReminders(reminders, now).find((entry) => entry.kind === 'lms_change');
    expect(item?.href).toBe('/plan?reanalyze=lms&impactId=impact-1&taskId=task-1&courseId=1');
    expect(item?.message).not.toContain('Phục hồi');
    expect(item?.message).toContain('chỉ đổi sau khi bạn xác nhận');
  });

  it('asks for AI reanalysis when the teacher schedule changed without a conflict', () => {
    const reminders = build({
      tasks: [],
      planImpacts: [{
        id: 'schedule-change-1',
        kind: 'schedule_changed',
        title: 'Giảng viên đã thay đổi lịch học',
        message: 'Buổi học chuyển sang 15:00–16:00. Bấm AI phân tích lại.',
        deficitMin: 0,
        affectedBlockIds: [],
        detectedAt: now.toISOString(),
      }],
    });
    const item = activeReminders(reminders, now).find((entry) => entry.kind === 'lms_change');
    expect(item).toMatchObject({
      title: 'Giảng viên đã thay đổi lịch học',
      href: '/plan?reanalyze=lms&impactId=schedule-change-1',
    });
  });

  it('creates an actionable reanalysis notification when the student joins a new course', () => {
    const reminders = build({
      tasks: [],
      planImpacts: [{
        id: 'course-added:2',
        kind: 'course_added',
        title: 'Bạn được thêm vào môn học mới',
        message: 'Bấm AI phân tích lại để cập nhật kế hoạch.',
        courseId: '2',
        deficitMin: 0,
        affectedBlockIds: [],
        detectedAt: now.toISOString(),
      }],
    });
    const item = activeReminders(reminders, now).find((entry) => entry.kind === 'lms_change');
    expect(item).toMatchObject({
      title: 'Bạn được thêm vào môn học mới',
      href: '/plan?reanalyze=lms&impactId=course-added%3A2&courseId=2',
    });
  });

  it.each([
    ['capacity_released', 'released-capacity'],
    ['deadline_later', 'later-deadline'],
    ['assignment_removed', 'removed-assignment'],
  ] as const)('keeps %s visible as an actionable Plan-change notification', (kind, id) => {
    const reminders = build({
      planImpacts: [{
        id,
        kind,
        title: 'Kế hoạch cần được kiểm tra lại',
        message: 'Dữ liệu môn học vừa thay đổi.',
        taskId: 'task-1',
        courseId: '1',
        deficitMin: 0,
        affectedBlockIds: [],
        detectedAt: now.toISOString(),
      }],
    });
    const item = activeReminders(reminders, now).find((entry) => entry.kind === 'lms_change');
    expect(item?.href).toBe(`/plan?reanalyze=lms&impactId=${id}&taskId=task-1&courseId=1`);
  });

  it('stops at three browser deliveries per local day and never hides in-app reminders', () => {
    const reminders = build({
      tasks: [
        task({ id: 'a', title: 'A' }),
        task({ id: 'b', title: 'B' }),
        task({ id: 'c', title: 'C' }),
        task({ id: 'd', title: 'D' }),
      ],
    });
    const state: ReminderState = {
      preferences: { enabled: true, browserEnabled: true, dailyCap: 3, studyBlockLeadMinutes: 15, digestHour: 20 },
      deliveredAt: {},
      readIds: [],
    };
    expect(activeReminders(reminders, now).length).toBeGreaterThan(3);
    expect(selectBrowserDeliveries(reminders, state, now)).toHaveLength(3);
    state.deliveredAt['already-sent'] = now.toISOString();
    expect(selectBrowserDeliveries(reminders, state, now)).toHaveLength(2);
  });

  it('does not remind after LMS has recorded a submission', () => {
    const reminders = build({
      tasks: [task({
        status: 'done',
        submission: { state: 'submitted', attempts: 1, submittedAt: '2026-10-02T10:00:00Z', late: false, score: null, feedback: '', rubricAssessment: {} },
      })],
    });
    expect(reminders.filter((item) => item.kind.startsWith('deadline'))).toHaveLength(0);
  });
});
