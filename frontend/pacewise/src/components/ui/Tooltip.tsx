import { cloneElement, useEffect, useId, useRef, useState, type ReactElement } from 'react';
import { createPortal } from 'react-dom';

/** Delayed mouse tooltip, immediate keyboard help; portal escapes scrolling rails. */
export function Tooltip({ label, children, enabled = true }: {
  label: string;
  children: ReactElement<{ 'aria-describedby'?: string }>;
  enabled?: boolean;
}) {
  const id = useId();
  const anchor = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const cancelTimer = () => { clearTimeout(timer.current); timer.current = undefined; };
  const hide = () => { cancelTimer(); setPosition(null); };
  const show = () => {
    cancelTimer();
    if (!enabled || !anchor.current) return;
    const rect = anchor.current.getBoundingClientRect();
    setPosition({ left: Math.max(8, Math.min(rect.right + 10, window.innerWidth - 288)),
      top: Math.max(28, Math.min(rect.top + rect.height / 2, window.innerHeight - 28)) });
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    if (!position) return;
    const dismissWithKeyboard = (event: KeyboardEvent) => { if (event.key === 'Escape') hide(); };
    window.addEventListener('scroll', hide, true);
    window.addEventListener('resize', hide);
    window.addEventListener('keydown', dismissWithKeyboard);
    return () => {
      window.removeEventListener('scroll', hide, true);
      window.removeEventListener('resize', hide);
      window.removeEventListener('keydown', dismissWithKeyboard);
    };
  }, [position]);
  if (!enabled) return children;
  return <div ref={anchor} className="min-w-0" onPointerEnter={(event) => {
    if (event.pointerType === 'touch') return;
    cancelTimer(); timer.current = setTimeout(show, 700);
  }} onPointerLeave={hide} onFocus={show} onBlur={hide} onClick={hide}
    onKeyDown={(event) => { if (event.key === 'Escape') hide(); }}>
    {cloneElement(children, { 'aria-describedby': position ? id : children.props['aria-describedby'] })}
    {position && createPortal(<span id={id} role="tooltip" className="pointer-events-none fixed z-[80] max-w-[280px] -translate-y-1/2 rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white shadow-pop"
      style={position}>{label}</span>, document.body)}
  </div>;
}
