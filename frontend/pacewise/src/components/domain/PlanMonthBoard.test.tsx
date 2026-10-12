import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PlanTimelineItem } from '../../utils/planTimeline';
import { PlanMonthBoard } from './PlanMonthBoard';

const item: PlanTimelineItem = {
  id: 'pacewise:block-1',
  source: 'pacewise',
  title: 'Mini project',
  date: '2026-10-05',
  start: '19:00',
  end: '20:00',
  durationMin: 60,
  kind: 'study_block',
  kindLabel: 'Study block',
  readOnly: false,
};

describe('PlanMonthBoard', () => {
  it('summarizes events and opens the selected day in week view', () => {
    const onSelectDate = vi.fn();
    render(<PlanMonthBoard dates={['2026-10-05']} month="2026-10" items={[item]} onSelectDate={onSelectDate} />);

    expect(screen.getByText(/Mini project/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Thứ Hai 05\/10/ }));
    expect(onSelectDate).toHaveBeenCalledWith('2026-10-05');
  });
});
