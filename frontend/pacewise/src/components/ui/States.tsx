import React from 'react';
import { cx } from '../../utils/cx';
import { Button } from './Button';
import { Card } from './Card';
import { Icon, type IconName } from './Icon';

export function EmptyState({
  icon = 'calendar',
  title,
  description,
  action,
  className,
}: {
  icon?: IconName;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={cx('flex flex-col items-center px-6 py-10 text-center sm:py-14', className)}>
      <span className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-light text-primary-ink">
        <Icon name={icon} size={28} />
      </span>
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mt-2 max-w-md text-muted">{description}</p>
      {action && <div className="mt-6">{action}</div>}
    </Card>
  );
}

export function LoadingState({ title, steps, current, note }: { title: string; steps: string[]; current: number; note?: string }) {
  return (
    <Card className="mx-auto w-full max-w-xl" aria-busy="true">
      <div aria-live="polite">
        <h2 className="text-xl font-semibold">{title}</h2>
        <p className="mt-1 text-muted">
          {steps[Math.min(current, steps.length - 1)]} · Bước {Math.min(current + 1, steps.length)} / {steps.length}
        </p>
      </div>
      <ol className="mt-6 space-y-3">
        {steps.map((s, i) => {
          const state = i < current ? 'done' : i === current ? 'current' : 'todo';
          return (
            <li key={s} className="flex items-center gap-3">
              <span
                className={cx(
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
                  state === 'done' && 'bg-success-light text-success-ink',
                  state === 'current' && 'bg-primary-light text-primary-ink',
                  state === 'todo' && 'border border-line text-muted',
                )}
              >
                {state === 'done' ? (
                  <Icon name="check" size={16} />
                ) : state === 'current' ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden="true" />
                ) : (
                  <span className="text-sm font-semibold">{i + 1}</span>
                )}
              </span>
              <span className={cx('font-medium', state === 'todo' ? 'text-muted' : 'text-ink')}>{s}</span>
            </li>
          );
        })}
      </ol>
      {note && <p className="caption mt-6 rounded-xl bg-canvas px-4 py-3">{note}</p>}
    </Card>
  );
}

export function ErrorState({
  title,
  description,
  requestId,
  onRetry,
  secondary,
}: {
  title: string;
  description: string;
  requestId?: string;
  onRetry?: () => void;
  secondary?: React.ReactNode;
}) {
  return (
    <Card tone="danger" className="mx-auto w-full max-w-xl" role="alert">
      <div className="flex gap-4">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white text-danger-ink">
          <Icon name="cloudOff" size={22} />
        </span>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="mt-1 text-ink/80">{description}</p>
          {requestId && <p className="caption mt-2">Mã yêu cầu: {requestId}</p>}
          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
            {onRetry && (
              <Button icon="refresh" onClick={onRetry}>
                Thử lại
              </Button>
            )}
            {secondary}
          </div>
        </div>
      </div>
    </Card>
  );
}

export function Banner({
  tone = 'info',
  icon,
  children,
  action,
}: {
  tone?: 'info' | 'warning' | 'success' | 'neutral';
  icon?: IconName;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  const styles = {
    info: 'bg-primary-light text-[#23408F] border-[#D6E2FD]',
    warning: 'bg-warning-light text-[#6B4600] border-[#F6DDA8]',
    success: 'bg-success-light text-[#1F5A3E] border-[#C7EBD8]',
    neutral: 'bg-slate-50 text-slate-700 border-line',
  }[tone];
  return (
    <div className={cx('flex flex-col gap-3 rounded-2xl border px-4 py-3 sm:flex-row sm:items-center', styles)} role={tone === 'warning' ? 'status' : undefined}>
      <div className="flex min-w-0 flex-1 items-start gap-3">
        {icon && <Icon name={icon} size={20} className="mt-0.5 shrink-0" />}
        <div className="min-w-0 text-[15px]">{children}</div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
