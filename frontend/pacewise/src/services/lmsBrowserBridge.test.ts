import { afterEach, describe, expect, it, vi } from 'vitest';
import { openLmsSession } from './lmsBrowserBridge';
import { createLmsBrowserBridge } from './api';
vi.mock('./api', () => ({ createLmsBrowserBridge: vi.fn() }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks(); });
describe('secure LMS browser navigation', () => {
  it('uses credentialed CORS instead of an Origin-null form, then navigates without identity', async () => {
    vi.mocked(createLmsBrowserBridge).mockResolvedValue({ code: 'opaque-test-code', expires_in: 60 });
    const assign = vi.fn();
    vi.stubGlobal('window', { location: { origin: 'http://localhost:5173', assign } });
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ redirect: '/' })));
    vi.stubGlobal('fetch', fetchMock);
    await openLmsSession('http://localhost:8010');
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8010/api/pacewise/sso/consume', expect.objectContaining({
      method: 'POST', mode: 'cors', credentials: 'include', redirect: 'error', referrerPolicy: 'no-referrer',
      headers: { Accept: 'application/json' },
    }));
    expect(fetchMock.mock.calls[0][1].body.toString()).toBe('code=opaque-test-code');
    expect(assign).toHaveBeenCalledWith('http://localhost:8010/');
    expect(document.querySelector('form')).toBeNull();
  });
  it.each([
    [403, { detail: 'PaceWise origin required' }],
    [200, { redirect: 'https://attacker.invalid/' }],
  ])('does not navigate on rejected or unsafe acknowledgement (%s)', async (status, body) => {
    const assign = vi.fn();
    vi.stubGlobal('window', { location: { origin: 'http://localhost:5173', assign } });
    vi.mocked(createLmsBrowserBridge).mockResolvedValue({ code: 'opaque-test-code', expires_in: 60 });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
    await expect(openLmsSession('http://localhost:8010')).rejects.toThrow();
    expect(assign).not.toHaveBeenCalled();
  });
  it('rejects script URLs and insecure remote endpoints before requesting a code', async () => {
    await expect(openLmsSession('javascript:alert(1)')).rejects.toThrow();
    await expect(openLmsSession('http://evil.example')).rejects.toThrow();
    expect(createLmsBrowserBridge).not.toHaveBeenCalled();
  });
});
