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

const labels = {
  recall: 'Nhắc lại ý chính',
  explain: 'Giải thích theo cách của bạn',
  why: 'Vì sao điều này đúng?',
  application: 'Thử áp dụng',
  transfer: 'Thử tình huống khác',
};
const activeStatuses = new Set(['active', 'needs_support', 'verification_required']);
const stageOrder = ['recall', 'explain', 'why', 'application', 'transfer'] as const;

interface AssessmentMessage {
  id: string;
  role: 'agent' | 'student' | 'system';
  text: string;
  kind?: 'question' | 'feedback' | 'hint' | 'notice';
}

function initialMessages(checkpoint: AdaptiveCheckpoint, fallbackQuestion: string): AssessmentMessage[] {
  const messages: AssessmentMessage[] = [];
  if (checkpoint.last_result?.feedback) {
    messages.push({ id: uid('assessment-message'), role: 'agent', kind: 'feedback', text: checkpoint.last_result.feedback });
  }
  if (checkpoint.status === 'coverage_gap') {
    messages.push({
      id: uid('assessment-message'), role: 'system', kind: 'notice',
      text: `Chưa có câu hỏi được duyệt cho bước “${labels[checkpoint.stage]}”. Bạn có thể tiếp tục học và Reflect.`,
    });
  } else if (checkpoint.question?.text || fallbackQuestion) {
    messages.push({
      id: uid('assessment-message'), role: 'agent', kind: 'question',
      text: checkpoint.question?.text ?? fallbackQuestion,
    });
  }
  if (checkpoint.status === 'completed') {
    messages.push({ id: uid('assessment-message'), role: 'system', kind: 'notice',
      text: 'Đã ghi nhận bằng chứng mức hiểu. Kết quả sẽ được Reflect tổng hợp; lịch chưa bị tự thay đổi.' });
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
        setMessages(initialMessages(result, assessment.question));
        onStatusChange?.(result);
      }
    }).catch((failure: unknown) => {
      if (generation.current === current) setError(failure instanceof Error ? failure.message : 'Chưa tải được checkpoint.');
    }).finally(() => { if (generation.current === current) setBusy(false); });
    void getDueAssessmentProbes(courseId).then((probes) => {
      if (generation.current === current) setDue(probes.filter((probe) => assessment.knowledgeComponentIds?.includes(probe.kc_id)));
    }).catch(() => { /* Optional reminders must not block learning. */ });
    return () => { generation.current += 1; };
  }, [courseId, blockId, assessment.id, onStatusChange]);

  const act = async (action: 'hint' | 'answer') => {
    if (!checkpoint || busy) return;
    followLatest();
    const current = generation.current;
    const body = `${checkpoint.session_id}:${action}:${action === 'answer' ? answer.trim() : ''}`;
    if (pending.current?.body !== body) pending.current = { body, key: uid('checkpoint-event') };
    setBusy(true); setError('');
    try {
      const result = await adaptiveCheckpointAction({ sessionId: checkpoint.session_id, courseId, action,
        eventKey: pending.current.key, answer: action === 'answer' ? answer.trim() : '' });
      if (generation.current !== current) return;
      const submittedAnswer = answer.trim();
      setMessages((currentMessages) => {
        const next = [...currentMessages];
        if (action === 'answer') {
          next.push({ id: uid('assessment-message'), role: 'student', text: submittedAnswer });
          if (result.last_result?.feedback) {
            next.push({ id: uid('assessment-message'), role: 'agent', kind: 'feedback', text: result.last_result.feedback });
          }
        } else if (result.hint && result.hint !== checkpoint.hint) {
          next.push({ id: uid('assessment-message'), role: 'agent', kind: 'hint', text: `Gợi ý: ${result.hint}` });
        }
        if (result.status === 'coverage_gap') {
          next.push({ id: uid('assessment-message'), role: 'system', kind: 'notice',
            text: `Chưa có câu hỏi được duyệt cho bước “${labels[result.stage]}”. Chưa đủ bằng chứng để kết luận bước này.` });
        } else if (result.question?.text && result.question.id !== checkpoint.question?.id) {
          next.push({ id: uid('assessment-message'), role: 'agent', kind: 'question', text: result.question.text });
        }
        if (result.status === 'completed') {
          next.push({ id: uid('assessment-message'), role: 'system', kind: 'notice',
            text: 'Đã ghi nhận bằng chứng mức hiểu. Kết quả sẽ được Reflect tổng hợp; lịch chưa bị tự thay đổi.' });
        }
        return next;
      });
      if (action === 'answer') setAnswer('');
      setCheckpoint(result); pending.current = null; onStatusChange?.(result);
    } catch (failure) {
      if (generation.current === current) setError(failure instanceof Error ? failure.message : 'Chưa gửi được checkpoint.');
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
        setMessages(initialMessages(result, assessment.question));
        pending.current = null; onStatusChange?.(result);
      }
    } catch (failure) {
      if (generation.current === current) setError(failure instanceof Error ? failure.message : 'Chưa mở được kiểm tra nhớ.');
    } finally { if (generation.current === current) setBusy(false); }
  };

  const submit = (event: FormEvent) => { event.preventDefault(); void act('answer'); };
  const active = checkpoint ? activeStatuses.has(checkpoint.status) : false;
  const stageNumber = checkpoint ? stageOrder.indexOf(checkpoint.stage) + 1 : 1;
  const progress = checkpoint?.mode === 'retention' ? 100 : Math.max(20, stageNumber * 20);
  const content = (
    <>
      <div className="border-b border-line px-4 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2"><Icon name="message" size={18} className="text-primary-ink" /><h2 id="do-checkpoint-title" className="font-bold">Kiểm tra mình</h2></div>
          </div>
          {active && (
            <Button type="button" size="sm" variant="ghost" onClick={() => setConversationPaused((value) => !value)}>
              {conversationPaused ? 'Tiếp tục kiểm tra' : 'Dừng kiểm tra'}
            </Button>
          )}
        </div>
        {checkpoint && (
          <div className="mt-3">
            <div className="flex items-center justify-between gap-3 text-xs font-semibold">
              <span>{checkpoint.mode === 'retention' ? 'Kiểm tra lại khả năng ghi nhớ' : `Bước ${stageNumber}/5 · ${labels[checkpoint.stage]}`}</span>
              <span className="text-muted">{progress}%</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100" aria-hidden="true"><div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${progress}%` }} /></div>
          </div>
        )}
      </div>

      {checkpoint?.question?.formative_only && <p role="status" className="mx-4 mt-3 rounded-lg bg-warning-light p-3 text-xs text-warning-ink">Câu AI này chỉ hỗ trợ đối thoại, không dùng để nâng mức hiểu. Sau đó hệ thống sẽ kiểm chứng bằng câu đã duyệt.</p>}
      {checkpoint?.status === 'coverage_gap' && <p role="status" className="sr-only">Chưa có câu hỏi được duyệt cho mức này.</p>}

      <div ref={transcriptRef} onScroll={handleTranscriptScroll} className="auto-hide-scrollbar h-[clamp(300px,46dvh,420px)] space-y-3 overflow-y-auto overscroll-contain bg-canvas/50 px-4 py-4" aria-live="polite" aria-label="Hội thoại kiểm tra mức hiểu">
        {busy && messages.length === 0 && <p className="text-sm text-muted">Đang chuẩn bị câu hỏi đã duyệt…</p>}
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
        {busy && messages.length > 0 && <p className="text-sm text-muted">Assessment Agent đang xem câu trả lời…</p>}
      </div>

      {conversationPaused ? (
        <div className="border-t border-line p-4 text-center">
          <p className="text-sm font-semibold">Đã dừng kiểm tra tạm thời</p>
          <p className="mt-1 text-xs text-muted">Hội thoại vẫn được giữ trong phiên Do này và không ảnh hưởng đồng hồ học.</p>
          <Button type="button" className="mt-3" size="sm" onClick={() => setConversationPaused(false)}>Tiếp tục kiểm tra</Button>
        </div>
      ) : (
        <form className="border-t border-line bg-white p-4" onSubmit={submit}>
          <label className="sr-only" htmlFor="do-checkpoint-answer">Trả lời bằng lời của bạn</label>
          <div className="flex items-end gap-2">
            <textarea id="do-checkpoint-answer" rows={2} value={answer} onChange={(event) => setAnswer(event.target.value)}
              onKeyDown={(event) => submitChatOnEnter(event, () => void act('answer'))}
              disabled={busy || !active} title="Enter để gửi · Shift+Enter xuống dòng"
              className="min-h-11 flex-1 resize-none rounded-xl border border-line bg-white px-3 py-2 text-sm focus:border-primary-dark focus:outline-none"
              placeholder={active ? 'Trả lời theo cách hiểu của bạn…' : 'Bài kiểm tra hiện không nhận thêm câu trả lời'} />
            <Button type="submit" size="sm" icon="send" loading={busy} disabled={!active || !answer.trim()} aria-label="Gửi câu trả lời" />
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => void act('hint')} disabled={busy || !active || checkpoint?.hint_level === 5}>Nhận một gợi ý</Button>
            <p className="text-[11px] text-muted">Enter để gửi · Shift+Enter xuống dòng</p>
          </div>
        </form>
      )}

      {error && <p role="alert" className="mx-4 mb-3 rounded-lg bg-danger-light p-2 text-xs text-danger-ink">{error}</p>}
      {checkpoint?.last_result && (
        <p className="mx-4 mb-3 text-xs text-muted">
          Đánh giá dựa trên câu hỏi được giảng viên duyệt{assessment.source || checkpoint.question?.source
            ? ` · ${assessment.source || checkpoint.question?.source}` : ''}. Nguồn và rubric không được hiển thị trước khi bạn trả lời.
        </p>
      )}
      {checkpoint?.last_result && <details className="mx-4 mb-3 rounded-xl border border-line bg-white p-3 text-xs">
        <summary className="cursor-pointer font-semibold">Xem bằng chứng của câu gần nhất</summary>
        <p className="mt-2 text-muted">{checkpoint.last_result.provisional ? 'Mức tạm thời (chưa xác nhận)' : 'Mức đã thể hiện'}: {checkpoint.last_result.demonstrated_level} · Tin cậy: {checkpoint.last_result.confidence}</p>
        {checkpoint.last_result.criterion_scores.length > 0 && <ul className="mt-2 space-y-2">{checkpoint.last_result.criterion_scores.map((criterion) => <li key={criterion.criterion_id}>
          {criterion.criterion_id}: mức {criterion.score}/4 · “{criterion.evidence_quote}”
        </li>)}</ul>}
        {checkpoint.last_result.requires_instructor_review && <p className="mt-2 text-warning-ink">Đang chờ giảng viên xem lại; chưa nâng trạng thái kiến thức. Bạn vẫn có thể tiếp tục học, Reflect và lập kế hoạch, không cần chờ duyệt.</p>}
      </details>}
      {checkpoint?.status === 'verification_required' && <p className="mt-2 text-xs text-muted">{checkpoint.review?.status === 'verifying'
        ? `Kết quả chưa chắc chắn. Câu kiểm chứng bổ sung ${checkpoint.verification_count}/${checkpoint.verification_limit ?? 2}; không cần chờ giảng viên để tiếp tục học.`
        : 'Thử câu mới không gợi ý để kiểm chứng khả năng tự làm trong PaceWise.'}</p>}
      {checkpoint?.review?.status === 'abstained' && <p role="status" className="mt-2 text-xs text-warning-ink">Chưa có kết luận hợp lệ, không coi là bạn chưa hiểu. Tiếp tục phiên học hoặc Reflect; kế hoạch không bị khóa.</p>}
      {!!checkpoint?.review?.resolved_case_ids?.length && <p role="status" className="mt-2 text-xs text-success-ink">Bằng chứng mới đã giải quyết ca chờ xem lại; không tự duyệt kết luận cũ.</p>}
      {(checkpoint?.status === 'stopped' || checkpoint?.status === 'review_required' || checkpoint?.status === 'coverage_gap') &&
        <Button className="mx-4 mb-3" type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void openProbe(undefined, true)}>Kiểm tra lại bằng câu đã duyệt</Button>}
      {checkpoint?.delayed_probe && <p className="mx-4 mb-3 text-xs text-muted">Kiểm tra nhớ sớm nhất: {new Date(checkpoint.delayed_probe.due_at).toLocaleString('vi-VN')}. Chưa xác nhận khả năng ghi nhớ dài hạn.</p>}
      {due.map((probe) => <Button className="mx-4 mb-3" key={probe.id} type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void openProbe(probe.id)}>Kiểm tra nhớ đến hạn</Button>)}
    </>
  );
  if (embedded) {
    return <div id="do-understanding-checkpoint" aria-labelledby="do-checkpoint-title">{content}</div>;
  }
  return <Card id="do-understanding-checkpoint" className="overflow-hidden !p-0" aria-labelledby="do-checkpoint-title">{content}</Card>;
}
