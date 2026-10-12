import { useEffect, useState } from 'react';
import { Icon } from '../ui/Icon';
import { applyTheme, type PaceWiseTheme } from '../../utils/uiPreferences';

const currentTheme = (): PaceWiseTheme => document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';

export function ThemeToggle({ sidebar = false }: { sidebar?: boolean }) {
  const [theme, setTheme] = useState<PaceWiseTheme>(currentTheme);
  useEffect(() => {
    // Desktop and mobile controls remain in sync when either one changes theme.
    const observer = new MutationObserver(() => setTheme(currentTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  }, []);
  const next = theme === 'light' ? 'dark' : 'light';
  const toggle = () => {
    applyTheme(next, true);
    setTheme(next);
  };
  return (
    <button
      type="button"
      onClick={toggle}
      className={sidebar
        ? 'relative flex h-11 w-full items-center justify-center rounded-xl text-slate-500 hover:bg-slate-50 hover:text-ink'
        : 'relative flex h-10 w-10 items-center justify-center rounded-xl border border-line bg-white text-muted hover:bg-primary-light hover:text-primary-ink'}
      aria-label={`Chuyển sang giao diện ${next === 'dark' ? 'tối' : 'sáng'}`}
      title={`Chuyển sang giao diện ${next === 'dark' ? 'tối' : 'sáng'}`}
      aria-pressed={theme === 'dark'}
    >
      <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={19} />
    </button>
  );
}
