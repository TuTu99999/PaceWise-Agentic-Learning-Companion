// Push-only service worker. Never caches LMS, OAuth callbacks, chat or auth APIs.
self.addEventListener('push', (event) => {
  let payload = {};
  try { payload = event.data?.json() ?? {}; } catch { /* Safe generic fallback. */ }
  event.waitUntil(self.registration.showNotification(payload.title ?? 'PaceWise · Nhắc học', {
    body: payload.body ?? 'Mở PaceWise để xem việc học cần chú ý.',
    tag: payload.tag ?? 'pacewise-reminder',
    data: { href: payload.href ?? '/plan' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const candidate = event.notification.data?.href ?? '/plan';
  const href = /^\/(?:plan|study|reflect|recover)(?:\/|\?|$)/.test(candidate) ? candidate : '/plan';
  const target = new URL(`/app#${href}`, self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const existing = windows.find((client) => new URL(client.url).origin === self.location.origin && new URL(client.url).pathname === '/app');
    if (existing) { await existing.navigate(target); await existing.focus(); }
    else await self.clients.openWindow(target);
  })());
});
