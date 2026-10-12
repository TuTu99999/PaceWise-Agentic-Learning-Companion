export type PaceWiseTheme = 'light' | 'dark';

export const PACEWISE_THEME_STORAGE_KEY = 'pacewise-theme';
export const PACEWISE_LANGUAGE_STORAGE_KEY = 'pacewise-language';

export function storedTheme(): PaceWiseTheme | null {
  try {
    const value = window.localStorage.getItem(PACEWISE_THEME_STORAGE_KEY);
    return value === 'dark' || value === 'light' ? value : null;
  } catch {
    return null;
  }
}

export function preferredTheme(): PaceWiseTheme {
  return storedTheme()
    ?? (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}

export function applyTheme(theme: PaceWiseTheme, persist = false) {
  document.documentElement.dataset.theme = theme;
  if (!persist) return;
  try { window.localStorage.setItem(PACEWISE_THEME_STORAGE_KEY, theme); }
  catch { /* The active page still keeps the selected theme. */ }
}

export function themeFromStorageEvent(event: StorageEvent) {
  if (event.key !== PACEWISE_THEME_STORAGE_KEY) return;
  if (event.newValue === 'dark' || event.newValue === 'light') applyTheme(event.newValue);
}
