import { useLocale } from '../../i18n/LocaleContext';
import { cx } from '../../utils/cx';

export function LanguageToggle({ compact = false }: { compact?: boolean }) {
  const { locale, setLocale, toggleLocale, t } = useLocale();
  if (compact) return <button
    type="button"
    onClick={toggleLocale}
    className="flex h-8 min-w-8 items-center justify-center rounded-lg border border-line bg-white px-1.5 text-[10px] font-extrabold text-muted hover:bg-canvas hover:text-ink"
    aria-label={locale === 'vi' ? 'Switch to English' : 'Chuyển sang tiếng Việt'}
  >{locale === 'vi' ? 'EN' : 'VI'}</button>;
  return <div className={cx('inline-flex rounded-xl border border-line bg-white p-0.5 text-xs')} role="group" aria-label={t('Ngôn ngữ', 'Language')}>
    {(['vi', 'en'] as const).map((value) => <button
      key={value}
      type="button"
      aria-pressed={locale === value}
      aria-label={value === 'vi' ? t('Tiếng Việt', 'Vietnamese') : t('Tiếng Anh', 'English')}
      onClick={() => setLocale(value)}
      className={cx('rounded-[9px] font-bold transition-colors', compact ? 'h-8 min-w-8 px-1.5' : 'h-9 min-w-10 px-2', locale === value ? 'bg-primary text-white' : 'text-muted hover:bg-canvas hover:text-ink')}
    >{value.toUpperCase()}</button>)}
  </div>;
}
