import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { calendarToday } from './useCalendarToday';
import { PlanCalendarBoard } from '../components/domain/PlanCalendarBoard';
import { PlanMonthBoard } from '../components/domain/PlanMonthBoard';

afterEach(() => vi.useRealTimers());
describe('real-time calendar highlighting', () => {
  it('uses Vietnam midnight, not UTC or the fixed demo clock', () => {
    expect(calendarToday(new Date('2026-10-08T17:01:00Z'))).toBe('2026-10-09');
    expect(calendarToday(new Date('2026-10-08T16:59:00Z'))).toBe('2026-10-08');
  });
  it('highlights exactly the current teaching calendar column', () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-09T03:00:00Z'));
    render(<PlanCalendarBoard readOnly dates={['2026-10-08', '2026-10-09']} items={[]} />);
    expect(screen.getByText('Hôm nay').parentElement).toHaveAttribute('aria-current', 'date');
    expect(screen.getByLabelText('Lịch ngày 2026-10-09')).toHaveClass('calendar-today-column');
    expect(screen.getByLabelText('Lịch ngày 2026-10-08')).not.toHaveClass('calendar-today-column');
  });
  it('highlights the month cell without changing selection', () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-09T03:00:00Z'));
    render(<PlanMonthBoard dates={['2026-10-08', '2026-10-09']} month="2026-10" items={[]} onSelectDate={vi.fn()} />);
    expect(screen.getAllByRole('button').filter((button) => button.getAttribute('aria-current') === 'date')).toHaveLength(1);
  });
});
