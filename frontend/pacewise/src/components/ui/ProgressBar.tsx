import { cx } from '../../utils/cx';

export function ProgressBar({
  value,
  max,
  label,
  tone = 'primary',
  size = 'md',
  className,
}: {
  value: number;
  max: number;
  label: string;
  tone?: 'primary' | 'success' | 'warning' | 'danger';
  size?: 'sm' | 'md';
  className?: string;
}) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  const color = { primary: 'bg-primary', success: 'bg-success', warning: 'bg-warning', danger: 'bg-danger' }[tone];
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={Math.min(value, max)}
      aria-valuetext={`${pct}%`}
      className={cx('w-full overflow-hidden rounded-full bg-slate-100', size === 'sm' ? 'h-1.5' : 'h-2.5', className)}
    >
      <div className={cx('h-full rounded-full transition-all', color)} style={{ width: `${pct}%` }} />
    </div>
  );
}
