import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LessonForm, WeightsForm } from './TeacherAuthoringForms';
import type { TeacherManagementData } from '../../types/teacherManagement';

const data = (groups: TeacherManagementData['weights']['groups'] = []): TeacherManagementData => ({
  tasks: [], lessons: [], resources: [], weights: { groups, version: 'v1' },
});

describe('teacher authoring forms', () => {
  it('creates one lesson by default and explains optional weekly recurrence', async () => {
    const mutate = vi.fn().mockResolvedValue(undefined);
    const first = render(<LessonForm data={data()} mutate={mutate} onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Tên buổi học/), { target: { value: 'Chương 1' } });
    fireEvent.change(screen.getByLabelText(/Bắt đầu \(GMT\+7\)/), { target: { value: '2026-10-12T08:00' } });
    fireEvent.change(screen.getByLabelText(/Kết thúc \(GMT\+7\)/), { target: { value: '2026-10-12T09:00' } });
    expect(screen.queryByLabelText('Tổng số buổi trong chuỗi (2–16)')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu buổi học' }));
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('lessons', expect.objectContaining({ repeat_count: 1 }), 'POST'));
    first.unmount(); mutate.mockClear();

    render(<LessonForm data={data()} mutate={mutate} onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Tên buổi học/), { target: { value: 'Chương 1' } });
    fireEvent.change(screen.getByLabelText(/Bắt đầu \(GMT\+7\)/), { target: { value: '2026-10-12T08:00' } });
    fireEvent.change(screen.getByLabelText(/Kết thúc \(GMT\+7\)/), { target: { value: '2026-10-12T09:00' } });
    fireEvent.click(screen.getByLabelText('Lặp lại buổi này mỗi tuần'));
    fireEvent.change(screen.getByLabelText(/Tổng số buổi trong chuỗi/), { target: { value: '8' } });
    expect(screen.getByText(/buổi hiện tại và 7 tuần tiếp theo/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu buổi học' }));
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('lessons', expect.objectContaining({ repeat_count: 8 }), 'POST'));
  });

  it('adds a 10 percent attendance group and proportionally keeps the total at 100', async () => {
    const mutate = vi.fn().mockResolvedValue(undefined);
    render(<WeightsForm data={data([
      { id: 1, name: 'Bài tập', weight: 25 },
      { id: 2, name: 'Quiz', weight: 20 },
      { id: 3, name: 'Project', weight: 55 },
    ])} mutate={mutate} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Thêm Chuyên cần 10%' }));
    expect(screen.getByLabelText(/Nhóm 4/)).toHaveValue('Chuyên cần');
    expect(screen.getByLabelText(/Trọng số nhóm 1/)).toHaveValue(22.5);
    expect(screen.getByLabelText(/Trọng số nhóm 2/)).toHaveValue(18);
    expect(screen.getByLabelText(/Trọng số nhóm 3/)).toHaveValue(49.5);
    expect(screen.getByLabelText(/Trọng số nhóm 4/)).toHaveValue(10);
    expect(screen.getByText('Tổng trọng số: 100.00%')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu trọng số' }));
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('weights', {
      groups: [
        { id: 1, name: 'Bài tập', weight: 22.5 },
        { id: 2, name: 'Quiz', weight: 18 },
        { id: 3, name: 'Project', weight: 49.5 },
        { name: 'Chuyên cần', weight: 10 },
      ],
      expected_version: 'v1',
    }, 'PUT'));
  });
});
