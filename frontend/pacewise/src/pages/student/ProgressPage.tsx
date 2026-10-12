import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { StatTile } from '../../components/domain/StatTile';
import { LMSLearningSnapshot } from '../../components/domain/LMSLearningSnapshot';
import { TaskCard } from '../../components/domain/TaskCard';
import { WarningCard } from '../../components/domain/WarningCard';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { Input, Select, Textarea } from '../../components/ui/Field';
import { PageHeader } from '../../components/ui/PageHeader';
import { ProgressBar } from '../../components/ui/ProgressBar';
import { Banner } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { useDerived } from '../../hooks/useDerived';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useAppStore } from '../../store/AppStore';
import { trackProgress, type AgentResponse } from '../../services/api';
import { DEMO_TODAY, formatDay, formatDuration, formatHours, weekDates } from '../../utils/time';
import { calculatePilotMetrics } from '../../utils/pilotMetrics';

export function ProgressPage() {
  useDocumentTitle('Tiến độ');
  const { state, dispatch } = useAppStore();
  const {
    scopeCourse,
    scopeLabel,
    scopedDrifts: drifts,
    scopedPlan,
    scopedSessions: visibleSessions,
    scopedStats: stats,
    scopedTasks: visibleTasks,
    taskById,
    courseById,
    unavailable,
  } = useDerived();
  const navigate = useNavigate();
  const toast = useToast();
  const open = visibleTasks.filter((t) => t.status !== 'done');
  const done = visibleTasks.filter((t) => t.status === 'done');
  const openTaskKey = open.map((task) => task.id).join('|');

  const [form, setForm] = useState({ taskId: open[0]?.id ?? '', minutes: '', date: DEMO_TODAY, note: '' });
  const [errors, setErrors] = useState<{ minutes?: string; taskId?: string }>({});
  const [tracking, setTracking] = useState<AgentResponse | null>(null);
  const scopedCourseData = scopeCourse ? state.courseData[scopeCourse.id] : undefined;
  const pilot = useMemo(
    () => calculatePilotMetrics(
      visibleTasks,
      scopedPlan,
      visibleSessions,
      state.recoveryCount,
      state.availability,
      unavailable,
    ),
    [visibleTasks, scopedPlan, visibleSessions, state.recoveryCount, state.availability, unavailable],
  );
  const pilotBaseline = state.courseScope === 'all'
    ? state.pilotMetricsHistory[state.pilotMetricsHistory.length - 1]
    : undefined;
  const onTimeDelta = pilot?.onTimeSubmissionRate != null && pilotBaseline?.onTimeSubmissionRate != null
    ? pilot.onTimeSubmissionRate - pilotBaseline.onTimeSubmissionRate
    : null;
  const unplannedDeadlineCount = pilot
    ? Math.max(0, pilot.openDeadlineCount - pilot.plannedDeadlineCount)
    : 0;
  const estimateMessage = pilot?.estimateMaePercent == null
    ? 'Chưa đủ phiên học để cá nhân hoá thời lượng dự kiến.'
    : `Thời lượng thực tế thường lệch khoảng ${Math.round(pilot.estimateMaePercent * 100)}% so với dự kiến.`;

  useEffect(() => {
    let active = true;
    void trackProgress(scopedPlan, state.availability, unavailable, visibleTasks, visibleSessions)
      .then((result) => active && setTracking(result))
      .catch(() => active && setTracking(null));
    return () => { active = false; };
  }, [scopedPlan, state.settings.lastSync, state.courseScope, state.availability, unavailable, visibleTasks, visibleSessions]);

  useEffect(() => {
    const nextTaskId = open[0]?.id ?? '';
    setForm((current) => ({ ...current, taskId: nextTaskId }));
    setTracking(null);
  }, [state.courseScope, openTaskKey]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const m = Number(form.minutes);
    const next: typeof errors = {};
    if (!form.taskId) next.taskId = 'Chọn nhiệm vụ.';
    if (!form.minutes || !Number.isFinite(m) || m <= 0) next.minutes = 'Nhập số phút lớn hơn 0.';
    else if (m > 600) next.minutes = 'Một lần nhập tối đa 600 phút.';
    setErrors(next);
    if (Object.keys(next).length) return;
    dispatch({ type: 'ADD_MANUAL_SESSION', session: { taskId: form.taskId, minutes: m, date: form.date, note: form.note.trim() || undefined } });
    toast({ tone: 'success', title: 'Đã lưu thời gian học', description: `${formatDuration(m)} cho ${taskById.get(form.taskId)?.title}. Tiến độ đã được cập nhật.` });
    setForm((f) => ({ ...f, minutes: '', note: '' }));
  };

  return (
    <div className="page">
      <PageHeader
        title="Tiến độ"
        description={`Thời gian thực tế so với kế hoạch của ${scopeLabel}.`}
      />

      {tracking && (
        <div className="mb-5">
          <Banner tone={tracking.risk_signals?.length ? 'warning' : 'success'} icon={tracking.risk_signals?.length ? 'info' : 'checkCircle'}>
            {tracking.response}
          </Banner>
        </div>
      )}

      <div className="mb-5">
        {scopedCourseData && <LMSLearningSnapshot data={scopedCourseData} />}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile icon="checkCircle" label="Đã hoàn thành" value={`${stats.done} / ${stats.total}`} hint="nhiệm vụ" />
        <StatTile icon="file" label="Còn lại" value={stats.remaining} hint="nhiệm vụ" />
        <StatTile icon="clock" label="Phiên học" value={stats.sessionCount} hint="trong tuần" />
        <StatTile icon="chart" label="Đã học" value={formatHours(stats.studiedMin)} hint={`dự kiến tới giờ: ${formatHours(stats.plannedUntilNow)}`} />
      </div>

      {pilot && (
        <Card className="mt-5" tone={pilot.atRiskDeadlineCount > 0 ? 'warning' : 'default'} aria-labelledby="actionable-progress">
          <CardHeader
            id="actionable-progress"
            title={pilot.atRiskDeadlineCount > 0 ? `${pilot.atRiskDeadlineCount} deadline đang có rủi ro` : 'Kế hoạch đang trong tầm kiểm soát'}
            subtitle={unplannedDeadlineCount > 0 ? `${unplannedDeadlineCount} deadline chưa được bảo vệ đủ bằng ca tự học.` : estimateMessage}
          />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted">{estimateMessage}</p>
            {pilot.atRiskDeadlineCount > 0 && (
              <Button icon="refresh" onClick={() => navigate('/recover')}>Phục hồi ngay</Button>
            )}
          </div>
        </Card>
      )}

      {drifts[0] && taskById.get(drifts[0].taskId) && (
        <div className="mt-5">
          <WarningCard drift={drifts[0]} task={taskById.get(drifts[0].taskId)!} />
        </div>
      )}

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2 lg:gap-6">
        <Card aria-labelledby="start">
          <CardHeader id="start" title="Phiên tự học theo kế hoạch" subtitle="Do Agent chỉ mở từ ca tự học đã được Plan Agent tạo và xác nhận." />
          <Button icon="calendar" onClick={() => navigate('/plan')}>Mở lịch học PaceWise</Button>
          {state.activeSession && (
            <p className="caption mt-3">
              Đang có phiên chạy cho <strong>{taskById.get(state.activeSession.taskId)?.title}</strong>.
            </p>
          )}
        </Card>

        <Card aria-labelledby="manual-title" id="manual">
          <CardHeader id="manual-title" title="Nhập thủ công" subtitle="Dùng khi bạn học mà quên bật hẹn giờ, hoặc để sửa dữ liệu." />
          <form className="space-y-4" onSubmit={submit} noValidate>
            <Select label="Nhiệm vụ" value={form.taskId} onChange={(e) => setForm({ ...form, taskId: e.target.value })} options={visibleTasks.map((t) => ({ value: t.id, label: `${courseById.get(t.courseId)?.code ?? ''} · ${t.title}` }))} error={errors.taskId} />
            <div className="grid grid-cols-2 gap-3">
              <Input label="Thời lượng (phút)" inputMode="numeric" value={form.minutes} onChange={(e) => setForm({ ...form, minutes: e.target.value.replace(/[^\d]/g, '') })} error={errors.minutes} placeholder="45" />
              <Select label="Ngày" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} options={weekDates().filter((d) => d <= DEMO_TODAY).map((d) => ({ value: d, label: formatDay(d, { relative: true }) }))} />
            </div>
            <Textarea label="Ghi chú" rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} maxLength={300} hint="Không bắt buộc" />
            <Button type="submit" icon="check">
              Lưu thời gian
            </Button>
          </form>
        </Card>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2 lg:gap-6">
        <Card aria-labelledby="tasks">
          <CardHeader id="tasks" title="Nhiệm vụ đang làm" subtitle={`${open.length} nhiệm vụ`} />
          <div className="space-y-2.5">
            {open.map((t) => (
              <TaskCard key={t.id} task={t} course={courseById.get(t.courseId)} atRisk={drifts.some((d) => d.taskId === t.id)} />
            ))}
          </div>
          {done.length > 0 && (
            <details className="mt-4">
              <summary className="min-h-[44px] cursor-pointer py-2 font-semibold text-primary-ink">Đã hoàn thành ({done.length})</summary>
              <div className="mt-2 space-y-2.5">
                {done.map((t) => (
                  <TaskCard key={t.id} task={t} course={courseById.get(t.courseId)} compact />
                ))}
              </div>
            </details>
          )}
        </Card>
        <Card aria-labelledby="sessions">
          <CardHeader id="sessions" title="Lịch sử phiên học" subtitle="Mới nhất trước" />
          {visibleSessions.length ? (
            <ul className="divide-y divide-line">
              {visibleSessions.slice(0, 10).map((s) => (
                <li key={s.id} className="flex items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{taskById.get(s.taskId)?.title}</p>
                    <p className="caption">
                      {formatDay(s.date, { relative: true })} · {s.source === 'timer' ? 'Hẹn giờ' : 'Nhập tay'}
                      {s.note ? ` · ${s.note}` : ''}
                    </p>
                  </div>
                  <span className="font-semibold tabular-nums">{formatDuration(s.minutes)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">Chưa có phiên học nào.</p>
          )}
          <div className="mt-4">
            <p className="mb-2 text-sm text-muted">Thời gian đã học so với kế hoạch cả tuần</p>
            <ProgressBar value={stats.studiedMin} max={Math.max(stats.plannedMin, 1)} label="Đã học so với kế hoạch 7 ngày" />
          </div>
        </Card>
      </div>

      {pilot && (
        <details className="mt-5 rounded-2xl border border-line bg-white px-5 py-3">
          <summary className="min-h-[44px] cursor-pointer py-2 font-semibold text-primary-ink">Dữ liệu đánh giá pilot</summary>
          <p className="mb-4 text-sm text-muted">Dùng cho đánh giá sản phẩm; không phải mục tiêu học tập hằng ngày.</p>
          <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <div><dt className="caption">Deadline có kế hoạch</dt><dd className="font-semibold">{Math.round(pilot.planCoverageRate * 100)}%</dd></div>
            <div><dt className="caption">Deadline có rủi ro</dt><dd className="font-semibold">{pilot.atRiskDeadlineCount}</dd></div>
            <div>
              <dt className="caption">Nộp đúng hạn</dt>
              <dd className="font-semibold">{pilot.onTimeSubmissionRate === null ? 'Chưa đủ mẫu' : `${pilot.onTimeSubmissionCount}/${pilot.submittedAssignmentCount ?? 0} bài · ${Math.round(pilot.onTimeSubmissionRate * 100)}%`}</dd>
              {onTimeDelta !== null && state.pilotMetricsHistory.length > 1 && (
                <span className={onTimeDelta >= 0 ? 'caption text-success-ink' : 'caption text-danger-ink'}>{onTimeDelta >= 0 ? '+' : ''}{Math.round(onTimeDelta * 100)} điểm % so với baseline</span>
              )}
            </div>
            <div><dt className="caption">Sai số estimate</dt><dd className="font-semibold">{pilot.estimateMaePercent === null ? 'Chưa đủ mẫu' : `${Math.round(pilot.estimateMaePercent * 100)}%`}</dd></div>
          </dl>
        </details>
      )}
    </div>
  );
}
