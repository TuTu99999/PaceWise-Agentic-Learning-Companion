import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { LanguageToggle } from '../components/domain/LanguageToggle';
import { LocaleProvider, useLocale } from './LocaleContext';

function Probe() {
  const { t } = useLocale();
  return <p>{t('Đăng nhập')}</p>;
}

describe('shared PaceWise locale', () => {
  beforeEach(() => window.localStorage.clear());

  it('switches to English, updates the document language, and persists the landing-compatible key', () => {
    render(<LocaleProvider><LanguageToggle /><Probe /></LocaleProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Tiếng Anh' }));
    expect(screen.getByText('Sign in')).toBeInTheDocument();
    expect(document.documentElement.lang).toBe('en');
    expect(window.localStorage.getItem('pacewise-language')).toBe('en');
  });

  it('restores English selected on the landing page', () => {
    window.localStorage.setItem('pacewise-language', 'en');
    render(<LocaleProvider><Probe /></LocaleProvider>);
    expect(screen.getByText('Sign in')).toBeInTheDocument();
  });
});
