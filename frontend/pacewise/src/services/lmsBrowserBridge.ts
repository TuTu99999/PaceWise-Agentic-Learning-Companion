import { createLmsBrowserBridge } from './api';

/** CORS preserves Origin even when the page uses no-referrer. No credential goes into a URL. */
export async function openLmsSession(baseUrl: string): Promise<void> {
  const target = new URL(baseUrl, window.location.origin);
  if (!['https:', 'http:'].includes(target.protocol)) throw new Error('Invalid LMS URL');
  if (target.protocol !== 'https:' && !['localhost', '127.0.0.1'].includes(target.hostname)) {
    throw new Error('LMS requires HTTPS outside localhost');
  }
  const { code } = await createLmsBrowserBridge();
  const response = await fetch(`${target.origin}/api/pacewise/sso/consume`, {
    method: 'POST',
    mode: 'cors',
    credentials: 'include',
    referrerPolicy: 'no-referrer',
    redirect: 'error',
    headers: { Accept: 'application/json' },
    body: new URLSearchParams({ code }),
  });
  if (!response.ok) throw new Error('Không thể chuyển sang LMS. Thử lại hoặc kiểm tra cấu hình kết nối.');
  const result = await response.json();
  if (result.redirect !== '/') throw new Error('Invalid LMS destination');
  window.location.assign(`${target.origin}/`);
}
