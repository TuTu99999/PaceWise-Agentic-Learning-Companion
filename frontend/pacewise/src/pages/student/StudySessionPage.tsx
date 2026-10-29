import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { DoSessionAssistant } from '../../components/domain/DoSessionAssistant';
import { StudyWorkList } from '../../components/domain/StudyWorkList';
import { DoSessionSupport } from '../../components/domain/DoSessionSupport';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Field';
import { Icon } from '../../components/ui/Icon';
import { Modal } from '../../components/ui/Modal';
import { ProgressBar } from '../../components/ui/ProgressBar';
import { Banner, EmptyState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { useDerived } from '../../hooks/useDerived';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useDurableStudyTimer } from '../../hooks/useDurableStudyTimer';
import { materialRevision, useDoPreparation } from '../../hooks/useDoPreparation';
import { useAppStore } from '../../store/AppStore';
import type { AssessmentItem, DoBlocker, DoSessionEvaluation, DoWorkResult, InterruptionReason } from '../../types';
import type { AdaptiveCheckpoint } from '../../types/adaptiveAssessment';
import { remainingOf } from '../../utils/progress';
import { replanHref } from '../../utils/replanNavigation';
import { studyBlockAccess } from '../../utils/studyBlockAccess';
import { confirmedBlockIssue } from '../../utils/calendarEditing';
import { routineSleepSlots } from '../../utils/routine';
import {
  clearDoAssistantMode,
  readDoAssistantMode,
  type DoAssistantMode,
  writeDoAssistantMode,
} from '../../utils/doSessionUiState';
import { lmsUnavailableSlots, mergeUnavailable } from '../../utils/lmsPlanning';
import { durationMin, formatDay, formatDuration, formatTimer } from '../../utils/time';

const OUTCOME_LABEL: Record<DoSessionEvaluation['status'], string> = {
  on_track: 'Đúng tiến độ',
  completed: 'Hoàn thành milestone',
  needs_more_time: 'Cần thêm thời gian',
  blocked: 'Đang bị kẹt kiến thức',
  missed: 'Bỏ lỡ phiên học',
};

const ASSESSMENT_LABEL: Record<string, string> = {
  recall: 'Nhớ lại', conceptual: 'Hiểu khái niệm', reasoning: 'Lập luận',
  application: 'Vận dụng', transfer: 'Chuyển giao', retention: 'Ghi nhớ sau đó',
};

const normalizedScopeName = (value: string) => value
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .toLowerCase()
  .replace(/\s+/g, ' ')
  .trim();

const sameChapter = (left: string, right: string) => {
  const leftValue = normalizedScopeName(left);
  const rightValue = normalizedScopeName(right);
  if (leftValue === rightValue) return true;
  const number = (value: string) => value.match(/(?:chuong|chapter)\s*(\d+)/)?.[1];
  return Boolean(number(leftValue) && number(leftValue) === number(rightValue));
};

export function assessmentMatchScore(
  context: string,
  assessmentOrTopic: Pick<AssessmentItem, 'topic' | 'question' | 'moduleId' | 'sourceChapter'> | string,
  scopeOrQuestion?: { module_ids?: string[]; module_names?: string[] } | string,
) {
  const assessment = typeof assessmentOrTopic === 'string'
    ? { topic: assessmentOrTopic, question: typeof scopeOrQuestion === 'string' ? scopeOrQuestion : '' }
    : assessmentOrTopic;
  const scope = typeof scopeOrQuestion === 'object' ? scopeOrQuestion : undefined;
  const terms = (value: string) => new Set(
    normalizedScopeName(value)
      .split(/[^a-z0-9]+/)
      .filter((token) => token.length >= 4),
  );
  const contextTerms = terms(context);
  const lexicalScore = [...terms(`${assessment.topic} ${assessment.question}`)]
    .filter((token) => contextTerms.has(token)).length;
  const moduleIds = scope?.module_ids ?? [];
  const moduleNames = scope?.module_names ?? [];
  const hasMappedScope = moduleIds.length > 0 || moduleNames.length > 0;
  const moduleMatches = Boolean(assessment.moduleId && moduleIds.includes(assessment.moduleId));
  const chapterMatches = Boolean(
    assessment.sourceChapter && moduleNames.some((name) => sameChapter(assessment.sourceChapter ?? '', name)),
  );
  if (hasMappedScope && (assessment.moduleId || assessment.sourceChapter)) {
    return moduleMatches || chapterMatches ? 1000 + lexicalScore : 0;
  }
  return lexicalScore;
}

export function StudySessionPage() {
  const { taskId = '' } = useParams<{ taskId: string }>();
  const [searchParams] = useSearchParams();
  const blockId = searchParams.get('blockId');
  const navigate = useNavigate();
  const { state, dispatch } = useAppStore();
  const { taskById, courseOf } = useDerived();
  const toast = useToast();
  const task = taskById.get(taskId);
  const session = state.activeSession;
  const [done, setDone] = useState<{ minutes: number; evaluation?: DoSessionEvaluation } | null>(null);
  const [showSmartTriage, setShowSmartTriage] = useState(false);
  const [showSessionReview, setShowSessionReview] = useState(false);
  const [workResult, setWorkResult] = useState<DoWorkResult>('planned_part_done');
  const [additionalMinutes, setAdditionalMinutes] = useState('');
  const [blocker, setBlocker] = useState<DoBlocker>('none');
  const [blockerNote, setBlockerNote] = useState('');
  const [finishing, setFinishing] = useState(false);
  const [offlineMinutes, setOfflineMinutes] = useState('30');
  const [clock, setClock] = useState(Date.now());
  const [interruptionReason, setInterruptionReason] = useState<InterruptionReason>('none');
  const [assistantMode, setAssistantMode] = useState<DoAssistantMode>('learn');
  const taskBlocks = [...(state.plan?.blocks ?? [])]
    .filter((block) => block.taskId === taskId && block.status !== 'history')
    .sort((left, right) => left.date.localeCompare(right.date) || left.start.localeCompare(right.start));
  const plannedBlock = blockId
    ? taskBlocks.find((block) => block.id === blockId)
    : taskBlocks.find((block) => studyBlockAccess(block, clock).state === 'available')
      ?? taskBlocks[taskBlocks.length - 1];
  const access = plannedBlock ? studyBlockAccess(plannedBlock, clock) : undefined;
  const startIssue = plannedBlock ? confirmedBlockIssue(plannedBlock, state.plan?.blocks ?? [], state.tasks,
    mergeUnavailable([...state.unavailable, ...routineSleepSlots(state.routineProfile)], lmsUnavailableSlots(state.courseData))) : undefined;
  const course = task ? courseOf(task.id) : undefined;
  const revision = JSON.stringify([materialRevision(course ? state.courseData[course.id] : undefined),
    task?.objective, task?.dueAt, plannedBlock?.milestoneTitle, plannedBlock?.date, plannedBlock?.start, plannedBlock?.end]);
  const { preparation, loading: preparing, error: prepareError, retry: retryPreparation } = useDoPreparation(
    state.user?.id, course?.id, plannedBlock?.id, revision,
    state.workspaceReady && access?.state === 'available' && !startIssue);
  // Query the requested block even after a re-plan removed it. The server will
  // close any stale active timer so it cannot keep blocking the next Do session.
  const timer = useDurableStudyTimer(course?.id, plannedBlock?.id ?? blockId ?? undefined, state.workspaceReady);
  const mine = timer.session && ['running', 'paused'].includes(timer.session.status) ? timer.session : null;
  const elapsed = timer.elapsed;
  // Router can reuse this component between blocks; never carry a previous
  // block's completion or Reflect answers into the next session.
  useEffect(() => {
    setDone(null); setShowSmartTriage(false); setShowSessionReview(false);
    setWorkResult('planned_part_done'); setAdditionalMinutes(''); setBlocker('none'); setBlockerNote('');
    setInterruptionReason('none');
    setAssistantMode(readDoAssistantMode(state.user?.id, plannedBlock?.id));
  }, [taskId, plannedBlock?.id, state.user?.id]);
  useEffect(() => {
    if (timer.session?.status === 'completed' && timer.session.evaluation) {
      clearDoAssistantMode(state.user?.id, plannedBlock?.id);
      setDone({ minutes: timer.session.evaluation.actual_minutes, evaluation: timer.session.evaluation });
    }
    if (timer.session) setInterruptionReason(timer.session.interruption_reason);
  }, [plannedBlock?.id, state.user?.id, timer.session]);
  const checkpointContext = `${task?.title ?? ''} ${task?.objective ?? ''} ${plannedBlock?.milestoneTitle ?? ''} ${preparation?.scope?.module_names.join(' ') ?? ''}`;
  const checkpointAssessment = state.assessments
    .filter((item) => (
      item.status === 'approved'
      && Boolean(item.assessmentSetId && item.sourceChapter && item.sourceResourceId)
      && (!item.courseId || item.courseId === task?.courseId)
    ))
    .map((item) => ({ item, score: assessmentMatchScore(checkpointContext, item, preparation?.scope) }))
    .filter(({ score }) => score > 0)
    .sort((left, right) => right.score - left.score)[0]?.item;
  const changeAssistantMode = useCallback((mode: DoAssistantMode) => {
    setAssistantMode(mode);
    writeDoAssistantMode(state.user?.id, plannedBlock?.id, mode);
  }, [plannedBlock?.id, state.user?.id]);
  const recordAssessmentSignal = useCallback((checkpoint: AdaptiveCheckpoint) => {
    if (checkpoint.last_result) dispatch({ type: 'MARK_PLAN_NEEDS_ANALYSIS' });
  }, [dispatch]);
  useEffect(() => {
    if (!blockId) return;
    const timer = window.setInterval(() => setClock(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, [blockId]);
  useDocumentTitle(mine ? `${formatTimer(elapsed)} · ${task?.title}` : 'Phiên học');

  if (!task && (!state.workspaceReady || ['idle', 'loading'].includes(state.courseSourceStatus))) {
    return (
      <div className="page flex min-h-[calc(100dvh-4rem)] max-w-2xl items-center justify-center">
        <Card className="w-full text-center" role="status" aria-live="polite">
          <span className="mx-auto block h-7 w-7 animate-spin rounded-full border-2 border-primary border-r-transparent" aria-hidden="true" />
          <h1 className="mt-4 text-xl font-bold">Đang khôi phục phiên Do</h1>
          <p className="mt-2 text-sm text-muted">Đang tải nhiệm vụ, lịch học và checkpoint gần nhất…</p>
        </Card>
      </div>
    );
  }

  if (!task && state.courseSourceStatus === 'error') {
    return (
      <div className="page flex min-h-[calc(100dvh-4rem)] max-w-2xl items-center justify-center">
        <EmptyState icon="alert" title="Chưa tải được dữ liệu phiên Do" description="Kết nối chưa ổn định. Phiên học vẫn được giữ và không cộng thời gian chưa quan sát." action={<ButtonLink to="/plan">Về lịch học PaceWise</ButtonLink>} />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="page">
        <EmptyState icon="file" title="Không tìm thấy nhiệm vụ" description="Hãy chọn lại nhiệm vụ từ Dashboard." action={<ButtonLink to="/dashboard">Về trang Tổng quan</ButtonLink>} />
      </div>
    );
  }

  if (blockId && !plannedBlock) {
    return (
      <div className="page flex min-h-[calc(100dvh-4rem)] max-w-2xl items-center justify-center">
        <EmptyState icon="calendar" title="Ca tự học không còn hiệu lực" description="Ca cũ đã được tự hủy vì hết thời gian hoặc đã được Plan Agent thay thế. Bạn có thể mở ca Do mới từ lịch học." action={<ButtonLink to="/plan">Về lịch học PaceWise</ButtonLink>} />
      </div>
    );
  }

  if (!plannedBlock) {
    return (
      <div className="page flex min-h-[calc(100dvh-4rem)] max-w-2xl items-center justify-center">
        <EmptyState icon="calendar" title="Hãy mở phiên từ lịch học" description="Do Agent chỉ được kích hoạt từ ca tự học đã được Plan Agent tạo và sinh viên xác nhận." action={<ButtonLink to="/plan">Về lịch học PaceWise</ButtonLink>} />
      </div>
    );
  }

  const other = session && (session.taskId !== taskId || (session.blockId && session.blockId !== plannedBlock.id))
    ? taskById.get(session.taskId) : null;
  if (startIssue && !mine) return <div className="page"><EmptyState icon="calendar" title="Ca tự học cần kiểm tra lại" description={startIssue} action={<ButtonLink to="/plan">Về lịch học PaceWise</ButtonLink>} /></div>;

  const finishSession = async (
    minutes: number,
    nextResult: DoWorkResult = workResult,
    nextAdditionalMinutes = Number(additionalMinutes) || 0,
    nextBlocker = blocker,
    nextNote = blockerNote,
    offline = false,
  ) => {
    if (!course) return;
    setFinishing(true);
    try {
      const completed = await timer.act('complete', {
        workResult: nextResult,
        additionalMinutes: nextResult === 'planned_part_done' ? 0 : Math.min(1440, Math.max(0, nextAdditionalMinutes)),
        blocker: nextBlocker,
        note: nextNote.trim(), interruptionReason,
        outsideMinutes: offline ? minutes : 0,
      });
      const evaluation = completed.evaluation!;
      setShowSessionReview(false);
      setShowSmartTriage(false);
      setDone({ minutes: evaluation.actual_minutes, evaluation });
      if (evaluation.needs_recovery) {
        toast({ tone: 'warning', title: 'Kế hoạch có thể cần phục hồi', description: evaluation.next_action });
      } else {
        toast({ tone: 'success', title: 'Do Agent đã ghi nhận phiên học', description: evaluation.next_action });
      }
      clearDoAssistantMode(state.user?.id, plannedBlock.id);
      navigate(`/reflect?activity=${encodeURIComponent(`study:${plannedBlock.id}`)}`, { replace: true });
    } catch (error) {
      toast({ tone: 'danger', title: 'Chưa thể kết thúc phiên', description: error instanceof Error ? error.message : 'Hãy thử lại.' });
    } finally {
      setFinishing(false);
    }
  };

  if (access?.state === 'waiting_prerequisite' && !mine && !done) {
    return (
      <div className="page flex min-h-[calc(100dvh-4rem)] max-w-2xl items-center justify-center">
        <Card className="w-full text-center">
          <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-warning-light text-warning-ink"><Icon name="calendar" size={28} /></span>
          <h1 className="mt-4 text-2xl font-bold">Chưa tới phần kiến thức cần thiết</h1>
          <p className="mx-auto mt-2 max-w-md text-muted">
            Phiên Do đã được lập trước cho tương lai và sẽ mở sau khi buổi học liên quan kết thúc. PaceWise chưa giả định rằng bạn đã học hoặc đã hiểu nội dung này.
          </p>
          <p className="mt-4 text-sm font-semibold">Có thể bắt đầu từ {new Date(access.availableAt).toLocaleString('vi-VN')}</p>
          <ButtonLink to="/plan" className="mt-6">Về lịch học PaceWise</ButtonLink>
        </Card>
      </div>
    );
  }

  if (access?.state === 'ended' && !mine && !done) {
    return (
      <div className="page flex min-h-[calc(100dvh-4rem)] max-w-2xl items-center justify-center">
        <Card className="w-full text-center">
          <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-light text-primary-ink"><Icon name="calendar" size={28} /></span>
          <h1 className="mt-4 text-2xl font-bold">Buổi tự học đã kết thúc</h1>
          <p className="mx-auto mt-2 max-w-md text-muted">
            Ca tự học vẫn được giữ trên lịch sử; Plan Agent sẽ xử lý phần chưa hoàn thành trong lần phân tích tiếp theo.
          </p>
          {plannedBlock && <p className="mt-4 text-sm font-semibold">{formatDay(plannedBlock.date)} · {plannedBlock.start}–{plannedBlock.end}</p>}
          <ButtonLink to="/plan" className="mt-6">Về lịch học PaceWise</ButtonLink>
        </Card>
      </div>
    );
  }

  if (done) {
    return (
      <div className="page flex min-h-[calc(100dvh-4rem)] max-w-2xl items-center justify-center">
        <Card className="w-full text-center" role="status">
          <h1 className="text-2xl font-bold">Tự học</h1>
          <p className="mt-1 text-sm text-muted">{task.title}{course ? ` · ${course.code}` : ''}</p>
          <div className="mx-auto mt-7 flex h-56 w-56 flex-col items-center justify-center rounded-full border-[9px] border-success bg-white shadow-sm sm:h-64 sm:w-64">
            <Icon name="checkCircle" size={28} className="text-success-ink" />
            <p className="mt-3 text-5xl font-bold tabular-nums tracking-tight">{formatTimer(done.minutes * 60_000)}</p>
            <p className="mt-2 text-xs font-bold uppercase tracking-[0.16em] text-success-ink">Đã kết thúc phiên</p>
          </div>

          <div className="mx-auto mt-6 flex max-w-sm justify-center gap-8 text-sm">
            <p><span className="font-bold text-success-ink">Đã ghi nhận:</span> {formatDuration(done.minutes)}</p>
            <p><span className="font-bold text-primary-ink">Nhiệm vụ còn lại:</span> {formatDuration(remainingOf(taskById.get(task.id)!))}</p>
          </div>

          <div className="mx-auto mt-6 max-w-md rounded-xl border border-line bg-canvas p-4">
            <p className="mb-2 text-sm">
              {done.evaluation?.work_result === 'needs_more_time'
                ? `Phiên đã kết thúc; bạn cần thêm khoảng ${done.evaluation.remaining_minutes} phút.`
                : done.evaluation?.work_result === 'blocked'
                  ? `Phiên đã kết thúc khi đang bị vướng; dự kiến cần thêm ${done.evaluation.remaining_minutes} phút.`
                  : 'Phần việc dự kiến của phiên đã hoàn thành.'}
            </p>
            <p className="mb-3 text-sm text-muted">{Object.keys(timer.session?.evaluation?.assessment_summary ?? {}).length
              ? `Bài kiểm tra: ${Object.entries(timer.session?.evaluation?.assessment_summary ?? {}).map(([dimension, result]) => `${ASSESSMENT_LABEL[dimension] ?? dimension}: ${result === 'passed' ? 'đạt' : 'chưa đạt'}`).join(' · ')}`
              : 'Chưa có bằng chứng từ bài kiểm tra độc lập trong phiên này.'}</p>
            <p className={`font-semibold ${done.evaluation?.needs_recovery ? 'text-warning-ink' : 'text-success-ink'}`}>
              {done.evaluation ? OUTCOME_LABEL[done.evaluation.status] : 'Đã kết thúc phiên học'}
            </p>
            <p className="mt-1 text-sm text-muted">{done.evaluation?.next_action ?? 'Thời gian thực tế đã được lưu vào Tiến độ.'}</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              <ButtonLink to="/plan">Về lịch học PaceWise</ButtonLink>
              <ButtonLink to={`/reflect?activity=${encodeURIComponent(`study:${plannedBlock.id}`)}`} variant="secondary">Phản tư phiên này</ButtonLink>
              {done.evaluation?.needs_recovery && <ButtonLink to={replanHref('progress', { taskId: task.id, courseId: task.courseId })} variant="secondary">Xem cập nhật lịch</ButtonLink>}
            </div>
          </div>
        </Card>
      </div>
    );
  }

  const running = mine?.status === 'running';
  const target = plannedBlock
    ? Math.max(1, durationMin(plannedBlock.start, plannedBlock.end)) * 60_000
    : Math.min(90, Math.max(25, remainingOf(task))) * 60_000;
  const progress = Math.min(100, Math.round((elapsed / target) * 100));

  return (
    <div className="page max-w-6xl">
      {other && (
        <div className="mb-5">
          <Banner tone="warning" icon="alert" action={<ButtonLink to={`/study/${encodeURIComponent(other.id)}/session${session?.blockId ? `?blockId=${encodeURIComponent(session.blockId)}` : ''}`} size="sm" variant="secondary">Mở phiên đang chạy</ButtonLink>}>
            Bạn đang có một phiên học cho <strong>{other.title}</strong>. Kết thúc phiên đó trước khi bắt đầu phiên mới.
          </Banner>
        </div>
      )}
      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,0.65fr)]">
        <div className="min-w-0 space-y-5">
      <Card className="text-center">
        <h1 className="text-xl font-bold">{task.title.split(' — ')[0]}</h1>
        <p className="mt-2 text-sm text-muted">{course?.name}
          {preparation?.scope?.module_names.filter(name => !course?.name.includes(name)).length
            ? ` · ${preparation.scope.module_names.filter(name => !course?.name.includes(name)).join(' · ')}` : ''}</p>

        <div
          className="mx-auto mt-7 h-56 w-56 rounded-full p-[9px] shadow-sm sm:h-64 sm:w-64"
          style={{ background: `conic-gradient(rgb(var(--pw-primary-ink)) ${progress}%, rgb(var(--pw-line)) ${progress}% 100%)` }}
        >
          <div className="flex h-full w-full flex-col items-center justify-center rounded-full bg-white">
            <Icon name={running ? 'sparkle' : 'clock'} size={26} className="text-primary-ink" />
            <p
              className="mt-3 text-5xl font-bold tabular-nums tracking-tight text-ink"
              role="timer"
              aria-live="off"
              aria-label={`Timer ghi nhận ${Math.floor(elapsed / 60000)} phút`}
            >
              {formatTimer(elapsed)}
            </p>
            <p className="mt-2 text-xs font-bold uppercase tracking-[0.16em] text-primary-ink">{mine ? (running ? 'Đang tự học' : 'Đã tạm dừng') : 'Sẵn sàng'}</p>
          </div>
        </div>

        <div className="sr-only"><ProgressBar value={elapsed} max={target} label="Thời gian phiên so với mục tiêu" /></div>
        <div className="mx-auto mt-5 flex max-w-md justify-center gap-8 text-sm text-muted">
          <p>Ca này: <strong className="text-ink">{formatDuration(target / 60_000)}</strong></p>
          {plannedBlock && <p>Khung giờ: <strong className="text-ink">{plannedBlock.start}–{plannedBlock.end}</strong></p>}
        </div>

        <div className="mx-auto mt-6 max-w-md rounded-xl bg-canvas px-4 py-3 text-left">
          <p className="text-sm font-semibold text-muted">Việc cần làm</p>
          <StudyWorkList
            className="mt-2"
            title={preparation?.objective ?? plannedBlock.milestoneTitle ?? 'Ca tự học cho nhiệm vụ này'}
          />
        </div>

        <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
          {!mine ? (
            <Button size="lg" icon="play" disabled={!!other || timer.busy || !!timer.error} onClick={() => void timer.start()}>
              Bắt đầu học
            </Button>
          ) : (
            <>
              {running ? (
                <Button size="lg" variant="secondary" icon="pause" disabled={timer.busy || !!timer.error} onClick={() => void timer.act('pause', { interruptionReason }).catch(() => {})}>
                  Tạm dừng
                </Button>
              ) : (
                <Button size="lg" variant="secondary" icon="play" disabled={timer.busy || !!timer.error} onClick={() => void timer.act('resume', { interruptionReason }).catch(() => {})}>
                  Tiếp tục
                </Button>
              )}
              <Button
                size="lg"
                icon="check"
                disabled={timer.busy || !!timer.error}
                onClick={() => {
                  const openReview = async () => {
                    if (running) await timer.act('pause', { interruptionReason });
                  // If session is less than 2 minutes, open Smart Triage to diagnose true intent!
                  if (elapsed < 120000) {
                    setOfflineMinutes(String(Math.max(1, durationMin(plannedBlock.start, plannedBlock.end))));
                    setShowSmartTriage(true);
                    return;
                  }
                  setShowSessionReview(true);
                  };
                  void openReview().catch(() => {});
                }}
              >
                Kết thúc phiên
              </Button>
            </>
          )}
        </div>
        {timer.error && <div role="alert" className="mt-3 text-sm text-danger-ink">{timer.error}<Button size="sm" variant="secondary" onClick={() => void timer.retry().catch(() => {})}>Thử lưu lại checkpoint</Button></div>}
        {mine && (
          <button
            className="mt-4 min-h-[44px] text-sm font-semibold text-muted underline-offset-4 hover:text-ink hover:underline"
            onClick={() => {
              void timer.act('cancel').then(() => {
                clearDoAssistantMode(state.user?.id, plannedBlock?.id);
                navigate('/plan');
              }).catch(() => {});
            }}
          >
            Hủy phiên (không ghi thời gian)
          </button>
        )}
      </Card>
        </div>
        <aside className="min-w-0 space-y-5" data-testid="do-session-sidebar">
          <DoSessionSupport
            key={JSON.stringify([state.user?.id, course?.id, plannedBlock.id])}
            preparation={preparation}
            loading={preparing}
            error={prepareError || undefined}
            onRetry={retryPreparation}
          />
          {mine && (
            <DoSessionAssistant
              key={`${course?.id ?? task.courseId}:${plannedBlock.id}`}
              courseId={course?.id ?? task.courseId}
              blockId={plannedBlock.id}
              taskTitle={task.title}
              objective={preparation?.objective || plannedBlock.milestoneTitle || 'Ca tự học cho nhiệm vụ này'}
              assessment={checkpointAssessment}
              onAssessmentStatusChange={recordAssessmentSignal}
              mode={assistantMode}
              onModeChange={changeAssistantMode}
            />
          )}
        </aside>
      </div>
      <div className="mt-5 text-center">
        <ButtonLink to="/plan" variant="secondary">Về lịch học PaceWise</ButtonLink>
      </div>

      <Modal
        open={showSessionReview}
        onClose={() => !finishing && setShowSessionReview(false)}
        title="Kết thúc phiên học"
        description="Chọn kết quả thực tế của phần việc trong phiên này."
        footer={(
          <>
            <Button variant="secondary" disabled={finishing || timer.busy} onClick={() => void timer.act('resume', { interruptionReason }).then(() => setShowSessionReview(false)).catch(() => {})}>Tiếp tục học</Button>
            <Button
              icon="check"
              loading={finishing}
              disabled={(workResult !== 'planned_part_done' && (Number(additionalMinutes) < 1 || Number(additionalMinutes) > 1440)) || (workResult === 'blocked' && blocker === 'none')}
              onClick={() => void finishSession(Math.max(1, Math.round(elapsed / 60_000)))}
            >
              Kết thúc và phản tư
            </Button>
          </>
        )}
      >
        <div className="space-y-5">
          <fieldset>
            <legend className="text-sm font-semibold">Kết quả phiên này thế nào?</legend>
            <div className="mt-2 grid gap-2">
              {[
                { value: 'planned_part_done', label: 'Đã hoàn thành phần dự kiến', detail: 'Không còn phần việc nào của ca này cần xếp lại.' },
                { value: 'needs_more_time', label: 'Chưa xong, cần học tiếp', detail: 'Ghi số phút cần thêm để Recover kiểm tra lịch.' },
                { value: 'blocked', label: 'Đang bị vướng', detail: 'Ghi trở ngại và thời gian cần thêm; đây chưa phải bằng chứng mức hiểu.' },
              ].map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    const value = option.value as DoWorkResult;
                    setWorkResult(value);
                    if (value !== 'blocked') setBlocker('none');
                  }}
                  className={`rounded-xl border p-3 text-left ${workResult === option.value ? 'border-primary-dark bg-primary-light text-primary-ink' : 'border-line bg-white text-muted hover:bg-slate-50'}`}
                  aria-pressed={workResult === option.value}
                >
                  <span className="block text-sm font-bold text-ink">{option.label}</span>
                  <span className="mt-1 block text-xs font-normal">{option.detail}</span>
                </button>
              ))}
            </div>
          </fieldset>

          {workResult !== 'planned_part_done' && (
            <Input
              label="Cần thêm khoảng bao nhiêu phút?"
              type="number"
              min="1"
              max="1440"
              inputMode="numeric"
              value={additionalMinutes}
              onChange={(event) => setAdditionalMinutes(event.target.value.replace(/[^\d]/g, '').slice(0, 4))}
              hint="Nhập số phút thực tế để PaceWise tạo bản nháp Recover; lịch chưa tự thay đổi."
            />
          )}

          {workResult === 'blocked' && (
            <>
              <label className="block text-sm font-semibold">
                Trở ngại chính
                <select value={blocker} onChange={(event) => setBlocker(event.target.value as DoBlocker)} className="mt-2 block h-11 w-full rounded-xl border border-line bg-white px-3 text-sm font-normal">
                  <option value="none">Chọn trở ngại</option>
                  <option value="knowledge">Chưa hiểu kiến thức</option>
                  <option value="time">Thiếu thời gian</option>
                  <option value="interruption">Bị gián đoạn</option>
                  <option value="other">Thiếu học liệu, công cụ hoặc lý do khác</option>
                </select>
              </label>
              <Input
                label="Phần đang vướng — không bắt buộc"
                value={blockerNote}
                maxLength={200}
                onChange={(event) => setBlockerNote(event.target.value)}
              />
            </>
          )}

        </div>
      </Modal>

      {/* Smart Triage Dialog for < 2 minute completions */}
      <Modal
        open={showSmartTriage}
        onClose={() => setShowSmartTriage(false)}
        title="Xác nhận hoàn tất phiên học"
        description={`Đồng hồ mới chạy ${formatTimer(elapsed)}. Chọn cách ghi nhận đúng với phiên này.`}
        size="lg"
      >
        <div className="space-y-4">
          <div className="rounded-xl border border-line bg-white p-4">
            <h4 className="font-semibold text-ink">Tiếp tục học</h4>
            <p className="caption mt-1">Quay lại phiên hiện tại và tiếp tục tính giờ.</p>
            <Button
              className="mt-3"
              size="sm"
              variant="secondary"
              onClick={() => void timer.act('resume', { interruptionReason }).then(() => setShowSmartTriage(false)).catch(() => {})}
            >
              Tiếp tục phiên
            </Button>
          </div>

          <div className="rounded-xl border border-line bg-canvas/40 p-4 transition hover:border-primary">
            <div className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-light text-xs font-bold text-primary-ink">
                1
              </span>
              <h4 className="font-semibold text-ink">Mình đã tự học xong từ trước (offline)</h4>
            </div>
            <p className="caption mt-1">
              Ghi nhận đúng thời lượng bạn đã học bên ngoài để số liệu tuần và đánh giá Reflect cuối tuần chính xác.
            </p>
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <div className="w-36">
                <Input
                  label="Số phút thực tế"
                  type="number"
                  value={offlineMinutes}
                  onChange={(e) => setOfflineMinutes(e.target.value.replace(/[^\d]/g, ''))}
                  placeholder="60"
                />
              </div>
              <Button
                size="sm"
                icon="check"
                loading={finishing}
                onClick={() => {
                  const m = Math.min(1440, Math.max(1, Number(offlineMinutes) || task?.estimateMin || 45));
                  void finishSession(m, 'planned_part_done', 0, 'none', 'Tự học offline', true);
                }}
              >
                Lưu {offlineMinutes || task?.estimateMin} phút
              </Button>
            </div>
          </div>

          <div className="rounded-xl border border-line bg-slate-50 p-4">
            <div className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-200 text-xs font-bold text-slate-700">
                2
              </span>
              <h4 className="font-semibold text-ink">Bấm nhầm hoặc chưa bắt đầu học</h4>
            </div>
            <p className="caption mt-1">Hủy phiên này, không ghi nhận thời gian ảo vào lịch sử học tập.</p>
            <div className="mt-3">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  void timer.act('cancel').then(() => navigate('/plan')).catch(() => {});
                }}
              >
                Hủy phiên (không ghi giờ)
              </Button>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
