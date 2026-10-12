import { afterEach, describe, expect, it, vi } from 'vitest';
import { getPushStatus, registerPush } from './api';
import { enablePushNotifications } from './pushNotifications';

vi.mock('./api', () => ({ getPushStatus: vi.fn(), registerPush: vi.fn(), unregisterPush: vi.fn() }));
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.resetAllMocks(); });

function device(permission: NotificationPermission) {
  vi.stubGlobal('isSecureContext', true);
  vi.stubGlobal('PushManager', function PushManager() {});
  const requestPermission = vi.fn().mockResolvedValue(permission);
  vi.stubGlobal('Notification', { requestPermission });
  const subscribe = vi.fn().mockResolvedValue({ toJSON: () => ({ endpoint: 'https://provider.test/test', keys: { p256dh: 'public', auth: 'auth' } }) });
  const registration = { pushManager: { getSubscription: vi.fn().mockResolvedValue(null), subscribe } };
  vi.stubGlobal('navigator', { serviceWorker: { register: vi.fn().mockResolvedValue(registration), ready: Promise.resolve(registration) } });
  return { requestPermission, subscribe };
}

describe('Push subscription client', () => {
  it('never registers a device when permission is denied', async () => {
    const browser = device('denied');
    await expect(enablePushNotifications()).rejects.toThrow('Chưa được cấp quyền');
    expect(browser.subscribe).not.toHaveBeenCalled();
    expect(registerPush).not.toHaveBeenCalled();
  });
  it('registers with VAPID and posts only after opt-in', async () => {
    const browser = device('granted');
    vi.mocked(getPushStatus).mockResolvedValue({ configured: true, publicKey: 'AQID', subscribed: false });
    vi.mocked(registerPush).mockResolvedValue({ ok: true });
    await enablePushNotifications();
    expect(browser.requestPermission).toHaveBeenCalledOnce();
    expect(browser.subscribe).toHaveBeenCalledWith(expect.objectContaining({ userVisibleOnly: true }));
    expect(registerPush).toHaveBeenCalledOnce();
  });
});
