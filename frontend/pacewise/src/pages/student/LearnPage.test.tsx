import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { englishSuggestionTaskTitle, LearnPage } from './LearnPage';
import { ApiError, askHint, askQuestion } from '../../services/api';
import { LocaleProvider } from '../../i18n/LocaleContext';
import { PACEWISE_LANGUAGE_STORAGE_KEY } from '../../utils/uiPreferences';

const mocks = vi.hoisted(() => ({ state: {} as Record<string, any>, activeTasks: [] as Array<{ title: string }>, dispatch: vi.fn(), toast: vi.fn() }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => mocks }));
vi.mock('../../hooks/useDerived', () => ({ useDerived: () => ({ activeCourse: { code: 'DS201', name: 'Toán rời rạc' }, activeTasks: mocks.activeTasks }) }));
vi.mock('../../hooks/useElementWidth', () => ({ useElementWidth: () => ({ ref: { current: null }, width: 1280 }) }));
vi.mock('../../components/ui/Toast', () => ({ useToast: () => mocks.toast }));
vi.mock('../../services/api', async (original) => ({ ...await original<typeof import('../../services/api')>(), askQuestion: vi.fn(), askHint: vi.fn(), assessUnderstanding: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.removeItem(PACEWISE_LANGUAGE_STORAGE_KEY);
  mocks.activeTasks = [];
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
const setupEnglish = () => {
  localStorage.setItem(PACEWISE_LANGUAGE_STORAGE_KEY, 'en');
  return render(<LocaleProvider><MemoryRouter><LearnPage /></MemoryRouter></LocaleProvider>);
};
const send = (text = 'Tính phản xạ là gì?') => {
  fireEvent.change(screen.getByPlaceholderText('Hỏi về khái niệm, bài tập hoặc tra cứu học liệu...'), { target: { value: text } });
  fireEvent.click(screen.getByTitle('Gửi câu hỏi'));
};

describe('student chatbot request lifecycle', () => {
  it('translates demo-course suggestion titles instead of leaking Vietnamese into English UI', () => {
    expect(englishSuggestionTaskTitle('Bài tập Chương 2: Mô hình cơ sở dữ liệu')).toBe('Chapter 2 assignment: Database models');
    expect(englishSuggestionTaskTitle('Bài tập Chương 2: Kỹ thuật tìm kiếm')).toBe('Chapter 2 assignment: Searching techniques');
    expect(englishSuggestionTaskTitle('Bài tập Chương 2: Mở rộng C++ phần 1')).toBe('Chapter 2 assignment: Extended C++ — Part 1');
    expect(englishSuggestionTaskTitle('Bài tập Chương 1: Công nghệ Web')).toBe('Chapter 1 assignment: Web technologies');
    expect(englishSuggestionTaskTitle('Quiz tháng 01 · 20 phút')).toBe('Monthly quiz 01 · 20 minutes');
    expect(englishSuggestionTaskTitle('Hoàn thành BTVN 2026 T10.2: Hàm')).toBe('Complete homework 2026 T10.2: Functions');
    expect(englishSuggestionTaskTitle('Hoàn thành Bài tập Chương 2: Mô hình cơ sở dữ liệu')).toBe('Complete Chapter 2 assignment: Database models');
  });

  it('renders generated suggestion cards fully in English', () => {
    mocks.activeTasks = [{ title: 'Bài tập Chương 2: Mô hình cơ sở dữ liệu' }];
    setupEnglish();

    expect(screen.getByText('Explain the knowledge needed to complete “Chapter 2 assignment: Database models”.')).toBeVisible();
    expect(screen.queryByText(/Giải thích kiến thức/)).not.toBeInTheDocument();
  });

  it('sends the selected English UI locale with chatbot questions', async () => {
    vi.mocked(askQuestion).mockResolvedValue({ kind: 'conversation', text: 'Hello!', citations: [], sources: [], suggestions: [] });
    setupEnglish();

    fireEvent.change(screen.getByPlaceholderText('Ask about concepts, exercises, or course materials...'), {
      target: { value: 'Cơ sở dữ liệu là gì?' },
    });
    fireEvent.click(screen.getByTitle('Send question'));

    await waitFor(() => expect(askQuestion).toHaveBeenCalledWith(
      'Cơ sở dữ liệu là gì?', [], expect.any(AbortSignal), expect.any(Function), 'en',
    ));
  });

  it('submits with Enter and preserves Shift+Enter for multiline input', async () => {
    vi.mocked(askQuestion).mockResolvedValue({ kind: 'grounded', text: 'Trả lời', citations: [], sources: [], suggestions: [] });
    setup();
    const input = screen.getByPlaceholderText('Hỏi về khái niệm, bài tập hoặc tra cứu học liệu...');
    fireEvent.change(input, { target: { value: 'CSDL là gì?' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(askQuestion).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(askQuestion).toHaveBeenCalledOnce());
    expect(askQuestion).toHaveBeenCalledWith('CSDL là gì?', [], expect.any(AbortSignal), expect.any(Function), 'vi');
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

  it('keeps the original question in context when requesting an integrity-safe hint', async () => {
    mocks.state.qaMessages = [
      { id: 'question', role: 'user', text: 'Giúp mình tìm số lớn nhất trong SQL', createdAt: new Date().toISOString() },
      { id: 'integrity', role: 'assistant', text: 'Mình không thể làm bài thay bạn.', kind: 'integrity', createdAt: new Date().toISOString() },
    ];
    vi.mocked(askHint).mockResolvedValue({ kind: 'hint', text: 'Bắt đầu bằng cách xác định cột cần so sánh.', citations: [], sources: [], suggestions: [] });

    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Cho mình gợi ý' }));

    await waitFor(() => expect(askHint).toHaveBeenCalledWith([
      { role: 'user', content: 'Giúp mình tìm số lớn nhất trong SQL' },
      { role: 'assistant', content: 'Mình không thể làm bài thay bạn.' },
    ], 'vi'));
    expect(mocks.dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: 'ADD_QA', message: expect.objectContaining({ role: 'assistant', text: 'Bắt đầu bằng cách xác định cột cần so sánh.' }),
    }));
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
    expect(screen.getByText('Đã đạt giới hạn AI')).toBeVisible();
    expect(screen.getByText(/Một yêu cầu đang xử lý/)).toBeVisible();
    expect(screen.getByTitle('Gửi câu hỏi')).toBeDisabled();
    expect(askQuestion).toHaveBeenCalledOnce();
  });
});
