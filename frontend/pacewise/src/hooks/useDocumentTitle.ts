import { useEffect } from 'react';
import { useLocale } from '../i18n/LocaleContext';

export function useDocumentTitle(title: string) {
  const { t } = useLocale();
  const localized = t(title);
  useEffect(() => {
    document.title = `${localized} · PaceWise`;
  }, [localized]);
}
