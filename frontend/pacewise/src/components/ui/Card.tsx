import React from 'react';
import { cx } from '../../utils/cx';

type CardProps = React.HTMLAttributes<HTMLElement> & { as?: 'section' | 'div' | 'article' | 'aside'; padded?: boolean; tone?: 'default' | 'primary' | 'warning' | 'danger' | 'success' | 'accent' };

const tones = {
  default: 'bg-white border-line',
  primary: 'bg-white border-[#D6E2FD]',
  warning: 'bg-warning-light border-[#F6DDA8]',
  danger: 'bg-danger-light border-[#F6CFCF]',
  success: 'bg-success-light border-[#C7EBD8]',
  accent: 'bg-accent-light border-[#DDD6FD]',
};

export function Card({ as = 'section', padded = true, tone = 'default', className, ...rest }: CardProps) {
  const Tag = as;
  return <Tag className={cx('rounded-2xl border shadow-card', tones[tone], padded && 'p-5 sm:p-6', className)} {...rest} />;
}

export function CardHeader({ title, action, subtitle, id }: { title: React.ReactNode; subtitle?: React.ReactNode; action?: React.ReactNode; id?: string }) {
  return (
    <div className="mb-4 flex items-start gap-3">
      <div className="min-w-0 flex-1">
        <h2 id={id} className="card-title">
          {title}
        </h2>
        {subtitle && <p className="caption mt-0.5">{subtitle}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
