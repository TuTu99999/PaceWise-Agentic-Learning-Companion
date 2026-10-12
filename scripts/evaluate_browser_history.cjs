/* Real local browser regression. No tokens, profile data, or learning mutations. */
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.PACEWISE_URL || 'http://localhost:5173';

(async () => {
  const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge', headless: true });
  const results = [];
  try {
    for (const role of ['student', 'teacher']) {
      const context = await browser.newContext({ viewport: role === 'student'
        ? { width: 390, height: 844 } : { width: 1366, height: 900 } });
      try {
        const page = await context.newPage();
        const pageErrors = [];
        page.on('pageerror', error => pageErrors.push(error.message));
        const home = role === 'student' ? '/plan' : '/instructor';
        const first = role === 'student' ? '/learn' : '/instructor/schedule';
        const second = role === 'student' ? '/settings' : '/instructor/profile';
        const ready = async route => {
          try {
            await page.waitForURL(url => url.hash === `#${route}`, { timeout: 30000 });
          } catch {
            throw new Error(`${role}: expected ${route}, got ${new URL(page.url()).hash}`);
          }
          await page.locator(`a[href="#${route.split('?')[0]}"]`).filter({ visible: true }).first().waitFor();
          assert.equal(await page.locator('input[type=password]').count(), 0);
          console.log(JSON.stringify({ role, route, status: 'passed' }));
        };
        const visitTab = async route => {
          const links = page.locator(`a[href="#${route}"]`).filter({ visible: true });
          if (!(await links.count())) {
            await page.getByRole('button', { name: /Thêm/ }).click();
          }
          await page.locator(`a[href="#${route}"]`).filter({ visible: true }).first().click();
          await ready(route);
        };
        await page.goto(`${base}/`);
        await page.goto(`${base}/app#/login`);
        await page.locator('input[type=email]').fill(`${role}@canvas.local`);
        await page.locator('input[type=password]').fill('demo123');
        await page.locator('button[type=submit]').click();
        await ready(home);
        await visitTab(first);
        await visitTab(second);
        await page.goBack(); await ready(first);
        await page.goBack(); await ready(home);
        await page.goForward(); await ready(first);
        await page.goForward(); await ready(second);
        await page.reload(); await ready(second);

        // Old login entries must not present login to an authenticated session.
        await page.goto(`${base}/app#/login`);
        await ready(home);
        assert.ok((await page.title()).includes('PaceWise'));
        await page.goBack(); await ready(second);

        if (role === 'student') {
          // Exercise the callback URL without starting OAuth or writing events.
          await page.goto(`${base}/app#/settings?google_calendar=denied&tab=calendar`);
          await ready('/settings?tab=calendar');
          assert.equal(await page.evaluate(() => typeof history.state?.key), 'string');
          await page.reload(); await ready('/settings?tab=calendar');
          assert.equal(await page.evaluate(() => history.state?.idx), 0);
          await visitTab('/learn');
          await page.goBack(); await ready('/settings?tab=calendar');
          assert.ok(!(await page.url()).includes('google_calendar='));
        }

        await page.getByRole('button', { name: 'Đăng xuất PaceWise', exact: true }).filter({ visible: true }).first().click();
        await page.waitForURL('**#/login');
        await page.locator('input[type=password]').waitFor();
        // Back and reload cannot resurrect a server-revoked session.
        await page.goBack();
        await page.waitForURL('**#/login');
        await page.locator('input[type=password]').waitFor();
        await page.reload();
        await page.locator('input[type=password]').waitFor();
        assert.equal(new URL(page.url()).hash, '#/login');
        assert.equal(pageErrors.length, 0, 'Browser must not throw application errors');
        results.push({ role, back_forward: 'passed', reload: 'passed', stale_login_entry: 'passed',
          revoked_session: 'passed', ...(role === 'student' ? { oauth_history: 'passed' } : {}) });
      } finally { await context.close(); }
    }
    console.log(JSON.stringify({ target: base, results }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
