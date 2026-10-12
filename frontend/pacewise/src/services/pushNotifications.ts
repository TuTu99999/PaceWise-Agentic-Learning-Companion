import { getPushStatus, registerPush, unregisterPush } from './api';

export function supportsPush(): boolean {
  return window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

function publicKeyBytes(value: string): Uint8Array {
  const decoded = atob(value.replace(/-/g, '+').replace(/_/g, '/'));
  const result = new Uint8Array(decoded.length);
  for (let index = 0; index < decoded.length; index++) result[index] = decoded.charCodeAt(index);
  return result;
}

export async function enablePushNotifications(): Promise<void> {
  if (!supportsPush()) throw new Error('Nhắc nền cần HTTPS (hoặc localhost) và trình duyệt hỗ trợ Web Push.');
  // Permission is requested only from the user's click, never during page load.
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw new Error('Chưa được cấp quyền thông báo. Nhắc trong PaceWise vẫn hoạt động.');
  const config = await getPushStatus();
  if (!config.configured || !config.publicKey) throw new Error('Backend chưa cấu hình Web Push.');
  await navigator.serviceWorker.register('/pacewise-sw.js', { scope: '/' });
  const registration = await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true, applicationServerKey: publicKeyBytes(config.publicKey),
  });
  await registerPush(subscription.toJSON());
}

export async function disablePushNotifications(): Promise<void> {
  await unregisterPush();
  if ('serviceWorker' in navigator) {
    const registration = await navigator.serviceWorker.getRegistration('/');
    const subscription = await registration?.pushManager.getSubscription();
    await subscription?.unsubscribe();
  }
}
