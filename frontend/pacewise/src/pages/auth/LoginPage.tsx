import { useEffect, useState, type FormEvent } from 'react';
import { Navigate } from 'react-router-dom';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Input } from '../../components/ui/Field';
import { Icon } from '../../components/ui/Icon';
import { Logo } from '../../layouts/AppShell';
import { homeFor } from '../../routes/guards';
import { ApiError, login } from '../../services/api';
import { useAppStore } from '../../store/AppStore';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { preloadInstructorOverview } from '../../routes/instructorRouteLoaders';
import { LanguageToggle } from '../../components/domain/LanguageToggle';
import { useLocale } from '../../i18n/LocaleContext';

export function LoginPage() {
  const { t } = useLocale();
  useDocumentTitle('Đăng nhập');
  const { state, dispatch } = useAppStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ email?: string; password?: string; form?: string }>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void preloadInstructorOverview();
  }, []);

  if (!state.authReady) return <div className="flex min-h-screen items-center justify-center text-muted">Đang kiểm tra phiên đăng nhập…</div>;
  if (state.user) return <Navigate to={homeFor(state.user.role)} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const next: typeof errors = {};
    if (!email.trim()) next.email = t('Nhập email để đăng nhập.');
    else if (!/^\S+@\S+\.\S+$/.test(email)) next.email = t('Email chưa đúng định dạng.');
    if (!password) next.password = t('Nhập mật khẩu.');
    setErrors(next);
    if (Object.keys(next).length) return;
    setLoading(true);
    try {
      const user = await login(email, password);
      // Navigate above owns the single history replacement. The authenticated
      // store/layout owns data loading; a late refresh must never change routes.
      dispatch({ type: 'LOGIN', user });
    } catch (err) {
      setErrors({ form: err instanceof ApiError ? err.message : t('Chưa thể đăng nhập. Vui lòng thử lại.') });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <section className="relative overflow-hidden bg-primary-light px-6 py-10 sm:px-10 lg:flex lg:w-[46%] lg:flex-col lg:px-14 lg:py-14">
        <div className="flex items-center justify-between gap-3"><Logo /><LanguageToggle /></div>
        <div className="mt-10 lg:mt-auto">
          <h1 className="text-[30px] font-bold leading-tight tracking-tight sm:text-4xl">{t('Lập kế hoạch học tập nhẹ nhàng hơn.')}</h1>
          <p className="mt-4 max-w-md text-[17px] text-slate-600">{t('Biết việc cần làm tiếp theo, hiểu vì sao — và luôn là người quyết định cuối cùng.')}</p>
          <ul className="mt-8 hidden space-y-3 sm:block">
            {['Xác nhận đề xuất trước khi áp dụng vào lịch', 'Hỏi đáp dựa trên học liệu được phép truy cập', 'Theo dõi tiến độ và điều chỉnh kế hoạch'].map((item) => (
              <li key={item} className="flex items-center gap-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-success-ink">
                  <Icon name="check" size={16} />
                </span>
                {t(item)}
              </li>
            ))}
          </ul>
        </div>
        <div className="lg:mt-auto" />
      </section>

      <section className="flex flex-1 items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-md">
          <h2 className="text-2xl font-bold">{t('Đăng nhập')}</h2>
          <p className="mt-1 text-muted">{t('Hệ thống tự nhận vai trò từ tài khoản của bạn.')}</p>
          <form className="mt-8 space-y-4" onSubmit={submit} noValidate>
            {errors.form && (
              <div role="alert" className="flex gap-2 rounded-xl border border-[#F6CFCF] bg-danger-light px-4 py-3 text-sm font-medium text-danger-ink">
                <Icon name="info" size={18} className="shrink-0" />
                {errors.form}
              </div>
            )}
            <Input label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} placeholder="ten@truong.edu.vn" />
            <Input
              label={t('Mật khẩu')}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={errors.password}
            />
            <Button type="submit" size="lg" block loading={loading}>
              {t('Đăng nhập')}
            </Button>
          </form>
          <div className="my-5 flex items-center gap-3 text-xs font-medium uppercase tracking-wide text-muted" aria-hidden="true">
            <span className="h-px flex-1 bg-line" />
            {t('hoặc')}
            <span className="h-px flex-1 bg-line" />
          </div>
          <ButtonLink to="/signup" variant="secondary" size="lg" block>
            {t('Tiếp tục với Google')}
          </ButtonLink>
          <p className="mt-3 text-center text-sm text-muted">
            {t('Dùng cho cả đăng nhập và tạo tài khoản sinh viên mới. PaceWise không yêu cầu mật khẩu Google.')}
          </p>
        </div>
      </section>
    </div>
  );
}
