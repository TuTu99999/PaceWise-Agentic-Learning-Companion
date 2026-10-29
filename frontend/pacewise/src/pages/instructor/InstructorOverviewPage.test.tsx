import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { InstructorDashboard } from '../../types';
import { InstructorOverviewPage } from './InstructorOverviewPage';
import { clearInstructorPageCache } from '../../services/instructorPageCache';
import { LocaleProvider } from '../../i18n/LocaleContext';

const dashboard: InstructorDashboard = {
  summary: { highRisk: 2, openWarnings: 3, overdue: 4 },
  studentAlerts: [{
    id: '1:10', studentId: '10', studentName: 'Nguyễn Minh', courseId: '1', courseCode: 'CS101',
    severity: 'high', overdueCount: 2, upcomingCount: 1, nearestDueAt: '2026-10-15T08:00:00Z',
  }],
  systemNotices: [{
    id: 'overdue:1', title: 'Rà soát deadline · CS101', message: '4 lượt nộp đã quá hạn.',
    at: '2026-10-14T07:00:00Z', tone: 'danger',
  }],
  courses: [{
    id: '1', code: 'CS101', name: 'Nhập môn lập trình Python', term: 'HK1', studentCount: 28,
    highRisk: 2, openWarnings: 3, overdue: 4, completionRate: 0.59,
    completionCount: 333, completionTotal: 560,
  }],
  weeklyCompletion: [{
    week: '05/10', weekNumber: 1, weekStart: '2026-10-05', weekEnd: '2026-10-11',
    rate: 0.59, count: 33, total: 56, scheduledTotal: 56, taskCount: 2,
    lessonCount: 2, status: 'past',
  }, {
    week: '12/10', weekNumber: 2, weekStart: '2026-10-12', weekEnd: '2026-10-18',
    rate: null, count: 0, total: 0, scheduledTotal: 0, taskCount: 0,
    lessonCount: 2, status: 'current',
  }],
  currentWeek: {
    weekNumber: 2, weekStart: '2026-10-12', weekEnd: '2026-10-18', rate: null,
    count: 0, total: 0, scheduledTotal: 0, taskCount: 0, lessonCount: 2,
  },
  privacy: { scope: 'individual', containsDirectIdentifiers: true },
  generatedAt: '2026-10-14T07:00:00Z',
};

const mocks = vi.hoisted(() => ({
  state: { user: { id: 'teacher', courseId: '1', courseIds: ['1'] }, lmsRevision: 0 },
  fetchDashboard: vi.fn(),
}));

vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ state: mocks.state }) }));
vi.mock('../../services/api', async (original) => {
  const actual = await original<typeof import('../../services/api')>();
  return { ...actual, fetchInstructorDashboard: mocks.fetchDashboard };
});

describe('instructor dashboard overview', () => {
  beforeEach(() => {
    window.localStorage.clear();
    clearInstructorPageCache();
    mocks.fetchDashboard.mockReset();
    mocks.fetchDashboard.mockResolvedValue(dashboard);
    mocks.state = { user: { id: 'teacher', courseId: '1', courseIds: ['1'] }, lmsRevision: 0 };
  });

  const show = () => render(<MemoryRouter><InstructorOverviewPage /></MemoryRouter>);

  it('renders the three requested dashboard sections in order and removes the old flow', async () => {
    const { container } = show();
    expect(await screen.findByText('Sinh viên cần chú ý')).toBeInTheDocument();
    expect(screen.queryByText('Rủi ro cao')).not.toBeInTheDocument();
    expect(screen.getAllByText('Cảnh báo mở').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Trễ hạn').length).toBeGreaterThan(0);
    expect(screen.getByText('Sinh viên có deadline đang cần chú ý.')).toBeInTheDocument();
    expect(screen.getByText('Sinh viên có ít nhất một nhiệm vụ quá hạn.')).toBeInTheDocument();
    expect(screen.getByText('Cần xử lý sớm')).toBeInTheDocument();
    expect(screen.getByText('Từ PaceWise')).toBeInTheDocument();
    expect(screen.getByText('Tổng hợp lớp đang chọn')).toBeInTheDocument();
    expect(screen.getByText('Xu hướng hoàn thành theo tuần')).toBeInTheDocument();
    expect(screen.getByText('Nguyễn Minh')).toBeInTheDocument();
    expect(screen.getByText('Mỗi cảnh báo tương ứng một sinh viên thuộc môn đang chọn.')).toBeInTheDocument();
    expect(screen.getAllByText('59%').length).toBeGreaterThan(0);
    expect(screen.getByText(/^Tuần này ·/)).toHaveTextContent('Tuần này · Tuần 2 · 12/10–18/10: Chưa có deadline đến hạn');
    expect(screen.getByText(/^Tuần 1/)).toHaveTextContent('Tuần 1 · 05/10–11/10');
    expect(screen.getByText(/^Tuần 2/)).toHaveTextContent('Tuần 2 · 12/10–18/10');
    expect(screen.getByText(/CS101 · Nhập môn lập trình Python · 2 tuần/)).toBeInTheDocument();
    expect(screen.queryByText('Tuần này: 59%')).not.toBeInTheDocument();
    expect(screen.queryByText('Tiến độ kế hoạch và bằng chứng học tập')).not.toBeInTheDocument();
    expect(screen.queryByText('Chủ đề cần chú ý')).not.toBeInTheDocument();

    const headings = [...container.querySelectorAll('h2')].map((item) => item.textContent);
    expect(headings.indexOf('Sinh viên cần chú ý')).toBeLessThan(headings.indexOf('Tổng hợp lớp đang chọn'));
    expect(headings.indexOf('Tổng hợp lớp đang chọn')).toBeLessThan(headings.indexOf('Xu hướng hoàn thành theo tuần'));
    expect(mocks.fetchDashboard).toHaveBeenCalledWith('1');
  });

  it('renders instructor overview chrome and dynamic alerts fully in English', async () => {
    window.localStorage.setItem('pacewise-language', 'en');
    render(<LocaleProvider><MemoryRouter><InstructorOverviewPage /></MemoryRouter></LocaleProvider>);

    expect(await screen.findByText('Selected class summary')).toBeInTheDocument();
    expect(screen.getByText('Students needing attention')).toBeInTheDocument();
    expect(screen.getByText('Needs prompt action')).toBeInTheDocument();
    expect(screen.getByText('From PaceWise')).toBeInTheDocument();
    expect(screen.getByText('Each alert represents one student in the selected course.')).toBeInTheDocument();
    expect(screen.getByText(/2 overdue tasks/)).toBeInTheDocument();
    expect(screen.getByText(/1 deadline within 72 hours/)).toBeInTheDocument();
    expect(screen.getByText('Review deadlines · CS101')).toBeInTheDocument();
    expect(screen.getByText('4 submissions overdue.')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Class' })).toBeInTheDocument();
    expect(screen.getByText('Nhập môn lập trình Python')).toBeInTheDocument();
  });

  it('refreshes the new cross-course dashboard', async () => {
    show();
    await screen.findByText('Tổng hợp lớp đang chọn');
    fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }));
    await waitFor(() => expect(mocks.fetchDashboard).toHaveBeenCalledTimes(2));
  });

  it('restores a fresh dashboard instantly when returning to the tab', async () => {
    const first = show();
    await screen.findByText('Tổng hợp lớp đang chọn');
    first.unmount();
    show();
    expect(screen.getByText('Tổng hợp lớp đang chọn')).toBeInTheDocument();
    expect(mocks.fetchDashboard).toHaveBeenCalledTimes(1);
  });

  it('reloads every metric and student alert for the course selected above', async () => {
    const secondCourse = {
      ...dashboard,
      summary: { highRisk: 1, openWarnings: 0, overdue: 1 },
      studentAlerts: [{
        ...dashboard.studentAlerts[0], id: '2:20', studentId: '20', studentName: 'Trần Lan',
        courseId: '2', courseCode: 'DB201', overdueCount: 1, upcomingCount: 1,
      }],
      courses: [{ ...dashboard.courses[0], id: '2', code: 'DB201', name: 'Hệ cơ sở dữ liệu' }],
    };
    mocks.fetchDashboard.mockResolvedValueOnce(dashboard).mockResolvedValueOnce(secondCourse);
    const view = show();
    expect(await screen.findByText('Nguyễn Minh')).toBeInTheDocument();

    mocks.state = { user: { id: 'teacher', courseId: '2', courseIds: ['1', '2'] }, lmsRevision: 0 };
    view.rerender(<MemoryRouter><InstructorOverviewPage /></MemoryRouter>);

    expect(await screen.findByText('Trần Lan')).toBeInTheDocument();
    expect(screen.queryByText('Nguyễn Minh')).not.toBeInTheDocument();
    expect(screen.getAllByText('DB201').length).toBeGreaterThan(0);
    expect(mocks.fetchDashboard).toHaveBeenLastCalledWith('2');
  });

  it('shows course creation when the instructor owns no active course', () => {
    mocks.state = { user: { id: 'teacher', courseId: '0', courseIds: [] }, lmsRevision: 0 };
    show();
    expect(screen.getByText('Tạo môn học đầu tiên')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Quản lý môn học' })).toHaveAttribute('href', '/instructor/courses');
    expect(mocks.fetchDashboard).not.toHaveBeenCalled();
  });

  it('shows a truthful empty trend instead of a fabricated zero', async () => {
    mocks.fetchDashboard.mockResolvedValue({ ...dashboard, weeklyCompletion: [] });
    show();
    expect(await screen.findByText('Chưa có nhiệm vụ đến hạn để tạo xu hướng.')).toBeInTheDocument();
    expect(screen.getByText(/^Tuần này ·/)).toHaveTextContent('Tuần này · Tuần 2 · 12/10–18/10: Chưa có deadline đến hạn');
  });

  it('shows the real current calendar week rate instead of the latest historical week', async () => {
    mocks.fetchDashboard.mockResolvedValue({
      ...dashboard,
      currentWeek: {
        weekNumber: 2, weekStart: '2026-10-12', weekEnd: '2026-10-18', rate: 0.75,
        count: 15, total: 20, scheduledTotal: 20, taskCount: 1, lessonCount: 2,
      },
    });
    show();
    expect(await screen.findByText(/^Tuần này ·/)).toHaveTextContent('Tuần này · Tuần 2 · 12/10–18/10: 75%');
    expect(screen.getByText(/^Tuần 1/)).toHaveTextContent('Tuần 1 · 05/10–11/10');
  });
});
