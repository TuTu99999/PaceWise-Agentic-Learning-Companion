import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SignUpPage } from './SignUpPage';
import { getGoogleSignInStatus, startGoogleSignIn } from '../../services/api';

vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ state: { authReady: true, user: null } }) }));
vi.mock('../../layouts/AppShell', () => ({ Logo: () => <span>PaceWise</span> }));
vi.mock('../../services/api', () => ({ ApiError: class extends Error {}, getGoogleSignInStatus: vi.fn(), startGoogleSignIn: vi.fn() }));
const setup = (path = '/signup') => render(<MemoryRouter initialEntries={[path]}><SignUpPage /></MemoryRouter>);
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getGoogleSignInStatus).mockResolvedValue({ configured: true });
});

describe('Google student sign-in', () => {
  it('does not ask for a Google password or allow a role selector', async () => {
    setup();
    const button = await screen.findByRole('button', { name: 'Chọn tài khoản Google' });
    await waitFor(() => expect(button).toBeEnabled());
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('disables Google sign-in when Google is not configured', async () => {
    vi.mocked(getGoogleSignInStatus).mockResolvedValue({ configured: false });
    setup();
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('tạm chưa sẵn sàng'));
    expect(screen.getByRole('button', { name: 'Chọn tài khoản Google' })).toBeDisabled();
    expect(screen.getByRole('link', { name: 'Quay lại đăng nhập' })).toHaveAttribute('href', '/login');
  });

  it('coalesces double submission and rejects an unexpected redirect origin', async () => {
    let finish!: (value: { authorizationUrl: string }) => void;
    vi.mocked(startGoogleSignIn).mockReturnValue(new Promise(resolve => { finish = resolve; }));
    setup();
    const button = screen.getByRole('button', { name: 'Chọn tài khoản Google' });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button); fireEvent.click(button);
    expect(startGoogleSignIn).toHaveBeenCalledExactlyOnceWith();
    finish({ authorizationUrl: 'https://evil.test/oauth' });
    expect(await screen.findByRole('alert')).toHaveTextContent('Chưa mở được Google');
  });

  it('explains cancellation instead of displaying raw OAuth errors', async () => {
    setup('/signup?google_auth=denied');
    expect(await screen.findByRole('alert')).toHaveTextContent('hủy tiếp tục với Google');
  });

  it('allows retry after a transport error without calling it missing configuration', async () => {
    vi.mocked(getGoogleSignInStatus).mockRejectedValueOnce(new Error('offline'));
    setup();
    expect(await screen.findByRole('alert')).toHaveTextContent('Chưa kiểm tra được kết nối');
    expect(screen.queryByText(/tạm chưa sẵn sàng/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại kết nối' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Chọn tài khoản Google' })).toBeEnabled());
    expect(getGoogleSignInStatus).toHaveBeenCalledTimes(2);
  });
});
