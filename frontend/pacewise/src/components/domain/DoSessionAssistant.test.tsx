import '@testing-library/jest-dom/vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { askDoQuestion, getDoChatHistory } from '../../services/api';
import type { AssessmentItem } from '../../types';
import { DoSessionAssistant } from './DoSessionAssistant';
import { LocaleProvider } from '../../i18n/LocaleContext';

vi.mock('../../services/api', () => ({ askDoQuestion: vi.fn(), getDoChatHistory: vi.fn() }));
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
  window.localStorage.clear();
  vi.mocked(getDoChatHistory).mockResolvedValue([]);
  vi.mocked(askDoQuestion).mockResolvedValue({
    kind: 'grounded',
    text: 'Quan hệ bắc cầu được xác định như sau.',
    citations: ['source-1'],
    suggestions: [],
    sources: [{ id: 'source-1', name: 'Chương 3', location: 'Trang 4', excerpt: 'Định nghĩa quan hệ bắc cầu.' }],
  });
});

describe('DoSessionAssistant', () => {
  it('opens learning support by default and keeps assessment as a separate tab', async () => {
    render(<DoSessionAssistant {...props} />);
    expect(screen.getByRole('tab', { name: 'Hỏi để học' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Kiểm tra mình' })).toHaveAttribute('aria-selected', 'false');
    expect(await screen.findByPlaceholderText('Hỏi về nội dung đang học…')).toBeVisible();
    expect(screen.queryByText(/Ưu tiên nội dung của ca hiện tại/)).not.toBeInTheDocument();
    expect(screen.queryByText('Chatbot kiểm tra chưa thể bắt đầu')).not.toBeInTheDocument();
  });

  it('sends on Enter with the current course and block scope, then shows citations', async () => {
    render(<DoSessionAssistant {...props} />);
    const input = screen.getByPlaceholderText('Hỏi về nội dung đang học…');
    await waitFor(() => expect(input).not.toBeDisabled());
    fireEvent.change(input, { target: { value: 'Tính bắc cầu là gì?' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(askDoQuestion).toHaveBeenCalledWith({
      ...props,
      question: 'Tính bắc cầu là gì?',
    }, expect.any(Function), 'vi'));
    expect(await screen.findByText('Quan hệ bắc cầu được xác định như sau.')).toBeVisible();
    expect(screen.getByText(/Đã kiểm tra 1 nguồn/)).toBeVisible();
  });

  it('restores the active block transcript after reload', async () => {
    vi.mocked(getDoChatHistory).mockResolvedValue([
      { id: 'u1', role: 'student', text: 'Tính bắc cầu là gì?' },
      { id: 'a1', role: 'assistant', text: 'Định nghĩa đã kiểm tra.', result: {
        kind: 'grounded', text: 'Định nghĩa đã kiểm tra.', citations: ['s1'], suggestions: [],
        sources: [{ id: 's1', name: 'Chương 3', location: 'Trang 4', excerpt: 'Nguồn.' }],
      } },
    ]);
    render(<DoSessionAssistant {...props} />);
    expect(await screen.findByText('Tính bắc cầu là gì?')).toBeVisible();
    expect(screen.getByText('Định nghĩa đã kiểm tra.')).toBeVisible();
    expect(screen.getByText(/Đã kiểm tra 1 nguồn/)).toBeVisible();
    expect(getDoChatHistory).toHaveBeenCalledWith('7', 'block-1');
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

  it('renders the complete assistant shell in English', async () => {
    window.localStorage.setItem('pacewise-language', 'en');
    render(<LocaleProvider><DoSessionAssistant {...props} /></LocaleProvider>);
    expect(screen.getByRole('heading', { name: 'Session assistant' })).toBeVisible();
    expect(screen.getByRole('tab', { name: 'Learn with AI' })).toBeVisible();
    expect(screen.getByRole('tab', { name: 'Self-check' })).toBeVisible();
    expect(await screen.findByText('What part are you stuck on?')).toBeVisible();
    expect(screen.getByText(/Ask about a concept, example, or solution step/)).toBeVisible();
    expect(screen.getByPlaceholderText('Ask about the current topic…')).toBeVisible();
    expect(screen.queryByText(/Trợ lý|Hỏi về khái niệm|Hỏi để học|Kiểm tra mình/)).toBeNull();
  });

  it('shows streamed answer chunks before the validated final response arrives', async () => {
    let finish!: (value: Awaited<ReturnType<typeof askDoQuestion>>) => void;
    vi.mocked(askDoQuestion).mockImplementation(async (_input, onDelta) => {
      onDelta?.('The first streamed sentence');
      return await new Promise((resolve) => { finish = resolve; });
    });
    render(<DoSessionAssistant {...props} />);
    const input = await screen.findByPlaceholderText('Hỏi về nội dung đang học…');
    fireEvent.change(input, { target: { value: 'Explain it' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(await screen.findByText('The first streamed sentence')).toBeVisible();
    expect(screen.getByLabelText('AI đang trả lời')).toBeVisible();
    await act(async () => finish({ kind: 'conversation', text: 'The complete answer', citations: [], sources: [], suggestions: [] }));
    expect(await screen.findByText('The complete answer')).toBeVisible();
    expect(screen.queryByLabelText('AI đang trả lời')).toBeNull();
  });
});
