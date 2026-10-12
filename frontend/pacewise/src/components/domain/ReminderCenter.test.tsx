import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { acceptMyCourseInvitation, claimReminders, fetchMyCourseInvitations, getCurrentSession } from '../../services/api';
import { defaultReminderPreferences } from '../../utils/studyPreferences';
import { ReminderCenter } from './ReminderCenter';

const fixture = vi.hoisted(() => ({ state: {} as any, dispatch: vi.fn(), notify: vi.fn() }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => fixture }));
vi.mock('../ui/Toast', () => ({ useToast: () => vi.fn() }));
vi.mock('../../services/api', () => ({
  acceptMyCourseInvitation: vi.fn(), claimReminders: vi.fn(), fetchMyCourseInvitations: vi.fn(), getCurrentSession: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-10-09T10:00:00+07:00'));
  const notify = Object.assign(fixture.notify, { permission: 'granted' });
  vi.stubGlobal('Notification', notify);
  fixture.state = {
    user: { id: '2', role: 'student' },
    plan: null, tasks: [], courses: [], courseData: {}, planImpacts: [], reflections: {},
    sessions: [{ id: 's1', taskId: 't1', completedAt: '2026-10-09T09:50:00+07:00' }],
    reminders: { preferences: { ...defaultReminderPreferences, browserEnabled: true }, readIds: [], deliveredAt: {} },
  };
  vi.mocked(claimReminders).mockResolvedValue({ ids: [] });
  vi.mocked(fetchMyCourseInvitations).mockResolvedValue({ invitations: [] });
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

async function openCenter() {
  await act(async () => { render(<MemoryRouter><ReminderCenter /></MemoryRouter>); });
}

describe('Foreground and background notification ownership', () => {
  it('accepts an in-app course invitation and refreshes the schedule without a token or link', async () => {
    vi.mocked(fetchMyCourseInvitations).mockResolvedValueOnce({ invitations: [{
      id: 'invite-1', courseId: 8, code: 'DS201', name: 'Toán rời rạc', term: '2026', teacher: 'Giảng viên A', expiresAt: '2026-10-18T10:00:00+07:00',
    }] });
    vi.mocked(acceptMyCourseInvitation).mockResolvedValue({ courseId: 8, joined: true });
    vi.mocked(getCurrentSession).mockResolvedValue({ id: '2', role: 'student', courseIds: ['8'] } as never);
    await openCenter();
    await act(async () => { await Promise.resolve(); });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Tham gia và đồng bộ lịch' }));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(acceptMyCourseInvitation).toHaveBeenCalledExactlyOnceWith('invite-1');
    expect(fixture.dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'REFRESH_SESSION' }));
    expect(screen.queryByText('invite-1')).not.toBeInTheDocument();
    expect(screen.queryByText(/token/i)).not.toBeInTheDocument();
  });
  it.each([false, true])('links the %s reminder view directly to automatic Plan analysis, not Recover', async compact => {
    fixture.state.reminders.preferences.browserEnabled = false;
    fixture.state.planImpacts = [{ id: 'new-assignment', kind: 'assignment_added', title: 'Có deadline mới', message: 'New task',
      taskId: 't1', courseId: '1', deficitMin: 20, affectedBlockIds: [], detectedAt: '2026-10-09T09:59:00+07:00' }];
    await act(async () => { render(<MemoryRouter><ReminderCenter compact={compact} /></MemoryRouter>); });
    expect(screen.getByRole('link', { name: 'Xem cập nhật lịch' })).toHaveAttribute('href',
      '/plan?reanalyze=lms&impactId=new-assignment&taskId=t1&courseId=1');
    expect(screen.queryByText('Mở Phục hồi')).not.toBeInTheDocument();
    if (compact) {
      const link = screen.getByRole('link', { name: 'Xem cập nhật lịch' });
      const popup = link.closest('details')!;
      popup.open = true;
      fireEvent.click(link);
      expect(popup.open).toBe(false);
    }
  });
  it('does not dispatch or show a notification when the backend rejects a duplicate/capped claim', async () => {
    vi.mocked(claimReminders).mockResolvedValue({ ids: [] });
    await openCenter();
    expect(claimReminders).toHaveBeenCalledTimes(1);
    expect(fixture.notify).not.toHaveBeenCalled();
    expect(fixture.dispatch).not.toHaveBeenCalled();
  });
  it('shows only reminders accepted by the shared backend budget', async () => {
    vi.mocked(claimReminders).mockResolvedValue({ ids: ['reflect-session:s1'] });
    fixture.notify.mockImplementation(() => ({ close: vi.fn() }));
    await openCenter();
    expect(fixture.notify).toHaveBeenCalledTimes(1);
    expect(fixture.dispatch).toHaveBeenCalledWith({ type: 'RECORD_REMINDER_DELIVERY', ids: ['reflect-session:s1'], deliveredAt: '2026-10-09T03:00:00.000Z' });
  });
  it('does not produce a second local notification when background push owns delivery', async () => {
    fixture.state.reminders.preferences.pushEnabled = true;
    await openCenter();
    expect(claimReminders).not.toHaveBeenCalled();
    expect(fixture.notify).not.toHaveBeenCalled();
  });
});
