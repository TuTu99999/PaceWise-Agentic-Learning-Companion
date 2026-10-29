import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const dispatch = vi.hoisted(() => vi.fn());
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ dispatch, state: {
  courses: [{ id: '1', code: 'TRR', name: 'Toán rời rạc' }, { id: '2', code: 'CS', name: 'Lập trình' }],
  studyPreferences: { sessionMinutes: 60, breakMinutes: 10, activityRhythms: [
    { courseId: 1, activityType: 'concept', sessionMinutes: 45, breakMinutes: 5 },
  ] },
} }) }));
import { ActivityRhythmSettings } from './ActivityRhythmSettings';

beforeEach(() => dispatch.mockClear());
describe('course/activity rhythm student choice', () => {
  it('uses saved scoped preference and does not apply a change before explicit save', () => {
    render(<ActivityRhythmSettings />);
    expect(screen.getByLabelText('Phiên riêng (phút)')).toHaveValue(45);
    fireEvent.change(screen.getByLabelText('Phiên riêng (phút)'), { target: { value: '30' } });
    expect(dispatch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu nhịp riêng' }));
    expect(dispatch).toHaveBeenCalledWith({ type: 'UPSERT_ACTIVITY_RHYTHM', rhythm: { courseId: 1, activityType: 'concept', sessionMinutes: 30, breakMinutes: 5 } });
    expect(screen.getByRole('status')).toHaveTextContent('Đã lưu nhịp riêng');
  });
  it('falls back independently for another course or activity and validates bounds', () => {
    render(<ActivityRhythmSettings />);
    fireEvent.change(screen.getByLabelText('Loại hoạt động'), { target: { value: 'coding' } });
    expect(screen.getByLabelText('Phiên riêng (phút)')).toHaveValue(60);
    fireEvent.change(screen.getByLabelText('Môn áp dụng'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Loại hoạt động'), { target: { value: 'concept' } });
    expect(screen.getByLabelText('Phiên riêng (phút)')).toHaveValue(60);
    fireEvent.change(screen.getByLabelText('Phiên riêng (phút)'), { target: { value: '5' } });
    expect(screen.getByRole('button', { name: 'Lưu nhịp riêng' })).toBeDisabled();
    expect(dispatch).not.toHaveBeenCalled();
  });
  it('removes just the selected override', () => {
    render(<ActivityRhythmSettings />);
    fireEvent.click(screen.getByRole('button', { name: 'Dùng mặc định' }));
    expect(dispatch).toHaveBeenCalledWith({ type: 'REMOVE_ACTIVITY_RHYTHM', courseId: 1, activityType: 'concept' });
  });
});
