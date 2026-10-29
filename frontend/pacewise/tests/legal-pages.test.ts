import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(process.cwd(), '../../landingpage');
const privacy = readFileSync(resolve(root, 'privacy.html'), 'utf8');
const terms = readFileSync(resolve(root, 'terms.html'), 'utf8');
const nginx = readFileSync(resolve(process.cwd(), 'nginx.conf'), 'utf8');

describe('public legal pages', () => {
  it('publishes direct, unauthenticated routes for OAuth review', () => {
    expect(nginx).toContain('location = /privacy');
    expect(nginx).toContain('try_files /privacy.html =404');
    expect(nginx).toContain('location = /terms');
    expect(nginx).toContain('try_files /terms.html =404');
  });

  it('fully discloses Google data access, use, storage, sharing, and revocation', () => {
    expect(privacy).toContain('calendar.freebusy');
    expect(privacy).toContain('calendar.events.owned');
    expect(privacy).toContain('truy cập, thu thập, sử dụng, lưu trữ và chia sẻ');
    expect(privacy).toContain('Google API Services User Data Policy');
    expect(privacy).toContain('Limited Use');
    expect(privacy).toContain('ngắt kết nối');
    expect(privacy).toContain('canhquat213@gmail.com');
  });

  it('cross-links terms and privacy without requiring app authentication', () => {
    expect(privacy).toContain('href="/terms"');
    expect(terms).toContain('href="/privacy"');
    expect(terms).toContain('Liêm chính học thuật');
    expect(terms).toContain('Google Calendar');
  });
});
