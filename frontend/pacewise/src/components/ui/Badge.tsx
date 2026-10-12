import React from 'react';
import { cx } from '../../utils/cx';
import type { Tone } from '../../types';
import { Icon, type IconName } from './Icon';

const tones: Record<Tone, string> = {
  primary: 'bg-primary-light text-primary-ink',
  success: 'bg-success-light text-success-ink',
  warning: 'bg-warning-light text-warning-ink',
  danger: 'bg-danger-light text-danger-ink',
  accent: 'bg-accent-light text-accent-ink',
  neutral: 'bg-slate-100 text-slate-600',
};

export function Badge({ tone = 'neutral', icon, children, className }: { tone?: Tone; icon?: IconName; children: React.ReactNode; className?: string }) {
  return (
    <span className={cx('inline-flex min-h-[26px] items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-[13px] font-semibold', tones[tone], className)}>
      {icon && <Icon name={icon} size={14} />}
      {children}
    </span>
  );
}

export function Dot({ tone }: { tone: Tone }) {
  const color = { primary: 'bg-primary', success: 'bg-success', warning: 'bg-warning', danger: 'bg-danger', accent: 'bg-accent', neutral: 'bg-slate-400' }[tone];
  return <span className={cx('inline-block h-2.5 w-2.5 shrink-0 rounded-full', color)} aria-hidden="true" />;
}
