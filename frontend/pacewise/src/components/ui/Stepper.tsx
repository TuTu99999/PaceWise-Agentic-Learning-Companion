import { cx } from '../../utils/cx';
import { Icon } from './Icon';

export function Stepper({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className="flex items-center gap-2" aria-label="Các bước">
      {steps.map((s, i) => {
        const state = i < current ? 'done' : i === current ? 'current' : 'todo';
        return (
          <li key={s} className="flex min-w-0 flex-1 items-center gap-2" aria-current={state === 'current' ? 'step' : undefined}>
            <span
              className={cx(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold',
                state === 'done' && 'bg-success-light text-success-ink',
                state === 'current' && 'bg-primary-dark text-white',
                state === 'todo' && 'border border-line bg-white text-muted',
              )}
            >
              {state === 'done' ? <Icon name="check" size={16} /> : i + 1}
              <span className="sr-only">{state === 'done' ? ' (xong)' : state === 'current' ? ' (bước hiện tại)' : ''}</span>
            </span>
            <span className={cx('truncate text-sm font-semibold', state === 'todo' ? 'text-muted' : 'text-ink', state !== 'current' && 'hidden sm:inline')}>{s}</span>
            {i < steps.length - 1 && <span className="mx-1 h-px min-w-[12px] flex-1 bg-line" aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
}
