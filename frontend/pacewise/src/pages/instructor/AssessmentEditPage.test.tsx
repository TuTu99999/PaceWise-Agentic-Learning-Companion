import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { saveInstructorAction } from '../../services/api';
import { AssessmentEditPage, chapterKnowledgeComponentId } from './AssessmentEditPage';
import { LocaleProvider } from '../../i18n/LocaleContext';

vi.mock('../../services/api', () => ({ saveInstructorAction: vi.fn() }));
vi.mock('../../components/ui/Toast', () => ({ useToast: () => vi.fn() }));
vi.mock('../../hooks/useTeacherManagement', () => ({ useTeacherManagement: () => ({
  loading: false,
  error: '',
  data: {
    resources: [
      { id: 11, title: 'TRR_Full_P4.pdf', chapter: 'Chương 2: Quan hệ' },
      { id: 12, title: 'Chapter_1.pdf', chapter: 'Chương 1: Tập hợp' },
    ],
    materials: [], tasks: [], lessons: [], weights: { groups: [], version: '1' },
  },
}) }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ dispatch: vi.fn(), state: {
  assessments: [{ id: 'Q-1', topic: 'Relations', question: 'Explain binary relation transitivity in your own words.',
    courseId: '7001', status: 'approved', level: 'conceptual', source: 'TRR_Full_P4.pdf', sourceResourceId: 11,
    sourceChapter: 'Chương 2: Quan hệ', moduleId: 'module-2', version: 1,
    rubric: ['Correct definition', 'Grounded reasoning'], knowledgeComponentIds: ['relation.transitivity'] }],
  courseScope: '7001',
  user: { id: 'teacher-1', courseId: '7001' },
  teacherWorkspace: { courseStructure: {
    modules: [{ id: 'module-1', title: 'Chương 1: Tập hợp' }, { id: 'module-2', title: 'Chương 2: Quan hệ' }],
    knowledgeComponents: [
      { id: 'set.union', moduleId: 'module-1', name: 'Phép hợp', status: 'approved' },
      { id: 'relation.transitivity', moduleId: 'module-2', name: 'Bắc cầu', status: 'approved' },
    ],
  } },
} }) }));

const open = () => render(<MemoryRouter initialEntries={['/instructor/assessment/Q-1']}>
  <Routes><Route path="/instructor/assessment/:itemId" element={<AssessmentEditPage />} />
    <Route path="/instructor/assessment" element={<p>Saved blueprint</p>} /></Routes>
</MemoryRouter>);

const openEnglish = () => render(<LocaleProvider><MemoryRouter initialEntries={['/instructor/assessment/Q-1']}>
  <Routes><Route path="/instructor/assessment/:itemId" element={<AssessmentEditPage />} />
    <Route path="/instructor/assessment" element={<p>Saved blueprint</p>} /></Routes>
</MemoryRouter></LocaleProvider>);

beforeEach(() => {
  vi.resetAllMocks();
  window.localStorage.clear();
  vi.mocked(saveInstructorAction).mockResolvedValue({ id: 'action-1', createdAt: '2026-10-09T00:00:00Z', payload: { version: 2 } });
});

describe('Teacher-owned question blueprint', () => {
  it('creates a stable hidden chapter mapping when no detailed course component exists', () => {
    expect(chapterKnowledgeComponentId('7001', 'Chương 2: Kỹ thuật tìm kiếm'))
      .toBe('chapter:7001:chuong-2-ky-thuat-tim-kiem');
  });

  it('keeps the main approval flow focused on question, source, and rubric', () => {
    open();
    expect(screen.getByLabelText('Câu hỏi 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Chương')).toHaveValue('Chương 2: Quan hệ');
    expect(screen.getByLabelText('Tài liệu')).toHaveValue('11');
    expect(screen.queryByLabelText('Nội dung được kiểm tra')).not.toBeInTheDocument();
    expect(screen.queryByText('Sinh viên sẽ thấy')).not.toBeInTheDocument();
    expect(screen.queryByText('Chưa có thay đổi.')).not.toBeInTheDocument();
    expect(screen.getByText('Các ý đúng AI cần tìm')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Ý chính hoặc khái niệm bắt buộc sinh viên phải nêu')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Thêm câu hỏi' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Mức kiểm chứng')).not.toBeInTheDocument();
    expect(screen.queryByText('Cài đặt nâng cao')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Kiểu chấm')).not.toBeInTheDocument();
    expect(screen.queryByText('Relations')).not.toBeInTheDocument();
    expect(screen.queryByText(/v1/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Lưu và xuất bản' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Lưu nháp' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Trả lại kèm ghi chú' })).not.toBeInTheDocument();
  });

  it('renders the complete question authoring form in English', () => {
    window.localStorage.setItem('pacewise-language', 'en');
    openEnglish();

    expect(screen.getByRole('heading', { name: 'Edit assessment question set' })).toBeInTheDocument();
    expect(screen.getByText('Open-response question set')).toBeInTheDocument();
    expect(screen.getByLabelText('Chapter')).toBeInTheDocument();
    expect(screen.getByLabelText('Material')).toBeInTheDocument();
    expect(screen.getByText('Questions')).toBeInTheDocument();
    expect(screen.getByLabelText('Question 1')).toBeInTheDocument();
    expect(screen.getByText('Required ideas for AI to check')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Essential idea or concept the student must state')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add question' })).toBeInTheDocument();
    expect(screen.queryByText('Câu hỏi')).not.toBeInTheDocument();
  });

  it('filters uploaded course files by chapter and saves the stable source reference', async () => {
    open();
    fireEvent.change(screen.getByLabelText('Chương'), { target: { value: 'Chương 1: Tập hợp' } });
    expect(screen.getByRole('option', { name: 'Chapter_1.pdf' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'TRR_Full_P4.pdf' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Tài liệu'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu và xuất bản' }));
    await waitFor(() => expect(saveInstructorAction).toHaveBeenCalledWith('assessment', 'Q-1', expect.objectContaining({
      source: 'Chapter_1.pdf', sourceResourceId: 12, sourceChapter: 'Chương 1: Tập hợp', moduleId: 'module-1',
      knowledgeComponentIds: ['set.union'],
    })));
  });

  it('stores every teacher question as an open rubric-driven self-check', async () => {
    open();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu và xuất bản' }));
    await waitFor(() => expect(saveInstructorAction).toHaveBeenCalledWith('assessment', 'Q-1',
      expect.objectContaining({ status: 'approved', assessmentSetId: 'Q-1', answerType: 'open', level: 'conceptual', assessmentStage: 'explain',
        knowledgeComponentIds: ['relation.transitivity'],
        questionDesign: expect.objectContaining({ mode: 'fixed', stages: ['explain'] }) })));
    expect(await screen.findByText('Saved blueprint')).toBeInTheDocument();
  });

  it('saves added questions independently under the same question set', async () => {
    open();
    fireEvent.click(screen.getByRole('button', { name: 'Thêm câu hỏi' }));
    expect(screen.getByText('2/5 câu')).toBeVisible();
    expect(screen.getByLabelText('Câu hỏi 2')).toBeVisible();
    expect(screen.queryByLabelText('Câu hỏi 1')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Câu hỏi 2'), { target: { value: 'Explain how union works using your own example.' } });
    fireEvent.change(screen.getByLabelText('Câu 2, ý cần có 1'), { target: { value: 'States the union rule' } });
    fireEvent.change(screen.getByLabelText('Câu 2, ý cần có 2'), { target: { value: 'Provides a valid example' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu và xuất bản' }));
    await waitFor(() => expect(saveInstructorAction).toHaveBeenCalledTimes(2));
    expect(vi.mocked(saveInstructorAction).mock.calls[1][2]).toEqual(expect.objectContaining({
      assessmentSetId: 'Q-1',
      question: 'Explain how union works using your own example.',
      rubric: ['States the union rule', 'Provides a valid example'],
    }));
  });
});
