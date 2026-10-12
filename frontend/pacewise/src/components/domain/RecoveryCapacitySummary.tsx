import type { RecoveryOption, Task } from '../../types';
import { formatDuration } from '../../utils/time';

interface RecoveryCapacitySummaryProps {
  option: RecoveryOption;
  taskById?: Map<string, Task>;
  compact?: boolean;
}

function capacityValue(minutes: number) {
  return `${minutes.toLocaleString('vi-VN')} phút · ${formatDuration(minutes)}`;
}

export function RecoveryCapacitySummary({ option, taskById, compact = false }: RecoveryCapacitySummaryProps) {
  const hasBreakdown = [option.workloadMinutes, option.scheduledMinutes, option.missingMinutes]
    .every((value) => typeof value === 'number');

  if (!hasBreakdown) {
    return (
      <dl className="space-y-3 text-[15px]">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-muted">Tác động</dt>
          <dd className="mt-1">{option.impact}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-muted">Thời lượng điều chỉnh</dt>
          <dd className="mt-1">{option.time}</dd>
        </div>
      </dl>
    );
  }

  const workload = option.workloadMinutes!;
  const scheduled = option.scheduledMinutes!;
  const missing = option.missingMinutes!;
  return (
    <div>
      <dl className={`grid gap-2 ${compact ? 'grid-cols-1' : 'sm:grid-cols-3'}`}>
        <div className="rounded-xl bg-slate-50 px-3 py-2.5">
          <dt className="text-xs font-semibold uppercase tracking-wide text-muted">Khối lượng cần sắp xếp</dt>
          <dd className="mt-1 font-semibold tabular-nums">{capacityValue(workload)}</dd>
        </div>
        <div className="rounded-xl bg-success-light px-3 py-2.5">
          <dt className="text-xs font-semibold uppercase tracking-wide text-success-ink">Đã xếp được</dt>
          <dd className="mt-1 font-semibold tabular-nums text-success-ink">{capacityValue(scheduled)}</dd>
        </div>
        <div className={`rounded-xl px-3 py-2.5 ${missing > 0 ? 'bg-danger-light text-danger-ink' : 'bg-success-light text-success-ink'}`}>
          <dt className="text-xs font-semibold uppercase tracking-wide">Còn thiếu capacity</dt>
          <dd className="mt-1 font-semibold tabular-nums">{capacityValue(missing)}</dd>
        </div>
      </dl>

      {missing > 0 && (option.shortfalls?.length ?? 0) > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-danger-ink">Nhiệm vụ chưa đủ thời lượng</p>
          <ul className="mt-1 space-y-1 text-sm">
            {option.shortfalls!.slice(0, 4).map((shortfall) => (
              <li key={shortfall.taskId} className="flex justify-between gap-3">
                <span className="min-w-0 truncate">{taskById?.get(shortfall.taskId)?.title ?? shortfall.taskId}</span>
                <strong className="shrink-0 tabular-nums">thiếu {formatDuration(shortfall.missingMin)}</strong>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
