import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { runInNewContext } from 'node:vm';
import { describe, expect, it, vi } from 'vitest';

function worker(windows: Array<{ url: string; navigate: ReturnType<typeof vi.fn>; focus: ReturnType<typeof vi.fn> }> = []) {
  const handlers: Record<string, (event: unknown) => void> = {};
  const showNotification = vi.fn().mockResolvedValue(undefined);
  const openWindow = vi.fn().mockResolvedValue(undefined);
  runInNewContext(readFileSync(resolve(process.cwd(), 'public/pacewise-sw.js'), 'utf8'), { URL, self: {
    location: { origin: 'https://pacewise.test' },
    addEventListener: (name: string, callback: (event: unknown) => void) => { handlers[name] = callback; },
    registration: { showNotification }, clients: { matchAll: async () => windows, openWindow },
  } });
  return { handlers, showNotification, openWindow };
}

describe('Push-only service worker', () => {
  it('shows push without a loaded page and never registers a fetch/cache interceptor', async () => {
    const instance = worker();
    let pending: Promise<void> | undefined;
    instance.handlers.push({ data: { json: () => ({ title: 'PaceWise', tag: 'r1', href: '/reflect?activity=study:b1' }) }, waitUntil: (promise: Promise<void>) => { pending = promise; } });
    await pending;
    expect(instance.showNotification).toHaveBeenCalledWith('PaceWise', expect.objectContaining({ tag: 'r1' }));
    expect(instance.handlers.fetch).toBeUndefined();
  });
  it('opens /app with the correct hash route when there is no tab', async () => {
    const instance = worker();
    let pending: Promise<void> | undefined;
    instance.handlers.notificationclick({ notification: { close: vi.fn(), data: { href: '/reflect?activity=study:b1' } }, waitUntil: (promise: Promise<void>) => { pending = promise; } });
    await pending;
    expect(instance.openWindow).toHaveBeenCalledWith('https://pacewise.test/app#/reflect?activity=study:b1');
  });
  it('rejects external routes and focuses the existing app instead of landing page', async () => {
    const existing = { url: 'https://pacewise.test/app#/settings', navigate: vi.fn(), focus: vi.fn() };
    const instance = worker([existing]);
    let pending: Promise<void> | undefined;
    instance.handlers.notificationclick({ notification: { close: vi.fn(), data: { href: '//evil.test' } }, waitUntil: (promise: Promise<void>) => { pending = promise; } });
    await pending;
    expect(existing.navigate).toHaveBeenCalledWith('https://pacewise.test/app#/plan');
    expect(existing.focus).toHaveBeenCalledOnce();
    expect(instance.openWindow).not.toHaveBeenCalled();
  });
});
