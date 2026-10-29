import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HashRouter, Link, useLocation } from 'react-router-dom';
import { downloadPlanIcs, exportPlanToGoogleCalendar, getGoogleCalendarStatus, getRhythmProposal } from '../../services/api';
import { SettingsPage } from './SettingsPage';
import { LocaleProvider } from '../../i18n/LocaleContext';
import { PACEWISE_LANGUAGE_STORAGE_KEY } from '../../utils/uiPreferences';

const mocks = vi.hoisted(() => ({
  dispatch: vi.fn(), toast: vi.fn(), state: {} as Record<string, any>,
  persistence: { status: 'saved', savedAt: null as string | null, message: null as string | null },
}));
vi.mock('../../components/ui/Toast', () => ({ useToast: () => mocks.toast }));
vi.mock('../../services/courseSource', () => ({ standaloneCourses: true }));
vi.mock('../../services/api', () => ({
  connectGoogleCalendar: vi.fn(), disconnectGoogleCalendar: vi.fn(), downloadPlanIcs: vi.fn(),
  exportPlanToGoogleCalendar: vi.fn(), getGoogleCalendarStatus: vi.fn(), syncGoogleCalendarBusy: vi.fn(),
  getRhythmProposal: vi.fn(), confirmRhythmProposal: vi.fn(), syncCanvas: vi.fn(),
}));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({
  dispatch: mocks.dispatch,
  state: mocks.state,
  persistence: mocks.persistence,
}) }));

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.removeItem(PACEWISE_LANGUAGE_STORAGE_KEY);
  Object.assign(mocks.persistence, { status: 'saved', savedAt: null, message: null });
  Object.keys(mocks.state).forEach((key) => delete mocks.state[key]);
  Object.assign(mocks.state, {
    user: { name: 'Calendar Student', email: 'student@example.edu' },
    availability: [{ weekday: 0, enabled: true, start: '15:00', end: '17:00' }],
    unavailable: [], tasks: [{ id: 'task-1', title: 'Ôn quan hệ hai ngôi' }],
    plan: { weekStart: '2026-10-05', blocks: [
      { id: 'block-1', taskId: 'task-1', date: '2026-10-05', start: '15:00', end: '16:00' },
    ] },
    planDraft: null,
  });
  window.history.replaceState(null, '', '/app#/settings');
  vi.mocked(getGoogleCalendarStatus).mockResolvedValue({
    configured: true, connected: false, accountEmail: null, lastFreeBusySyncAt: null,
    calendarId: 'primary', connectedAt: null,
  });
});
afterEach(() => window.history.replaceState(null, '', '/'));

function RouteLocation() {
  const location = useLocation();
  return <>
    <output data-testid="route-location">{location.pathname}{location.search}</output>
    <Link to="/settings?google_calendar=denied&tab=calendar">OAuth callback fixture</Link>
  </>;
}

function renderSettings() {
  return render(<HashRouter><RouteLocation /><SettingsPage /></HashRouter>);
}

function renderSettingsEnglish() {
  localStorage.setItem(PACEWISE_LANGUAGE_STORAGE_KEY, 'en');
  return render(<LocaleProvider><HashRouter><RouteLocation /><SettingsPage /></HashRouter></LocaleProvider>);
}

describe('Student Settings', () => {
  it('renders dynamic data, synchronization, rhythm, and Google statuses fully in English', async () => {
    mocks.state.workspaceReady = true;
    mocks.state.settings = { lastSync: '2026-10-18T07:39:37Z', staleData: false };
    mocks.persistence.savedAt = '2026-10-18T07:39:38Z';
    vi.mocked(getRhythmProposal).mockResolvedValue({ status: 'insufficient_evidence', proposal: null } as never);
    vi.mocked(getGoogleCalendarStatus).mockResolvedValue({
      configured: true, connected: true, accountEmail: 'personal.calendar@gmail.com',
      lastFreeBusySyncAt: '2026-10-15T04:13:49Z', calendarId: 'primary', connectedAt: '2026-10-09T00:00:00Z',
    });

    renderSettingsEnglish();

    expect(await screen.findByText('personal.calendar@gmail.com')).toBeInTheDocument();
    expect(screen.getByText('PaceWise · internal data')).toBeVisible();
    expect(screen.getByText('Courses, schedules, and learning materials are managed directly in PaceWise; no LMS connection is required.')).toBeVisible();
    expect(screen.getByText('PaceWise data is up to date')).toBeVisible();
    expect(screen.getByText(/Last synchronized:/)).toBeVisible();
    expect(screen.getByText('There is not enough comparable evidence to suggest a different rhythm. Your current choices remain unchanged.')).toBeVisible();
    expect(screen.getByText(/Last saved:/)).toBeVisible();
    expect(screen.getByText('personal.calendar@gmail.com').parentElement).toHaveTextContent('Connected to personal.calendar@gmail.com. PaceWise does not edit or delete your other events.');
    expect(screen.getByText(/Busy times last imported:/)).toBeVisible();
    expect(screen.getByText('1 study session in the current plan · can be exported as an .ics file independently of Google.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Add 1 session to Google' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Add 1 session to Google' }));
    expect(screen.getByRole('button', { name: 'Confirm creating 1 event' })).toBeVisible();
  });

  it('keeps transport errors distinct from missing OAuth configuration and allows retry', async () => {
    vi.mocked(getGoogleCalendarStatus).mockRejectedValueOnce(new Error('Network failed')).mockResolvedValue({
      configured: true, connected: false, accountEmail: null, lastFreeBusySyncAt: null,
      calendarId: 'primary', connectedAt: null,
    });
    renderSettings();
    expect(await screen.findByRole('alert')).toHaveTextContent('Không kiểm tra được kết nối Google');
    expect(screen.queryByText(/Quản trị viên chưa cấu hình/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra kết nối Google lại' }));
    expect(await screen.findByRole('button', { name: 'Kết nối Google Calendar' })).toBeInTheDocument();
  });
  it('removes availability/privacy cards without changing saved schedule or account/calendar controls', async () => {
    renderSettings();
    expect(await screen.findByRole('button', { name: 'Kết nối Google Calendar' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Chính sách quyền riêng tư' })).toHaveAttribute('href', '/privacy');
    expect(screen.queryByText('Thời gian rảnh mặc định')).not.toBeInTheDocument();
    expect(screen.queryByText('Quyền riêng tư')).not.toBeInTheDocument();
    expect(screen.queryByText(/Giảng viên chỉ thấy số liệu tổng hợp/)).not.toBeInTheDocument();
    expect(screen.getByText('student@example.edu')).toBeInTheDocument();
    expect(screen.getByText('Đồng bộ dữ liệu PaceWise')).toBeInTheDocument();
    expect(screen.getByText('1 ca tự học trong kế hoạch hiện tại · có thể xuất file .ics độc lập với Google.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tải file .ics' })).toBeEnabled();
    expect(mocks.dispatch).not.toHaveBeenCalled();
    expect(exportPlanToGoogleCalendar).not.toHaveBeenCalled();
  });

  it.each(['connected', 'denied', 'error'])('keeps /app after handling OAuth result %s', async (result) => {
    window.history.replaceState(null, '', `/app#/settings?google_calendar=${result}`);
    renderSettings();
    await waitFor(() => expect(window.location.hash).toBe('#/settings'));
    expect(window.location.pathname).toBe('/app');
    expect(window.location.hash).toBe('#/settings');
    expect(window.history.state.idx).toBe(0);
    expect(screen.getByTestId('route-location')).toHaveTextContent('/settings');
    expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({
      tone: result === 'connected' ? 'success' : 'danger',
    }));
  });

  it('shows the connected Google account rather than assuming the LMS email', async () => {
    vi.mocked(getGoogleCalendarStatus).mockResolvedValue({
      configured: true, connected: true, accountEmail: 'personal.calendar@gmail.com', lastFreeBusySyncAt: null,
      calendarId: 'primary', connectedAt: '2026-10-09T00:00:00Z',
    });
    renderSettings();
    expect(await screen.findByText('personal.calendar@gmail.com')).toBeInTheDocument();
    expect(screen.getByText('student@example.edu')).toBeInTheDocument();
  });

  it('downloads ICS independently from Google Calendar connection', async () => {
    const file = new Blob(['BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n'], { type: 'text/calendar' });
    vi.mocked(downloadPlanIcs).mockResolvedValue(file);
    const createObjectURL = vi.fn(() => 'blob:pacewise-calendar');
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    renderSettings();

    fireEvent.click(await screen.findByRole('button', { name: 'Tải file .ics' }));
    await waitFor(() => expect(downloadPlanIcs).toHaveBeenCalledTimes(1));
    expect(click).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledWith(file);
    expect(revokeObjectURL).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Tải file .ics' })).toBeEnabled();

    click.mockRestore();
  });

  it('cleans a callback arriving on the already-mounted settings route and preserves other parameters', async () => {
    renderSettings();
    await screen.findByRole('button', { name: 'Kết nối Google Calendar' });
    fireEvent.click(screen.getByRole('link', { name: 'OAuth callback fixture' }));
    await waitFor(() => expect(window.location.hash).toBe('#/settings?tab=calendar'));
    expect(window.history.state.idx).toBe(1);
    expect(screen.getByTestId('route-location')).toHaveTextContent('/settings?tab=calendar');
    expect(mocks.toast).toHaveBeenCalledTimes(1);
  });

  it('still requires explicit confirmation before writing study blocks to Google', async () => {
    vi.mocked(getGoogleCalendarStatus).mockResolvedValue({
      configured: true, connected: true, accountEmail: 'personal.calendar@gmail.com', lastFreeBusySyncAt: null,
      calendarId: 'primary', connectedAt: '2026-10-09T00:00:00Z',
    });
    vi.mocked(exportPlanToGoogleCalendar).mockResolvedValue({ created: [], skipped: ['block-1'] });
    renderSettings();
    fireEvent.click(await screen.findByRole('button', { name: 'Đưa 1 ca lên Google' }));
    expect(screen.getByRole('dialog', { name: 'Xác nhận tạo sự kiện' })).toBeInTheDocument();
    expect(exportPlanToGoogleCalendar).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận tạo 1 sự kiện' }));
    await waitFor(() => expect(exportPlanToGoogleCalendar).toHaveBeenCalledWith([
      { blockId: 'block-1', title: 'PaceWise: Ôn quan hệ hai ngôi',
        start: '2026-10-05T15:00:00+07:00', end: '2026-10-05T16:00:00+07:00' },
    ]));
  });

  it('explains a connected account with no confirmed plan and links back to Plan', async () => {
    vi.mocked(getGoogleCalendarStatus).mockResolvedValue({
      configured: true, connected: true, accountEmail: 'personal.calendar@gmail.com', lastFreeBusySyncAt: '2026-10-11T04:35:27Z',
      calendarId: 'primary', connectedAt: '2026-10-09T00:00:00Z',
    });
    mocks.state.plan = null;
    mocks.state.planDraft = { blocks: [] };
    renderSettings();
    expect(await screen.findByText('personal.calendar@gmail.com')).toBeInTheDocument();
    expect(screen.getByText(/Google đã kết nối, nhưng chưa có ca tự học đã xác nhận/)).toBeInTheDocument();
    expect(screen.getByText(/Bản nháp hiện chưa xếp được ca nào/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Mở Plan để tạo kế hoạch' })).toHaveAttribute('href', '#/plan');
    expect(screen.queryByRole('button', { name: /Đưa .* lên Google/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tải file .ics' })).toBeDisabled();
  });
});
