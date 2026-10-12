import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { askDoQuestion } from '../../services/api';
import type { AssessmentItem } from '../../types';
import { DoSessionAssistant } from './DoSessionAssistant';

vi.mock('../../services/api', () => ({ askDoQuestion: vi.fn() }));
vi.mock('./AdaptiveDoCheckpoint', () => ({
  AdaptiveDoCheckpoint: ({ assessment }: { assessment: AssessmentItem }) => (
    <div>Assessment conversation: {assessment.question}</div>
  ),
}));

const props = {
  courseId: '7',
  blockId: 'block-1',
  taskTitle: 'Bài tập quan hệ',
  objective: 'Giải thích tính bắc cầu',
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(askDoQuestion).mockResolvedValue({
    kind: 'grounded',
    text: 'Quan hệ bắc cầu được xác định như sau.',
    citations: ['source-1'],
    suggestions: [],
    sources: [{ id: 'source-1', name: 'Chương 3', location: 'Trang 4', excerpt: 'Định nghĩa quan hệ bắc cầu.' }],
  });
});

describe('DoSessionAssistant', () => {
  it('opens learning support by default and keeps assessment as a separate tab', () => {
    render(<DoSessionAssistant {...props} />);
    expect(screen.getByRole('tab', { name: 'Hỏi để học' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Kiểm tra mình' })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByPlaceholderText('Hỏi về nội dung đang học…')).toBeVisible();
    expect(screen.queryByText('Chatbot kiểm tra chưa thể bắt đầu')).not.toBeInTheDocument();
  });

  it('sends on Enter with the current course and block scope, then shows citations', async () => {
    render(<DoSessionAssistant {...props} />);
    const input = screen.getByPlaceholderText('Hỏi về nội dung đang học…');
    fireEvent.change(input, { target: { value: 'Tính bắc cầu là gì?' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(askDoQuestion).toHaveBeenCalledWith({
      ...props,
      question: 'Tính bắc cầu là gì?',
    }, expect.any(Function)));
    expect(await screen.findByText('Quan hệ bắc cầu được xác định như sau.')).toBeVisible();
    expect(screen.getByText(/Đã kiểm tra 1 nguồn/)).toBeVisible();
  });

  it('keeps the conversation viewport at a stable height while messages are appended', () => {
    render(<DoSessionAssistant {...props} />);
    expect(screen.getByLabelText('Hội thoại hỗ trợ học trong phiên')).toHaveClass(
      'h-[clamp(300px,46dvh,420px)]',
      'overflow-y-auto',
    );
  });

  it('uses Shift+Enter for a new line without sending', () => {
    render(<DoSessionAssistant {...props} />);
    const input = screen.getByPlaceholderText('Hỏi về nội dung đang học…');
    fireEvent.change(input, { target: { value: 'Dòng một' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(askDoQuestion).not.toHaveBeenCalled();
  });

  it('keeps support available when no approved assessment exists', () => {
    render(<DoSessionAssistant {...props} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Kiểm tra mình' }));
    expect(screen.getByText('Chatbot kiểm tra chưa thể bắt đầu')).toBeVisible();
    expect(screen.getByText(/vẫn có thể dùng “Hỏi để học”/)).toBeVisible();
    fireEvent.click(screen.getByRole('tab', { name: 'Hỏi để học' }));
    expect(screen.getByPlaceholderText('Hỏi về nội dung đang học…')).toBeVisible();
  });

  it('starts the independent assessment conversation only after its tab is opened', () => {
    const assessment: AssessmentItem = {
      id: 'Q-1', topic: 'Quan hệ', question: 'Giải thích tính bắc cầu', rubric: ['Đúng định nghĩa'], status: 'approved',
    };
    render(<DoSessionAssistant {...props} assessment={assessment} />);
    expect(screen.queryByText(/Assessment conversation/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Kiểm tra mình' }));
    expect(screen.getByText('Assessment conversation: Giải thích tính bắc cầu')).toBeVisible();
  });
});
