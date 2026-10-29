import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LocaleProvider } from '../../i18n/LocaleContext';
import { StudyBlockDialog } from './StudyBlockDialog';

const block = {
  id: 'block-1',
  taskId: 'task-1',
  date: '2026-10-05',
  start: '19:00',
  end: '20:00',
};

describe('StudyBlockDialog', () => {
  beforeEach(() => window.localStorage.clear());
  it('accepts exact minute values and reports the resulting duration', () => {
    const onSave = vi.fn(() => true);
    render(
      <StudyBlockDialog
        block={block}
        title="Ôn vòng lặp"
        saved={false}
        draftReady
        saving={false}
        minDate="2026-10-05"
        maxDate="2026-10-18"
        onClose={vi.fn()}
        onSave={onSave}
        onStart={vi.fn()}
        onApplyAndStart={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('Bắt đầu'), { target: { value: '19:07' } });
    fireEvent.change(screen.getByLabelText('Kết thúc'), { target: { value: '20:13' } });

    expect(screen.getByText('Thời lượng chính xác: 66 phút.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu giờ chính xác' }));
    expect(onSave).toHaveBeenCalledWith({ ...block, start: '19:07', end: '20:13' });
  });

  it('renders grouped work as a readable list and separates the assignment title', () => {
    render(
      <StudyBlockDialog
        block={block}
        title="Làm Câu 1.1; Câu 1.2; Sản phẩm nộp — Bài tập Chương 1"
        saved={false}
        draftReady
        saving={false}
        minDate="2026-10-05"
        maxDate="2026-10-18"
        onClose={vi.fn()}
        onSave={vi.fn(() => true)}
        onStart={vi.fn()}
        onApplyAndStart={vi.fn()}
      />,
    );

    const list = screen.getByRole('list', { name: 'Nội dung ca tự học' });
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    expect(list).toHaveTextContent('Câu 1.1');
    expect(list).toHaveTextContent('Câu 1.2');
    expect(list).toHaveTextContent('Sản phẩm nộp');
    expect(screen.getByText('Bài tập Chương 1')).toBeVisible();
  });

  it('shows repeated work labels only once for an existing duplicated draft', () => {
    render(
      <StudyBlockDialog
        block={block}
        title="Làm Câu 1.1; Câu 1.2; Câu 1.1; Câu 1.2 — Bài tập Chương 1"
        saved={false}
        draftReady
        saving={false}
        minDate="2026-10-05"
        maxDate="2026-10-18"
        onClose={vi.fn()}
        onSave={vi.fn(() => true)}
        onStart={vi.fn()}
        onApplyAndStart={vi.fn()}
      />,
    );

    const list = screen.getByRole('list', { name: 'Nội dung ca tự học' });
    expect(list.querySelectorAll('li')).toHaveLength(2);
    expect(list).toHaveTextContent('Câu 1.1');
    expect(list).toHaveTextContent('Câu 1.2');
  });

  it('updates the summary live and allows a longer learner-chosen session with a warning', () => {
    const onSave = vi.fn(() => true);
    render(
      <StudyBlockDialog
        block={block}
        title="Ôn vòng lặp"
        saved={false}
        draftReady
        saving={false}
        minDate="2026-10-05"
        maxDate="2026-10-18"
        remainingWorkMin={60}
        onClose={vi.fn()}
        onSave={onSave}
        onStart={vi.fn()}
        onApplyAndStart={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('Bắt đầu'), { target: { value: '18:50' } });

    expect(screen.getByText('Thứ Hai 05/10 · 18:50–20:00')).toBeVisible();
    expect(screen.getByText('Ca này dài hơn 1 giờ công việc chưa được xếp. Bạn vẫn có thể lưu; Plan Agent sẽ tính lại phần thời gian thêm.')).toBeVisible();
    const saveButton = screen.getByRole('button', { name: 'Lưu giờ chính xác' });
    expect(saveButton).toBeEnabled();
    fireEvent.click(saveButton);
    expect(onSave).toHaveBeenCalledWith({ ...block, start: '18:50' });
  });

  it('renders dynamic validation and status messages entirely in English', () => {
    window.localStorage.setItem('pacewise-language', 'en');
    render(
      <LocaleProvider>
        <StudyBlockDialog
          block={block}
          title="Ôn vòng lặp"
          saved={false}
          startIssue="Ca này chưa được xác nhận hoặc vừa đổi giờ. Hãy phân tích và áp dụng lại trước khi bắt đầu Do."
          draftReady={false}
          saving={false}
          minDate="2026-10-05"
          maxDate="2026-10-18"
          onClose={vi.fn()}
          onSave={vi.fn(() => true)}
          onStart={vi.fn()}
          onApplyAndStart={vi.fn()}
        />
      </LocaleProvider>,
    );

    expect(screen.getByText('This session is unconfirmed or its time has changed. Run AI planning and apply the plan again before starting it.')).toBeVisible();
    fireEvent.change(screen.getByLabelText('Start'), { target: { value: '19:59' } });
    expect(screen.getByText('A study session must be at least 15 minutes long.')).toBeVisible();
    expect(screen.getByText('The new time is saved for this session immediately; AI planning will recalculate the remaining schedule.')).toBeVisible();
    expect(screen.queryByText(/Ca tự học|Sau khi đổi giờ|chưa được xác nhận/)).toBeNull();
  });
});
