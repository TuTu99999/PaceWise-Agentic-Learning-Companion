import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StudyBlockDialog } from './StudyBlockDialog';

const block = {
  id: 'block-1',
  taskId: 'task-1',
  date: '2026-10-05',
  start: '19:00',
  end: '20:00',
};

describe('StudyBlockDialog', () => {
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
});
