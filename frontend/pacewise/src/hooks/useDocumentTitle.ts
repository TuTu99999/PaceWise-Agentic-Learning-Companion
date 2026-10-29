import { useLayoutEffect } from 'react';
import { useLocale } from '../i18n/LocaleContext';

export function useDocumentTitle(title: string, enabled = true) {
  const { t } = useLocale();
  const localized = t(title);
  useLayoutEffect(() => {
    if (!enabled) return;
    document.title = `${localized} · PaceWise`;
  }, [enabled, localized]);
}
