import type { DiffItem, DiffType, Task } from '../../types';
import { cx } from '../../utils/cx';
import { formatDay, formatRange } from '../../utils/time';
import { Badge } from '../ui/Badge';
import type { IconName } from '../ui/Icon';

export const diffMeta: Record<DiffType, { label: string; tone: 'success' | 'primary' | 'danger' | 'neutral'; icon: IconName; row: string }> = {
  added: { label: 'Thêm mới', tone: 'success', icon: 'plus', row: 'border-[#C7EBD8] bg-success-light/60' },
  moved: { label: 'Đã dời', tone: 'primary', icon: 'move', row: 'border-[#D6E2FD] bg-primary-light/60' },
  removed: { label: 'Đã bỏ', tone: 'danger', icon: 'minus', row: 'border-[#F6CFCF] bg-danger-light/60' },
  unchanged: { label: 'Không đổi', tone: 'neutral', icon: 'check', row: 'border-line bg-white' },
};

const slot = (s?: { date: string; start: string; end: string }) => (s ? `${formatDay(s.date)} · ${formatRange(s.start, s.end)}` : '—');

export function DiffList({ items, taskById }: { items: DiffItem[]; taskById: Map<string, Task> }) {
  return (
    <ul className="space-y-3">
      {items.map((d, i) => {
        const m = diffMeta[d.type];
        return (
          <li key={i} className={cx('rounded-2xl border p-4', m.row)}>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={m.tone} icon={m.icon}>
                {m.label}
              </Badge>
              <p className="font-semibold">{taskById.get(d.taskId)?.title}</p>
            </div>
            {d.type === 'unchanged' ? (
              <p className="caption mt-2">{slot(d.before)}</p>
            ) : (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <div className="rounded-xl bg-white/80 px-3 py-2">
                  <p className="caption">Trước</p>
                  <p className={cx('font-medium', d.type !== 'added' && 'text-muted line-through decoration-slate-400')}>{slot(d.before)}</p>
                </div>
                <div className="rounded-xl bg-white px-3 py-2 ring-1 ring-line">
                  <p className="caption">Sau</p>
                  <p className="font-semibold">{d.type === 'removed' ? 'Không còn trong lịch' : slot(d.after)}</p>
                </div>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
