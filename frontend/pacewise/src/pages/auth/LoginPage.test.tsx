import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createContext, useContext, useReducer, type ReactNode } from 'react';
import { Link, MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LoginPage } from './LoginPage';
import { fetchInstructorData, login, syncCanvas } from '../../services/api';

const mocks = vi.hoisted(() => ({ useStore: null as null | (() => unknown) }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => mocks.useStore!() }));
vi.mock('../../layouts/AppShell', () => ({ Logo: () => <span>PaceWise</span> }));
vi.mock('../../services/api', () => ({
  ApiError: class extends Error {}, login: vi.fn(), syncCanvas: vi.fn(), fetchInstructorData: vi.fn(),
}));
vi.mock('../../services/instructorOverviewCache', () => ({ writeInstructorOverviewCache: vi.fn() }));
vi.mock('../../routes/instructorRouteLoaders', () => ({
  preloadInstructorOverview: vi.fn().mockResolvedValue(undefined),
  preloadInstructorRoutes: vi.fn().mockResolvedValue(undefined),
}));

function Store({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer((_: unknown, action: { type: string; user?: unknown }) => (
    { authReady: true, user: action.type === 'LOGIN' ? action.user : null }
  ), { authReady: true, user: null });
  mocks.useStore = () => useContext(StoreContext);
  return <StoreContext.Provider value={{ state, dispatch }}>{children}</StoreContext.Provider>;
}

const StoreContext = createContext<unknown>(null);

function Page() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const store = mocks.useStore!() as { dispatch: (action: { type: string }) => void };
  return <>
    <h1>{pathname}</h1>
    <Link to="/settings">Settings</Link>
    <Link to="/learn">Do</Link>
    <button onClick={() => navigate(-1)}>Back</button>
    <button onClick={() => navigate(1)}>Forward</button>
    <button onClick={() => { store.dispatch({ type: 'LOGOUT' }); navigate('/login', { replace: true }); }}>Logout</button>
  </>;
}

function setup() {
  render(<Store><MemoryRouter initialEntries={['/login']}><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="*" element={<Page />} />
  </Routes></MemoryRouter></Store>);
}

beforeEach(() => vi.clearAllMocks());

describe('login and browser history', () => {
  it('offers one Google entry point for both returning and new students', () => {
    setup();
    expect(screen.getByRole('link', { name: 'Tiếp tục với Google' })).toHaveAttribute('href', '/signup');
    expect(screen.getByText(/cả đăng nhập và tạo tài khoản sinh viên mới/)).toBeInTheDocument();
  });

  it.each(['student', 'instructor'] as const)('does not redirect %s again when login data finishes late', async (role) => {
    let finish!: (data: never) => void;
    const pending = new Promise<never>((resolve) => { finish = resolve; });
    vi.mocked(syncCanvas).mockReturnValue(pending);
    vi.mocked(fetchInstructorData).mockReturnValue(pending);
    vi.mocked(login).mockResolvedValue({ id: 'test', role } as Awaited<ReturnType<typeof login>>);
    setup();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'test@example.edu' } });
    fireEvent.change(screen.getByLabelText('Mật khẩu'), { target: { value: 'demo' } });
    fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }));
    expect(await screen.findByRole('heading', { name: role === 'student' ? '/plan' : '/instructor' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('link', { name: 'Settings' }));
    await act(async () => finish({} as never));
    expect(screen.getByRole('heading', { name: '/settings' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByRole('heading', { name: role === 'student' ? '/plan' : '/instructor' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Forward' }));
    expect(await screen.findByRole('heading', { name: '/settings' })).toBeInTheDocument();
    // Authenticated data belongs to the app store/layout, never to a departed login page.
    expect(syncCanvas).not.toHaveBeenCalled();
    expect(fetchInstructorData).not.toHaveBeenCalled();
  });

  it('replaces login rather than leaving a login entry behind the home page', async () => {
    vi.mocked(login).mockResolvedValue({ id: 'test', role: 'student' } as Awaited<ReturnType<typeof login>>);
    setup();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'test@example.edu' } });
    fireEvent.change(screen.getByLabelText('Mật khẩu'), { target: { value: 'demo' } });
    fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }));
    await screen.findByRole('heading', { name: '/plan' });
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: '/plan' })).toBeInTheDocument());
    expect(screen.queryByLabelText('Mật khẩu')).not.toBeInTheDocument();
  });
});
