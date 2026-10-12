import React from 'react';
import { Link } from 'react-router-dom';
import { cx } from '../../utils/cx';
import { Icon, type IconName } from './Icon';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'soft';
type Size = 'sm' | 'md' | 'lg';

const base =
  'inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-colors whitespace-nowrap select-none disabled:cursor-not-allowed disabled:opacity-100';
const variants: Record<Variant, string> = {
  primary: 'bg-primary-dark text-[#FFFFFF] hover:bg-primary-deeper disabled:bg-slate-200 disabled:text-slate-500',
  secondary: 'bg-white text-ink border border-line hover:bg-slate-50 hover:border-slate-300 disabled:text-slate-400 disabled:bg-slate-50',
  ghost: 'bg-transparent text-primary-ink hover:bg-primary-light disabled:text-slate-400',
  soft: 'bg-primary-light text-primary-ink hover:bg-[#E2ECFF] disabled:text-slate-400',
  danger: 'bg-white text-danger-ink border border-[#F3C9C9] hover:bg-danger-light',
};
const sizes: Record<Size, string> = {
  sm: 'min-h-[40px] px-3 text-sm',
  md: 'min-h-[44px] px-4 text-[15px]',
  lg: 'min-h-[48px] px-5 text-[15px]',
};

interface Common {
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  iconRight?: IconName;
  loading?: boolean;
  block?: boolean;
}

export type ButtonProps = Common & React.ButtonHTMLAttributes<HTMLButtonElement>;

export function Button({ variant = 'primary', size = 'md', icon, iconRight, loading, block, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      className={cx(base, variants[variant], sizes[size], block && 'w-full', className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden="true" /> : icon && <Icon name={icon} size={18} />}
      {children}
      {iconRight && <Icon name={iconRight} size={18} />}
    </button>
  );
}

export function ButtonLink({
  to,
  variant = 'primary',
  size = 'md',
  icon,
  iconRight,
  block,
  className,
  children,
  ...rest
}: Common & { to: string } & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>) {
  return (
    <Link to={to} className={cx(base, variants[variant], sizes[size], block && 'w-full', className)} {...rest}>
      {icon && <Icon name={icon} size={18} />}
      {children}
      {iconRight && <Icon name={iconRight} size={18} />}
    </Link>
  );
}

export function IconButton({ icon, label, className, ...rest }: { icon: IconName; label: string } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      aria-label={label}
      title={label}
      className={cx('inline-flex h-11 w-11 items-center justify-center rounded-xl text-muted hover:bg-slate-100 hover:text-ink', className)}
      {...rest}
    >
      <Icon name={icon} size={20} />
    </button>
  );
}
