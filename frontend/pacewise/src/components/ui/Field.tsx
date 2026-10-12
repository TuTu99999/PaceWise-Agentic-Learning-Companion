import React, { useId } from 'react';
import { cx } from '../../utils/cx';
import { Icon } from './Icon';

const control =
  'w-full min-h-[44px] rounded-xl border bg-white px-3.5 py-2.5 text-[15px] text-ink placeholder:text-slate-400 transition-colors focus:outline-none focus-visible:outline-none focus:border-primary-dark focus:ring-4 focus:ring-primary/15 disabled:bg-slate-50 disabled:text-slate-400';

interface FieldShellProps {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  hideLabel?: boolean;
  className?: string;
  children: (ids: { id: string; describedBy?: string; invalid: boolean }) => React.ReactNode;
}

export function Field({ label, hint, error, required, hideLabel, className, children }: FieldShellProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [errId, hintId].filter(Boolean).join(' ') || undefined;
  return (
    <div className={cx('flex min-w-0 flex-col gap-1.5', className)}>
      <label htmlFor={id} className={cx('text-sm font-semibold text-ink', hideLabel && 'sr-only')}>
        {label}
        {required && <span className="ml-0.5 text-danger-ink" aria-hidden="true">*</span>}
      </label>
      {children({ id, describedBy, invalid: !!error })}
      {error && (
        <p id={errId} className="flex items-start gap-1.5 text-sm font-medium text-danger-ink">
          <Icon name="info" size={16} className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}
      {hint && !error && (
        <p id={hintId} className="caption">
          {hint}
        </p>
      )}
    </div>
  );
}

type InputProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, 'id'> & Omit<FieldShellProps, 'children'>;
export function Input({ label, hint, error, required, hideLabel, className, ...rest }: InputProps) {
  return (
    <Field label={label} hint={hint} error={error} required={required} hideLabel={hideLabel} className={className}>
      {({ id, describedBy, invalid }) => (
        <input
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          required={required}
          className={cx(control, invalid ? 'border-danger-ink bg-[#FFFBFB]' : 'border-line')}
          {...rest}
        />
      )}
    </Field>
  );
}

type TextareaProps = Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'id'> & Omit<FieldShellProps, 'children'>;
export function Textarea({ label, hint, error, required, hideLabel, className, rows = 3, ...rest }: TextareaProps) {
  return (
    <Field label={label} hint={hint} error={error} required={required} hideLabel={hideLabel} className={className}>
      {({ id, describedBy, invalid }) => (
        <textarea
          id={id}
          rows={rows}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          className={cx(control, 'resize-y leading-relaxed', invalid ? 'border-danger-ink' : 'border-line')}
          {...rest}
        />
      )}
    </Field>
  );
}

type SelectProps = Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'id'> &
  Omit<FieldShellProps, 'children'> & { options: { value: string; label: string }[] };
export function Select({ label, hint, error, required, hideLabel, className, options, ...rest }: SelectProps) {
  return (
    <Field label={label} hint={hint} error={error} required={required} hideLabel={hideLabel} className={className}>
      {({ id, describedBy, invalid }) => (
        <div className="relative">
          <select
            id={id}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            className={cx(control, 'appearance-none pr-10', invalid ? 'border-danger-ink' : 'border-line')}
            {...rest}
          >
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <Icon name="chevronDown" size={18} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted" />
        </div>
      )}
    </Field>
  );
}

type TimeSelectProps = Omit<SelectProps, 'options'> & {
  stepMinutes?: number;
  includeEndOfDay?: boolean;
};

/** Locale-independent 24-hour control; avoids browser-specific SA/CH rendering. */
export function TimeSelect({
  stepMinutes = 30,
  includeEndOfDay = false,
  value,
  ...rest
}: TimeSelectProps) {
  const lastMinute = includeEndOfDay ? 24 * 60 : 24 * 60 - stepMinutes;
  const values = Array.from(
    { length: Math.floor(lastMinute / stepMinutes) + 1 },
    (_, index) => index * stepMinutes,
  ).map((minutes) => {
    if (minutes === 24 * 60) return '24:00';
    return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
  });
  const current = typeof value === 'string' ? value : undefined;
  if (current && !values.includes(current)) values.push(current);
  values.sort((left, right) => {
    const toMinutes = (clock: string) => {
      const [hours, minutes] = clock.split(':').map(Number);
      return hours * 60 + minutes;
    };
    return toMinutes(left) - toMinutes(right);
  });

  return (
    <Select
      {...rest}
      value={value}
      options={values.map((clock) => ({ value: clock, label: clock }))}
    />
  );
}

export function Checkbox({ label, description, className, ...rest }: { label: React.ReactNode; description?: React.ReactNode } & React.InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className={cx('flex items-start gap-3', className)}>
      <input id={id} type="checkbox" className="mt-0.5 h-5 w-5 shrink-0 cursor-pointer rounded border-line accent-[#3F6FE8]" {...rest} />
      <label htmlFor={id} className="min-w-0 cursor-pointer">
        <span className="block font-medium text-ink">{label}</span>
        {description && <span className="caption block">{description}</span>}
      </label>
    </div>
  );
}

export function Switch({ checked, onChange, label, description }: { checked: boolean; onChange: (v: boolean) => void; label: string; description?: string }) {
  const id = useId();
  return (
    <div className="flex items-center gap-4">
      <div className="min-w-0 flex-1">
        <label htmlFor={id} className="font-medium text-ink">
          {label}
        </label>
        {description && <p className="caption">{description}</p>}
      </div>
      <button
        id={id}
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cx('relative h-7 w-12 shrink-0 rounded-full transition-colors', checked ? 'bg-primary-dark' : 'bg-slate-300')}
      >
        <span className={cx('absolute top-1 h-5 w-5 rounded-full bg-white shadow transition-all', checked ? 'left-6' : 'left-1')} />
      </button>
    </div>
  );
}
