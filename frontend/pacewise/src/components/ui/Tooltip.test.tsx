import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Tooltip } from './Tooltip';

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
const setup = () => render(<Tooltip label="Lịch dạy"><a href="#schedule" aria-label="Lịch dạy">Icon</a></Tooltip>);

describe('icon rail tooltip', () => {
  it('waits 700ms before showing mouse help and hides on leave', () => {
    vi.useFakeTimers(); setup();
    const link = screen.getByRole('link', { name: 'Lịch dạy' });
    fireEvent.pointerEnter(link);
    act(() => vi.advanceTimersByTime(699));
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1));
    const tooltip = screen.getByRole('tooltip');
    expect(tooltip).toHaveTextContent('Lịch dạy');
    expect(link).toHaveAttribute('aria-describedby', tooltip.id);
    fireEvent.pointerLeave(link);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
  it('cancels brief hovers and cleans pending timers on unmount', () => {
    vi.useFakeTimers(); const { unmount } = setup();
    const link = screen.getByRole('link', { name: 'Lịch dạy' });
    fireEvent.pointerEnter(link); fireEvent.pointerLeave(link);
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    fireEvent.pointerEnter(link); expect(vi.getTimerCount()).toBe(1);
    unmount(); expect(vi.getTimerCount()).toBe(0);
  });
  it('shows help for keyboard focus, dismisses on Escape/click/scroll', () => {
    setup(); const link = screen.getByRole('link', { name: 'Lịch dạy' });
    fireEvent.focus(link); expect(screen.getByRole('tooltip')).toBeInTheDocument();
    fireEvent.keyDown(link, { key: 'Escape' }); expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    fireEvent.focus(link); fireEvent.click(link); expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    fireEvent.focus(link); fireEvent.scroll(window); expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
  it('does not add tooltip behavior for expanded navigation', () => {
    render(<Tooltip label="Lịch dạy" enabled={false}><a href="#schedule">Lịch dạy</a></Tooltip>);
    fireEvent.focus(screen.getByRole('link')); expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
  it('dismisses a hovered tooltip with Escape even when its link is not focused', () => {
    vi.useFakeTimers(); setup();
    fireEvent.pointerEnter(screen.getByRole('link'));
    act(() => vi.advanceTimersByTime(700));
    expect(screen.getByRole('tooltip')).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
});
