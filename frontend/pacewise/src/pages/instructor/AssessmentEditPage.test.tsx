import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { previewQuestionDesign, saveInstructorAction } from '../../services/api';
import { AssessmentEditPage } from './AssessmentEditPage';

vi.mock('../../services/api', () => ({ previewQuestionDesign: vi.fn(), saveInstructorAction: vi.fn() }));
vi.mock('../../components/ui/Toast', () => ({ useToast: () => vi.fn() }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ dispatch: vi.fn(), state: {
  assessments: [{ id: 'Q-1', topic: 'Relations', question: 'Explain binary relation transitivity in your own words.',
    status: 'approved', level: 'conceptual', source: 'TRR_Full_P4.pdf', version: 1,
    rubric: ['Correct definition', 'Grounded reasoning'], knowledgeComponentIds: ['relation.transitivity'] }],
  teacherWorkspace: { courseStructure: { knowledgeComponents: [{ id: 'relation.transitivity', name: 'Bắc cầu', status: 'approved' }] } },
} }) }));

const open = () => render(<MemoryRouter initialEntries={['/instructor/assessment/Q-1']}>
  <Routes><Route path="/instructor/assessment/:itemId" element={<AssessmentEditPage />} />
    <Route path="/instructor/assessment" element={<p>Saved blueprint</p>} /></Routes>
</MemoryRouter>);

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(saveInstructorAction).mockResolvedValue({ id: 'action-1', createdAt: '2026-10-09T00:00:00Z', payload: { version: 2 } });
  vi.mocked(previewQuestionDesign).mockResolvedValue({ saved: false, course_id: 7001, examples: [
    { stage: 'recall', question: 'PREVIEW relation', expected_facts: { holds: false, minimal_additions: [['1', '3']] } },
  ] });
});

describe('Teacher-owned question blueprint', () => {
  it('previews a verified template without saving and hides stale preview on property change', async () => {
    open();
    fireEvent.change(screen.getByLabelText('Cách tạo câu hỏi'), { target: { value: 'relation_template' } });
    fireEvent.click(screen.getByRole('button', { name: 'Xem biến thể và đáp án checker' }));
    expect(await screen.findByText(/PREVIEW relation/)).toBeInTheDocument();
    expect(saveInstructorAction).not.toHaveBeenCalled();
    expect(previewQuestionDesign).toHaveBeenCalledWith(expect.objectContaining({ mode: 'relation_template', relation_property: 'transitive' }),
      ['Correct definition', 'Grounded reasoning'], 'TRR_Full_P4.pdf');
    fireEvent.change(screen.getByLabelText('Tính chất cần kiểm chứng'), { target: { value: 'symmetric' } });
    expect(screen.queryByText(/PREVIEW relation/)).not.toBeInTheDocument();
  });

  it('saves a versioned shared blueprint rather than preview instances into the bank', async () => {
    open();
    fireEvent.change(screen.getByLabelText('Cách tạo câu hỏi'), { target: { value: 'relation_template' } });
    fireEvent.click(screen.getByRole('button', { name: 'Duyệt và xuất bản' }));
    await waitFor(() => expect(saveInstructorAction).toHaveBeenCalledWith('assessment', 'Q-1',
      expect.objectContaining({ status: 'approved', knowledgeComponentIds: ['relation.transitivity'],
        questionDesign: expect.objectContaining({ mode: 'relation_template', stages: ['recall', 'explain', 'why', 'application', 'transfer'] }) })));
    expect(await screen.findByText('Saved blueprint')).toBeInTheDocument();
  });
});
