import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { uploadTeacherDocument } from '../../services/api';
import { PdfUpload } from './PdfUpload';
import { lessonChapterOptions, materialChapterOptions } from './TeacherMaterialsPanel';
import type { TeacherLesson, TeacherManagementData } from '../../types/teacherManagement';
import { LocaleProvider } from '../../i18n/LocaleContext';

vi.mock('../../services/api', () => ({ uploadTeacherDocument: vi.fn() }));

describe('chapter document batch uploads', () => {
  beforeEach(() => { vi.clearAllMocks(); window.localStorage.clear(); });
  const chapters = ['Chapter 3', 'Chapter 4'];
  const select = () => fireEvent.change(screen.getByLabelText('Tải tài liệu môn học'), { target: {
    files: [new File(['%PDF-'], 'one.pdf'), new File(['%PDF-'], 'two.pdf')],
  } });

  it('builds unique chapter choices from active imported lesson titles', () => {
    const lesson = (title: string, patch: Partial<TeacherLesson> = {}) => ({
      id: 1, title, description: '', starts_at: '', ends_at: '', mode: 'online' as const,
      location: '', meeting_url: '', resource_ids: [], cancelled: false, version: 'v1', ...patch,
    });
    expect(lessonChapterOptions([
      lesson('[CS101] Ca học online: Vòng lặp · 90 phút'), lesson('Vòng lặp'),
      lesson('Ca học trực tiếp: Hàm · 120 phút'), lesson('Đã hủy', { cancelled: true }),
    ])).toEqual(['Hàm', 'Vòng lặp']);
  });

  it('also suggests canonical task and existing material chapters', () => {
    const data = {
      lessons: [],
      tasks: [{ chapter: 'Chương 4: Ngôn ngữ SQL' }],
      resources: [{ chapter: 'Bài tập theo chương' }, { chapter: 'Chương 2: Mô hình CSDL' }],
      materials: [{ chapter: 'Chương 4: Ngôn ngữ SQL' }],
    } as unknown as TeacherManagementData;

    expect(materialChapterOptions(data)).toEqual([
      'Chương 2: Mô hình CSDL',
      'Chương 4: Ngôn ngữ SQL',
    ]);
  });

  it('uses the single batch chapter for every file and retries only a failed upload', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    vi.mocked(uploadTeacherDocument).mockResolvedValueOnce({ fileId: 1, duplicate: false })
      .mockRejectedValueOnce(new Error('Temporary failure')).mockResolvedValueOnce({ fileId: 2, duplicate: false });
    render(<PdfUpload courseId="1" chapters={chapters} onUploaded={refresh} />);
    fireEvent.change(screen.getByRole('combobox', { name: /Chương \/ module của tài liệu/ }), { target: { value: 'Chapter 3' } });
    select();
    fireEvent.change(screen.getByRole('combobox', { name: /Chương \/ module của tài liệu/ }), { target: { value: 'Chapter 4' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tải 2 tài liệu' }));
    await screen.findByText('Temporary failure');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Thử tải lại' })).toBeEnabled());
    expect(uploadTeacherDocument).toHaveBeenNthCalledWith(1, '1', expect.objectContaining({ name: 'one.pdf' }), 'Chapter 4', 'learning_material');
    expect(uploadTeacherDocument).toHaveBeenNthCalledWith(2, '1', expect.objectContaining({ name: 'two.pdf' }), 'Chapter 4', 'learning_material');
    fireEvent.click(screen.getByRole('button', { name: 'Thử tải lại' }));
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(2));
    expect(uploadTeacherDocument).toHaveBeenCalledTimes(3);
    expect(uploadTeacherDocument).toHaveBeenLastCalledWith('1', expect.objectContaining({ name: 'two.pdf' }), 'Chapter 4', 'learning_material');
  });

  it('lets an instructor type a lecture chapter even when the schedule has no topic', () => {
    render(<PdfUpload courseId="1" chapters={[]} onUploaded={vi.fn()} />);
    fireEvent.change(screen.getByRole('combobox', { name: /Chương \/ module của tài liệu/ }), {
      target: { value: '__custom_chapter__' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: 'Tên chương / module mới' }), {
      target: { value: 'Chương 4: Ngôn ngữ SQL' },
    });
    expect(screen.getByLabelText('Tải tài liệu môn học')).toBeEnabled();
    expect(screen.getByText(/Chọn chương bài giảng/)).toBeInTheDocument();
    expect(document.querySelector('datalist')).not.toBeInTheDocument();
    expect(uploadTeacherDocument).not.toHaveBeenCalled();
  });

  it('does not let an old batch overwrite the newly selected course', async () => {
    let complete!: (value: { fileId: number; duplicate: boolean }) => void;
    vi.mocked(uploadTeacherDocument).mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
    const refresh = vi.fn();
    const view = render(<PdfUpload courseId="1" chapters={chapters} onUploaded={refresh} />);
    fireEvent.change(screen.getByRole('combobox', { name: /Chương \/ module của tài liệu/ }), { target: { value: 'Chapter 3' } }); select();
    fireEvent.click(screen.getByRole('button', { name: 'Tải 2 tài liệu' }));
    view.rerender(<PdfUpload courseId="2" chapters={['Chapter 9']} onUploaded={refresh} />);
    await act(async () => complete({ fileId: 1, duplicate: false }));
    expect(screen.queryByText('one.pdf')).not.toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled(); expect(uploadTeacherDocument).toHaveBeenCalledOnce();
  });

  it('uploads a mixed Word package with an explicit privacy role', async () => {
    vi.mocked(uploadTeacherDocument).mockResolvedValue({ fileId: 9, duplicate: false });
    render(<PdfUpload courseId="1" chapters={chapters} onUploaded={vi.fn().mockResolvedValue(undefined)} />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Loại nội dung' }), { target: { value: 'mixed_assignment_package' } });
    expect(screen.getByRole('option', { name: 'Tự nhận diện nhiều chương trong Word' })).toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: /Chương \/ module của tài liệu/ }), { target: { value: 'Bài tập theo chương' } });
    fireEvent.change(screen.getByLabelText('Tải tài liệu môn học'), { target: {
      files: [new File(['word'], 'oop-assignment.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })],
    } });
    fireEvent.click(screen.getByRole('button', { name: 'Tải 1 tài liệu' }));
    await waitFor(() => expect(uploadTeacherDocument).toHaveBeenCalledWith(
      '1', expect.objectContaining({ name: 'oop-assignment.docx' }), 'Bài tập theo chương', 'mixed_assignment_package',
    ));
  });

  it('renders dynamic file labels and upload controls fully in English', () => {
    window.localStorage.setItem('pacewise-language', 'en');
    render(<LocaleProvider><PdfUpload courseId="1" chapters={chapters} onUploaded={vi.fn()} /></LocaleProvider>);
    fireEvent.change(screen.getByRole('combobox', { name: 'Document chapter / module' }), { target: { value: 'Chapter 3' } });
    fireEvent.change(screen.getByLabelText('Upload course materials'), { target: {
      files: [new File(['%PDF-'], 'lesson.pdf')],
    } });
    expect(screen.queryByRole('combobox', { name: 'Chapter for lesson.pdf' })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Content type for lesson.pdf' })).not.toBeInTheDocument();
    expect(screen.getByText(/For a Word file that includes answers/)).toBeInTheDocument();
    expect(screen.queryByText('Chọn chương / chủ đề')).not.toBeInTheDocument();
  });
});
