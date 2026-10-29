import { useEffect, useRef, useState, type FormEvent } from 'react';
import { adaptiveCheckpointAction, getDueAssessmentProbes, startAdaptiveCheckpoint } from '../../services/api';
import { useChatAutoScroll } from '../../hooks/useChatAutoScroll';
import type { AssessmentItem } from '../../types';
import type { AdaptiveCheckpoint, DelayedProbe } from '../../types/adaptiveAssessment';
import { submitChatOnEnter } from '../../utils/chatInput';
import { uid } from '../../utils/time';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Icon } from '../ui/Icon';
import { useLocale, type Locale } from '../../i18n/LocaleContext';

const activeStatuses = new Set(['active', 'needs_support', 'verification_required']);

interface AssessmentMessage {
  id: string;
  role: 'agent' | 'student' | 'system';
  text: string;
  kind?: 'question' | 'feedback' | 'hint' | 'notice';
}

function verificationNotice(checkpoint: AdaptiveCheckpoint, locale: Locale): string {
  if (checkpoint.reason === 'need_unseen_item_without_hint') {
    return locale === 'en'
      ? 'Your answer met the expected ideas. Because you used a hint, answer one more question without a hint to confirm your understanding.'
      : 'Câu trả lời đã đạt các ý cần thiết. Vì bạn đã dùng gợi ý, hãy trả lời thêm một câu không gợi ý để xác nhận mức hiểu.';
  }
  if (checkpoint.reason === 'formative_requires_approved_anchor') {
    return locale === 'en'
      ? 'That practice answer was recorded. Answer one instructor-approved question to confirm the planning signal.'
      : 'Câu luyện tập đã được ghi nhận. Hãy trả lời thêm một câu đã được giảng viên duyệt để xác nhận tín hiệu cho Plan.';
  }
  return locale === 'en'
    ? 'Your answer did not yet match enough of the expected ideas. Try one more short question.'
    : 'Câu trả lời chưa khớp đủ các ý cần kiểm tra. Thử thêm một câu ngắn nhé.';
}

function answerNotice(checkpoint: AdaptiveCheckpoint, locale: Locale): string {
  if (checkpoint.status === 'verification_required') return verificationNotice(checkpoint, locale);
  if (checkpoint.status === 'needs_support') {
    return locale === 'en'
      ? 'Your answer did not address enough of this question yet. Try again and focus on what the question asks.'
      : 'Câu trả lời chưa đáp ứng đủ ý của câu hỏi này. Hãy thử lại và tập trung đúng nội dung đang được hỏi.';
  }
  if (checkpoint.status === 'completed') {
    return locale === 'en'
      ? 'Check complete. The result was recorded for Plan.'
      : 'Đã hoàn tất kiểm tra. Kết quả đã được ghi nhận cho Plan.';
  }
  if (checkpoint.status === 'stopped' || checkpoint.status === 'review_required') {
    return locale === 'en'
      ? 'Recorded as an unknown planning signal. Your schedule has not changed.'
      : 'Đã ghi nhận là tín hiệu chưa xác định. Lịch chưa thay đổi.';
  }
  if (checkpoint.status === 'active') {
    return locale === 'en'
      ? 'Answer recorded. Continue with the next question.'
      : 'Đã ghi nhận câu trả lời. Tiếp tục với câu tiếp theo.';
  }
  return locale === 'en' ? 'Answer recorded.' : 'Đã ghi nhận câu trả lời.';
}

function initialMessages(checkpoint: AdaptiveCheckpoint, fallbackQuestion: string, locale: Locale): AssessmentMessage[] {
  const messages: AssessmentMessage[] = [];
  if (checkpoint.status === 'coverage_gap') {
    messages.push({
      id: uid('assessment-message'), role: 'system', kind: 'notice',
      text: locale === 'en'
        ? 'No approved question is available for this topic. The current Plan remains unchanged.'
        : 'Chưa có câu hỏi được duyệt cho nội dung này. Plan hiện tại không thay đổi.',
    });
  } else if (checkpoint.status === 'completed') {
    messages.push({ id: uid('assessment-message'), role: 'system', kind: 'notice',
      text: locale === 'en'
        ? 'Recorded for Plan. Your schedule has not been changed.'
        : 'Đã ghi nhận cho Plan. Lịch của bạn chưa thay đổi.' });
  } else if (checkpoint.status === 'stopped' || checkpoint.status === 'review_required') {
    messages.push({ id: uid('assessment-message'), role: 'system', kind: 'notice',
      text: locale === 'en'
        ? 'Recorded as an unknown planning signal. Your schedule has not changed.'
        : 'Đã ghi nhận là tín hiệu chưa xác định. Lịch chưa thay đổi.' });
  } else {
    if (checkpoint.status === 'verification_required') {
      messages.push({ id: uid('assessment-message'), role: 'system', kind: 'notice',
        text: verificationNotice(checkpoint, locale) });
    }
    if (checkpoint.question?.text || fallbackQuestion) {
    messages.push({
      id: uid('assessment-message'), role: 'agent', kind: 'question',
      text: checkpoint.question?.text ?? fallbackQuestion,
    });
    }
  }
  return messages;
}

export function AdaptiveDoCheckpoint({
  courseId,
  blockId,
  assessment,
  onStatusChange,
  embedded = false,
}: {
  courseId: string;
  blockId: string;
  assessment: AssessmentItem;
  onStatusChange?: (checkpoint: AdaptiveCheckpoint) => void;
  embedded?: boolean;
}) {
  const { locale } = useLocale();
  const [checkpoint, setCheckpoint] = useState<AdaptiveCheckpoint | null>(null);
  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [due, setDue] = useState<DelayedProbe[]>([]);
  const [messages, setMessages] = useState<AssessmentMessage[]>([]);
  const [conversationPaused, setConversationPaused] = useState(false);
  const generation = useRef(0);
  const pending = useRef<{ body: string; key: string } | null>(null);
  const transcriptRevision = `${messages.length}:${busy}:${error}`;
  const { containerRef: transcriptRef, handleScroll: handleTranscriptScroll, followLatest } = useChatAutoScroll(transcriptRevision);

  useEffect(() => {
    const current = ++generation.current;
    setCheckpoint(null); setAnswer(''); setError(''); setBusy(true); setDue([]); setMessages([]);
    setConversationPaused(false); pending.current = null;
    void startAdaptiveCheckpoint({ courseId, blockId, assessmentId: assessment.id }).then((result) => {
      if (generation.current === current) {
        setCheckpoint(result);
        setMessages(initialMessages(result, assessment.question, locale));
        onStatusChange?.(result);
      }
    }).catch((failure: unknown) => {
      if (generation.current === current) setError(failure instanceof Error
        ? failure.message
        : locale === 'en' ? 'Could not load the self-check.' : 'Chưa tải được phần tự kiểm tra.');
    }).finally(() => { if (generation.current === current) setBusy(false); });
    void getDueAssessmentProbes(courseId).then((probes) => {
      if (generation.current === current) setDue(probes.filter((probe) => assessment.knowledgeComponentIds?.includes(probe.kc_id)));
    }).catch(() => { /* Optional reminders must not block learning. */ });
    return () => { generation.current += 1; };
  }, [courseId, blockId, assessment.id, locale, onStatusChange]);

  const act = async (action: 'hint' | 'answer') => {
    if (!checkpoint || busy) return;
    followLatest();
    const current = generation.current;
    const body = `${checkpoint.session_id}:${action}:${action === 'answer' ? answer.trim() : ''}`;
    if (pending.current?.body !== body) pending.current = { body, key: uid('checkpoint-event') };
    setBusy(true); setError('');
    try {
      const result = await adaptiveCheckpointAction({ sessionId: checkpoint.session_id, courseId, action,
        eventKey: pending.current.key, answer: action === 'answer' ? answer.trim() : '', locale });
      if (generation.current !== current) return;
      const submittedAnswer = answer.trim();
      setMessages((currentMessages) => {
        const next = [...currentMessages];
        if (action === 'answer') {
          next.push({ id: uid('assessment-message'), role: 'student', text: submittedAnswer });
          next.push({ id: uid('assessment-message'), role: 'system', kind: 'notice', text: answerNotice(result, locale) });
        } else if (result.hint && result.hint !== checkpoint.hint) {
          next.push({ id: uid('assessment-message'), role: 'agent', kind: 'hint',
            text: `${locale === 'en' ? 'Hint' : 'Gợi ý'}: ${result.hint}` });
        }
        if (result.status === 'coverage_gap') {
          next.push({ id: uid('assessment-message'), role: 'system', kind: 'notice',
            text: locale === 'en'
              ? 'No approved question is available for this topic. The current Plan remains unchanged.'
              : 'Chưa có câu hỏi được duyệt cho nội dung này. Plan hiện tại không thay đổi.' });
        } else if (result.question?.text && result.question.id !== checkpoint.question?.id) {
          next.push({ id: uid('assessment-message'), role: 'agent', kind: 'question', text: result.question.text });
        }
        return next;
      });
      if (action === 'answer') setAnswer('');
      setCheckpoint(result); pending.current = null; onStatusChange?.(result);
    } catch (failure) {
      if (generation.current === current) setError(failure instanceof Error
        ? failure.message
        : locale === 'en' ? 'Could not submit the answer.' : 'Chưa gửi được câu trả lời.');
    } finally { if (generation.current === current) setBusy(false); }
  };

  const openProbe = async (probeId?: string, restart = false) => {
    const current = generation.current;
    setBusy(true); setError('');
    try {
      const result = await startAdaptiveCheckpoint({ courseId, blockId, assessmentId: assessment.id,
        probeId: probeId ?? (restart ? checkpoint?.probe_id ?? undefined : undefined), restart });
      if (generation.current === current) {
        setCheckpoint(result); setAnswer(''); setConversationPaused(false);
        setMessages(initialMessages(result, assessment.question, locale));
        pending.current = null; onStatusChange?.(result);
      }
    } catch (failure) {
      if (generation.current === current) setError(failure instanceof Error
        ? failure.message
        : locale === 'en' ? 'Could not open the retention check.' : 'Chưa mở được kiểm tra ghi nhớ.');
    } finally { if (generation.current === current) setBusy(false); }
  };

  const submit = (event: FormEvent) => { event.preventDefault(); void act('answer'); };
  const active = checkpoint ? activeStatuses.has(checkpoint.status) : false;
  const content = (
    <>
      <div className="border-b border-line px-4 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2"><Icon name="message" size={18} className="text-primary-ink" /><h2 id="do-checkpoint-title" className="font-bold">{locale === 'en' ? 'Self-check' : 'Kiểm tra mình'}</h2></div>
          </div>
          {active && (
            <Button type="button" size="sm" variant="ghost" onClick={() => setConversationPaused((value) => !value)}>
              {conversationPaused ? (locale === 'en' ? 'Resume' : 'Tiếp tục') : (locale === 'en' ? 'Pause' : 'Tạm dừng')}
            </Button>
          )}
        </div>
        <p className="mt-2 text-xs text-muted">
          {locale === 'en'
            ? 'The question and expected ideas are instructor-approved. Your answer only adds signals for Plan/Replan; it is not a course grade.'
            : 'Câu hỏi và các ý đúng đã được giảng viên duyệt. Câu trả lời chỉ bổ sung tín hiệu cho Plan/Replan, không phải điểm môn học.'}
        </p>
        {checkpoint && (
          <div className="mt-3">
            <p className="text-xs font-semibold">
              {checkpoint.mode === 'retention'
                ? (locale === 'en' ? 'Retention check' : 'Kiểm tra ghi nhớ')
                : checkpoint.status === 'verification_required'
                  ? (locale === 'en' ? 'Additional question' : 'Câu hỏi bổ sung')
                  : (locale === 'en' ? 'Written understanding check' : 'Câu hỏi kiểm tra mức hiểu')}
            </p>
          </div>
        )}
      </div>

      {checkpoint?.question?.formative_only && <p role="status" className="mx-4 mt-3 rounded-lg bg-warning-light p-3 text-xs text-warning-ink">{locale === 'en' ? 'Practice only. An approved question will verify the planning signal.' : 'Chỉ là câu luyện tập. Tín hiệu cho Plan sẽ được kiểm tra bằng câu đã duyệt.'}</p>}
      {checkpoint?.status === 'coverage_gap' && <p role="status" className="sr-only">{locale === 'en' ? 'No approved question is available for this step.' : 'Chưa có câu hỏi được duyệt cho bước này.'}</p>}

      <div ref={transcriptRef} onScroll={handleTranscriptScroll} className="auto-hide-scrollbar h-[clamp(300px,46dvh,420px)] space-y-3 overflow-y-auto overscroll-contain bg-canvas/50 px-4 py-4" aria-live="polite" aria-label={locale === 'en' ? 'Understanding check conversation' : 'Hội thoại kiểm tra mức hiểu'}>
        {busy && messages.length === 0 && <p className="text-sm text-muted">{locale === 'en' ? 'Preparing an approved question…' : 'Đang chuẩn bị câu hỏi đã duyệt…'}</p>}
        {messages.map((message) => (
          <div key={message.id} className={message.role === 'student' ? 'ml-10 flex justify-end' : message.role === 'system' ? 'flex justify-center' : 'mr-8 flex justify-start'}>
            <div className={message.role === 'student'
              ? 'max-w-full rounded-2xl rounded-br-md bg-primary-dark px-3.5 py-2.5 text-sm text-white'
              : message.role === 'system'
                ? 'max-w-[92%] rounded-xl border border-line bg-white px-3 py-2 text-center text-xs text-muted'
                : message.kind === 'hint'
                  ? 'max-w-[92%] rounded-2xl rounded-bl-md border border-warning bg-warning-light px-3.5 py-2.5 text-sm'
                  : 'max-w-[92%] rounded-2xl rounded-bl-md border border-line bg-white px-3.5 py-2.5 text-sm'}>
              <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{message.text}</p>
            </div>
          </div>
        ))}
        {busy && messages.length > 0 && <p className="text-sm text-muted">{locale === 'en' ? 'Recording your answer…' : 'Đang ghi nhận câu trả lời…'}</p>}
      </div>

      {conversationPaused ? (
        <div className="border-t border-line p-4 text-center">
          <p className="text-sm font-semibold">{locale === 'en' ? 'Self-check paused' : 'Đã tạm dừng'}</p>
          <p className="mt-1 text-xs text-muted">{locale === 'en' ? 'This conversation stays in the current study session.' : 'Hội thoại vẫn được giữ trong phiên học hiện tại.'}</p>
          <Button type="button" className="mt-3" size="sm" onClick={() => setConversationPaused(false)}>{locale === 'en' ? 'Resume' : 'Tiếp tục'}</Button>
        </div>
      ) : (
        <form className="border-t border-line bg-white p-4" onSubmit={submit}>
          <label className="sr-only" htmlFor="do-checkpoint-answer">{locale === 'en' ? 'Answer in your own words' : 'Trả lời bằng lời của bạn'}</label>
          <div className="flex items-end gap-2">
            <textarea id="do-checkpoint-answer" rows={2} value={answer} onChange={(event) => setAnswer(event.target.value)}
              onKeyDown={(event) => submitChatOnEnter(event, () => void act('answer'))}
              disabled={busy || !active} title={locale === 'en' ? 'Enter to send · Shift+Enter for a new line' : 'Enter để gửi · Shift+Enter xuống dòng'}
              className="min-h-11 flex-1 resize-none rounded-xl border border-line bg-white px-3 py-2 text-sm focus:border-primary-dark focus:outline-none"
              placeholder={active ? (locale === 'en' ? 'Answer in your own words…' : 'Trả lời theo cách hiểu của bạn…') : (locale === 'en' ? 'No more answers are needed' : 'Không cần trả lời thêm')} />
            <Button type="submit" size="sm" icon="send" loading={busy} disabled={!active || !answer.trim()} aria-label={locale === 'en' ? 'Send answer' : 'Gửi câu trả lời'} />
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => void act('hint')} disabled={busy || !active || checkpoint?.hint_level === 5}>{locale === 'en' ? 'Get a hint' : 'Nhận gợi ý'}</Button>
            <p className="text-[11px] text-muted">{locale === 'en' ? 'Enter to send · Shift+Enter for a new line' : 'Enter để gửi · Shift+Enter xuống dòng'}</p>
          </div>
        </form>
      )}

      {error && <p role="alert" className="mx-4 mb-3 rounded-lg bg-danger-light p-2 text-xs text-danger-ink">{error}</p>}
      {(checkpoint?.status === 'stopped' || checkpoint?.status === 'review_required' || checkpoint?.status === 'coverage_gap') &&
        <Button className="mx-4 mb-3" type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void openProbe(undefined, true)}>{locale === 'en' ? 'Try another approved question' : 'Thử câu đã duyệt khác'}</Button>}
      {checkpoint?.delayed_probe && <p className="mx-4 mb-3 text-xs text-muted">{locale === 'en' ? 'Retention check available from' : 'Có thể kiểm tra ghi nhớ từ'}: {new Date(checkpoint.delayed_probe.due_at).toLocaleString(locale === 'en' ? 'en-US' : 'vi-VN')}.</p>}
      {due.map((probe) => <Button className="mx-4 mb-3" key={probe.id} type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void openProbe(probe.id)}>{locale === 'en' ? 'Run due retention check' : 'Kiểm tra ghi nhớ đến hạn'}</Button>)}
    </>
  );
  if (embedded) {
    return <div id="do-understanding-checkpoint" aria-labelledby="do-checkpoint-title">{content}</div>;
  }
  return <Card id="do-understanding-checkpoint" className="overflow-hidden !p-0" aria-labelledby="do-checkpoint-title">{content}</Card>;
}
