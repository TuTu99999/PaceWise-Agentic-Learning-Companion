import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CourseSwitcher } from './CourseSwitcher';

const mocks = vi.hoisted(() => ({
  dispatch: vi.fn(),
  toast: vi.fn(),
  switchCourse: vi.fn(),
  syncCanvas: vi.fn(),
}));

vi.mock('../../store/AppStore', () => ({
  useAppStore: () => ({
    state: {
      user: { courseId: '1' },
      courseScope: '1',
      courses: [
        { id: '1', code: 'CS101', name: 'Lập trình' },
        { id: '2', code: 'TRR', name: 'Toán rời rạc' },
      ],
    },
    dispatch: mocks.dispatch,
  }),
}));
vi.mock('../ui/Toast', () => ({ useToast: () => mocks.toast }));
vi.mock('../../services/api', () => ({
  switchCourse: mocks.switchCourse,
  syncCanvas: mocks.syncCanvas,
}));

describe('CourseSwitcher success notification preference', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.switchCourse.mockResolvedValue({ courseId: '2' });
    mocks.syncCanvas.mockResolvedValue({
      activeCourseId: '2', courses: [], tasks: [], guidance: [], assessments: [], courseData: {},
    });
  });

  it('switches and syncs silently when success notifications are disabled', async () => {
    render(<CourseSwitcher notifyOnSuccess={false} />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2' } });
    await waitFor(() => expect(mocks.dispatch).toHaveBeenCalledWith({ type: 'SET_ACTIVE_COURSE', courseId: '2' }));
    await waitFor(() => expect(mocks.dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'SYNC_CANVAS' })));
    expect(mocks.toast).not.toHaveBeenCalled();
  });

  it('keeps existing success notifications elsewhere', async () => {
    render(<CourseSwitcher />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2' } });
    await waitFor(() => expect(mocks.toast).toHaveBeenCalledWith({ tone: 'success', title: 'Đã chuyển môn học' }));
  });

  it('still reports switch failures when success notifications are disabled', async () => {
    mocks.switchCourse.mockRejectedValue(new Error('Không thể kết nối'));
    render(<CourseSwitcher notifyOnSuccess={false} />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2' } });
    await waitFor(() => expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({
      tone: 'danger', title: 'Chưa chuyển được môn học',
    })));
    expect(mocks.dispatch).not.toHaveBeenCalled();
    expect(mocks.syncCanvas).not.toHaveBeenCalled();
  });

  it('still warns when the new course cannot be refreshed', async () => {
    mocks.syncCanvas.mockRejectedValue(new Error('Sync unavailable'));
    render(<CourseSwitcher notifyOnSuccess={false} />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2' } });
    await waitFor(() => expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({
      tone: 'warning', title: 'Đã chuyển môn, nhưng chưa làm mới được dữ liệu',
    })));
    expect(mocks.toast).not.toHaveBeenCalledWith(expect.objectContaining({ tone: 'success' }));
  });
});
