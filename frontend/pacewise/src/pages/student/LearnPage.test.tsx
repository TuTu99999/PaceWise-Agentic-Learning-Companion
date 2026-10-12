import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LearnPage } from './LearnPage';
import { ApiError, askQuestion } from '../../services/api';

const mocks = vi.hoisted(() => ({ state: {} as Record<string, any>, dispatch: vi.fn(), toast: vi.fn() }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => mocks }));
vi.mock('../../hooks/useDerived', () => ({ useDerived: () => ({ activeCourse: { code: 'DS201', name: 'Toán rời rạc' }, activeTasks: [] }) }));
vi.mock('../../hooks/useElementWidth', () => ({ useElementWidth: () => ({ ref: { current: null }, width: 1280 }) }));
vi.mock('../../components/ui/Toast', () => ({ useToast: () => mocks.toast }));
vi.mock('../../services/api', async (original) => ({ ...await original<typeof import('../../services/api')>(), askQuestion: vi.fn(), askHint: vi.fn(), assessUnderstanding: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
  HTMLElement.prototype.scrollIntoView = vi.fn();
  mocks.state = {
    user: { id: 'u', courseId: 'c1' },
    courses: [
      { id: 'c1', code: 'DS201', name: 'Toán rời rạc' },
      { id: 'c2', code: 'CS101', name: 'Lập trình' },
    ],
    courseScope: 'c1', assessments: [], quickChecks: [], qaMessages: [], qaConversations: [], activeConversationId: null,
  };
});

const setup = () => render(<MemoryRouter><LearnPage /></MemoryRouter>);
const send = (text = 'Tính phản xạ là gì?') => {
  fireEvent.change(screen.getByPlaceholderText('Hỏi về khái niệm, bài tập hoặc tra cứu học liệu...'), { target: { value: text } });
  fireEvent.click(screen.getByTitle('Gửi câu hỏi'));
};

describe('student chatbot request lifecycle', () => {
  it('submits with Enter and preserves Shift+Enter for multiline input', async () => {
    vi.mocked(askQuestion).mockResolvedValue({ kind: 'grounded', text: 'Trả lời', citations: [], sources: [], suggestions: [] });
    setup();
    const input = screen.getByPlaceholderText('Hỏi về khái niệm, bài tập hoặc tra cứu học liệu...');
    fireEvent.change(input, { target: { value: 'CSDL là gì?' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(askQuestion).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(askQuestion).toHaveBeenCalledOnce());
    expect(askQuestion).toHaveBeenCalledWith('CSDL là gì?', [], expect.any(AbortSignal), expect.any(Function));
  });

  it('renders social and out-of-scope replies without a false missing-source state', () => {
    mocks.state.qaMessages = [
      { id: 'hello', role: 'assistant', text: 'Chào bạn!', kind: 'conversation', createdAt: new Date().toISOString() },
      { id: 'scope', role: 'assistant', text: 'Câu này không thuộc nội dung môn DS201.', kind: 'out_of_scope', createdAt: new Date().toISOString() },
    ];
    setup();

    expect(screen.getByText('Chào bạn!')).toBeVisible();
    expect(screen.getByText('Ngoài phạm vi môn')).toBeVisible();
    expect(screen.queryByText('Chưa đủ nguồn')).not.toBeInTheDocument();
    expect(screen.queryByText('Chưa đủ nguồn để trả lời chắc chắn')).not.toBeInTheDocument();
  });

  it('keeps the Do tab focused on the course chatbot without a duplicate understanding check', () => {
    setup();
    expect(screen.getByText('Chatbot môn học')).toBeVisible();
    expect(screen.queryByRole('tab', { name: /Kiểm tra nhanh/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Kiểm tra mức độ hiểu bài/i)).not.toBeInTheDocument();
  });

  it('sends bounded conversational history and coalesces rapid duplicate submits', async () => {
    let resolve!: (value: any) => void;
    vi.mocked(askQuestion).mockReturnValue(new Promise((done) => { resolve = done; }));
    mocks.state.qaMessages = [{ id: 'old', role: 'user', text: 'Quan hệ hai ngôi', createdAt: new Date().toISOString() }];
    setup(); send(); send();
    expect(askQuestion).toHaveBeenCalledOnce();
    expect(vi.mocked(askQuestion).mock.calls[0][1]).toEqual([{ role: 'user', content: 'Quan hệ hai ngôi' }]);
    await act(async () => resolve({ kind: 'grounded', text: 'Trả lời', citations: [], sources: [], suggestions: [] }));
    expect(mocks.dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'ADD_QA', message: expect.objectContaining({ role: 'assistant', text: 'Trả lời' }) }));
  });

  it('shows useful progress stages while the verified answer is pending', () => {
    vi.useFakeTimers();
    vi.mocked(askQuestion).mockReturnValue(new Promise(() => undefined));
    setup(); send();
    expect(screen.getByText('Đang tìm trong học liệu của môn…')).toBeVisible();
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText('Đang đối chiếu các đoạn liên quan…')).toBeVisible();
    act(() => vi.advanceTimersByTime(1600));
    expect(screen.getByText('Đang tổng hợp câu trả lời và kiểm tra trích dẫn…')).toBeVisible();
    vi.useRealTimers();
  });

  it('renders real streamed chunks before the final verified answer completes', async () => {
    let resolve!: (value: any) => void;
    vi.mocked(askQuestion).mockImplementation((_question, _history, _signal, onDelta) => {
      onDelta?.('Quan hệ bắc cầu ');
      onDelta?.('được định nghĩa là…');
      return new Promise((done) => { resolve = done; });
    });
    setup(); send();

    expect(await screen.findByText(/Quan hệ bắc cầu được định nghĩa là/)).toBeVisible();
    await act(async () => resolve({ kind: 'grounded', text: 'Câu trả lời đã kiểm tra.', citations: [], sources: [], suggestions: [] }));
    expect(mocks.dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: 'ADD_QA', message: expect.objectContaining({ role: 'assistant', text: 'Câu trả lời đã kiểm tra.' }),
    }));
  });

  it('does not append an old response after changing course', async () => {
    let resolve!: (value: any) => void;
    vi.mocked(askQuestion).mockReturnValue(new Promise((done) => { resolve = done; }));
    const view = setup(); send();
    const signal = vi.mocked(askQuestion).mock.calls[0][2]!;
    mocks.state.user = { id: 'u', courseId: 'c2' };
    view.rerender(<MemoryRouter><LearnPage /></MemoryRouter>);
    expect(signal.aborted).toBe(true);
    await act(async () => resolve({ kind: 'grounded', text: 'Old course answer', sources: [] }));
    expect(mocks.dispatch.mock.calls.some(([action]) => action.message?.role === 'assistant')).toBe(false);
  });

  it('honors Retry-After and does not automatically repeat expensive calls', async () => {
    vi.mocked(askQuestion).mockRejectedValue(new ApiError('RATE_LIMITED', 'Một yêu cầu đang xử lý', undefined, 10));
    setup(); send();
    await waitFor(() => expect(screen.getByText(/Có thể gửi lại sau/)).toBeInTheDocument());
    expect(screen.getByTitle('Gửi câu hỏi')).toBeDisabled();
    expect(askQuestion).toHaveBeenCalledOnce();
  });
});
