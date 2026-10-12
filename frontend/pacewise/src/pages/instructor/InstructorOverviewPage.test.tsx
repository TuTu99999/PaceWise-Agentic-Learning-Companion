import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api';
import { InstructorOverviewPage } from './InstructorOverviewPage';
import type { GroupStats } from '../../types';

function makeState() {
  const stats: GroupStats = { groupId: 'all', onTimeRate: 0, onTimeCount: 0, onTimeTotal: 0, atRisk: 0,
    riskWindowDays: 14, progressImprovement: null, assignmentRisks: [], weeklyCompletion: [], topics: [] };
  return {
    user: { id: 'teacher', courseId: 'course' }, courses: [{ id: 'course', code: 'TRR', name: 'Toán rời rạc' }],
    classGroups: [{ id: 'all', name: 'Cả lớp', n: 8 }], reviewQueue: [],
    teacherWorkspace: { settings: { minimumGroupSize: 5 } }, groupStats: { all: stats } as Record<string, GroupStats>,
  };
}
const mocks = vi.hoisted(() => ({ state: {} as ReturnType<typeof makeState>, loading: false, error: null as ApiError | null, refresh: vi.fn() }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ state: mocks.state }) }));
vi.mock('../../hooks/useInstructorData', () => ({ useInstructorData: () => mocks }));

describe('instructor overview scope and truthful metrics', () => {
  beforeEach(() => {
    mocks.refresh.mockReset(); mocks.loading = false; mocks.error = null;
    mocks.state = makeState();
  });
  const show = () => render(<MemoryRouter><InstructorOverviewPage /></MemoryRouter>);

  it('shows no-data, not 0% failure; removes duplicate LMS feedback and statistics', () => {
    show();
    expect(screen.getByText('Chưa có dữ liệu')).toBeInTheDocument();
    expect(screen.getByText('Chưa có nhiệm vụ đến hạn để tính xu hướng.')).toBeInTheDocument();
    expect(screen.queryByText('Khuyến nghị ôn tập')).not.toBeInTheDocument();
    expect(screen.queryByText('Cấu trúc và hoạt động LMS')).not.toBeInTheDocument();
    expect(screen.queryByText('Trạng thái học liệu PaceWise')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Nhóm sinh viên')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }));
    expect(mocks.refresh).toHaveBeenCalledOnce();
  });

  it('uses standalone PaceWise wording while the first aggregate is loading', () => {
    mocks.loading = true; mocks.state.classGroups = [];
    show();
    expect(screen.getByText('Đang tải dữ liệu tổng hợp của môn học...')).toBeInTheDocument();
    expect(screen.getByText(/PaceWise đang tổng hợp và ẩn danh/)).toBeInTheDocument();
    expect(screen.queryByText(/đồng bộ.*LMS/i)).not.toBeInTheDocument();
  });

  it('shows course creation instead of a source error when the instructor has no course', () => {
    mocks.state.user.courseId = '0';
    mocks.state.courses = [];
    mocks.state.classGroups = [];
    show();
    expect(screen.getByText('Tạo môn học đầu tiên')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Quản lý môn học' })).toHaveAttribute('href', '/instructor/courses');
    expect(screen.queryByText(/LMS/i)).not.toBeInTheDocument();
  });

  it('does not pretend a workload estimate is known and keeps HITL non-blocking', () => {
    mocks.state.groupStats.all.assignmentRisks = [{ assignmentId: 'a', title: 'Bài quan hệ', dueAt: '2026-10-10T10:00:00Z', atRiskCount: 2, totalStudents: 8, missingMinutes: 240 }];
    mocks.state.groupStats.all.topics = [{ topic: 'Bắc cầu', needsSupport: 1, n: 5 }];
    show();
    expect(screen.getByText('Bài quan hệ')).toBeInTheDocument();
    expect(screen.queryByText(/giờ.*chưa được bảo vệ/)).not.toBeInTheDocument();
    expect(screen.getByText(/Sinh viên vẫn tiếp tục Plan–Do–Reflect/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Xem thiết kế kiểm chứng' })).toBeInTheDocument();
  });

  it('warns when cached data is stale after an error and offers retry', () => {
    mocks.error = new ApiError('UNKNOWN', 'offline');
    show();
    expect(screen.getByText('Chưa làm mới được số liệu')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
    expect(mocks.refresh).toHaveBeenCalledOnce();
  });

  it('suppresses small-cohort progress without claiming the class is failing', () => {
    mocks.state.classGroups[0].n = 4;
    mocks.state.groupStats = {};
    show();
    expect(screen.getByText('Chưa đủ dữ liệu để hiển thị.')).toBeInTheDocument();
    expect(screen.queryByText('Nộp đúng hạn')).not.toBeInTheDocument();
  });
});
