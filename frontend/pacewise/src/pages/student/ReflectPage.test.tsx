import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ReflectPage } from './ReflectPage';

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

  it('defaults to the finished week and keeps current-week planning separate from observed learning', () => {
    render(<MemoryRouter><ReflectPage /></MemoryRouter>);

    expect(screen.getByText(/Đang tổng kết tuần đã kết thúc 05\/10–11\/10/)).toBeInTheDocument();
    expect(screen.getByText('1 mốc · tất cả môn · 05/10–11/10')).toBeInTheDocument();
    expect(screen.getByText('Phiên Do đã ghi nhận')).toBeInTheDocument();
    expect(screen.queryByText(/Bạn đang phản tư sớm/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Tuần này/ }));

    expect(screen.getByText(/Bạn đang phản tư sớm/)).toBeInTheDocument();
    expect(screen.getByText(/1 nhiệm vụ và 1 giờ chỉ là phần đã lên kế hoạch, không phải bằng chứng đã học/)).toBeInTheDocument();
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

    expect(screen.getByText('Task 5')).toBeInTheDocument();
    expect(screen.queryByText('Task 1')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Xem thêm 2 hoạt động/ }));
    expect(screen.getByText('Task 1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Thu gọn hoạt động/ })).toBeInTheDocument();
  });
});
