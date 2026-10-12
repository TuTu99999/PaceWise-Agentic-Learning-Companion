import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { defaultReminderPreferences } from '../../utils/studyPreferences';
import { enablePushNotifications } from '../../services/pushNotifications';
import { getPushStatus } from '../../services/api';
import { StudySettingsCards } from './StudySettingsCards';

const fixture = vi.hoisted(() => ({ dispatch: vi.fn(), toast: vi.fn() }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ dispatch: fixture.dispatch, state: {
  reminders: { preferences: defaultReminderPreferences }, studyPreferences: { sessionMinutes: 90, breakMinutes: 10 },
} }) }));
vi.mock('../ui/Toast', () => ({ useToast: () => fixture.toast }));
vi.mock('../../services/pushNotifications', () => ({ supportsPush: () => true, enablePushNotifications: vi.fn(), disablePushNotifications: vi.fn() }));
vi.mock('../../services/api', () => ({ getPushStatus: vi.fn().mockResolvedValue({ configured: true, subscribed: false, publicKey: 'test' }) }));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getPushStatus).mockResolvedValue({ configured: true, subscribed: false, publicKey: 'test' });
});
describe('Study Settings controls', () => {
  it('edits each reminder type independently without changing the plan', () => {
    render(<StudySettingsCards />);
    for (const [label, key] of [['Nhắc deadline', 'deadlineEnabled'], ['Nhắc bắt đầu Do và lịch học', 'studyEnabled'], ['Nhắc hoàn thành Reflect', 'reflectEnabled']]) {
      fireEvent.click(screen.getByLabelText(label));
      expect(fixture.dispatch).toHaveBeenCalledWith({ type: 'UPDATE_REMINDER_PREFERENCES', patch: { [key]: false } });
    }
    fireEvent.change(screen.getByLabelText('Nhắc Do trước (phút)'), { target: { value: '30' } });
    expect(fixture.dispatch).toHaveBeenCalledWith({ type: 'UPDATE_REMINDER_PREFERENCES', patch: { studyBlockLeadMinutes: 30 } });
  });
  it('stores session and break preferences without automatically replanning', () => {
    render(<StudySettingsCards />);
    fireEvent.change(screen.getByLabelText('Tối đa mỗi ca ưu tiên (phút)'), { target: { value: '25' } });
    fireEvent.change(screen.getByLabelText('Nghỉ giữa phiên (phút)'), { target: { value: '5' } });
    expect(fixture.dispatch.mock.calls.map(([action]) => action)).toEqual([
      { type: 'UPDATE_STUDY_PREFERENCES', patch: { sessionMinutes: 25 } },
      { type: 'UPDATE_STUDY_PREFERENCES', patch: { breakMinutes: 5 } },
    ]);
  });
  it('asks for device permissions only after clicking enable, and updates prefs after success', async () => {
    vi.mocked(enablePushNotifications).mockResolvedValue(undefined);
    render(<StudySettingsCards />);
    expect(enablePushNotifications).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Bật nhắc khi đóng tab' }));
    await waitFor(() => expect(fixture.dispatch).toHaveBeenCalledWith({
      type: 'UPDATE_REMINDER_PREFERENCES', patch: { browserEnabled: true, pushEnabled: true },
    }));
  });
  it('does not claim push enabled after permission/provider failure', async () => {
    vi.mocked(enablePushNotifications).mockRejectedValue(new Error('Permission denied'));
    render(<StudySettingsCards />);
    fireEvent.click(screen.getByRole('button', { name: 'Bật nhắc khi đóng tab' }));
    await waitFor(() => expect(fixture.toast).toHaveBeenCalledWith(expect.objectContaining({ tone: 'danger' })));
    expect(fixture.dispatch).not.toHaveBeenCalled();
  });
});
