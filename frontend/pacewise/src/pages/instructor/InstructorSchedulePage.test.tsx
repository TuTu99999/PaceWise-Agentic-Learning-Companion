import { fireEvent, render as rtlRender, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Course, LMSCalendarItem, LMSCourseData } from '../../types';
import { InstructorSchedulePage } from './InstructorSchedulePage';
const render = (ui: ReactElement) => rtlRender(ui, { wrapper: MemoryRouter });

const fixture = vi.hoisted(() => ({ state: {} as {
  courses: Course[]; courseData: Record<string, LMSCourseData>; workspaceReady: boolean; settings: { staleData: boolean };
} }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ state: fixture.state }) }));
// Isolate the read-only grid from the independently mounted LMS authoring controller.
vi.mock('../../components/domain/TeacherLessonManager', () => ({ TeacherLessonManager: () => null }));
const event = (id: string, courseId: number, title: string): LMSCalendarItem => ({
  id, source_id: courseId, type: 'event', course_id: courseId, course_code: null, title,
  starts_at: '2026-10-05T09:07:00+07:00', ends_at: '2026-10-05T10:22:00+07:00',
  duration_minutes: 75, event_kind: 'class', editable: true, location: 'Phòng A101',
});
const snapshot = (courseId: string, calendarItems: LMSCalendarItem[]): LMSCourseData => ({
  courseId, calendarItems, modules: [], resources: [], plannerItems: [], appointmentGroups: [],
});

beforeEach(() => {
  fixture.state = {
    courses: [{ id: '1', code: 'CS101', name: 'Python', tone: 'primary' }, { id: '2', code: 'TRR', name: 'Toán rời rạc', tone: 'accent' }],
    courseData: {
      '1': snapshot('1', [event('python', 1, 'Buổi Python')]),
      '2': snapshot('2', [event('relations', 2, 'Chương 3: Quan hệ hai ngôi')]),
    },
    workspaceReady: true, settings: { staleData: false },
  };
});

describe('InstructorSchedulePage read-only calendar', () => {
  it('defaults to all courses and omits every student or editing control', () => {
    render(<InstructorSchedulePage />);
    expect(screen.getByLabelText('Lọc lịch theo môn học')).toHaveValue('all');
    expect(screen.getByText('CS101 · Buổi Python')).toBeInTheDocument();
    expect(screen.getByText('TRR · Chương 3: Quan hệ hai ngôi')).toBeInTheDocument();
    expect(screen.getByLabelText('Lịch tuần chỉ xem')).toBeInTheDocument();
    expect(screen.queryByText('00:00')).not.toBeInTheDocument();
    expect(screen.queryByText('06:00')).not.toBeInTheDocument();
    expect(screen.getByText('07:00')).toBeInTheDocument();
    for (const name of [/Thêm buổi học/, /AI lập kế hoạch/, /Study block/, /Giờ sinh hoạt/, /Bắt đầu DO/, /Reflect/, /Xóa/, /Thay đổi thời lượng/]) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByText('Lịch cá nhân')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Chọn nhiệm vụ')).not.toBeInTheDocument();
    expect(document.querySelectorAll('[draggable="true"]')).toHaveLength(0);
  });

  it('filters locally by course and restores all courses', () => {
    render(<InstructorSchedulePage />);
    fireEvent.change(screen.getByLabelText('Lọc lịch theo môn học'), { target: { value: '2' } });
    expect(screen.queryByText('CS101 · Buổi Python')).not.toBeInTheDocument();
    expect(screen.getByText('TRR · Chương 3: Quan hệ hai ngôi')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Lọc lịch theo môn học'), { target: { value: 'all' } });
    expect(screen.getByText('CS101 · Buổi Python')).toBeInTheDocument();
  });

  it('opens a view-only detail dialog and never exposes save controls', () => {
    render(<InstructorSchedulePage />);
    fireEvent.click(screen.getByTitle('09:07–10:22 · Buổi Python'));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Phòng A101')).toBeInTheDocument();
    expect(within(dialog).getByText('CS101 · Python')).toBeInTheDocument();
    expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: /Lưu|Sửa|Xóa|DO|Reflect/ })).not.toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('supports month, drilling into a week, next-seven-days, and date navigation', () => {
    render(<InstructorSchedulePage />);
    fireEvent.click(screen.getByRole('button', { name: 'Tháng' }));
    expect(screen.getByLabelText('Tổng quan tháng')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Thứ Hai 05/10 · 2 mục' }));
    expect(screen.getByRole('button', { name: 'Tuần' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.change(screen.getByLabelText('Chọn ngày'), { target: { value: '2026-10-08' } });
    fireEvent.click(screen.getByRole('button', { name: '7 ngày tới' }));
    expect(screen.getByLabelText('Lịch ngày 2026-10-08')).toBeInTheDocument();
    expect(screen.getByLabelText('Lịch ngày 2026-10-14')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Khoảng sau' }));
    expect(screen.getByLabelText('Chọn ngày')).toHaveValue('2026-10-15');
    fireEvent.click(screen.getByRole('button', { name: 'Hôm nay' }));
    expect(screen.getByLabelText('Chọn ngày')).toHaveValue('2026-10-05');
  });

  it('updates displayed events when the synchronized snapshot changes', () => {
    const { rerender } = render(<InstructorSchedulePage />);
    fixture.state = { ...fixture.state, courseData: { ...fixture.state.courseData, '1': snapshot('1', [event('python', 1, 'Buổi Python cập nhật')]) } };
    rerender(<InstructorSchedulePage />);
    expect(screen.queryByText('CS101 · Buổi Python')).not.toBeInTheDocument();
    expect(screen.getByText('CS101 · Buổi Python cập nhật')).toBeInTheDocument();
  });

  it('shows loading, empty, and stale-data states without student actions', () => {
    fixture.state = { ...fixture.state, courseData: {}, workspaceReady: false };
    const { rerender } = render(<InstructorSchedulePage />);
    expect(screen.getByRole('status')).toHaveTextContent('Đang tải lịch dạy');
    fixture.state = { ...fixture.state, workspaceReady: true, settings: { staleData: true } };
    rerender(<InstructorSchedulePage />);
    expect(screen.getByText('Chưa có lịch cho môn học và khoảng thời gian đang chọn.')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Đồng bộ chưa thành công');
  });
});
