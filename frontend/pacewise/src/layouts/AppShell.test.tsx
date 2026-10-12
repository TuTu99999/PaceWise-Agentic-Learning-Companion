import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from './AppShell';
import { logout } from '../services/api';
const { dispatch, toast } = vi.hoisted(() => ({ dispatch: vi.fn(), toast: vi.fn() }));
vi.mock('../services/api', () => ({ logout: vi.fn() }));
vi.mock('../services/lmsBrowserBridge', () => ({ openLmsSession: vi.fn() }));
vi.mock('../components/domain/ThemeToggle', () => ({ ThemeToggle: () => null }));
vi.mock('../components/ui/Toast', () => ({ useToast: () => toast }));
vi.mock('../store/AppStore', () => ({ useAppStore: () => ({ state: { user: { id: '12', name: 'Test' } }, dispatch }) }));
beforeEach(() => { vi.clearAllMocks(); vi.unstubAllEnvs(); localStorage.clear(); sessionStorage.clear(); });

it('hides LMS entry on desktop and mobile while keeping logout in PaceWise-only demo', () => {
  vi.stubEnv('VITE_LMS_WEB_ENABLED', 'false');
  render(<MemoryRouter><AppShell iconOnly items={[
    { to: '/plan', label: 'Plan', icon: 'calendar', primary: true },
    { to: '/do', label: 'Do', icon: 'play', primary: true },
    { to: '/settings', label: 'Settings', icon: 'settings', primary: true },
  ]} roleLabel="Sinh viên" roleTone="primary" /></MemoryRouter>);
  expect(screen.queryByRole('button', { name: 'Quay lại LMS' })).not.toBeInTheDocument();
  const mobile = screen.getAllByRole('navigation', { name: 'Điều hướng chính' })[1];
  expect(mobile).toHaveClass('grid-cols-4');
  expect(within(mobile).getByRole('button', { name: 'Đăng xuất PaceWise' })).toBeInTheDocument();
});

it('does not offer LMS entry in instructor mobile menu when web is disabled', () => {
  vi.stubEnv('VITE_LMS_WEB_ENABLED', 'false');
  render(<MemoryRouter><AppShell iconOnly items={[
    { to: '/overview', label: 'Overview', icon: 'chart', primary: true },
    { to: '/profile', label: 'Profile', icon: 'users' },
  ]} roleLabel="Giảng viên" roleTone="accent" /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', { name: /Thêm/ }));
  const menu = screen.getByRole('dialog', { name: 'Menu' });
  expect(within(menu).queryByRole('button', { name: 'Quay lại LMS' })).not.toBeInTheDocument();
  expect(within(menu).getByRole('button', { name: 'Đăng xuất PaceWise' })).toBeInTheDocument();
});
describe('logout reflects server revocation', () => {
  const setup = () => render(<MemoryRouter><AppShell items={[]} roleLabel="Sinh viên" roleTone="primary" /></MemoryRouter>);
  it('does not fake logout on network failure', async () => {
    vi.mocked(logout).mockRejectedValue(new Error('offline')); setup();
    fireEvent.click(screen.getByRole('button', { name: 'Đăng xuất PaceWise' }));
    await waitFor(() => expect(toast).toHaveBeenCalled());
    expect(dispatch).not.toHaveBeenCalled();
  });
  it('clears private browser caches only after server success', async () => {
    vi.stubEnv('VITE_LMS_WEB_ENABLED', 'false');
    vi.mocked(logout).mockResolvedValue({ linkedLmsRevoked: true });
    localStorage.setItem('pacewise_qa_convs_12', 'private');
    sessionStorage.setItem('pacewise:instructor-overview:v2:test', 'private');
    setup(); fireEvent.click(screen.getByRole('button', { name: 'Đăng xuất PaceWise' }));
    await waitFor(() => expect(dispatch).toHaveBeenCalledWith({ type: 'LOGOUT' }));
    expect(localStorage.getItem('pacewise_qa_convs_12')).toBeNull();
    expect(sessionStorage.length).toBe(0);
    expect(toast).toHaveBeenCalledWith({
      tone: 'success',
      title: 'Đã đăng xuất',
      description: 'Phiên PaceWise trên thiết bị này đã được thu hồi.',
    });
  });
  it('reports that logout paused Do and requires an explicit return to Do', async () => {
    vi.stubEnv('VITE_LMS_WEB_ENABLED', 'false');
    vi.mocked(logout).mockResolvedValue({ linkedLmsRevoked: false, studySessionPaused: true });
    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Đăng xuất PaceWise' }));
    await waitFor(() => expect(dispatch).toHaveBeenCalledWith({ type: 'LOGOUT' }));
    expect(toast).toHaveBeenCalledWith({
      tone: 'success',
      title: 'Đã đăng xuất',
      description: 'Phiên Do đã tạm dừng. Đăng nhập lại và bấm Do khi bạn muốn tiếp tục.',
    });
  });
  it('leaves the Do screen after logout instead of reopening the active session', async () => {
    vi.stubEnv('VITE_LMS_WEB_ENABLED', 'false');
    vi.mocked(logout).mockResolvedValue({ linkedLmsRevoked: false, studySessionPaused: true });
    render(<MemoryRouter initialEntries={['/study/1/session']}><Routes>
      <Route path="/study/:taskId/session" element={<AppShell items={[]} roleLabel="Sinh viên" roleTone="primary" />} />
      <Route path="/login" element={<h1>Đăng nhập lại</h1>} />
    </Routes></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Đăng xuất PaceWise' }));
    expect(await screen.findByRole('heading', { name: 'Đăng nhập lại' })).toBeVisible();
  });
  it('does not mention LMS or Canvas in the PaceWise-only logout message', async () => {
    vi.stubEnv('VITE_LMS_WEB_ENABLED', 'false');
    vi.mocked(logout).mockResolvedValue({ linkedLmsRevoked: false });
    setup(); fireEvent.click(screen.getByRole('button', { name: 'Đăng xuất PaceWise' }));
    await waitFor(() => expect(toast).toHaveBeenCalled());
    expect(JSON.stringify(toast.mock.calls)).not.toMatch(/LMS|Canvas/);
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ tone: 'success', title: 'Đã đăng xuất' }));
  });
  it('honors server logout even when browser storage is unavailable', async () => {
    vi.stubEnv('VITE_LMS_WEB_ENABLED', 'false');
    vi.mocked(logout).mockResolvedValue({ linkedLmsRevoked: true });
    const blocked = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('blocked'); });
    try {
      setup(); fireEvent.click(screen.getByRole('button', { name: 'Đăng xuất PaceWise' }));
      await waitFor(() => expect(dispatch).toHaveBeenCalledWith({ type: 'LOGOUT' }));
      expect(toast).toHaveBeenCalledWith(expect.objectContaining({ tone: 'success' }));
    } finally { blocked.mockRestore(); }
  });
});

it('keeps the current page and sidebar usable while the next tab chunk loads', async () => {
  let resolve!: (value: { default: () => React.JSX.Element }) => void;
  const SlowTab = lazy(() => new Promise<{ default: () => React.JSX.Element }>((done) => { resolve = done; }));
  render(<MemoryRouter initialEntries={['/']}>
    <Suspense fallback={<p>Whole app loading</p>}>
      <Routes><Route element={<AppShell items={[{ to: '/review', label: 'Review tab', icon: 'inbox', primary: true }]}
        roleLabel="Giảng viên" roleTone="accent" />}>
        <Route index element={<h1>Overview ready</h1>} />
        <Route path="review" element={<SlowTab />} />
      </Route></Routes>
    </Suspense>
  </MemoryRouter>);
  fireEvent.click(screen.getAllByRole('link', { name: 'Review tab' })[0]);
  // React Router 7 performs lazy navigation as a transition and preserves the
  // current outlet until the new chunk is ready instead of flashing a fallback.
  expect(screen.getByRole('heading', { name: 'Overview ready' })).toBeInTheDocument();
  expect(screen.queryByText('Whole app loading')).not.toBeInTheDocument();
  expect(screen.getAllByRole('link', { name: 'Review tab' })[0]).toBeVisible();
  expect(screen.getByRole('button', { name: 'Đăng xuất PaceWise' })).toBeVisible();
  await act(async () => resolve({ default: () => <h1>Review ready</h1> }));
  expect(screen.getByRole('heading', { name: 'Review ready' })).toBeInTheDocument();
});

it('keeps all instructor destinations and the mobile More menu when using an icon rail', () => {
  const items = [
    { to: '/instructor', label: 'Tổng quan lớp', icon: 'chart' as const, primary: true, end: true },
    { to: '/instructor/schedule', label: 'Lịch dạy', icon: 'calendar' as const, primary: true },
    { to: '/instructor/tasks', label: 'Nhiệm vụ học tập', icon: 'file' as const, primary: true },
    { to: '/instructor/review', label: 'Hàng chờ duyệt', icon: 'inbox' as const, primary: true, badge: 12 },
    { to: '/instructor/assessment', label: 'Thiết kế kiểm chứng', icon: 'clipboard' as const },
    { to: '/instructor/profile', label: 'Thông tin giảng viên', icon: 'users' as const },
  ];
  const { container } = render(<MemoryRouter><AppShell items={items} roleLabel="Giảng viên" roleTone="accent" iconOnly /></MemoryRouter>);
  const rail = container.querySelector('aside')!;
  expect(rail).toHaveClass('icon-only', 'w-[72px]');
  expect(within(rail).getByRole('link', { name: 'Lịch dạy' })).toHaveTextContent('');
  expect(within(rail).queryByText('Test')).not.toBeInTheDocument();
  expect(within(rail).getAllByRole('link')).toHaveLength(6);
  const mobile = container.querySelector<HTMLElement>('.mobile-bottom-nav')!;
  expect(within(mobile).getAllByRole('link')).toHaveLength(4);
  expect(within(mobile).queryByRole('button', { name: 'Quay lại LMS' })).not.toBeInTheDocument();
  fireEvent.click(within(mobile).getByRole('button', { name: 'Thêm' }));
  const menu = screen.getByRole('dialog', { name: 'Menu' });
  expect(within(menu).getByRole('link', { name: 'Thiết kế kiểm chứng' })).toBeInTheDocument();
  expect(within(menu).getByRole('link', { name: 'Thông tin giảng viên' })).toBeInTheDocument();
  expect(within(menu).getByRole('button', { name: 'Đăng xuất PaceWise' })).toBeInTheDocument();
});
