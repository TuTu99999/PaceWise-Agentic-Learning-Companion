import { useEffect, useRef, useState, type FormEvent } from 'react';
import { SourceModal } from '../../components/domain/Citation';
import { CourseSwitcher } from '../../components/domain/CourseSwitcher';
import { GroundedAssistantReply } from '../../components/domain/GroundedAssistantReply';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Icon } from '../../components/ui/Icon';
import { ErrorState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useDerived } from '../../hooks/useDerived';
import { useElementWidth } from '../../hooks/useElementWidth';
import { useChatAutoScroll } from '../../hooks/useChatAutoScroll';
import { Modal } from '../../components/ui/Modal';
import {
  ApiError,
  askHint,
  askQuestion,
} from '../../services/api';
import { useAppStore } from '../../store/AppStore';
import type { QAConversation, QAMessage, Source } from '../../types';
import type { QAResult } from '../../utils/qa';
import { cx } from '../../utils/cx';
import { uid } from '../../utils/time';
import { submitChatOnEnter } from '../../utils/chatInput';

const MAX_LEN = 1000;
function AssistantMessage({ m, onOpen, onHint, onAsk, hintLoading }: { m: QAMessage; onOpen: (s: Source) => void; onHint: () => void; onAsk: (q: string) => void; hintLoading: boolean }) {
  if (m.kind === 'integrity') {
    return (
      <Card tone="accent" as="article" aria-label="Chuyển hướng liêm chính học thuật" className="border border-amber-200 bg-amber-50/50">
        <div className="flex gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-accent-ink shadow-sm">
            <Icon name="shield" size={20} />
          </span>
          <div className="min-w-0">
            <h3 className="text-lg font-semibold">Mình không thể làm bài thay bạn.</h3>
            <p className="mt-1">Nhưng PaceWise có thể giúp bạn:</p>
            <ul className="mt-2 space-y-1.5">
              {['Xác định kiến thức cần dùng', 'Gợi ý cách tiếp cận', 'Đặt câu hỏi để bạn tự kiểm tra', 'Xem lại cách bạn đang làm'].map((x) => (
                <li key={x} className="flex gap-2">
                  <Icon name="check" size={18} className="mt-0.5 shrink-0 text-accent-ink" />
                  {x}
                </li>
              ))}
            </ul>
            <Button className="mt-4" icon="lightbulb" onClick={onHint} loading={hintLoading}>
              Cho mình gợi ý
            </Button>
          </div>
        </div>
      </Card>
    );
  }
  return <GroundedAssistantReply message={m} onOpen={onOpen} onAsk={onAsk} />;
}

export function LearnPage() {
  useDocumentTitle('Học tập & Hỏi đáp');
  const { state, dispatch } = useAppStore();
  const { activeCourse, activeTasks } = useDerived();
  const toast = useToast();

  // Q&A state
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState(0);
  const [streamingText, setStreamingText] = useState('');
  const requestRef = useRef<AbortController | null>(null);
  const [retryAt, setRetryAt] = useState(0);
  const [retrySeconds, setRetrySeconds] = useState(0);
  const [hintLoading, setHintLoading] = useState(false);
  const [error, setError] = useState<{ question: string; requestId: string } | null>(null);
  const [inputError, setInputError] = useState('');
  const [openSource, setOpenSource] = useState<Source | null>(null);
  const chatScrollRevision = `${state.qaMessages.length}:${loading}:${streamingText.length}:${error?.requestId ?? ''}`;
  const { containerRef: chatViewportRef, handleScroll: handleChatScroll, followLatest } = useChatAutoScroll(chatScrollRevision);
  useEffect(() => {
    requestRef.current?.abort();
    requestRef.current = null;
    setLoading(false);
    setStreamingText('');
    setError(null);
    setOpenSource(null);
    return () => { requestRef.current?.abort(); };
  }, [state.user?.courseId]);

  useEffect(() => {
    const update = () => setRetrySeconds(Math.max(0, Math.ceil((retryAt - Date.now()) / 1000)));
    update();
    if (!retryAt) return;
    const interval = window.setInterval(update, 1000);
    return () => window.clearInterval(interval);
  }, [retryAt]);

  useEffect(() => {
    if (!loading) return;
    setLoadingStage(0);
    const retrieval = window.setTimeout(() => setLoadingStage(1), 900);
    const generation = window.setTimeout(() => setLoadingStage(2), 2400);
    return () => { window.clearTimeout(retrieval); window.clearTimeout(generation); };
  }, [loading]);

  // Gemini Chat UI States
  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth >= 1280);
  const { ref: learningRef, width: learningWidth } = useElementWidth<HTMLDivElement>();
  const compactHistory = (learningWidth ?? window.innerWidth) < 1120;

  const suggestedQuestions = activeTasks.slice(0, 3).map(
    (task) => `Giải thích kiến thức cần để thực hiện “${task.title}”.`,
  );

  // Cuộc trò chuyện theo khóa học
  const activeCourseId = state.user?.courseId || 'general';
  const courseConversations = state.qaConversations.filter(
    (c) => c.courseId === activeCourseId,
  );

  const filteredConversations = courseConversations.filter((c) => {
    if (!searchQuery.trim()) return true;
    const qLower = searchQuery.toLowerCase();
    return (
      c.title.toLowerCase().includes(qLower) ||
      c.messages.some((m) => m.text.toLowerCase().includes(qLower))
    );
  });

  // Phân nhóm thời gian: Hôm nay, 7 ngày trước, Cũ hơn
  const now = new Date();
  const todayStr = now.toDateString();
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

  const todayConvs = filteredConversations.filter(
    (c) => new Date(c.updatedAt).toDateString() === todayStr,
  );
  const recentConvs = filteredConversations.filter((c) => {
    const d = new Date(c.updatedAt);
    return d.toDateString() !== todayStr && d >= sevenDaysAgo;
  });
  const olderConvs = filteredConversations.filter((c) => {
    const d = new Date(c.updatedAt);
    return d < sevenDaysAgo;
  });

  const push = (role: 'user' | 'assistant', text: string, r?: QAResult) => {
    const id = uid('qa');
    dispatch({
      type: 'ADD_QA',
      message: {
        id,
        role,
        text,
        kind: r?.kind,
        citations: r?.citations,
        sources: r?.sources,
        suggestions: r?.suggestions,
        createdAt: new Date().toISOString(),
      },
    });
    return id;
  };

  const ask = async (question: string, alreadyShown = false) => {
    if (requestRef.current || Date.now() < retryAt) return;
    const text = question.trim();
    if (!text) {
      setInputError('Nhập câu hỏi trước khi gửi.');
      return;
    }
    if (text.length > MAX_LEN) {
      setInputError(`Nội dung vượt quá ${MAX_LEN} ký tự. Hãy rút gọn trước khi gửi.`);
      return;
    }
    setInputError('');
    setError(null);
    followLatest();
    if (!alreadyShown) push('user', text);
    setQ('');
    setStreamingText('');
    setLoading(true);
    const controller = new AbortController();
    requestRef.current = controller;
    try {
      const history = state.qaMessages.slice(-4).map((message) => ({ role: message.role, content: message.text.slice(0, 1000) }));
      const r = await askQuestion(text, history, controller.signal, (delta) => {
        if (!controller.signal.aborted) setStreamingText((current) => current + delta);
      });
      if (controller.signal.aborted) return;
      push('assistant', r.text, r);
      setStreamingText('');
    } catch (e) {
      if (controller.signal.aborted) return;
      if (e instanceof ApiError && e.retryAfterSeconds) {
        const cooldownSeconds = Math.max(1, Math.ceil(e.retryAfterSeconds));
        setRetryAt(Date.now() + cooldownSeconds * 1000);
        // Show the server cooldown in the same render as the failed request.
        // The interval effect owns only the subsequent countdown ticks.
        setRetrySeconds(cooldownSeconds);
        toast({ tone: 'warning', title: 'Đang giới hạn yêu cầu', description: e.message });
      }
      setStreamingText('');
      setError({ question: text, requestId: e instanceof ApiError ? e.requestId : 'PW-REQ-UNKNOWN' });
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setLoading(false);
      }
    }
  };

  const submitQA = (e: FormEvent) => {
    e.preventDefault();
    ask(q);
  };

  const handleNewChat = () => {
    requestRef.current?.abort(); requestRef.current = null; setLoading(false); setStreamingText(''); setError(null);
    dispatch({ type: 'CREATE_QA_CONVERSATION' });
  };

  const handleSelectConv = (id: string) => {
    requestRef.current?.abort(); requestRef.current = null; setLoading(false); setStreamingText(''); setError(null);
    dispatch({ type: 'SELECT_QA_CONVERSATION', id });
  };

  const handleStartRename = (e: React.MouseEvent, id: string, currentTitle: string) => {
    e.stopPropagation();
    setEditingId(id);
    setEditTitle(currentTitle);
  };

  const handleSaveRename = (e: React.FormEvent, id: string) => {
    e.preventDefault();
    if (editTitle.trim()) {
      dispatch({ type: 'RENAME_QA_CONVERSATION', id, title: editTitle.trim() });
    }
    setEditingId(null);
  };

  const handleDeleteConv = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (window.confirm('Bạn có chắc chắn muốn xóa đoạn chat này không?')) {
      if (id === state.activeConversationId) {
        requestRef.current?.abort(); requestRef.current = null; setLoading(false); setError(null);
      }
      dispatch({ type: 'DELETE_QA_CONVERSATION', id });
      toast({ tone: 'success', title: 'Đã xóa đoạn chat' });
    }
  };

  const renderConvItem = (conv: QAConversation) => {
    const isActive = state.activeConversationId === conv.id;
    const isEditing = editingId === conv.id;

    if (isEditing) {
      return (
        <form
          key={conv.id}
          onSubmit={(e) => handleSaveRename(e, conv.id)}
          className="flex items-center gap-1 rounded-xl bg-white px-2 py-1.5 shadow-sm border border-primary/40"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            type="text"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            autoFocus
            className="w-full text-xs font-medium text-ink bg-transparent focus:outline-none"
            placeholder="Tên đoạn chat..."
          />
          <button type="submit" className="p-1 text-primary-dark hover:opacity-80" title="Lưu">
            <Icon name="check" size={14} />
          </button>
          <button type="button" onClick={() => setEditingId(null)} className="p-1 text-muted hover:text-ink" title="Hủy">
            <Icon name="x" size={14} />
          </button>
        </form>
      );
    }

    return (
      <div
        key={conv.id}
        onClick={() => { handleSelectConv(conv.id); if (compactHistory) setSidebarOpen(false); }}
        className={cx(
          'group relative flex items-center justify-between rounded-xl px-3 py-2.5 text-xs font-medium cursor-pointer transition select-none',
          isActive
            ? 'bg-blue-50/80 text-primary-dark font-semibold shadow-xs'
            : 'text-slate-600 hover:bg-slate-100/70 hover:text-ink',
        )}
      >
        <span className="truncate pr-14" title={conv.title}>
          {conv.title}
        </span>

        {/* Nút sửa/xóa hover */}
        <div className={cx('absolute right-2 flex items-center gap-0.5', isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 transition')}>
          <button
            type="button"
            onClick={(e) => handleStartRename(e, conv.id, conv.title)}
            className="p-1 rounded-md text-muted hover:text-primary-dark hover:bg-white/80 transition"
            title="Đổi tên đoạn chat"
          >
            <Icon name="edit" size={13} />
          </button>
          <button
            type="button"
            onClick={(e) => handleDeleteConv(e, conv.id)}
            className="p-1 rounded-md text-muted hover:text-danger-ink hover:bg-white/80 transition"
            title="Xóa đoạn chat"
          >
            <Icon name="trash" size={13} />
          </button>
        </div>
      </div>
    );
  };

  const historyContent = (
    <>
          {/* Header Sidebar: Cuộc trò chuyện mới */}
          <div className="p-3.5 space-y-2.5 border-b border-line/50">
            <button
              onClick={() => { handleNewChat(); if (compactHistory) setSidebarOpen(false); }}
              className="flex w-full items-center justify-center gap-2 rounded-2xl border border-line/80 bg-white px-4 py-2.5 text-xs font-semibold text-ink shadow-2xs hover:border-primary/50 hover:bg-primary-light/40 transition active:scale-[0.99]"
            >
              <Icon name="plus" size={16} className="text-primary-dark" />
              <span>Cuộc trò chuyện mới</span>
            </button>

            {/* Ô tìm kiếm đoạn chat */}
            <div className="relative">
              <span className="absolute inset-y-0 left-3 flex items-center text-muted pointer-events-none">
                <Icon name="search" size={14} />
              </span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Tìm kiếm đoạn chat..."
                className="w-full rounded-xl border border-line/70 bg-white pl-8 pr-7 py-1.5 text-xs text-ink placeholder:text-muted focus:border-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/10 transition"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute inset-y-0 right-2 flex items-center text-muted hover:text-ink"
                  title="Xóa tìm kiếm"
                >
                  <Icon name="x" size={12} />
                </button>
              )}
            </div>
          </div>

          {/* Danh sách các phiên hội thoại */}
          <div className="flex-1 overflow-y-auto px-2 py-3 space-y-4 auto-hide-scrollbar">
            {filteredConversations.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted">
                {searchQuery ? 'Không tìm thấy đoạn chat phù hợp.' : 'Chưa có cuộc trò chuyện nào.'}
              </div>
            ) : (
              <>
                {todayConvs.length > 0 && (
                  <div className="space-y-1">
                    <p className="px-3 text-[11px] font-semibold text-muted uppercase tracking-wider">Hôm nay</p>
                    {todayConvs.map(renderConvItem)}
                  </div>
                )}

                {recentConvs.length > 0 && (
                  <div className="space-y-1">
                    <p className="px-3 text-[11px] font-semibold text-muted uppercase tracking-wider">7 ngày trước</p>
                    {recentConvs.map(renderConvItem)}
                  </div>
                )}

                {olderConvs.length > 0 && (
                  <div className="space-y-1">
                    <p className="px-3 text-[11px] font-semibold text-muted uppercase tracking-wider">Cũ hơn</p>
                    {olderConvs.map(renderConvItem)}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Footer Sidebar */}
          <div className="p-3 border-t border-line/50 text-[11px] text-muted text-center flex items-center justify-between px-4">
            <span>{courseConversations.length} cuộc trò chuyện</span>
            {state.qaMessages.length > 0 && (
              <button
                onClick={() => dispatch({ type: 'CLEAR_QA' })}
                className="text-danger-ink hover:underline text-[11px]"
              >
                Xóa tin nhắn
              </button>
            )}
          </div>
    </>
  );
  return (
    <div ref={learningRef} className="learning-page flex min-h-0 min-w-0 overflow-hidden bg-white">
      {compactHistory ? (
        <Modal open={sidebarOpen} onClose={() => setSidebarOpen(false)} title="Lịch sử trò chuyện">
          <div className="flex max-h-[60dvh] min-h-0 flex-col">{historyContent}</div>
        </Modal>
      ) : sidebarOpen && (
        <aside className="flex w-72 shrink-0 flex-col border-r border-line bg-canvas" aria-label="Lịch sử trò chuyện">{historyContent}</aside>
      )}

      {/* 2. KHU VỰC TRÒ CHUYỆN CHÍNH (MAIN CANVAS) */}
      <section aria-label="Trò chuyện học tập" className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-canvas">
        {/* Top Control Bar */}
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-line/60 bg-white/80 px-3 py-2.5 backdrop-blur-sm sm:px-4">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-transparent text-muted transition hover:bg-slate-100 hover:text-ink"
              title={sidebarOpen ? 'Ẩn lịch sử chat' : 'Mở lịch sử chat'}
              aria-label={sidebarOpen ? 'Ẩn lịch sử chat' : 'Mở lịch sử chat'}
              aria-expanded={sidebarOpen}
            >
              <Icon name="menu" size={18} />
            </button>

            <div className="flex min-w-0 items-center gap-2">
              <CourseSwitcher compact notifyOnSuccess={false} />
              <span title={`${activeCourse?.code ?? 'Môn học'}: ${activeCourse?.name ?? 'Kho học liệu'}`} className="truncate text-xs font-semibold text-ink sm:text-sm">
                {activeCourse?.code ?? 'Môn học'}: {activeCourse?.name ?? 'Kho học liệu'}
              </span>
            </div>
          </div>

          <span className="rounded-full bg-primary-light px-3 py-1.5 text-xs font-semibold text-primary-ink">
            Chatbot môn học
          </span>
        </header>

        {/* VÙNG NỘI DUNG CUỘN */}
        <div
          ref={chatViewportRef}
          onScroll={handleChatScroll}
          className="auto-hide-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-6"
          aria-label="Tin nhắn chatbot"
        >
          <div className="mx-auto max-w-3xl space-y-6">
              {/* TRẠNG THÁI TRỐNG: LỜI CHÀO GEMINI */}
              {state.qaMessages.length === 0 && !loading && (
                <div className="flex flex-col items-center justify-center pt-8 pb-6 text-center animate-fade-in">
                  {/* Ngôi sao lấp lánh AI phong cách Gemini */}
                  <div className="relative mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-blue-500 via-indigo-400 to-amber-300 shadow-md shadow-blue-500/10">
                    <Icon name="sparkle" size={28} className="text-[#FFFFFF] drop-shadow-xs" />
                  </div>

                  <h2 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">
                    Xin chào! Hôm nay bạn muốn tìm hiểu kiến thức gì?
                  </h2>
                  <p className="mt-2 max-w-md text-xs sm:text-sm text-slate-500 leading-relaxed">
                    Hỏi về học liệu {activeCourse?.code ?? 'môn học'}. Mỗi câu trả lời có nguồn để đối chiếu; khi thiếu bằng chứng, PaceWise sẽ nói rõ.
                  </p>

                  {/* Suggestion Cards phong cách Google Gemini */}
                  {suggestedQuestions.length > 0 && (
                    <div className="mt-8 grid w-full grid-cols-1 gap-3 sm:grid-cols-3">
                      {suggestedQuestions.map((suggestion) => (
                        <button
                          key={suggestion}
                          onClick={() => ask(suggestion)}
                          className="flex flex-col justify-between rounded-2xl border border-line/80 bg-white p-4 text-left shadow-2xs transition hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-sm"
                        >
                          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50 text-blue-600 mb-2">
                            <Icon name="lightbulb" size={15} />
                          </span>
                          <span className="text-xs font-semibold text-ink line-clamp-3 leading-snug">
                            {suggestion}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* LUỒNG CÂU HỎI VÀ ĐỐI THOẠI */}
              {state.qaMessages.map((m) =>
                m.role === 'user' ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[85%] rounded-3xl rounded-br-md bg-[#2563EB] px-5 py-3 text-[14px] leading-relaxed text-[#FFFFFF] shadow-xs">
                      {m.text}
                    </div>
                  </div>
                ) : (
                  <div key={m.id} className="flex items-start gap-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-blue-600 shadow-2xs border border-line/70">
                      <Icon name="sparkle" size={16} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <AssistantMessage
                        m={m}
                        onOpen={setOpenSource}
                        onAsk={(s) => ask(s)}
                        hintLoading={hintLoading}
                        onHint={async () => {
                          setHintLoading(true);
                          push('user', 'Cho mình gợi ý');
                          const r = await askHint();
                          push('assistant', r.text, r);
                          setHintLoading(false);
                        }}
                      />
                    </div>
                  </div>
                ),
              )}

              {streamingText && (
                <div className="flex items-start gap-3" aria-live="polite">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line/70 bg-white text-blue-600 shadow-2xs">
                    <Icon name="sparkle" size={16} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <AssistantMessage
                      m={{ id: 'streaming-response', role: 'assistant', text: streamingText, createdAt: new Date().toISOString() }}
                      onOpen={setOpenSource}
                      onAsk={(suggestion) => ask(suggestion)}
                      hintLoading={false}
                      onHint={() => undefined}
                    />
                  </div>
                </div>
              )}

              {loading && !streamingText && (
                <div className="flex items-start gap-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-blue-600 shadow-2xs border border-line/70">
                    <Icon name="sparkle" size={16} />
                  </span>
                  <Card className="!p-4 bg-white shadow-2xs border border-line/70 flex-1" aria-busy="true">
                    <p className="flex items-center gap-3 text-xs text-muted">
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-r-transparent" aria-hidden="true" />
                      {[
                        'Đang tìm trong học liệu của môn…',
                        'Đang đối chiếu các đoạn liên quan…',
                        'Đang tổng hợp câu trả lời và kiểm tra trích dẫn…',
                      ][loadingStage]}
                    </p>
                  </Card>
                </div>
              )}

              {error && (
                <ErrorState
                  title="Chưa thể kết nối dịch vụ AI"
                  description="Câu hỏi của bạn vẫn được giữ lại. Chưa có gì bị mất."
                  requestId={error.requestId}
                  onRetry={() => ask(error.question, true)}
                />
              )}
            </div>
        </div>

        {/* 3. FLOATING PILL PROMPT BAR Ở ĐÁY PHONG CÁCH GOOGLE GEMINI */}
        <div className="p-3 bg-gradient-to-t from-white via-white/95 to-transparent shrink-0">
            <form onSubmit={submitQA} className="mx-auto max-w-3xl">
              <div className="flex items-center gap-2 rounded-full border border-line/80 bg-white px-4 py-2 shadow-lg shadow-black/5 focus-within:border-primary-dark focus-within:ring-4 focus-within:ring-primary/10 transition">
                <textarea
                  id="question"
                  rows={1}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(event) => submitChatOnEnter(event, () => void ask(q))}
                  placeholder="Hỏi về khái niệm, bài tập hoặc tra cứu học liệu..."
                  aria-invalid={!!inputError || undefined}
                  className="max-h-32 min-w-0 flex-1 resize-none bg-transparent px-1 py-1 text-xs sm:text-sm text-ink placeholder:text-slate-400 focus:outline-none"
                />

                <button
                  type="submit"
                  disabled={!q.trim() || loading || retrySeconds > 0}
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#2563EB] text-[#FFFFFF] transition hover:opacity-90 disabled:opacity-30 disabled:pointer-events-none active:scale-95"
                  title="Gửi câu hỏi"
                  aria-label="Gửi câu hỏi"
                >
                  {loading ? (
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-r-transparent" />
                  ) : (
                    <Icon name="send" size={15} />
                  )}
                </button>
              </div>

              <div className="mt-1.5 flex items-center justify-between px-3 text-[11px] text-muted">
                <span>{inputError || (retrySeconds > 0 ? `Có thể gửi lại sau ${retrySeconds}s` : 'Enter để gửi · Shift+Enter xuống dòng')}</span>
                <span>{q.length}/{MAX_LEN}</span>
              </div>
            </form>
        </div>
      </section>

      <SourceModal source={openSource} onClose={() => setOpenSource(null)} />
    </div>
  );
}
