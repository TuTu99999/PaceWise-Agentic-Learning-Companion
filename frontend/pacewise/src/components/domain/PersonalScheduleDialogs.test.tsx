import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PlanTimelineItem } from '../../utils/planTimeline';
import { LmsCalendarNoticeDialog, PersonalSlotDialog, RoutineDialog } from './PersonalScheduleDialogs';

describe('personal calendar dialogs', () => {
  it('uses an unambiguous 24-hour bedtime and saves midnight as 00:00', () => {
    const onSave = vi.fn();
    render(<RoutineDialog open value={null} onClose={vi.fn()} onSave={onSave} />);

    fireEvent.change(screen.getByLabelText('Thường đi ngủ'), { target: { value: '00:00' } });
    expect(screen.getByText(/Nhập chính xác từng phút/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu giờ sinh hoạt' }));

    expect(onSave).toHaveBeenCalledWith({
      wakeTime: '07:00', sleepTime: '00:00', preferred: ['morning', 'evening'],
    });
  });

  it('accepts a minute-exact bedtime and normalizes a Vietnamese h separator', () => {
    const onSave = vi.fn();
    render(<RoutineDialog open value={null} onClose={vi.fn()} onSave={onSave} />);

    fireEvent.change(screen.getByLabelText('Thường đi ngủ'), { target: { value: '23h3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu giờ sinh hoạt' }));

    expect(onSave).toHaveBeenCalledWith({
      wakeTime: '07:00', sleepTime: '23:03', preferred: ['morning', 'evening'],
    });
  });

  it('opens a full keyboard so mobile users can type a clock separator', () => {
    render(<RoutineDialog open value={null} onClose={vi.fn()} onSave={vi.fn()} />);

    expect(screen.getByLabelText('Thường thức dậy')).toHaveAttribute('inputmode', 'text');
    expect(screen.getByLabelText('Thường đi ngủ')).toHaveAttribute('inputmode', 'text');
  });

  it('rejects an invalid typed clock instead of guessing', () => {
    render(<RoutineDialog open value={null} onClose={vi.fn()} onSave={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Thường đi ngủ'), { target: { value: '25:70' } });
    expect(screen.getByText('Nhập giờ 24h hợp lệ, ví dụ 23:10.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Lưu giờ sinh hoạt' })).toBeDisabled();
  });

  it('prefills date and exact times when editing a personal activity', () => {
    const onSubmit = vi.fn();
    render(
      <PersonalSlotDialog
        open
        mode="edit"
        category="meal"
        initialLabel="Ăn tối"
        initialDate="2026-10-06"
        initialStart="19:10"
        initialEnd="20:00"
        minDate="2026-10-05"
        maxDate="2026-10-18"
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByDisplayValue('2026-10-06')).toBeTruthy();
    expect(screen.getByDisplayValue('19:10')).toBeTruthy();
    expect(screen.getByDisplayValue('20:00')).toBeTruthy();
    fireEvent.change(screen.getByDisplayValue('20:00'), { target: { value: '20:30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận thay đổi' }));
    expect(onSubmit).toHaveBeenCalledWith({
      date: '2026-10-06', start: '19:10', end: '20:30', label: 'Ăn tối', category: 'meal',
    });
  });

  it('shows an explanation for LMS items without editable date or time fields', () => {
    const item: PlanTimelineItem = {
      id: 'lms:class:1', source: 'lms', title: 'Ca học trực tiếp', date: '2026-10-06',
      start: '09:00', end: '10:30', durationMin: 90, courseCode: 'CS101',
      kind: 'class', kindLabel: 'Buổi học tại lớp', readOnly: true,
    };
    render(<LmsCalendarNoticeDialog item={item} onClose={vi.fn()} />);

    expect(screen.getByRole('dialog', { name: 'Không thể chỉnh lịch Canvas LMS' })).toBeTruthy();
    expect(screen.getByText(/thay đổi cục bộ sẽ lệch với lịch chính thức/)).toBeTruthy();
    expect(screen.queryByLabelText('Ngày')).toBeNull();
    expect(screen.queryByLabelText('Bắt đầu')).toBeNull();
    expect(screen.queryByLabelText('Kết thúc')).toBeNull();
  });
});
