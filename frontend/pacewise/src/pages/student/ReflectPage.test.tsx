import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ReflectPage } from './ReflectPage';
import { confirmReflection, createReflection } from '../../services/api';
import { LocaleProvider } from '../../i18n/LocaleContext';
import { PACEWISE_LANGUAGE_STORAGE_KEY } from '../../utils/uiPreferences';

const dispatch = vi.fn();
let state: Record<string, unknown>;

vi.mock('../../store/AppStore', () => ({
  useAppStore: () => ({ state, dispatch }),
}));
vi.mock('../../components/ui/Toast', () => ({ useToast: () => vi.fn() }));
vi.mock('../../services/api', () => ({
  createReflection: vi.fn(),
  confirmReflection: vi.fn(),
}));

describe('weekly reflection scope', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.removeItem(PACEWISE_LANGUAGE_STORAGE_KEY);
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-12T10:00:00.000Z')); // Monday 17:00 in Vietnam.
    state = {
      plan: {
        id: 'current',
        weekStart: '2026-10-12',
        savedAt: '2026-10-12T09:00:00Z',
        version: 2,
        blocks: [
          { id: 'future', taskId: 't-current', date: '2026-10-13', start: '08:00', end: '09:00' },
        ],
      },
      planHistory: [{
        id: 'previous',
        weekStart: '2026-10-05',
        savedAt: '2026-10-11T13:00:00Z',
        version: 1,
        blocks: [
          { id: 'past', taskId: 't-previous', date: '2026-10-06', start: '08:00', end: '09:00' },
        ],
      }],
      sessions: [{
        id: 'session-previous',
        taskId: 't-previous',
        blockId: 'past',
        date: '2026-10-06',
        minutes: 50,
        completionPercent: 100,
      }],
      tasks: [
        { id: 't-previous', courseId: 'course-1', title: 'Bài tuần trước', deadline: '2026-10-11T23:59:00+07:00', estimateMin: 60, status: 'done' },
        { id: 't-current', courseId: 'course-1', title: 'Bài tuần này', deadline: '2026-10-18T23:59:00+07:00', estimateMin: 60, status: 'todo' },
      ],
      courses: [{ id: 'course-1', code: 'CS101', name: 'Cơ sở dữ liệu' }],
      courseData: {},
      reflections: {},
    };
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders weekly reflection system text fully in English', () => {
    localStorage.setItem(PACEWISE_LANGUAGE_STORAGE_KEY, 'en');
    state = {
      ...state,
      plan: {
        id: 'current', weekStart: '2026-10-12', savedAt: '2026-10-12T09:00:00Z', version: 2,
        blocks: [{ id: 'current-do', taskId: 't-current', date: '2026-10-12', start: '08:00', end: '09:10', milestoneTitle: 'Hoàn thành Bài tập Chương 2: Mô hình cơ sở dữ liệu' }],
      },
      sessions: [{
        id: 'session-current', taskId: 't-current', blockId: 'current-do', date: '2026-10-12', minutes: 70,
        completionPercent: 100, outcome: 'planned_part_done', workResult: 'planned_part_done', remainingMinutes: 0,
      }],
      reflections: {
        'all:2026-10-12': {
          courseId: 'all',
          weekStart: '2026-10-12',
          scope: 'weekly',
          answers: [
            'Tuần này đã hoàn thành',
            'Nguyên nhân kế hoạch đúng là do t cố gắng học ở trên trường, trao dồi kiến thức.',
            'Tuần sau vẫn giữ nguyên thời lượng như này',
          ],
          savedAt: '2026-10-12T09:30:00.000Z',
        },
      },
    };

    render(<LocaleProvider><MemoryRouter><ReflectPage /></MemoryRouter></LocaleProvider>);

    expect(screen.getByText('All activities this week')).toBeVisible();
    expect(screen.getByText(/^1 activity · all courses ·/)).toBeVisible();
    expect(screen.getByText('Complete Chapter 2 assignment: Database models')).toBeVisible();
    expect(screen.getByText(/1 hour 10 minutes actual · 100%/)).toBeVisible();
    expect(screen.getByText(/A provisional weekly reflection is available/)).toBeVisible();
    expect(screen.getByText(/Plan is using the latest version/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Reflect again' })).toBeVisible();
    expect(screen.getByDisplayValue("I completed this week's work.")).toBeDisabled();
    expect(screen.getByDisplayValue('The plan stayed on track because I worked hard in class and strengthened my knowledge.')).toBeDisabled();
    expect(screen.getByDisplayValue('Keep the same study duration next week.')).toBeDisabled();
    expect(screen.queryByText(/tất cả môn|Phản tư tiếp|Plan đang dùng bản mới nhất/)).not.toBeInTheDocument();
  });

  it('defaults to the current calendar week and lets the learner inspect last week', () => {
    render(<MemoryRouter><ReflectPage /></MemoryRouter>);

    expect(screen.getByText(/Bạn đang phản tư sớm/)).toBeInTheDocument();
    expect(screen.getByText(/1 nhiệm vụ và 1 giờ chỉ là phần đã lên kế hoạch, không phải bằng chứng đã học/)).toBeInTheDocument();
    expect(screen.getByText('Phiên Do đã ghi nhận')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Tuần vừa qua/ }));

    expect(screen.getByText(/Đang tổng kết tuần đã kết thúc 05\/10–11\/10/)).toBeInTheDocument();
    expect(screen.getByText('1 mốc · tất cả môn · 05/10–11/10')).toBeInTheDocument();
    expect(screen.queryByText(/Bạn đang phản tư sớm/)).not.toBeInTheDocument();
  });

  it('shows the current weekly reflection and unlocks it through Phản tư tiếp', () => {
    state = {
      ...state,
      reflections: {
        'all:2026-10-12': {
          courseId: 'all',
          weekStart: '2026-10-12',
          scope: 'weekly',
          answers: ['Đã học phần mô hình.', 'Thiếu thời gian.', 'Ôn thêm.'],
          savedAt: '2026-10-12T09:30:00.000Z',
        },
      },
    };

    render(<MemoryRouter><ReflectPage /></MemoryRouter>);

    expect(screen.getByText(/Đã có phản tư tuần này — bản tạm thời/)).toBeInTheDocument();
    expect(screen.getByText(/Plan đang dùng bản mới nhất/)).toBeInTheDocument();
    expect(screen.getAllByRole('textbox')[0]).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Phản tư tiếp' }));
    expect(screen.getAllByRole('textbox')[0]).toBeEnabled();
  });

  it('treats the latest saved reflection as the weekly summary on Sunday', () => {
    vi.setSystemTime(new Date('2026-10-18T03:00:00.000Z')); // Sunday 10:00 in Vietnam.
    state = {
      ...state,
      reflections: {
        'all:2026-10-12': {
          courseId: 'all',
          weekStart: '2026-10-12',
          scope: 'weekly',
          answers: ['Đã học.', 'Đúng kế hoạch.', 'Tiếp tục.'],
          savedAt: '2026-10-17T14:00:00.000Z',
        },
      },
    };

    render(<MemoryRouter><ReflectPage /></MemoryRouter>);

    expect(screen.getByText(/Đã có tổng kết tuần/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Phản tư tiếp' })).toBeInTheDocument();
  });

  it('opens an explicitly requested historical activity in its own week', () => {
    render(<MemoryRouter initialEntries={['/reflect?activity=study:past']}><ReflectPage /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'Phản tư sau phiên học' })).toBeInTheDocument();
    expect(screen.getByText('Sau phiên này bạn đang ở mức nào?')).toBeInTheDocument();
  });

  it('keeps quick weeks fixed and opens a date picker for older weeks', () => {
    render(<MemoryRouter><ReflectPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: /Chọn tuần khác/ }));
    fireEvent.change(screen.getByLabelText('Chọn một ngày trong tuần'), {
      target: { value: '2026-09-23' },
    });

    expect(screen.getByRole('button', { name: /Tuần 21\/09–27\/09/ })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getAllByRole('button', { name: /Tuần vừa qua|Tuần này/ })).toHaveLength(2);
  });

  it('shows only three recent activities until the learner expands the list', () => {
    const blocks = Array.from({ length: 5 }, (_, index) => ({
      id: `past-${index + 1}`,
      taskId: `task-${index + 1}`,
      date: `2026-10-${String(index + 6).padStart(2, '0')}`,
      start: '08:00',
      end: '09:00',
      milestoneTitle: `Task ${index + 1}`,
    }));
    state = {
      ...state,
      planHistory: [{
        id: 'previous',
        weekStart: '2026-10-05',
        savedAt: '2026-10-11T13:00:00Z',
        version: 1,
        blocks,
      }],
      sessions: blocks.map((block, index) => ({
        id: `session-${index + 1}`,
        taskId: block.taskId,
        blockId: block.id,
        date: block.date,
        minutes: 50,
        completionPercent: 100,
      })),
      tasks: blocks.map((block) => ({
        id: block.taskId,
        courseId: 'course-1',
        title: block.milestoneTitle,
        deadline: `${block.date}T23:59:00+07:00`,
        estimateMin: 60,
        status: 'done',
      })),
    };

    render(<MemoryRouter><ReflectPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: /Tuần vừa qua/ }));
    expect(screen.getByText('Task 5')).toBeInTheDocument();
    expect(screen.queryByText('Task 1')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Xem thêm 2 hoạt động/ }));
    expect(screen.getByText('Task 1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Thu gọn hoạt động/ })).toBeInTheDocument();
  });

  it('submits structured Do reflection and carries trusted remaining minutes into replan', async () => {
    vi.useRealTimers();
    state = {
      ...state,
      plan: {
        id: 'current', weekStart: '2026-10-12', savedAt: '2026-10-12T09:00:00Z', version: 2,
        blocks: [{ id: 'current-do', taskId: 't-current', date: '2026-10-12', start: '08:00', end: '09:00', milestoneTitle: 'Phần dự kiến' }],
      },
      sessions: [{
        id: 'session-current', taskId: 't-current', blockId: 'current-do', date: '2026-10-12', minutes: 45,
        outcome: 'needs_more_time', workResult: 'needs_more_time', remainingMinutes: 30,
      }],
    };
    vi.mocked(createReflection).mockResolvedValue({
      workflow: 'reflect', status: 'awaiting_student', response: 'Bản phản tư', reflection_draft: {},
    } as never);
    vi.mocked(confirmReflection).mockResolvedValue({
      output: { replan_decision: { action: 'propose_draft', reasons: ['unfinished_work'], requires_confirmation: true, auto_apply: false } },
    } as never);

    render(<MemoryRouter initialEntries={['/reflect?activity=study:current-do']}><ReflectPage /></MemoryRouter>);
    expect(screen.queryByText('Chưa xong; cần thêm 30 phút.')).not.toBeInTheDocument();
    expect(screen.queryByText('Kết quả đã ghi nhận từ phiên Do')).not.toBeInTheDocument();
    expect(screen.queryByText(/thực tế 45 phút/)).not.toBeInTheDocument();
    expect(screen.queryByText(/0\/500 ký tự/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Làm bài kiểm tra' })).toBeVisible();
    expect(screen.queryByText('Làm Assessment')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Hiểu một phần, cần ôn lại' }));
    fireEvent.click(screen.getByRole('button', { name: 'AI phản tư mốc này' }));

    await waitFor(() => expect(createReflection).toHaveBeenCalled());
    expect(vi.mocked(createReflection).mock.calls[0][1]).toMatchObject({
      reflection_scope: 'activity',
      activity: {
        block_id: 'current-do',
        remaining_minutes: 30,
        work_result: 'needs_more_time',
        understanding_self_report: 'needs_review',
      },
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Lưu và về lịch học' }));
    await waitFor(() => expect(confirmReflection).toHaveBeenCalledWith('activity', 'course-1', 'vi'));
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: 'SAVE_REFLECTION',
      activityFeedback: expect.objectContaining({ understanding: 'needs_review', nextAction: 'continue_task' }),
    }));
  });

  it('sends English structured activity evidence and locale to the Reflection Agent', async () => {
    vi.useRealTimers();
    localStorage.setItem(PACEWISE_LANGUAGE_STORAGE_KEY, 'en');
    state = {
      ...state,
      plan: {
        id: 'current', weekStart: '2026-10-12', savedAt: '2026-10-12T09:00:00Z', version: 2,
        blocks: [{ id: 'current-do', taskId: 't-current', date: '2026-10-12', start: '08:00', end: '09:00', milestoneTitle: 'Planned section' }],
      },
      sessions: [{
        id: 'session-current', taskId: 't-current', blockId: 'current-do', date: '2026-10-12', minutes: 45,
        outcome: 'planned_part_done', workResult: 'planned_part_done', remainingMinutes: 0,
      }],
    };
    vi.mocked(createReflection).mockResolvedValue({
      workflow: 'reflect', status: 'awaiting_student', response: 'AI draft', reflection_draft: {},
    } as never);

    render(<LocaleProvider><MemoryRouter initialEntries={['/reflect?activity=study:current-do']}><ReflectPage /></MemoryRouter></LocaleProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Generate reflection' }));

    await waitFor(() => expect(createReflection).toHaveBeenCalled());
    expect(vi.mocked(createReflection).mock.calls[0][0]).toEqual([
      'The planned work for this session was completed.',
      'Self-assessment: Can continue independently. Obstacle: None.',
      'Move to the next task.',
    ]);
    expect(vi.mocked(createReflection).mock.calls[0][2]).toBe('en');
  });
});
