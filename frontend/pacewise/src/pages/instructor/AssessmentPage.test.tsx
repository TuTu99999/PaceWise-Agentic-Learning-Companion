import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { deleteAssessmentDesign } from '../../services/api';
import type { AssessmentItem } from '../../types';
import { AssessmentPage } from './AssessmentPage';
import { LocaleProvider } from '../../i18n/LocaleContext';

const mocks = vi.hoisted(() => ({ dispatch: vi.fn(), toast: vi.fn(), assessments: [] as AssessmentItem[] }));

vi.mock('../../hooks/useInstructorData', () => ({ useInstructorData: () => ({ loading: false, error: null }) }));
vi.mock('../../components/ui/Toast', () => ({ useToast: () => mocks.toast }));
vi.mock('../../services/api', () => ({ deleteAssessmentDesign: vi.fn(), saveInstructorAction: vi.fn() }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ dispatch: mocks.dispatch, state: {
  assessments: mocks.assessments,
  courseScope: 'all',
  user: { id: 'teacher-1', courseId: '7' },
  teacherWorkspace: { courseStructure: { knowledgeComponents: [
    { id: 'kc-relations', name: 'Quan hệ hai ngôi', status: 'approved' },
  ] } },
} }) }));

describe('Assessment bank authoring', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    mocks.assessments = [];
  });

  it('uses English for the question-set entry point and omits the two long helper lines', () => {
    window.localStorage.setItem('pacewise-language', 'en');
    render(<LocaleProvider><MemoryRouter><AssessmentPage /></MemoryRouter></LocaleProvider>);

    expect(screen.getByRole('button', { name: 'Create question set' })).toBeInTheDocument();
    expect(screen.getByText('No approved assessments yet')).toBeInTheDocument();
    expect(screen.queryByText(/Mỗi chương nên có 3–5 câu tự luận/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Tạo câu hỏi tự luận, chọn chương và tài liệu/)).not.toBeInTheDocument();
  });

  it('creates an editable course/KC-scoped draft so Do can receive an approved check', () => {
    render(<MemoryRouter initialEntries={['/instructor/assessment']}>
      <Routes>
        <Route path="/instructor/assessment" element={<AssessmentPage />} />
        <Route path="/instructor/assessment/:itemId" element={<p>Trình soạn câu kiểm tra</p>} />
      </Routes>
    </MemoryRouter>);

    expect(screen.queryByText('chưa gửi duyệt')).not.toBeInTheDocument();
    expect(screen.queryByText('cần quyết định')).not.toBeInTheDocument();
    expect(screen.queryByText('đang dùng')).not.toBeInTheDocument();
    expect(screen.queryByText('đã trả lại')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Tạo bộ câu hỏi' }));

    expect(mocks.dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: 'ADD_ASSESSMENT_DRAFT',
      item: expect.objectContaining({
        courseId: '7',
        topic: 'Quan hệ hai ngôi',
        status: 'draft',
        knowledgeComponentIds: ['kc-relations'],
      }),
    }));
    expect(screen.getByText('Trình soạn câu kiểm tra')).toBeInTheDocument();
  });

  it('deletes an assessment from the active bank only after explicit confirmation', async () => {
    mocks.assessments = [{
      id: 'Q-1', courseId: '7', topic: 'Week 1 Knowledge Check', question: 'Which value is immutable?',
      rubric: ['Đúng khái niệm', 'Giải thích có lập luận'], status: 'approved', level: 'conceptual',
      source: 'relations.pdf · page 3', version: 1, knowledgeComponentIds: ['kc-relations'],
    }];
    vi.mocked(deleteAssessmentDesign).mockResolvedValue({ entityId: 'Q-1', deleted: true, retainedAudit: true });
    render(<MemoryRouter><AssessmentPage /></MemoryRouter>);

    expect(screen.queryByText('Week 1 Knowledge Check')).not.toBeInTheDocument();
    expect(screen.queryByText('v1')).not.toBeInTheDocument();
    expect(screen.queryByText('Đang được dùng trong kiểm tra nhanh.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Xóa' }));
    expect(screen.getByRole('heading', { name: 'Xóa câu kiểm tra?' })).toBeVisible();
    expect(screen.getByText(/Bằng chứng học tập và lịch sử phê duyệt/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Xóa câu kiểm tra' }));

    await waitFor(() => expect(deleteAssessmentDesign).toHaveBeenCalledWith('Q-1'));
    expect(mocks.dispatch).toHaveBeenCalledWith({ type: 'DELETE_ASSESSMENT', id: 'Q-1' });
    expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({
      tone: 'success', title: 'Đã xóa khỏi ngân hàng câu hỏi',
    }));
  });
});
