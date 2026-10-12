import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { InstructorDataProvider } from '../../hooks/useInstructorData';
import { fetchInstructorData, fetchLmsFileIndexStatus, retryLmsFileIndex, type InstructorData } from '../../services/api';
import { LmsMaterialStatus } from './LmsMaterialStatus';

const mocks = vi.hoisted(() => ({ state: { user: { id: 'teacher', courseId: 'a' }, lmsRevision: 0, classGroups: [] }, dispatch: vi.fn() }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => mocks }));
vi.mock('../../services/api', async (original) => ({ ...await original<object>(), fetchInstructorData: vi.fn(), fetchLmsFileIndexStatus: vi.fn(), retryLmsFileIndex: vi.fn() }));

const aggregate: InstructorData = {
  classGroups: [], groupStats: {}, reviewQueue: [], assessments: [], audit: [], guidance: [], lmsSummary: null,
  privacy: { minimumGroupSize: 5, containsDirectIdentifiers: false },
  teacherWorkspace: { schedule: [], feedback: [], courseStructure: { modules: [], knowledgeComponents: [] },
    settings: { minimumGroupSize: 5, allowIndividualReview: false, requireStudentConsent: true, autoPublishApprovedResources: false } },
};
const files = [{ id: 1, title: 'Chapter 3 PDF', status: 'indexed', chunk_count: 12, error: '', updated_at: '', view_url: '/api/v1/lms-files/1/1/download' }];
const tree = (visible = true, courseId = 'a') => <InstructorDataProvider>{visible && <LmsMaterialStatus courseId={courseId} />}</InstructorDataProvider>;

describe('LMS material status when navigating instructor tabs', () => {
  beforeEach(() => {
    sessionStorage.clear(); vi.clearAllMocks();
    vi.mocked(fetchInstructorData).mockResolvedValue(aggregate);
    vi.mocked(fetchLmsFileIndexStatus).mockResolvedValue({ files });
  });

  it('shows the cached status immediately on return without another fresh request', async () => {
    const view = render(tree());
    await screen.findByText('Chapter 3 PDF');
    view.rerender(tree(false));
    view.rerender(tree());
    expect(screen.getByText('Chapter 3 PDF')).toBeInTheDocument();
    expect(screen.queryByText('Đang tải trạng thái…')).not.toBeInTheDocument();
    expect(fetchLmsFileIndexStatus).toHaveBeenCalledOnce();
  });

  it('keeps stale status visible while revalidating after fifteen seconds', async () => {
    const now = vi.spyOn(Date, 'now').mockReturnValue(1000);
    try {
      const view = render(tree());
      await screen.findByText('Chapter 3 PDF');
      view.rerender(tree(false));
      now.mockReturnValue(17000);
      let resolve!: (value: { files: typeof files }) => void;
      vi.mocked(fetchLmsFileIndexStatus).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
      view.rerender(tree());
      expect(screen.getByText('Chapter 3 PDF')).toBeInTheDocument();
      expect(screen.queryByText('Đang tải trạng thái…')).not.toBeInTheDocument();
      await act(async () => resolve({ files: [{ ...files[0], title: 'Updated PDF' }] }));
      expect(screen.getByText('Updated PDF')).toBeInTheDocument();
    } finally { now.mockRestore(); }
  });

  it('never renders another course file while the new course is loading', async () => {
    const view = render(tree());
    await screen.findByText('Chapter 3 PDF');
    let resolve!: (value: { files: typeof files }) => void;
    vi.mocked(fetchLmsFileIndexStatus).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    view.rerender(tree(true, 'b'));
    expect(screen.queryByText('Chapter 3 PDF')).not.toBeInTheDocument();
    await act(async () => resolve({ files: [] }));
    expect(screen.getByText('Chưa có học liệu trong môn này.')).toBeInTheDocument();
  });

  it('shows ready versus queued and retries only the failed current version', async () => {
    const version = 'a'.repeat(64);
    vi.mocked(fetchLmsFileIndexStatus).mockResolvedValueOnce({ files: [
      files[0], { ...files[0], id: 2, title: 'Chapter 4 PDF', status: 'failed', error: 'Tách nhỏ file.', version },
    ] }).mockResolvedValue({ files: [{ ...files[0], id: 2, title: 'Chapter 4 PDF', status: 'queued', version }] });
    vi.mocked(retryLmsFileIndex).mockResolvedValue({ status: 'queued' });
    render(tree());
    expect(await screen.findByText('Đã có · sẵn sàng · 12 đoạn')).toHaveClass('text-success-ink');
    expect(screen.getByText('Thiếu · lỗi xử lý')).toHaveClass('text-danger-ink');
    expect(screen.getByRole('link', { name: 'Xem tài liệu Chapter 3 PDF' })).toHaveAttribute('target', '_blank');
    expect(screen.getByRole('link', { name: 'Xem tài liệu Chapter 3 PDF' })).not.toHaveAttribute('download');
    fireEvent.click(screen.getByRole('button', { name: 'Thử xử lý lại' }));
    await waitFor(() => expect(retryLmsFileIndex).toHaveBeenCalledWith('a', 2, version));
    expect(await screen.findByText('Chờ xử lý')).toBeInTheDocument();
  });
});
