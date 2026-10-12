import { Suspense, useEffect, useRef, useState, type ReactNode } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Icon, type IconName } from '../components/ui/Icon';
import { Badge } from '../components/ui/Badge';
import { ThemeToggle } from '../components/domain/ThemeToggle';
import { useAppStore } from '../store/AppStore';
import { logout as logoutApi } from '../services/api';
import { cx } from '../utils/cx';
import { useToast } from '../components/ui/Toast';
import { openLmsSession } from '../services/lmsBrowserBridge';
import { Tooltip } from '../components/ui/Tooltip';
import { useLocale } from '../i18n/LocaleContext';
import { clearStudySessionContinuity } from '../utils/studySessionContinuity';

const LMS_URL = (import.meta.env.VITE_LMS_URL || 'http://localhost:8010').replace(/\/$/, '');

export interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  badge?: number;
  end?: boolean;
  /** Shown directly in the mobile bottom bar (max 4, the rest go to "Thêm"). */
  primary?: boolean;
}

export function Logo({ compact }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-dark text-[#FFFFFF]">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
          <path d="M3 15c3 0 3.5-7 6-7s3 8 6 8 3-5 6-5" />
        </svg>
      </span>
      {!compact && <span className="text-lg font-bold tracking-tight">PaceWise</span>}
    </span>
  );
}

export function AppShell({ items, roleLabel, roleTone, banner, iconOnly = false }: { items: NavItem[]; roleLabel: string; roleTone: 'primary' | 'accent'; banner?: ReactNode; iconOnly?: boolean }) {
  const { t } = useLocale();
  const { state, dispatch } = useAppStore();
  const navigate = useNavigate();
  const location = useLocation();
  const lmsWebEnabled = import.meta.env.VITE_LMS_WEB_ENABLED !== 'false';
  const [moreOpen, setMoreOpen] = useState(false);
  const toast = useToast();
  const authActionPending = useRef(false);
  useEffect(() => setMoreOpen(false), [location.pathname]);

  const logout = async () => {
    if (authActionPending.current) return;
    authActionPending.current = true;
    try {
      const result = await logoutApi();
      try {
        if (state.user) {
          window.localStorage.removeItem(`pacewise_qa_convs_${state.user.id}`);
          for (let index = window.sessionStorage.length - 1; index >= 0; index--) {
            const key = window.sessionStorage.key(index);
            if (key?.startsWith('pacewise:instructor-overview:')) window.sessionStorage.removeItem(key);
          }
        }
      } catch { /* Server revocation must not depend on browser storage availability. */ }
      clearStudySessionContinuity();
      dispatch({ type: 'LOGOUT' });
      navigate('/login', { replace: true });
      if (lmsWebEnabled && result?.linkedLmsRevoked === false) {
        toast({ tone: 'warning', title: 'Đã đăng xuất PaceWise', description: 'Chưa xác nhận thu hồi phiên LMS liên kết. Nếu đã mở Canvas, hãy đăng xuất bên đó nữa.' });
      } else {
        toast({
          tone: 'success',
          title: 'Đã đăng xuất',
          description: result?.studySessionPaused
            ? 'Phiên Do đã tạm dừng. Đăng nhập lại và bấm Do khi bạn muốn tiếp tục.'
            : 'Phiên PaceWise trên thiết bị này đã được thu hồi.',
        });
      }
    } catch {
      toast({ tone: 'danger', title: 'Chưa đăng xuất được', description: 'Phiên chưa được xác nhận thu hồi. Hãy thử lại khi kết nối ổn định.' });
    } finally { authActionPending.current = false; }
  };

  const returnToLms = async () => {
    if (authActionPending.current) return;
    authActionPending.current = true;
    try { await openLmsSession(LMS_URL); }
    catch { toast({ tone: 'danger', title: 'Chưa mở được LMS', description: 'Hãy thử lại; không có mật khẩu nào được truyền qua URL.' }); }
    finally { authActionPending.current = false; }
  };
  const localizedItems = items.map((item) => ({ ...item, label: t(item.label) }));
  const primary = localizedItems.filter((i) => i.primary).slice(0, 4);
  const rest = localizedItems.filter((i) => !primary.includes(i));
  // Compact desktop styling must not hide extra instructor tabs on mobile.
  const directMobileActions = iconOnly && rest.length === 0 && primary.length <= 3;

  const navClass = ({ isActive }: { isActive: boolean }) =>
    cx(
      'flex min-h-[44px] items-center gap-3 rounded-xl px-3 text-[15px] font-medium transition-colors',
      isActive ? 'bg-primary-light font-semibold text-primary-ink' : 'text-slate-600 hover:bg-slate-50 hover:text-ink',
    );

  return (
    <div className="app-shell min-h-screen lg:flex">
      <a href="#main" className="sr-only z-50 rounded-lg bg-white px-4 py-2 focus:not-sr-only focus:fixed focus:left-4 focus:top-4">
        {t('Bỏ qua tới nội dung chính')}
      </a>

      {/* Desktop sidebar */}
      <aside className={`app-sidebar sticky top-0 hidden h-dvh shrink-0 flex-col overflow-y-auto border-r border-line bg-white py-5 lg:flex ${iconOnly ? 'icon-only w-[72px] px-2' : 'w-[264px] px-4'}`}>
        <div className={iconOnly ? 'flex justify-center' : 'px-2'}>
          <Logo compact={iconOnly} />
        </div>
        {!iconOnly && <div className="sidebar-expanded mt-6 rounded-2xl border border-line bg-canvas px-3 py-3">
          <Badge tone={roleTone} icon={roleTone === 'primary' ? 'book' : 'users'}>
            {t(roleLabel)}
          </Badge>
          <p className="mt-2 truncate font-semibold">{state.user?.name}</p>
          <p className="caption truncate">{state.user?.email}</p>
        </div>}
        <nav className="mt-6 flex flex-col gap-1" aria-label={t('Điều hướng chính')}>
          {localizedItems.map((i) => (
            <Tooltip key={i.to} label={i.label} enabled={iconOnly}>
            <NavLink to={i.to} end={i.end} className={iconOnly ? ({ isActive }) => cx('relative flex h-11 items-center justify-center rounded-xl', isActive ? 'bg-primary-light text-primary-ink' : 'text-slate-500 hover:bg-slate-50 hover:text-ink') : navClass} aria-label={i.label} title={iconOnly ? undefined : i.label}>
              <Icon name={i.icon} size={20} />
              {!iconOnly && <span className="sidebar-expanded flex-1">{i.label}</span>}
              {!!i.badge && (
                <span className={cx('flex items-center justify-center rounded-full bg-warning-light font-bold text-warning-ink', iconOnly ? 'absolute right-0 top-0 h-4 min-w-4 px-1 text-[9px]' : 'h-6 min-w-[24px] px-1.5 text-xs')} aria-label={`${i.badge} mục cần chú ý`}>
                  {i.badge}
                </span>
              )}
            </NavLink>
            </Tooltip>
          ))}
        </nav>
        {iconOnly && (
          <div className="mt-1 flex flex-col items-center gap-1" aria-label={t('Giao diện')}>
            <Tooltip label={t('Chuyển giao diện sáng / tối')}><ThemeToggle sidebar /></Tooltip>
          </div>
        )}
        <div className="mt-auto flex flex-col gap-1 border-t border-line pt-3">
          {lmsWebEnabled && <Tooltip label={t('Quay lại LMS')} enabled={iconOnly}>
          <button onClick={returnToLms} aria-label={t('Quay lại LMS')} title={iconOnly ? undefined : t('Quay lại LMS')} className={`flex min-h-[44px] w-full items-center rounded-xl text-primary-ink hover:bg-primary-light ${iconOnly ? 'justify-center' : 'gap-3 px-3 text-[15px] font-medium'}`}>
            <Icon name="arrowLeft" size={20} />
            {!iconOnly && <span className="sidebar-expanded">{t('Quay lại LMS')}</span>}
          </button>
          </Tooltip>}
          <Tooltip label={t('Đăng xuất PaceWise')} enabled={iconOnly}>
          <button onClick={() => void logout()} aria-label={t('Đăng xuất PaceWise')} title={iconOnly ? undefined : t('Đăng xuất PaceWise')} className={`flex min-h-[44px] w-full items-center rounded-xl text-slate-600 hover:bg-slate-50 hover:text-ink ${iconOnly ? 'justify-center' : 'gap-3 px-3 text-[15px] font-medium'}`}>
            <Icon name="logout" size={20} />
            {!iconOnly && <span className="sidebar-expanded">{t('Đăng xuất PaceWise')}</span>}
          </button>
          </Tooltip>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-16 items-center gap-2 border-b border-line bg-white/95 px-3 backdrop-blur lg:hidden">
        <Logo />
        <span className="flex-1" />
        <Badge tone={roleTone}>{t(roleLabel)}</Badge>
        <ThemeToggle />
      </header>

      <div className="min-w-0 flex-1">
        {banner}
        <main id="main" tabIndex={-1} className="focus:outline-none">
          <Suspense fallback={<div className="page" role="status" aria-live="polite">Đang mở trang…</div>}>
            <Outlet />
          </Suspense>
        </main>
      </div>

      {/* Mobile bottom navigation */}
      <nav className={cx('mobile-bottom-nav fixed inset-x-0 bottom-0 z-40 grid border-t border-line bg-white pb-[env(safe-area-inset-bottom)] lg:hidden', directMobileActions && !lmsWebEnabled ? 'grid-cols-4' : 'grid-cols-5')} aria-label={t('Điều hướng chính')}>
        {primary.map((i) => (
          <NavLink
            key={i.to}
            to={i.to}
            end={i.end}
            className={({ isActive }) => cx('relative flex flex-col items-center justify-center gap-1 text-[11px] font-semibold', isActive ? 'text-primary-ink' : 'text-slate-500')}
          >
            <Icon name={i.icon} size={22} />
            <span className="max-w-full truncate px-1">{i.label}</span>
            {!!i.badge && <span className="absolute right-[22%] top-2 h-2.5 w-2.5 rounded-full bg-warning" aria-label="Có mục cần chú ý" />}
          </NavLink>
        ))}
        {directMobileActions ? <>
          {lmsWebEnabled && <button onClick={returnToLms} aria-label={t('Quay lại LMS')} title={t('Quay lại LMS')} className="flex flex-col items-center justify-center gap-1 text-[11px] font-semibold text-primary-ink">
            <Icon name="arrowLeft" size={22} />
            LMS
          </button>}
          <button onClick={() => void logout()} aria-label={t('Đăng xuất PaceWise')} title={t('Đăng xuất PaceWise')} className="flex flex-col items-center justify-center gap-1 text-[11px] font-semibold text-slate-500">
            <Icon name="logout" size={22} />
            {t('Đăng xuất')}
          </button>
        </> : <button
          onClick={() => setMoreOpen(true)}
          className={cx('relative flex flex-col items-center justify-center gap-1 text-[11px] font-semibold', rest.some((i) => location.pathname.startsWith(i.to)) ? 'text-primary-ink' : 'text-slate-500')}
          aria-haspopup="dialog"
          aria-expanded={moreOpen}
        >
          <Icon name="menu" size={22} />
          {t('Thêm')}
          {rest.some((i) => i.badge) && <span className="absolute right-[22%] top-2 h-2.5 w-2.5 rounded-full bg-warning" aria-hidden="true" />}
        </button>}
      </nav>

      {moreOpen && (
        <div className="fixed inset-0 z-50 flex items-end bg-slate-900/40 lg:hidden" onMouseDown={(e) => e.target === e.currentTarget && setMoreOpen(false)}>
          <div role="dialog" aria-modal="true" aria-label="Menu" className="w-full rounded-t-3xl bg-white px-4 pb-8 pt-3" onKeyDown={(e) => e.key === 'Escape' && setMoreOpen(false)}>
            <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-slate-200" aria-hidden="true" />
            <nav className="flex flex-col gap-1">
              {rest.map((i) => (
                <NavLink key={i.to} to={i.to} className={navClass} autoFocus={i === rest[0]}>
                  <Icon name={i.icon} size={20} />
                  <span className="flex-1">{i.label}</span>
                  {!!i.badge && <Badge tone="warning">{i.badge}</Badge>}
                </NavLink>
              ))}
              {lmsWebEnabled && <button onClick={returnToLms} className="flex min-h-[44px] items-center gap-3 rounded-xl px-3 text-[15px] font-medium text-primary-ink hover:bg-primary-light">
                <Icon name="arrowLeft" size={20} />
                {t('Quay lại LMS')}
              </button>}
              <button onClick={() => void logout()} className="flex min-h-[44px] items-center gap-3 rounded-xl px-3 text-[15px] font-medium text-slate-600 hover:bg-slate-50">
                <Icon name="logout" size={20} />
                {t('Đăng xuất PaceWise')}
              </button>
            </nav>
          </div>
        </div>
      )}
    </div>
  );
}
