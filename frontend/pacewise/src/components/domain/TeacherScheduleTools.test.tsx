import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TeacherScheduleTools } from './TeacherScheduleTools';
import { teacherScheduleAction, fetchTeacherScheduleHistory, fetchTeacherManagement } from '../../services/api';
import type { ManagedCourse, SchedulePreview } from '../../types/teacherManagement';

vi.mock('../../services/api', () => ({ teacherScheduleAction: vi.fn(), fetchTeacherScheduleHistory: vi.fn(), fetchTeacherManagement: vi.fn() }));
const courses: ManagedCourse[] = [
  { id: 1, code: 'CS101', name: 'Programming', archived: false, term: 'Demo', version: '1' },
  { id: 2, code: 'DS201', name: 'Math', archived: false, term: 'Demo', version: '2' },
  { id: 3, code: 'OLD', name: 'Old', archived: true, term: 'Demo', version: '3' },
];
const draft: SchedulePreview = { ticket: 'ticket', applied: false, mode: 'remove', counts: { removed_lessons: 2 }, errors: [], items: [],
  cancellations: [{ id: 1, course_id: 1, title: 'Old class', starts_at: '2000-01-01T02:00:00Z' }] };

beforeEach(() => {
  vi.clearAllMocks(); vi.mocked(teacherScheduleAction).mockResolvedValue(draft); vi.mocked(fetchTeacherScheduleHistory).mockResolvedValue([]);
  vi.mocked(fetchTeacherManagement).mockResolvedValue({ tasks: [], resources: [], weights: { groups: [], version: 'v1' }, lessons: [
    { id: 1, title: 'Old lesson', starts_at: '2000-01-01T02:00:00Z', ends_at: '2000-01-01T03:00:00Z', mode: 'offline',
      cancelled: false, version: 'v1', description: '', location: '', meeting_url: '', resource_ids: [] },
    { id: 2, title: 'Future lesson', starts_at: '2070-01-01T02:00:00Z', ends_at: '2070-01-01T03:00:00Z', mode: 'offline',
      cancelled: false, version: 'v1', description: '', location: '', meeting_url: '', resource_ids: [] },
  ] });
});

describe('teacher schedule preview/confirm', () => {
  it('lists course videos and exams for cleanup without changing the lesson editor', async () => {
    vi.mocked(fetchTeacherManagement).mockResolvedValueOnce({
      tasks: [], resources: [], lessons: [], weights: { groups: [], version: 'v1' },
      calendar_events: [{ id: 88, title: 'Old Python quiz', event_kind: 'quiz',
        starts_at: '2000-01-01T02:00:00Z', ends_at: '2000-01-01T03:00:00Z', mode: 'offline',
        cancelled: false, version: 'v1', description: '', location: '', meeting_url: '', resource_ids: [] }],
    });
    render(<TeacherScheduleTools courses={courses} selectedCourseId={1} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Nhập Excel / dọn lịch' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Dọn lịch' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Xóa buổi Old Python quiz' }));
    await waitFor(() => expect(teacherScheduleAction).toHaveBeenCalledWith('preview', {
      mode: 'remove', period: 'past', course_ids: [1], rows: [], lesson_ids: [88],
    }));
    expect(screen.getByText(/không xóa nhiệm vụ, deadline bài tập/)).toBeInTheDocument();
  });

  it('cleanup needs explicit scope, preview and acknowledgement; it never imports on open', async () => {
    const changed = vi.fn().mockResolvedValue(undefined);
    render(<TeacherScheduleTools courses={courses} selectedCourseId={1} onChanged={changed} />);
    fireEvent.click(screen.getByRole('button', { name: 'Nhập Excel / dọn lịch' }));
    expect(teacherScheduleAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('tab', { name: 'Dọn lịch' }));
    expect(screen.queryByLabelText('OLD · Old')).not.toBeInTheDocument();
    expect(screen.getByLabelText('CS101 · Programming')).toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Xem trước xóa tất cả trong phạm vi' }));
    const confirm = await screen.findByRole('button', { name: 'Xác nhận xóa các buổi đã chọn' });
    expect(confirm).toBeDisabled(); expect(changed).not.toHaveBeenCalled();
    expect(teacherScheduleAction).toHaveBeenLastCalledWith('preview', { mode: 'remove', period: 'past', course_ids: [1], rows: [] });
    fireEvent.click(screen.getByLabelText('Tôi đã kiểm tra đúng môn, thời gian và các thay đổi ở trên.'));
    vi.mocked(teacherScheduleAction).mockResolvedValueOnce({ ...draft, applied: true });
    fireEvent.click(confirm);
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
    expect(teacherScheduleAction).toHaveBeenLastCalledWith('confirm', { ticket: 'ticket' });
    expect(await screen.findByText(/Đã xóa khỏi lịch/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hoàn tất' })).toBeInTheDocument();
  });

  it('changing course scope invalidates preview and confirmation', async () => {
    render(<TeacherScheduleTools courses={courses} selectedCourseId={1} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Nhập Excel / dọn lịch' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Dọn lịch' }));
    fireEvent.click(screen.getByRole('button', { name: 'Xem trước xóa tất cả trong phạm vi' }));
    await screen.findByText('Old class', { exact: false });
    fireEvent.click(screen.getByLabelText('DS201 · Math'));
    expect(screen.queryByRole('button', { name: 'Xác nhận xóa các buổi đã chọn' })).not.toBeInTheDocument();
  });

  it('does not allow confirming errors and surfaces server conflict', async () => {
    vi.mocked(teacherScheduleAction).mockResolvedValueOnce({ ...draft, errors: [{ source: 'Lessons dòng 2', message: 'Trùng lịch' }] });
    render(<TeacherScheduleTools courses={courses} selectedCourseId={1} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Nhập Excel / dọn lịch' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Dọn lịch' }));
    fireEvent.click(screen.getByRole('button', { name: 'Xem trước xóa tất cả trong phạm vi' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Trùng lịch');
    expect(screen.getByRole('button', { name: 'Chưa thể nhập dữ liệu' })).toBeDisabled();
  });

  it('keeps the Excel confirmation visible and closes with a clear completion action', async () => {
    const changed = vi.fn().mockResolvedValue(undefined);
    const importDraft: SchedulePreview = { ...draft, mode: 'append', counts: { courses: 1, lessons: 2 }, cancellations: [] };
    vi.mocked(teacherScheduleAction).mockResolvedValueOnce(importDraft);
    render(<TeacherScheduleTools courses={courses} selectedCourseId={1} onChanged={changed} />);
    fireEvent.click(screen.getByRole('button', { name: 'Nhập Excel / dọn lịch' }));
    const file = new File(['schedule'], 'schedule.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    Object.defineProperty(file, 'arrayBuffer', { value: async () => new TextEncoder().encode('schedule').buffer });
    fireEvent.change(screen.getByLabelText('File lịch (.xlsx, tối đa 5 MB)'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra và xem trước file' }));

    const confirm = await screen.findByRole('button', { name: 'Xác nhận nhập dữ liệu' });
    expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Tôi đã kiểm tra đúng môn, thời gian và các thay đổi ở trên.'));
    vi.mocked(teacherScheduleAction).mockResolvedValueOnce({ ...importDraft, applied: true });
    fireEvent.click(confirm);

    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
    fireEvent.click(await screen.findByRole('button', { name: 'Hoàn tất' }));
    expect(screen.queryByRole('dialog', { name: 'Nhập và dọn lịch' })).not.toBeInTheDocument();
  });

  it('template is a download; cleanup explicitly distinguishes past from all lessons', async () => {
    render(<TeacherScheduleTools courses={courses} selectedCourseId={1} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Nhập Excel / dọn lịch' }));
    expect(screen.getByRole('link', { name: 'Tải file Excel mẫu (.xlsx)' })).toHaveAttribute('download');
    expect(screen.getByRole('button', { name: 'Kiểm tra và xem trước file' })).toBeDisabled();
    fireEvent.click(screen.getByRole('tab', { name: 'Dọn lịch' }));
    expect(screen.getByLabelText('Phạm vi buổi học')).toHaveValue('past');
    expect(await screen.findByRole('button', { name: 'Xóa buổi Old lesson' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Xóa buổi Future lesson' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Phạm vi buổi học'), { target: { value: 'all' } });
    expect(screen.getByRole('button', { name: 'Xóa buổi Future lesson' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Chọn tất cả môn đang dùng' }));
    expect(screen.getByLabelText('DS201 · Math')).toBeChecked();
  });

  it('removes an individual old lesson only after preview and acknowledgement', async () => {
    const changed = vi.fn().mockResolvedValue(undefined);
    render(<TeacherScheduleTools courses={courses} selectedCourseId={1} onChanged={changed} />);
    fireEvent.click(screen.getByRole('button', { name: 'Nhập Excel / dọn lịch' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Dọn lịch' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Xóa buổi Old lesson' }));
    const confirm = await screen.findByRole('button', { name: 'Xác nhận xóa các buổi đã chọn' });
    expect(confirm).toBeDisabled();
    expect(teacherScheduleAction).toHaveBeenCalledWith('preview', { mode: 'remove', period: 'past', course_ids: [1], rows: [], lesson_ids: [1] });
    expect(changed).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('Tôi đã kiểm tra đúng môn, thời gian và các thay đổi ở trên.'));
    vi.mocked(teacherScheduleAction).mockResolvedValueOnce({ ...draft, applied: true });
    vi.mocked(fetchTeacherManagement).mockResolvedValueOnce({ tasks: [], resources: [], lessons: [], weights: { groups: [], version: 'v2' } });
    fireEvent.click(confirm);
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Xóa buổi Old lesson' })).not.toBeInTheDocument());
  });

  it('all-course removal respects explicit scope and inclusive GMT+7 dates', async () => {
    render(<TeacherScheduleTools courses={courses} selectedCourseId={1} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Nhập Excel / dọn lịch' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Dọn lịch' }));
    fireEvent.click(screen.getByRole('button', { name: 'Chọn tất cả môn đang dùng' }));
    fireEvent.change(screen.getByLabelText('Phạm vi buổi học'), { target: { value: 'all' } });
    fireEvent.change(screen.getByLabelText('Từ ngày (để trống: không giới hạn)'), { target: { value: '2000-01-01' } });
    fireEvent.change(screen.getByLabelText('Đến ngày (để trống: không giới hạn)'), { target: { value: '2000-01-01' } });
    fireEvent.click(screen.getByRole('button', { name: 'Xem trước xóa tất cả trong phạm vi' }));
    await waitFor(() => expect(teacherScheduleAction).toHaveBeenCalledWith('preview', {
      mode: 'remove', period: 'all', course_ids: [1, 2], rows: [],
      from_at: '2000-01-01T00:00:00+07:00', until_at: '2000-01-01T17:00:00.000Z',
    }));
  });

  it('changing period clears acknowledgement and restoring old removals refreshes the parent', async () => {
    const changed = vi.fn().mockResolvedValue(undefined);
    vi.mocked(fetchTeacherScheduleHistory).mockResolvedValue([{ ...draft, applied: true, courses: ['1'] }]);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<TeacherScheduleTools courses={courses} selectedCourseId={1} onChanged={changed} />);
    fireEvent.click(screen.getByRole('button', { name: 'Nhập Excel / dọn lịch' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Dọn lịch' }));
    fireEvent.click(screen.getByRole('button', { name: 'Xem trước xóa tất cả trong phạm vi' }));
    await screen.findByRole('button', { name: 'Xác nhận xóa các buổi đã chọn' });
    fireEvent.change(screen.getByLabelText('Phạm vi buổi học'), { target: { value: 'all' } });
    expect(screen.queryByRole('button', { name: 'Xác nhận xóa các buổi đã chọn' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Lịch sử / khôi phục' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Khôi phục buổi học' }));
    await waitFor(() => expect(teacherScheduleAction).toHaveBeenCalledWith('restore', { ticket: 'ticket' }));
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  });

  it('clearly distinguishes a deletion history entry from a restored live schedule', async () => {
    vi.mocked(fetchTeacherScheduleHistory).mockResolvedValue([
      { ...draft, applied: true, courses: ['1'] },
      { ...draft, ticket: 'restored', applied: true, restored: true, courses: ['1'] },
    ]);
    render(<TeacherScheduleTools courses={courses} selectedCourseId={1} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Nhập Excel / dọn lịch' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Lịch sử / khôi phục' }));
    expect(await screen.findByText('Đã xóa khỏi lịch — chỉ giữ bản ghi để khôi phục.')).toBeInTheDocument();
    expect(screen.getByText('Đã khôi phục — các buổi đã được đưa lại vào lịch.')).toBeInTheDocument();
    expect(screen.getByText(/Đây là nhật ký các thao tác/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Khôi phục buổi học' })).toHaveLength(1);
    expect(teacherScheduleAction).not.toHaveBeenCalled();
  });
});
