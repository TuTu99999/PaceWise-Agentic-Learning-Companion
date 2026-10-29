import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider, useToast } from './Toast';

function ToastFixture() {
  const toast = useToast();
  return (
    <div>
      <button onClick={() => toast({ tone: 'success', title: 'Đã chuyển môn học' })}>Success</button>
      <button onClick={() => toast({ tone: 'info', title: 'Đã lưu nháp' })}>Info</button>
      <button onClick={() => toast({ tone: 'warning', title: 'Cần kiểm tra' })}>Warning</button>
      <button onClick={() => toast({ tone: 'danger', title: 'Không thể lưu' })}>Danger</button>
    </div>
  );
}

describe('ToastProvider notification policy', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('hides routine success and informational notices for both application roles', () => {
    render(<ToastProvider><ToastFixture /></ToastProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'Success' }));
    fireEvent.click(screen.getByRole('button', { name: 'Info' }));

    expect(screen.queryByText('Đã chuyển môn học')).not.toBeInTheDocument();
    expect(screen.queryByText('Đã lưu nháp')).not.toBeInTheDocument();
  });

  it('keeps only the newest actionable warning or error', () => {
    render(<ToastProvider><ToastFixture /></ToastProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'Warning' }));
    expect(screen.getByText('Cần kiểm tra')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Danger' }));
    expect(screen.queryByText('Cần kiểm tra')).not.toBeInTheDocument();
    expect(screen.getByText('Không thể lưu')).toBeInTheDocument();
  });

  it('dismisses an actionable alert automatically', () => {
    vi.useFakeTimers();
    render(<ToastProvider><ToastFixture /></ToastProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'Danger' }));
    expect(screen.getByText('Không thể lưu')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(5000));
    expect(screen.queryByText('Không thể lưu')).not.toBeInTheDocument();
  });
});
