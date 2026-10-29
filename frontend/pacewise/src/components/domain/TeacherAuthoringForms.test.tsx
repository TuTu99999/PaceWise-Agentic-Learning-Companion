import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LessonForm, TaskForm, WeightsForm } from './TeacherAuthoringForms';
import type { TeacherManagementData } from '../../types/teacherManagement';
import { LocaleProvider } from '../../i18n/LocaleContext';

const { uploadTeacherDocument } = vi.hoisted(() => ({ uploadTeacherDocument: vi.fn() }));
vi.mock('../../services/api', () => ({ uploadTeacherDocument }));

const data = (groups: TeacherManagementData['weights']['groups'] = []): TeacherManagementData => ({
  tasks: [], lessons: [], resources: [], weights: { groups, version: 'v1' },
});

describe('teacher authoring forms', () => {
  beforeEach(() => window.localStorage.clear());

  it('uploads a PDF or Word assignment and attaches its resource id before creating the task', async () => {
    uploadTeacherDocument.mockResolvedValue({ fileId: 42, duplicate: false });
    const mutate = vi.fn().mockResolvedValue(undefined);
    render(<TaskForm courseId="7" data={data()} mutate={mutate} onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Tên nhiệm vụ/), { target: { value: 'Bài tập chương 2' } });
    fireEvent.change(screen.getByLabelText(/Chương \/ module của nhiệm vụ/), { target: { value: 'Chương 2' } });
    fireEvent.change(screen.getByLabelText(/Deadline \(GMT\+7\)/), { target: { value: '2026-10-20T23:59' } });
    const file = new File(['assignment'], 'bai-tap-chuong-2.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
    fireEvent.change(screen.getByLabelText('Đính kèm đề bài PDF hoặc Word'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu nhiệm vụ' }));
    await waitFor(() => expect(uploadTeacherDocument).toHaveBeenCalledWith('7', file, 'Chương 2', 'student_assignment_brief'));
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('tasks', expect.objectContaining({ resource_ids: [42], chapter: 'Chương 2' }), 'POST'));
  });

  it('does not upload an assignment document without a chapter', async () => {
    uploadTeacherDocument.mockClear();
    const mutate = vi.fn().mockResolvedValue(undefined);
    render(<TaskForm courseId="7" data={data()} mutate={mutate} onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Tên nhiệm vụ/), { target: { value: 'Bài tập' } });
    fireEvent.change(screen.getByLabelText(/Deadline \(GMT\+7\)/), { target: { value: '2026-10-20T23:59' } });
    const file = new File(['assignment'], 'bai-tap.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('Đính kèm đề bài PDF hoặc Word'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu nhiệm vụ' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nhập chương / module');
    expect(uploadTeacherDocument).not.toHaveBeenCalled();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('creates one lesson by default and supports optional weekly recurrence without extra helper copy', async () => {
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
    expect(screen.queryByText(/buổi hiện tại và 7 tuần tiếp theo/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu buổi học' }));
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('lessons', expect.objectContaining({ repeat_count: 8 }), 'POST'));
  });

  it('renders weekly recurrence in English and removes the redundant descriptions', () => {
    window.localStorage.setItem('pacewise-language', 'en');
    render(<LocaleProvider><LessonForm data={data()} mutate={vi.fn()} onClose={vi.fn()} /></LocaleProvider>);

    expect(screen.getByRole('heading', { name: 'Add class session' })).toBeInTheDocument();
    expect(screen.getByLabelText('Repeat this session weekly')).toBeInTheDocument();
    expect(screen.getByText('Repeat schedule (optional)')).toBeInTheDocument();
    expect(screen.queryByText(/Buổi học được cập nhật cho sinh viên/)).not.toBeInTheDocument();
    expect(screen.queryByText(/buổi hiện tại và 7 tuần tiếp theo/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Repeat this session weekly'));
    expect(screen.getByLabelText(/Total sessions in the series/)).toBeInTheDocument();
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
