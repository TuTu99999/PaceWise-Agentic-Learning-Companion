import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { StatTile } from '../../components/domain/StatTile';
import { MarkdownContent } from '../../components/domain/MarkdownContent';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { Select, Textarea } from '../../components/ui/Field';
import { Icon } from '../../components/ui/Icon';
import { PageHeader } from '../../components/ui/PageHeader';
import { Banner } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { confirmReflection, createReflection, type AgentResponse } from '../../services/api';
import { useAppStore } from '../../store/AppStore';
import type { ReflectionActivity } from '../../utils/reflectionActivities';
import { buildReflectionActivities, reflectionActivityWindow, reflectionNeedsPlanReview } from '../../utils/reflectionActivities';
import { replanHref } from '../../utils/replanNavigation';
import { weekStats } from '../../utils/progress';
import { addDays, calendarWeekStart, currentAppDateTime, formatDay, formatDM, formatDuration, formatHours } from '../../utils/time';
import { defaultWeeklyReflectionWeekStart, planForReflectionWeek, weeklyReflectionCycle } from '../../utils/weeklyReflection';

const WEEKLY_QUESTIONS = [
  'Tuần này việc gì đã hoàn thành hoặc chưa hoàn thành?',
  'Nguyên nhân chính khiến kế hoạch đúng hoặc bị lệch?',
  'Tuần sau cần thay đổi thời lượng, khung giờ hay cách chia task nào?',
] as const;
const ACTIVITY_QUESTIONS = [
  'Sau hoạt động này, phần việc nào đã hoàn thành hoặc còn lại?',
  'Phiên có quá dài, mệt hoặc bị gián đoạn không? Nguyên nhân là gì?',
  'Bước tiếp theo phù hợp nhất là gì?',
] as const;
const MAX = 500;
const ACTIVITY_PREVIEW_LIMIT = 3;
const REFLECTION_STATUS_OPTIONS = [
  { value: 'all', label: 'Tất cả trạng thái' },
  { value: 'pending', label: 'Chưa phản tư' },
  { value: 'reflected', label: 'Đã phản tư' },
];

function ActivityButton({ activity, selected, onClick }: { activity: ReflectionActivity; selected: boolean; onClick: () => void }) {
  const result = activity.missed
    ? 'Chưa ghi nhận thực hiện'
    : activity.actualMinutes != null
      ? `${formatDuration(activity.actualMinutes)} thực tế${activity.completionPercent != null ? ` · ${activity.completionPercent}%` : ''}`
      : `${activity.start}${activity.end ? `–${activity.end}` : ''}`;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`w-full rounded-xl border p-3 text-left transition ${selected ? 'border-primary-dark bg-primary-light text-primary-ink' : 'border-line bg-white hover:border-primary'}`}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="text-xs font-bold uppercase tracking-wide">{activity.kindLabel}</span>
        <span className="text-xs text-muted">{activity.courseCode}</span>
      </span>
      <span className="mt-1 block truncate text-sm font-semibold text-ink">{activity.title}</span>
      <span className="mt-1 block text-xs text-muted">{formatDay(activity.date, { short: true })} · {result}</span>
    </button>
  );
}

export function ReflectPage() {
  useDocumentTitle('Phản tư học tập');
  const { state, dispatch } = useAppStore();
  const toast = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedActivity = searchParams.get('activity');
  const now = currentAppDateTime();
  const currentWeekStart = calendarWeekStart(now.date);
  const previousWeekStart = addDays(currentWeekStart, -7);
  const [selectedWeekStart, setSelectedWeekStart] = useState(() => (
    defaultWeeklyReflectionWeekStart(state.plan, now.date, now.time)
  ));
  const [weekPickerOpen, setWeekPickerOpen] = useState(false);
  const [courseFilter, setCourseFilter] = useState('all');
  const [reflectionStatus, setReflectionStatus] = useState('all');
  const [activitiesExpanded, setActivitiesExpanded] = useState(false);
  const reflectionPlan = useMemo(() => planForReflectionWeek(
    state.plan,
    state.planHistory,
    selectedWeekStart,
  ), [selectedWeekStart, state.plan, state.planHistory]);
  const cycle = weeklyReflectionCycle(reflectionPlan, now.date, now.time, selectedWeekStart);
  const activityWindow = reflectionActivityWindow({
    requestedActivity: Boolean(requestedActivity),
    weeklyStart: cycle.weekStart,
    weeklyEnd: cycle.weekEnd,
  });
  const activities = useMemo(() => buildReflectionActivities({
    plan: requestedActivity ? state.plan : reflectionPlan,
    sessions: state.sessions,
    tasks: state.tasks,
    courses: state.courses,
    courseData: state.courseData,
    from: activityWindow.from,
    to: activityWindow.to,
  }), [activityWindow.from, activityWindow.to, reflectionPlan, requestedActivity, state.courseData, state.courses, state.plan, state.sessions, state.tasks]);
  const reflectedActivityIds = useMemo(() => new Set(
    Object.values(state.reflections)
      .filter((item) => (item.scope ?? 'weekly') === 'activity' && item.activityId)
      .map((item) => item.activityId as string),
  ), [state.reflections]);
  const courseFilterOptions = useMemo(() => {
    const courses = new Map<string, string>();
    activities.forEach((item) => courses.set(item.courseId, item.courseCode));
    return [
      { value: 'all', label: 'Tất cả môn' },
      ...Array.from(courses, ([value, label]) => ({ value, label })).sort((left, right) => left.label.localeCompare(right.label)),
    ];
  }, [activities]);
  const filteredActivities = useMemo(() => activities.filter((item) => {
    if (courseFilter !== 'all' && item.courseId !== courseFilter) return false;
    const reflected = reflectedActivityIds.has(item.id) || Boolean(state.reflections[`activity:${item.id}`]);
    if (reflectionStatus === 'pending') return !reflected;
    if (reflectionStatus === 'reflected') return reflected;
    return true;
  }), [activities, courseFilter, reflectedActivityIds, reflectionStatus, state.reflections]);
  const [selectedId, setSelectedId] = useState(() => requestedActivity ? `activity:${requestedActivity}` : 'weekly');
  const activity = selectedId.startsWith('activity:')
    ? activities.find((item) => `activity:${item.id}` === selectedId)
    : undefined;
  const scope = activity ? 'activity' as const : 'weekly' as const;
  const reflectionWeekStart = activity ? calendarWeekStart(activity.date) : cycle.weekStart;
  const reflectionKey = activity ? `activity:${activity.id}` : `all:${reflectionWeekStart}`;
  const currentReflection = state.reflections[reflectionKey]
    ?? (scope === 'weekly'
      ? Object.values(state.reflections).find((item) => (item.scope ?? 'weekly') === 'weekly' && item.courseId === 'all' && item.weekStart === cycle.weekStart)
      : undefined);
  const stats = weekStats(state.tasks, state.sessions, reflectionPlan, cycle.weekStart);
  const questions = scope === 'activity' ? ACTIVITY_QUESTIONS : WEEKLY_QUESTIONS;
  const [answers, setAnswers] = useState<[string, string, string]>(currentReflection?.answers ?? ['', '', '']);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<AgentResponse | null>(null);
  const dirty = JSON.stringify(answers) !== JSON.stringify(currentReflection?.answers ?? ['', '', '']);
  const visibleActivities = useMemo(() => {
    if (activitiesExpanded) return filteredActivities;
    const selected = activity && filteredActivities.find((item) => item.id === activity.id);
    const ordered = selected
      ? [selected, ...filteredActivities.filter((item) => item.id !== selected.id)]
      : filteredActivities;
    return ordered.slice(0, ACTIVITY_PREVIEW_LIMIT);
  }, [activitiesExpanded, activity, filteredActivities]);

  useEffect(() => {
    setCourseFilter('all');
    setReflectionStatus('all');
    setActivitiesExpanded(false);
  }, [selectedWeekStart]);

  useEffect(() => {
    if (!requestedActivity) return;
    const requestedId = `activity:${requestedActivity}`;
    if (activities.some((item) => `activity:${item.id}` === requestedId)) setSelectedId(requestedId);
  }, [activities, requestedActivity]);

  useEffect(() => {
    setAnswers(currentReflection?.answers ?? ['', '', '']);
    setDraft(null);
    setError('');
  }, [reflectionKey, currentReflection?.savedAt]);

  const save = async () => {
    if (answers.every((answer) => !answer.trim())) {
      setError('Trả lời ít nhất một câu để tạo bản phản tư.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const metrics = activity
        ? {
            reflection_scope: 'activity',
            week_start: reflectionWeekStart,
            activity: {
              id: activity.id,
              task_id: activity.taskId,
              block_id: activity.blockId,
              kind: activity.kind,
              title: activity.title,
              course_id: activity.courseId,
              course_code: activity.courseCode,
              date: activity.date,
              planned_minutes: activity.plannedMinutes,
              actual_minutes: activity.actualMinutes,
              completion_percent: activity.completionPercent,
              blocker: activity.blocker,
              outcome: activity.outcome,
              missed: activity.missed,
            },
          }
        : {
            ...stats,
            reflection_scope: 'weekly',
            week_start: cycle.weekStart,
            week_end: cycle.weekEnd,
            effective_week_start: cycle.effectiveWeekStart,
            timezone: 'Asia/Ho_Chi_Minh',
            activity_count: activities.length,
            period_complete: cycle.periodComplete,
          };
      setDraft(await createReflection(answers.map((answer) => answer.trim()) as [string, string, string], metrics));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Chưa tạo được bản phản tư.');
    } finally {
      setLoading(false);
    }
  };

  const confirm = async () => {
    if (!draft) return;
    setLoading(true);
    try {
      const confirmed = await confirmReflection(scope, activity?.courseId);
      dispatch({
        type: 'SAVE_REFLECTION',
        reflectionKey,
        courseId: activity?.courseId ?? 'all',
        weekStart: reflectionWeekStart,
        effectiveWeekStart: scope === 'weekly' ? cycle.effectiveWeekStart : undefined,
        scope,
        activityId: activity?.id,
        activityTitle: activity?.title,
        activityKind: activity?.kind,
        answers: answers.map((answer) => answer.trim()) as [string, string, string],
        aiDraft: draft.reflection_draft ?? undefined,
        aiSummary: draft.response,
      });
      const needsPlanReview = confirmed.output?.replan_decision
        ? confirmed.output.replan_decision.action === 'propose_draft'
        : reflectionNeedsPlanReview(scope, activity);
      setDraft(null);
      toast({
        tone: 'success',
        title: scope === 'activity' ? 'Đã lưu phản tư sau phiên' : 'Đã lưu phản tư cả tuần',
        description: needsPlanReview
          ? `AI đang tạo bản đề xuất${scope === 'weekly' ? ` cho tuần ${formatDM(cycle.effectiveWeekStart)}` : ''}; lịch chưa bị thay đổi.`
          : 'Phiên học đang đúng hướng nên lịch hiện tại được giữ nguyên.',
      });
      navigate(needsPlanReview ? replanHref('reflection', { scope, taskId: activity?.taskId }) : '/plan', { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Chưa xác nhận được bản phản tư.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`page ${requestedActivity ? 'max-w-3xl' : 'max-w-6xl'}`}>
      <PageHeader
        title={requestedActivity ? 'Phản tư sau phiên học' : 'Reflect'}
        description={requestedActivity ? 'Ghi nhận nhanh kết quả vừa học; sau khi lưu bạn sẽ quay về thời khóa biểu.' : 'Chọn một mốc đã xảy ra để nhìn lại nhanh, hoặc chọn tất cả để tổng kết tuần học đa môn.'}
      />

      <div className={requestedActivity ? 'space-y-5' : 'grid items-start gap-5 lg:grid-cols-[320px_minmax(0,1fr)]'}>
        {!requestedActivity && <Card className="lg:sticky lg:top-4 !p-4">
          <div className="flex items-center gap-2">
            <Icon name="sparkle" size={18} className="text-primary-ink" />
            <h2 className="font-bold">Chọn phạm vi phản tư</h2>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2" role="group" aria-label="Chọn tuần phản tư">
            {[
              { label: 'Tuần vừa qua', value: previousWeekStart },
              { label: 'Tuần này', value: currentWeekStart },
            ].map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={selectedWeekStart === option.value}
                onClick={() => {
                  setSelectedWeekStart(option.value);
                  setSelectedId('weekly');
                  setWeekPickerOpen(false);
                }}
                className={`rounded-lg border px-2 py-2 text-xs font-semibold transition ${selectedWeekStart === option.value ? 'border-primary-dark bg-primary-light text-primary-ink' : 'border-line bg-white text-muted hover:border-primary'}`}
              >
                {option.label}<span className="mt-0.5 block font-normal">{formatDM(option.value)}–{formatDM(addDays(option.value, 6))}</span>
              </button>
            ))}
          </div>
          <div className="relative mt-2">
            <button
              type="button"
              aria-expanded={weekPickerOpen}
              aria-controls="reflection-week-picker"
              onClick={() => setWeekPickerOpen((open) => !open)}
              className={`flex w-full items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition ${![previousWeekStart, currentWeekStart].includes(selectedWeekStart) ? 'border-primary-dark bg-primary-light text-primary-ink' : 'border-line bg-white text-muted hover:border-primary'}`}
            >
              <Icon name="calendar" size={16} />
              {![previousWeekStart, currentWeekStart].includes(selectedWeekStart)
                ? `Tuần ${formatDM(selectedWeekStart)}–${formatDM(addDays(selectedWeekStart, 6))}`
                : 'Chọn tuần khác'}
            </button>
            {weekPickerOpen && (
              <div
                id="reflection-week-picker"
                className="absolute left-0 right-0 z-20 mt-2 rounded-xl border border-line bg-white p-3 shadow-lg"
                onKeyDown={(event) => {
                  if (event.key === 'Escape') setWeekPickerOpen(false);
                }}
              >
                <label htmlFor="reflection-week-date" className="block text-xs font-semibold text-ink">
                  Chọn một ngày trong tuần
                </label>
                <input
                  id="reflection-week-date"
                  type="date"
                  max={now.date}
                  value={selectedWeekStart}
                  onChange={(event) => {
                    if (!event.target.value) return;
                    setSelectedWeekStart(calendarWeekStart(event.target.value));
                    setSelectedId('weekly');
                    setWeekPickerOpen(false);
                  }}
                  className="mt-2 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink outline-none focus:border-primary-dark focus:ring-2 focus:ring-primary-light"
                />
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => setSelectedId('weekly')}
            aria-pressed={scope === 'weekly'}
            className={`mt-3 w-full rounded-xl border p-3 text-left transition ${scope === 'weekly' ? 'border-primary-dark bg-primary-light' : 'border-line bg-white hover:border-primary'}`}
          >
            <span className="block text-sm font-bold text-ink">Tất cả hoạt động trong tuần</span>
            <span className="mt-1 block text-xs text-muted">{activities.length} mốc · tất cả môn · {formatDM(cycle.weekStart)}–{formatDM(cycle.weekEnd)}</span>
          </button>
          {activities.length > 0 && (
            <div className="mt-4 grid grid-cols-2 gap-2">
              <Select
                label="Lọc theo môn"
                hideLabel
                aria-label="Lọc hoạt động theo môn"
                value={courseFilter}
                onChange={(event) => {
                  setCourseFilter(event.target.value);
                  setSelectedId('weekly');
                  setActivitiesExpanded(false);
                }}
                options={courseFilterOptions}
              />
              <Select
                label="Lọc theo trạng thái phản tư"
                hideLabel
                aria-label="Lọc hoạt động theo trạng thái phản tư"
                value={reflectionStatus}
                onChange={(event) => {
                  setReflectionStatus(event.target.value);
                  setSelectedId('weekly');
                  setActivitiesExpanded(false);
                }}
                options={REFLECTION_STATUS_OPTIONS}
              />
            </div>
          )}
          <div className={`mt-3 space-y-2 pr-1 ${activitiesExpanded ? 'max-h-[42vh] overflow-y-auto' : ''}`}>
            {visibleActivities.length > 0 && (
              <p className="px-1 text-xs font-medium text-muted">
                {activitiesExpanded ? `${filteredActivities.length} hoạt động trong tuần` : `${Math.min(filteredActivities.length, ACTIVITY_PREVIEW_LIMIT)} hoạt động gần nhất`}
              </p>
            )}
            {visibleActivities.map((item) => (
              <ActivityButton key={item.id} activity={item} selected={activity?.id === item.id} onClick={() => setSelectedId(`activity:${item.id}`)} />
            ))}
            {activities.length === 0 && <p className="rounded-xl bg-canvas p-3 text-sm text-muted">Chưa có phiên Do hoặc hoạt động có kết quả trong phạm vi này.</p>}
            {activities.length > 0 && filteredActivities.length === 0 && <p className="rounded-xl bg-canvas p-3 text-sm text-muted">Không có hoạt động phù hợp với bộ lọc.</p>}
          </div>
          {filteredActivities.length > ACTIVITY_PREVIEW_LIMIT && (
            <button
              type="button"
              className="mt-2 flex w-full items-center justify-center gap-1 rounded-lg px-3 py-2 text-xs font-semibold text-primary-ink hover:bg-primary-light"
              aria-expanded={activitiesExpanded}
              onClick={() => setActivitiesExpanded((expanded) => !expanded)}
            >
              {activitiesExpanded
                ? 'Thu gọn hoạt động'
                : `Xem thêm ${filteredActivities.length - ACTIVITY_PREVIEW_LIMIT} hoạt động`}
              <Icon name="chevronDown" size={15} className={activitiesExpanded ? 'rotate-180' : ''} />
            </button>
          )}
          <p className="mt-3 text-xs text-muted">Ăn, ngủ và lịch bận chỉ là ngữ cảnh lập kế hoạch nên không tạo phản tư riêng.</p>
        </Card>}

        <div className="min-w-0 space-y-5">
          {!activity ? (
            <>
              {cycle.isGracePeriod ? (
                <Banner tone="warning" icon="clock">Bạn đang dùng thời gian hoàn thành bù. Weekly Reflect đóng lúc 09:00 sáng nay.</Banner>
              ) : cycle.isPastPeriod ? (
                <Banner tone="info" icon="clock">Đang tổng kết tuần đã kết thúc {formatDM(cycle.weekStart)}–{formatDM(cycle.weekEnd)}. Số liệu chỉ tính phiên Do và kết quả học tập thuộc tuần này.</Banner>
              ) : cycle.isOpen ? (
                <Banner tone="info" icon="clock">Weekly Reflect đã mở. Kết quả của các phản tư ngắn sẽ được dùng làm bằng chứng tổng hợp.</Banner>
              ) : (
                <Banner tone="warning" icon="clock">Bạn đang phản tư sớm. AI chỉ dùng dữ liệu đến hiện tại; bạn có thể cập nhật bản tổng kết chính thức Chủ Nhật {formatDM(cycle.weekEnd)} lúc {cycle.opensAt}.</Banner>
              )}
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <StatTile icon="checkCircle" label="Nhiệm vụ đã hoàn thành" value={`${stats.done} / ${stats.total}`} />
                <StatTile icon="clock" label="Phiên Do đã ghi nhận" value={stats.sessionCount} />
                <StatTile icon="chart" label="Thời gian Do đã ghi nhận" value={formatHours(stats.studiedMin)} />
                <StatTile icon="calendar" label="Thời lượng đã lên lịch" value={formatHours(stats.plannedMin)} />
              </div>
              {activities.length === 0 && (
                <Banner tone="info" icon="info">
                  Chưa có phiên Do hoặc hoạt động có kết quả để AI tổng kết trong tuần này.
                  {stats.total > 0 || stats.plannedMin > 0
                    ? ` ${stats.total} nhiệm vụ và ${formatHours(stats.plannedMin)} chỉ là phần đã lên kế hoạch, không phải bằng chứng đã học.`
                    : ' Hãy học một phiên Do hoặc chọn tuần khác có dữ liệu.'}
                </Banner>
              )}
            </>
          ) : (
            <Banner tone={activity.missed ? 'warning' : 'info'} icon={activity.missed ? 'alert' : 'checkCircle'}>
              <strong>{activity.kindLabel} · {activity.courseCode}</strong><br />
              {activity.title} · {formatDay(activity.date)}{activity.start ? `, ${activity.start}${activity.end ? `–${activity.end}` : ''}` : ''}
              {activity.actualMinutes != null ? ` · thực tế ${formatDuration(activity.actualMinutes)}` : activity.missed ? ' · chưa có phiên Do' : ''}
            </Banner>
          )}

          <Card aria-labelledby="reflection-questions">
            <CardHeader
              id="reflection-questions"
              title={scope === 'activity' ? 'Phản tư sau hoạt động' : 'Phản tư cả tuần'}
              subtitle={scope === 'activity' ? 'Ghi nhận nhanh trong 20–30 giây.' : 'Tổng hợp mọi môn trong 5–10 phút.'}
            />
            {currentReflection && !dirty && (
              <div className="mb-4"><Banner tone="success" icon="checkCircle">Đã lưu lúc {new Date(currentReflection.savedAt).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}. Bạn vẫn có thể chỉnh sửa.</Banner></div>
            )}
            <div className="space-y-5">
              {questions.map((label, index) => (
                <Textarea
                  key={label}
                  label={`${index + 1}. ${label}`}
                  value={answers[index]}
                  maxLength={MAX}
                  hint={`${answers[index].length}/${MAX} ký tự`}
                  onChange={(event) => {
                    const next = [...answers] as [string, string, string];
                    next[index] = event.target.value;
                    setAnswers(next);
                  }}
                />
              ))}
            </div>
            {error && <p role="alert" className="mt-4 text-sm font-medium text-danger-ink">{error}</p>}
            {draft && (
              <div className="mt-5 rounded-xl border border-[#D6E2FD] bg-primary-light p-4">
                <h3 className="font-semibold">Bản phản tư do AI đề xuất — chưa lưu</h3>
                <div className="mt-2 text-sm"><MarkdownContent>{draft.response}</MarkdownContent></div>
                <div className="mt-4 flex flex-wrap gap-3">
                  <Button icon="check" onClick={confirm} loading={loading}>{scope === 'activity' ? 'Lưu và về lịch học' : 'Lưu và xem lịch đề xuất'}</Button>
                  <Button variant="secondary" onClick={() => setDraft(null)}>Chỉnh lại câu trả lời</Button>
                </div>
              </div>
            )}
            <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
              <Button icon="sparkle" onClick={save} loading={loading} disabled={!!currentReflection && !dirty}>
                {scope === 'activity' ? 'AI phản tư mốc này' : cycle.periodComplete ? 'AI tổng kết tất cả' : 'AI phản tư sớm'}
              </Button>
              {requestedActivity && <Button variant="secondary" onClick={() => navigate('/plan')}>Bỏ qua, về lịch học</Button>}
              {dirty && <span className="caption">Có thay đổi chưa lưu</span>}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
