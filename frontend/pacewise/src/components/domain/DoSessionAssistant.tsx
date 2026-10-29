import { useEffect, useRef, useState, type FormEvent } from 'react';
import { askDoQuestion, getDoChatHistory } from '../../services/api';
import { useChatAutoScroll } from '../../hooks/useChatAutoScroll';
import type { AssessmentItem, Source } from '../../types';
import type { AdaptiveCheckpoint } from '../../types/adaptiveAssessment';
import type { QAResult } from '../../utils/qa';
import { submitChatOnEnter } from '../../utils/chatInput';
import { uid } from '../../utils/time';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Icon } from '../ui/Icon';
import { AdaptiveDoCheckpoint } from './AdaptiveDoCheckpoint';
import { SourceModal } from './Citation';
import { GroundedAssistantReply } from './GroundedAssistantReply';
import { useLocale } from '../../i18n/LocaleContext';

type AssistantMode = 'learn' | 'assess';

interface SupportMessage {
  id: string;
  role: 'student' | 'assistant';
  text: string;
  result?: QAResult;
}

interface DoSessionAssistantProps {
  courseId: string;
  blockId: string;
  taskTitle: string;
  objective: string;
  assessment?: AssessmentItem;
  mode?: AssistantMode;
  onModeChange?: (mode: AssistantMode) => void;
  onAssessmentStatusChange?: (checkpoint: AdaptiveCheckpoint) => void;
}

function LearningSupportChat({ courseId, blockId, taskTitle, objective }: Omit<DoSessionAssistantProps, 'assessment'>) {
  const { locale, t } = useLocale();
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<SupportMessage[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [error, setError] = useState('');
  const [openSource, setOpenSource] = useState<Source | null>(null);
  const requestGeneration = useRef(0);
  const chatScrollRevision = `${messages.length}:${loading}:${streamingText.length}:${error}`;
  const { containerRef: chatViewportRef, handleScroll: handleChatScroll, followLatest } = useChatAutoScroll(chatScrollRevision);

  useEffect(() => {
    let current = true;
    setRestoring(true);
    setError('');
    void getDoChatHistory(courseId, blockId)
      .then((saved) => {
        if (current) setMessages(saved);
      })
      .catch((failure) => {
        if (current) setError(locale === 'en'
          ? 'Could not restore this session conversation.'
          : failure instanceof Error ? failure.message : 'Chưa khôi phục được hội thoại phiên này.');
      })
      .finally(() => {
        if (current) setRestoring(false);
      });
    return () => { current = false; };
  }, [blockId, courseId]);

  const ask = async () => {
    const text = question.trim();
    if (!text || loading || restoring) return;
    const generation = ++requestGeneration.current;
    followLatest();
    setMessages((current) => [...current, { id: uid('do-support-message'), role: 'student', text }]);
    setQuestion('');
    setError('');
    setStreamingText('');
    setLoading(true);
    try {
      const result = await askDoQuestion(
        { courseId, blockId, taskTitle, objective, question: text },
        (delta) => {
          if (requestGeneration.current === generation) setStreamingText((current) => current + delta);
        },
        locale,
      );
      if (requestGeneration.current !== generation) return;
      setMessages((current) => [...current, {
        id: uid('do-support-message'), role: 'assistant', text: result.text, result,
      }]);
      setStreamingText('');
    } catch (failure) {
      if (requestGeneration.current === generation) {
        setStreamingText('');
        setError(locale === 'en'
          ? 'Could not answer the question. Please try again.'
          : failure instanceof Error ? failure.message : 'Chưa thể trả lời câu hỏi. Hãy thử lại.');
        setQuestion(text);
      }
    } finally {
      if (requestGeneration.current === generation) setLoading(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void ask();
  };

  return (
    <div aria-labelledby="do-support-tab">
      <div
        ref={chatViewportRef}
        onScroll={handleChatScroll}
        className="auto-hide-scrollbar h-[clamp(300px,46dvh,420px)] space-y-3 overflow-y-auto overscroll-contain px-4 py-4"
        aria-live="polite"
        aria-label={t('Hội thoại hỗ trợ học trong phiên', 'In-session learning support conversation')}
      >
        {restoring && (
          <p className="flex items-center gap-2 text-sm text-muted" role="status">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-r-transparent" aria-hidden="true" />
            {t('Đang khôi phục hội thoại phiên này…', 'Restoring this session conversation…')}
          </p>
        )}
        {!restoring && messages.length === 0 && (
          <div className="rounded-xl border border-line bg-canvas p-3 text-sm">
            <p className="font-semibold">{t('Bạn đang vướng phần nào?', 'What part are you stuck on?')}</p>
            <p className="mt-1 text-muted">{t(
              'Hỏi về khái niệm, ví dụ hoặc bước làm. Câu trả lời sẽ kèm nguồn học liệu khi có.',
              'Ask about a concept, example, or solution step. Answers include course-material sources when available.',
            )}</p>
          </div>
        )}
        {messages.map((message) => (
          <div key={message.id} className={message.role === 'student' ? 'ml-8 flex justify-end sm:ml-10' : 'flex justify-start sm:mr-4'}>
            {message.role === 'assistant' && message.result ? (
              <div className="min-w-0 w-full">
                <GroundedAssistantReply message={{ ...message.result, text: message.text }} onOpen={setOpenSource} />
              </div>
            ) : (
              <div className="max-w-full rounded-2xl rounded-br-md bg-primary-dark px-3.5 py-2.5 text-sm text-white">
                <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{message.text}</p>
              </div>
            )}
          </div>
        ))}
        {streamingText && (
          <div className="flex justify-start sm:mr-4" aria-live="polite" aria-busy="true">
            <div className="min-w-0 w-full">
              <GroundedAssistantReply message={{ kind: 'conversation', text: streamingText, sources: [], suggestions: [] }} onOpen={setOpenSource} />
              <span className="ml-4 inline-block animate-pulse text-lg leading-none text-primary-dark" aria-label={t('AI đang trả lời', 'AI is responding')}>▍</span>
            </div>
          </div>
        )}
        {loading && !streamingText && (
          <p className="flex items-center gap-2 text-sm text-muted" role="status">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-r-transparent" aria-hidden="true" />
            {t('Đang tìm trong học liệu của môn…', 'Searching the course materials…')}
          </p>
        )}
      </div>
      <form className="border-t border-line bg-white p-4" onSubmit={submit}>
        <label className="sr-only" htmlFor="do-support-question">{t('Hỏi về nội dung đang học', 'Ask about the current topic')}</label>
        <div className="flex items-end gap-2">
          <textarea
            id="do-support-question"
            rows={2}
            value={question}
            onChange={(event) => setQuestion(event.target.value.slice(0, 1200))}
            onKeyDown={(event) => submitChatOnEnter(event, () => void ask())}
            disabled={loading || restoring}
            title={t('Enter để gửi · Shift+Enter xuống dòng', 'Enter to send · Shift+Enter for a new line')}
            className="min-h-11 flex-1 resize-none rounded-xl border border-line bg-white px-3 py-2 text-sm focus:border-primary-dark focus:outline-none"
            placeholder={t('Hỏi về nội dung đang học…', 'Ask about the current topic…')}
          />
          <Button type="submit" size="sm" icon="send" loading={loading} disabled={restoring || !question.trim()} aria-label={t('Gửi câu hỏi học tập', 'Send learning question')} />
        </div>
        <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-muted">
          <span>{error || t('Enter để gửi · Shift+Enter xuống dòng', 'Enter to send · Shift+Enter for a new line')}</span>
          <span>{question.length}/1200</span>
        </div>
        {error && <p role="alert" className="sr-only">{error}</p>}
      </form>
      <SourceModal source={openSource} onClose={() => setOpenSource(null)} />
    </div>
  );
}

export function DoSessionAssistant(props: DoSessionAssistantProps) {
  const { locale, t } = useLocale();
  const [internalMode, setInternalMode] = useState<AssistantMode>('learn');
  const [assessmentVisited, setAssessmentVisited] = useState(false);
  const mode = props.mode ?? internalMode;

  useEffect(() => {
    if (mode === 'assess') setAssessmentVisited(true);
  }, [mode]);

  const selectMode = (nextMode: AssistantMode) => {
    setInternalMode(nextMode);
    props.onModeChange?.(nextMode);
    if (nextMode === 'assess') setAssessmentVisited(true);
  };

  return (
    <Card className="overflow-hidden !p-0" aria-labelledby="do-session-assistant-title">
      <div className="px-4 pt-4">
        <div className="flex items-center gap-2">
          <Icon name="message" size={18} className="text-primary-ink" />
          <h2 id="do-session-assistant-title" className="font-bold">{t('Trợ lý trong phiên', 'Session assistant')}</h2>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1" role="tablist" aria-label={t('Chế độ trợ lý trong phiên', 'Session assistant mode')}>
          <button
            id="do-support-tab"
            type="button"
            role="tab"
            aria-selected={mode === 'learn'}
            aria-controls="do-support-panel"
            onClick={() => selectMode('learn')}
            className={`min-h-10 rounded-lg px-3 text-sm font-semibold transition ${mode === 'learn' ? 'bg-white text-primary-ink shadow-sm' : 'text-muted hover:text-ink'}`}
          >
            {t('Hỏi để học', 'Learn with AI')}
          </button>
          <button
            id="do-assessment-tab"
            type="button"
            role="tab"
            aria-selected={mode === 'assess'}
            aria-controls="do-assessment-panel"
            onClick={() => selectMode('assess')}
            className={`min-h-10 rounded-lg px-3 text-sm font-semibold transition ${mode === 'assess' ? 'bg-white text-primary-ink shadow-sm' : 'text-muted hover:text-ink'}`}
          >
            {t('Kiểm tra mình', 'Self-check')}
          </button>
        </div>
      </div>

      <div id="do-support-panel" role="tabpanel" aria-labelledby="do-support-tab" hidden={mode !== 'learn'}>
        <LearningSupportChat {...props} />
      </div>
      <div id="do-assessment-panel" role="tabpanel" aria-labelledby="do-assessment-tab" hidden={mode !== 'assess'}>
        {assessmentVisited && (props.assessment ? (
          <AdaptiveDoCheckpoint
            embedded
            courseId={props.courseId}
            blockId={props.blockId}
            assessment={props.assessment}
            onStatusChange={props.onAssessmentStatusChange}
          />
        ) : (
          <div id="do-understanding-checkpoint" className="p-4" role="status">
            <div className="rounded-xl border border-line bg-canvas p-3 text-sm">
              <p className="font-semibold">{locale === 'en' ? 'Self-check is not available yet' : 'Chatbot kiểm tra chưa thể bắt đầu'}</p>
              <p className="mt-1 text-muted">{locale === 'en'
                ? 'No instructor-approved question and rubric match this session yet. You can still use “Learn with AI”; support answers are not treated as assessment evidence.'
                : 'Chưa có câu hỏi và rubric được giảng viên duyệt cho đúng nội dung ca này. Bạn vẫn có thể dùng “Hỏi để học”; câu trả lời hỗ trợ không được dùng làm bằng chứng đánh giá.'}</p>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
