import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { Logo } from '../../layouts/AppShell';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { getGoogleSignInStatus, startGoogleSignIn, ApiError } from '../../services/api';
import { useAppStore } from '../../store/AppStore';
import { homeFor } from '../../routes/guards';
import { LanguageToggle } from '../../components/domain/LanguageToggle';
import { useLocale } from '../../i18n/LocaleContext';

const oauthErrors: Record<string, string> = {
  denied: 'Bạn đã hủy tiếp tục với Google. Có thể thử lại khi sẵn sàng.',
  existing: 'Email này đã có tài khoản PaceWise dùng mật khẩu. Hãy đăng nhập bằng email và mật khẩu để tránh liên kết nhầm tài khoản.',
  failed: 'Chưa xác minh được tài khoản Google. Vui lòng thử lại.',
};

export function SignUpPage() {
  const { t } = useLocale();
  useDocumentTitle('Tiếp tục với Google');
  const { state } = useAppStore();
  const [params] = useSearchParams();
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [statusError, setStatusError] = useState(false);
  const [statusAttempt, setStatusAttempt] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  useEffect(() => {
    let active = true;
    setConfigured(null); setStatusError(false);
    void getGoogleSignInStatus().then(result => { if (active) setConfigured(result.configured); })
      .catch(() => { if (active) { setConfigured(false); setStatusError(true); } });
    return () => { active = false; };
  }, [statusAttempt]);
  if (!state.authReady) return <div role="status" className="p-8 text-center">Đang kiểm tra phiên đăng nhập…</div>;
  if (state.user) return <Navigate to={homeFor(state.user.role)} replace />;
  const submit = async () => {
    if (pending.current || !configured) return;
    pending.current = true; setBusy(true); setError(null);
    try {
      const result = await startGoogleSignIn();
      const target = new URL(result.authorizationUrl);
      if (target.origin !== 'https://accounts.google.com' || target.pathname !== '/o/oauth2/v2/auth') throw new Error('Invalid OAuth destination');
      window.location.assign(target.href);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : 'Chưa mở được Google. Vui lòng thử lại.');
      pending.current = false; setBusy(false);
    }
  };
  const message = error || oauthErrors[params.get('google_auth') || ''];
  return <main className="flex min-h-screen items-center justify-center bg-primary-light px-4 py-10">
    <section className="w-full max-w-md rounded-3xl border border-line bg-white p-6 shadow-sm sm:p-9">
      <div className="flex items-center justify-between gap-3"><Logo /><LanguageToggle /></div>
      <h1 className="mt-8 text-2xl font-bold">{t('Tiếp tục với Google')}</h1>
      <p className="mt-3 text-sm text-muted">{t('Nếu Gmail đã liên kết với PaceWise, bạn sẽ được đăng nhập. Nếu chưa, PaceWise sẽ tạo tài khoản sinh viên sau khi Google xác minh.')}</p>
      <div className="mt-6 space-y-4">
        {message && <p role="alert" className="rounded-xl bg-danger-light p-3 text-sm text-danger-ink">{message}</p>}
        {configured === null && <p role="status" className="text-sm text-muted">Đang kiểm tra kết nối Google…</p>}
        {statusError && <div role="alert" className="rounded-xl bg-warning-light p-3 text-sm">
          <p>Chưa kiểm tra được kết nối Google. Vui lòng thử lại.</p>
          <Button type="button" variant="secondary" onClick={() => setStatusAttempt(value => value + 1)}>Thử lại kết nối</Button>
        </div>}
        {configured === false && !statusError && <p role="status" className="rounded-xl bg-warning-light p-3 text-sm">Đăng nhập Google tạm chưa sẵn sàng. Bạn vẫn có thể đăng nhập bằng email và mật khẩu.</p>}
        <Button type="button" size="lg" block loading={busy} disabled={!configured} onClick={submit}>{t('Chọn tài khoản Google')}</Button>
      </div>
      <p className="mt-4 text-sm text-muted">{t('Đăng nhập Google chỉ xác minh danh tính. Sau khi vào PaceWise, bạn có thể cấp riêng quyền Google Calendar trong Cài đặt.')}</p>
      <p className="mt-6 text-center text-sm">{t('Dùng email và mật khẩu?')} <Link to="/login" className="font-semibold text-primary hover:underline">{t('Quay lại đăng nhập')}</Link></p>
    </section>
  </main>;
}
