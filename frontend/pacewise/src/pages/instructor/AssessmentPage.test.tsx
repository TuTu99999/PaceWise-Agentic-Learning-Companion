import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AssessmentPage } from './AssessmentPage';

const dispatch = vi.fn();

vi.mock('../../hooks/useInstructorData', () => ({ useInstructorData: () => ({ loading: false, error: null }) }));
vi.mock('../../components/ui/Toast', () => ({ useToast: () => vi.fn() }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ dispatch, state: {
  assessments: [],
  courseScope: '7',
  teacherWorkspace: { courseStructure: { knowledgeComponents: [
    { id: 'kc-relations', name: 'Quan hệ hai ngôi', status: 'approved' },
  ] } },
} }) }));

describe('Assessment bank authoring', () => {
  it('creates an editable course/KC-scoped draft so Do can receive an approved check', () => {
    render(<MemoryRouter initialEntries={['/instructor/assessment']}>
      <Routes>
        <Route path="/instructor/assessment" element={<AssessmentPage />} />
        <Route path="/instructor/assessment/:itemId" element={<p>Trình soạn câu kiểm tra</p>} />
      </Routes>
    </MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: 'Tạo câu kiểm tra' }));

    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({
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
});
