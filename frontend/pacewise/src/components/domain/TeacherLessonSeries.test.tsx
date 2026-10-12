import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TeacherLessonManager } from './TeacherLessonManager';
import { teacherScheduleAction } from '../../services/api';

const { mutate, refresh } = vi.hoisted(() => ({ mutate: vi.fn(), refresh: vi.fn() }));
vi.mock('../../services/api', () => ({ teacherScheduleAction: vi.fn() }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ state: {
  user: { courseId: '1' }, courses: [{ id: '1', code: 'CS101' }],
} }) }));
vi.mock('../../hooks/useTeacherManagement', () => ({ useTeacherManagement: () => ({
  loading: false, error: '', mutate, refreshAfterMutation: refresh, reload: vi.fn(),
  data: { lessons: [{ id: 5, title: 'Weekly lesson', starts_at: '2070-10-12T09:00:00+07:00', ends_at: '2070-10-12T10:00:00+07:00',
    mode: 'offline', location: 'A101', meeting_url: '', resource_ids: [], description: '', series_key: 'series', version: 'v1', cancelled: false },
    { id: 6, title: 'Past lesson', starts_at: '2000-01-01T09:00:00+07:00', ends_at: '2000-01-01T10:00:00+07:00',
      mode: 'offline', location: '', meeting_url: '', resource_ids: [], description: '', version: 'v1', cancelled: false }],
    resources: [], tasks: [], materials: [], weights: { groups: [], version: 'v1' } },
}) }));

describe('teacher recurring lesson editing', () => {
  it('previews the series and only commits after the separate confirmation', async () => {
    vi.mocked(teacherScheduleAction).mockResolvedValue({ ticket: 'series-ticket', mode: 'replace_series', applied: false,
      counts: { lessons: 2, cancelled_lessons: 2 }, errors: [], items: [], cancellations: [] });
    render(<TeacherLessonManager inline preferredCourseId="1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Sửa các buổi còn lại của chuỗi' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Tên buổi học' }), { target: { value: 'Updated weekly lesson' } });
    fireEvent.click(screen.getByRole('button', { name: 'Xem trước thay đổi chuỗi' }));
    const confirm = await screen.findByRole('button', { name: 'Xác nhận sửa 2 buổi' });
    expect(teacherScheduleAction).toHaveBeenCalledTimes(1);
    expect(teacherScheduleAction).toHaveBeenCalledWith('series-preview', expect.objectContaining({
      course_ids: [1], series_lesson_id: 5, expected_version: 'v1', title: 'Updated weekly lesson', repeat_count: 1,
    }));
    expect(mutate).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
    fireEvent.click(confirm);
    await waitFor(() => expect(teacherScheduleAction).toHaveBeenCalledWith('confirm', { ticket: 'series-ticket' }));
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
  });

  it('shows removal for a past lesson while keeping edit/cancel restricted to the future', async () => {
    vi.clearAllMocks();
    vi.mocked(teacherScheduleAction).mockResolvedValue({ ticket: 'remove-ticket', mode: 'remove', applied: false,
      counts: { removed_lessons: 1 }, errors: [], items: [], cancellations: [] });
    render(<TeacherLessonManager inline preferredCourseId="1" />);
    fireEvent.change(screen.getByLabelText('Lọc buổi học'), { target: { value: 'past' } });
    expect(screen.queryByRole('button', { name: 'Sửa buổi' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hủy buổi' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Xóa buổi Past lesson' }));
    const confirm = await screen.findByRole('button', { name: 'Xác nhận xóa 1 buổi' });
    expect(teacherScheduleAction).toHaveBeenCalledWith('preview', {
      mode: 'remove', period: 'all', course_ids: [1], lesson_ids: [6], rows: [],
    });
    expect(refresh).not.toHaveBeenCalled();
    fireEvent.click(confirm);
    await waitFor(() => expect(teacherScheduleAction).toHaveBeenCalledWith('confirm', { ticket: 'remove-ticket' }));
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    expect(mutate).not.toHaveBeenCalled();
  });
});
