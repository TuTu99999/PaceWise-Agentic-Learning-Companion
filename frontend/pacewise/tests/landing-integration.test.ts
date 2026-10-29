import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const landingRoot = resolve(process.cwd(), '../../landingpage');
const html = readFileSync(resolve(landingRoot, 'PaceWise.html'), 'utf8');
const responsiveCss = readFileSync(resolve(landingRoot, 'landing-responsive.css'), 'utf8');
const integrationJs = readFileSync(resolve(landingRoot, 'landing-integration.js'), 'utf8');

describe('landing page integration', () => {
  it('contains exactly one HTML document', () => {
    expect(html.match(/<!doctype html>/gi)).toHaveLength(1);
    expect(html.match(/<html(?:\s|>)/gi)).toHaveLength(1);
    expect(html.match(/<\/html>/gi)).toHaveLength(1);
    expect(html.match(/<body(?:\s|>)/gi)).toHaveLength(1);
    expect(html.match(/<\/body>/gi)).toHaveLength(1);
  });

  it('loads the responsive and integration assets', () => {
    expect(html).toContain('href="/landing-responsive.css"');
    expect(html).toContain('src="/landing-integration.js"');
  });

  it('defines mobile breakpoints without a forced desktop width', () => {
    expect(responsiveCss).toContain('@media (max-width: 767px)');
    expect(responsiveCss).toContain('grid-template-columns: minmax(0, 1fr)');
    expect(responsiveCss).toMatch(/overflow-x:\s*hidden/);
  });

  it('routes login actions to the PaceWise app on the same origin', () => {
    expect(integrationJs).toContain("var APP_LOGIN_URL = '/app#/login'");
    expect(integrationJs).toContain('window.location.assign(APP_LOGIN_URL)');
  });

  it('shares language and appearance preferences with the PaceWise app', () => {
    expect(integrationJs).toContain("var LANGUAGE_KEY = 'pacewise-language'");
    expect(integrationJs).toContain("var THEME_KEY = 'pacewise-theme'");
    expect(integrationJs).toContain("window.addEventListener('storage'");
    expect(integrationJs).not.toContain("localStorage.setItem('pacewise:landing-theme'");
  });

  it('uses working login/signup anchors and removes unsupported sandbox promises', () => {
    const document = new DOMParser().parseFromString(html, 'text/html');
    const header = document.querySelector('header[role="banner"]')!;
    expect(header.querySelector('nav[role="navigation"] a[href="#try-it"]')).toBeNull();
    expect(header.querySelector('a[href="/app#/login"]')?.textContent).toBe('Đăng nhập');
    expect(header.querySelector('a[href="/app#/signup"]')?.textContent).toBe('Đăng ký');
    expect(html).not.toContain('sandbox 3 vai trò');
    expect(html).not.toContain('không cần tài khoản');
    expect(document.querySelectorAll('img')).toHaveLength(2);
    document.querySelectorAll('img').forEach(image => {
      expect(image.getAttribute('src')).toMatch(/^\/landing-assets\//);
      expect(image.getAttribute('alt')).toBeTruthy();
    });
  });

  it('links the public privacy policy and terms from the homepage', () => {
    const document = new DOMParser().parseFromString(html, 'text/html');
    expect(document.querySelector('footer a[href="/privacy"]')?.textContent).toBe('Chính sách quyền riêng tư');
    expect(document.querySelector('footer a[href="/terms"]')?.textContent).toBe('Điều khoản sử dụng');
  });
});
