import React, { createContext, useCallback, useContext, useState } from 'react';
import type { Toast } from '../../types';
import { cx } from '../../utils/cx';
import { uid } from '../../utils/time';
import { Icon } from './Icon';

type Push = (t: Omit<Toast, 'id'>) => void;
const ToastContext = createContext<Push>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback<Push>((t) => {
    const id = uid('toast');
    setToasts((list) => [...list, { ...t, id }]);
    window.setTimeout(() => setToasts((list) => list.filter((x) => x.id !== id)), 5000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-24 z-[60] flex flex-col items-center gap-2 px-4 lg:bottom-6 lg:items-end lg:px-6" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className="pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-2xl bg-ink px-4 py-3 text-white shadow-pop"
          >
            <Icon
              name={t.tone === 'success' ? 'checkCircle' : t.tone === 'danger' ? 'alert' : 'info'}
              size={20}
              className={cx('mt-0.5 shrink-0', t.tone === 'success' ? 'text-[#8CE0B6]' : t.tone === 'warning' ? 'text-[#F8D48A]' : t.tone === 'danger' ? 'text-[#F5A9A9]' : 'text-[#AFC6FA]')}
            />
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{t.title}</p>
              {t.description && <p className="text-sm text-slate-300">{t.description}</p>}
            </div>
            <button className="-mr-1 rounded-lg p-1 text-slate-300 hover:text-white" aria-label="Đóng thông báo" onClick={() => setToasts((l) => l.filter((x) => x.id !== t.id))}>
              <Icon name="x" size={18} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
