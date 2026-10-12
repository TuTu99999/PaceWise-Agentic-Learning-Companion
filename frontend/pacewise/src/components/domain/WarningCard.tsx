import type { Drift, Task } from '../../types';
import { formatDay, formatHours } from '../../utils/time';
import { ButtonLink } from '../ui/Button';
import { Card } from '../ui/Card';
import { Icon } from '../ui/Icon';

/** Drift warning: always facts → impact → choices. */
export function WarningCard({ drift, task, compact }: { drift: Drift; task: Task; compact?: boolean }) {
  const recoveryUrl = `/recover?taskId=${encodeURIComponent(task.id)}&courseId=${encodeURIComponent(task.courseId)}`;
  const isCapacityGap = drift.kind === 'capacity_gap';
  return (
    <Card tone="warning" aria-labelledby={`drift-${drift.taskId}`}>
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-warning-ink">
          <Icon name="alert" size={20} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 id={`drift-${drift.taskId}`} className="text-lg font-semibold">
            Kế hoạch đang lệch
          </h2>
          <p className="mt-0.5 text-ink/80">
            {isCapacityGap
              ? <>{task.title} đang thiếu <strong>{formatHours(drift.deficitMin)}</strong> ca tự học trước deadline.</>
              : <>{task.title} đang trễ khoảng <strong>{formatHours(drift.deficitMin)}</strong> so với kế hoạch.</>}
          </p>
        </div>
      </div>
      {!compact && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl bg-white/70 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-warning-ink">{isCapacityGap ? 'Năng lực đáp ứng' : 'Dữ liệu'}</p>
            <dl className="mt-2 grid grid-cols-2 gap-2">
              <div>
                <dt className="caption">{isCapacityGap ? 'Còn phải làm' : 'Bạn dự kiến học'}</dt>
                <dd className="text-xl font-bold tabular-nums">{formatHours(isCapacityGap ? task.estimateMin - task.loggedMin : drift.expectedMin)}</dd>
              </div>
              <div>
                <dt className="caption">{isCapacityGap ? 'Chưa được xếp' : 'Bạn đã học'}</dt>
                <dd className="text-xl font-bold tabular-nums">{formatHours(isCapacityGap ? drift.deficitMin : drift.loggedMin)}</dd>
              </div>
            </dl>
          </div>
          <div className="rounded-xl bg-white/70 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-warning-ink">Ảnh hưởng</p>
            <p className="mt-2">Hạn chót {formatDay(drift.deadline)}, 23:59 có thể bị ảnh hưởng nếu giữ nhịp hiện tại.</p>
          </div>
        </div>
      )}
      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <ButtonLink to={recoveryUrl} iconRight="arrowRight">
          Xem phương án phục hồi
        </ButtonLink>
        <ButtonLink to="/progress" variant="ghost">
          Dữ liệu chưa đúng? Nhập lại
        </ButtonLink>
      </div>
      <p className="caption mt-3">Bỏ qua cảnh báo sẽ không thay đổi lịch của bạn.</p>
    </Card>
  );
}
