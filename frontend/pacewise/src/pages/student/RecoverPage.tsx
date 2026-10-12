import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Badge } from '../../components/ui/Badge';
import { Button, ButtonLink } from '../../components/ui/Button';
import { RecoveryCapacitySummary } from '../../components/domain/RecoveryCapacitySummary';
import { Icon } from '../../components/ui/Icon';
import { PageHeader } from '../../components/ui/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/ui/States';
import { useDerived } from '../../hooks/useDerived';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useAppStore } from '../../store/AppStore';
import { generateRecoveryOptions, switchCourse } from '../../services/api';
import { cx } from '../../utils/cx';
import { formatDay, formatHours } from '../../utils/time';
import { lmsUnavailableSlots, mergeUnavailable } from '../../utils/lmsPlanning';
import type { Drift } from '../../types';

export function useRecoveryOptions() {
  const { state, dispatch } = useAppStore();
  const { drifts, taskById } = useDerived();
  const [searchParams] = useSearchParams();
  const requestedTaskId = searchParams.get('taskId');
  const requestedCourseId = searchParams.get('courseId');
  const impactId = searchParams.get('impactId');
  const impact = impactId ? state.planImpacts.find((item) => item.id === impactId) : undefined;
  const impactTask = impact?.taskId ? taskById.get(impact.taskId) : undefined;
  const syntheticDrift: Drift | undefined = impactTask && impact && impact.deficitMin > 0
    ? {
        taskId: impactTask.id,
        courseId: impactTask.courseId,
        kind: 'capacity_gap',
        expectedMin: 0,
        loggedMin: impactTask.loggedMin,
        deficitMin: impact.deficitMin,
        deadline: impact.deadline ?? impactTask.deadline,
      }
    : undefined;
  const drift = syntheticDrift ?? drifts.find((item) => (
    (!requestedTaskId || item.taskId === requestedTaskId)
    && (!requestedCourseId || item.courseId === requestedCourseId)
  )) ?? drifts[0];
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  // Version the cache when the recovery contract changes so persisted legacy
  // options are regenerated with the current structured capacity evidence.
  const recoveryKey = drift && state.plan ? `capacity-v2:${impactId ?? 'drift'}:${drift.taskId}:${drift.deficitMin}:${state.plan.id}` : null;
  useEffect(() => {
    if (!drift || !state.plan || !recoveryKey || state.recoveryOptionsKey === recoveryKey) return;
    let active = true;
    setLoading(true);
    setError(null);
    const task = taskById.get(drift.taskId);
    const load = async () => {
      if (task && state.user?.courseId !== task.courseId) {
        await switchCourse(task.courseId);
      }
      return generateRecoveryOptions(
        state.plan!,
        state.tasks,
        drift,
        state.availability,
        mergeUnavailable(state.unavailable, lmsUnavailableSlots(state.courseData)),
        impact,
      );
    };
    void load()
      .then((options) => {
        if (!active) return;
        if (task && state.user?.courseId !== task.courseId) {
          dispatch({ type: 'SET_ACTIVE_COURSE', courseId: task.courseId });
        }
        dispatch({ type: 'SET_RECOVERY_OPTIONS', options, key: recoveryKey });
      })
      .catch((reason: Error) => active && setError(reason))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [drift?.taskId, drift?.deficitMin, impact?.id, state.plan?.id, state.recoveryOptionsKey, recoveryKey, retryKey]);
  const options = state.recoveryOptionsKey === recoveryKey ? state.recoveryOptions : [];
  return {
    drift,
    impact,
    impactId,
    options,
    loading,
    error,
    retry: () => {
      dispatch({ type: 'SET_RECOVERY_OPTIONS', options: [], key: null });
      setRetryKey((value) => value + 1);
    },
  };
}

export function RecoverPage() {
  useDocumentTitle('Phục hồi kế hoạch');
  const { state } = useAppStore();
  const { taskById, courseById } = useDerived();
  const { drift, impactId, options, loading, error, retry } = useRecoveryOptions();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string | null>(null);

  if (!state.plan) {
    const hasDraft = !!state.planDraft;
    return (
      <div className="page">
        <PageHeader title="Phục hồi kế hoạch" />
        <EmptyState
          icon="calendar"
          title={hasDraft ? 'Kế hoạch đang ở bản xem trước' : 'Chưa có kế hoạch 7 ngày'}
          description={hasDraft
            ? 'Lịch đã được tạo nhưng chưa được áp dụng. Hãy mở bản xem trước và bấm “Xác nhận và lưu”; sau đó PaceWise mới có thể theo dõi và phục hồi kế hoạch.'
            : 'Bạn cần tạo và xác nhận kế hoạch học tập trước để PaceWise có thể theo dõi và hỗ trợ phục hồi khi lịch bị lệch.'}
          action={
            <ButtonLink to={hasDraft ? '/plan/preview' : '/plan/new'} icon={hasDraft ? 'check' : 'plus'} size="lg">
              {hasDraft ? 'Mở bản xem trước' : 'Tạo kế hoạch ngay'}
            </ButtonLink>
          }
        />
      </div>
    );
  }

  if (!drift) {
    return (
      <div className="page">
        <PageHeader title="Phục hồi kế hoạch" />
        <EmptyState
          icon="checkCircle"
          title="Kế hoạch đang đúng hướng"
          description="Hiện không có nhiệm vụ nào bị lệch so với kế hoạch. PaceWise sẽ báo khi cần điều chỉnh."
          action={<ButtonLink to="/dashboard">Về trang Tổng quan</ButtonLink>}
        />
      </div>
    );
  }
  if (loading) {
    return <div className="page"><LoadingState title="Đang tạo phương án phục hồi" steps={['Đọc tiến độ', 'Bảo vệ deadline', 'Kiểm tra đánh đổi']} current={1} /></div>;
  }
  if (error) {
    return <div className="page"><ErrorState title="Chưa tạo được phương án" description={error.message} onRetry={retry} /></div>;
  }
  const task = taskById.get(drift.taskId)!;
  const course = courseById.get(drift.courseId);
  const selectedOption = options.find((option) => option.id === selected);

  return (
    <div className="page">
      <PageHeader
        title="Phục hồi kế hoạch"
        description={
          <>
            <strong>{course?.code ? `${course.code} · ` : ''}{task.title}</strong> đang thiếu <strong className="text-ink">{formatHours(drift.deficitMin)}</strong>{' '}
            {drift.kind === 'missed_progress'
              ? <>(dự kiến đã học {formatHours(drift.expectedMin)}, thực tế {formatHours(drift.loggedMin)}).</>
              : <>trong lịch còn lại trước deadline.</>}{' '}
            Deadline {formatDay(drift.deadline)}, 23:59.
          </>
        }
      />
      <div className="mb-5 flex items-start gap-3 rounded-2xl border border-[#D6E2FD] bg-primary-light px-4 py-3 text-[#23408F]" role="status">
        <Icon name="info" size={20} className="mt-0.5 shrink-0" />
        <p>Chưa có thay đổi nào được áp dụng. Chọn một phương án để xem chi tiết thay đổi trước khi quyết định.</p>
      </div>

      <fieldset>
        <legend className="sr-only">Chọn phương án phục hồi</legend>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {options.map((o) => {
            const active = selected === o.id;
            return (
              <label
                key={o.id}
                className={cx(
                  'relative flex cursor-pointer flex-col rounded-2xl border-2 bg-white p-5 shadow-card transition-colors',
                  active ? 'border-primary-dark ring-4 ring-primary/10' : 'border-line hover:border-[#C9D8FB]',
                )}
              >
                <input type="radio" name="option" value={o.id} checked={active} onChange={() => setSelected(o.id)} className="sr-only" />
                <div className="flex items-center gap-2">
                  <span className={cx('flex h-6 w-6 items-center justify-center rounded-full border-2', active ? 'border-primary-dark bg-primary-dark text-white' : 'border-slate-300')} aria-hidden="true">
                    {active && <Icon name="check" size={14} />}
                  </span>
                  <span className="text-sm font-semibold text-muted">Phương án {o.id}</span>
                  {o.id !== 'C' && o.fullyRecovers && (
                    <Badge tone="success" className="ml-auto">
                      Bù đủ
                    </Badge>
                  )}
                  {o.id !== 'C' && !o.fullyRecovers && (
                    <Badge tone="warning" className="ml-auto">
                      Bù một phần
                    </Badge>
                  )}
                </div>
                <h2 className="mt-3 text-lg font-semibold">{o.title}</h2>
                <p className="mt-1 text-muted">{o.summary}</p>
                <div className="mt-4 space-y-3 text-[15px]">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted">Thay đổi</p>
                    <div>
                      <ul className="mt-1 space-y-1">
                        {o.changes.map((c) => (
                          <li key={c} className="flex gap-2">
                            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" aria-hidden="true" />
                            {c}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                  <RecoveryCapacitySummary option={o} taskById={taskById} compact />
                  <div className="rounded-xl bg-warning-light px-3 py-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-warning-ink">Đánh đổi</p>
                    <p className="mt-1">{o.tradeoff}</p>
                  </div>
                </div>
              </label>
            );
          })}
        </div>
      </fieldset>
      {options.length < 3 && <p className="caption mt-3">Chỉ có {options.length} phương án thỏa ràng buộc về thời gian rảnh và deadline.</p>}

      {selectedOption && !selectedOption.fullyRecovers && (
        <section className="mt-5 rounded-2xl border border-danger/30 bg-danger-light px-5 py-4" role="alert" aria-labelledby="capacity-warning">
          <h2 id="capacity-warning" className="text-lg font-semibold text-danger-ink">Kế hoạch chưa khả thi hoàn toàn</h2>
          <p className="mt-1 text-danger-ink">
            Không có phương án tự động nào được phép tự bỏ nhiệm vụ hoặc nhồi thêm thời gian ngoài lịch rảnh của bạn.
            Phần chưa xếp cần bạn điều chỉnh hoặc chấp nhận đánh đổi.
          </p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ink">
            <li>Tăng quỹ thời gian rảnh nếu thực tế bạn còn khung giờ có thể học.</li>
            <li>Sửa estimate nếu thời lượng ban đầu không còn chính xác.</li>
            <li>Ưu tiên deadline gần/trọng số cao; các nhiệm vụ khác vẫn được giữ dưới dạng rủi ro, không tự động bị bỏ.</li>
            <li>Nếu cần đổi deadline hoặc phạm vi học vụ, hãy trao đổi với giảng viên.</li>
          </ul>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button variant="secondary" icon="edit" onClick={() => navigate('/plan/new')}>
              Điều chỉnh quỹ thời gian và estimate
            </Button>
            <Button iconRight="arrowRight" onClick={() => navigate(`/recover/${selectedOption.id}${impactId ? `?${searchParamsForImpact(impactId, drift)}` : ''}`)}>
              Xem lịch phần đã xếp được
            </Button>
          </div>
        </section>
      )}

      <div className="sticky bottom-[76px] z-20 mt-6 flex flex-col-reverse gap-3 rounded-2xl border border-line bg-white/95 p-4 shadow-card backdrop-blur sm:flex-row sm:items-center lg:bottom-4">
        <ButtonLink to="/dashboard" variant="secondary">
          Để sau
        </ButtonLink>
        <p className="caption flex-1 sm:text-right">{selected ? `Đã chọn phương án ${selected}. Lịch chưa thay đổi.` : 'Bạn chưa chọn phương án nào.'}</p>
        <Button iconRight="arrowRight" disabled={!selected} onClick={() => navigate(`/recover/${selected}${impactId ? `?${searchParamsForImpact(impactId, drift)}` : ''}`)}>
          {selectedOption && !selectedOption.fullyRecovers ? 'Xem lịch phần đã xếp' : 'Xem thay đổi'}
        </Button>
      </div>
    </div>
  );
}

function searchParamsForImpact(impactId: string, drift: Drift) {
  return new URLSearchParams({ impactId, taskId: drift.taskId, courseId: drift.courseId }).toString();
}
