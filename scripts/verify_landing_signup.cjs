/* Read-only browser QA; real Google consent remains a user action. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const output = path.resolve(__dirname, '../outputs/landing-signup-qa');
  fs.mkdirSync(output, { recursive: true });
  const results = [];
  try {
    for (const width of [320, 390, 768, 1366]) {
      for (const colorScheme of ['light', 'dark']) {
        const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme });
        const page = await context.newPage();
        page.setDefaultTimeout(10000);
        await page.goto('http://localhost:5173/');
        await page.locator('img').evaluateAll(images => Promise.all(images.map(image => {
          image.loading = 'eager';
          return image.decode();
        })));
        const layout = await page.evaluate(() => ({
          width: document.documentElement.clientWidth,
          content: document.documentElement.scrollWidth,
          broken: [...document.images].filter(image => !image.complete || !image.naturalWidth).length,
        }));
        assert(layout.content <= layout.width + 1, `Horizontal overflow at ${width}/${colorScheme}`);
        assert.equal(layout.broken, 0);
        await page.screenshot({ path: path.join(output, `landing-${width}-${colorScheme}.png`), fullPage: true });
        await page.getByRole('link', { name: 'Bắt đầu với Google' }).click();
        await page.getByRole('heading', { name: 'Đăng ký tài khoản sinh viên' }).waitFor();
        await page.getByRole('button', { name: 'Tiếp tục với Google' }).waitFor();
        await page.waitForFunction(() => [...document.querySelectorAll('button')]
          .some(button => button.textContent.includes('Tiếp tục với Google') && !button.disabled));
        const ready = await page.getByRole('button', { name: 'Tiếp tục với Google' }).isEnabled();
        assert(ready, 'Google configuration check did not finish');
        assert.equal(await page.locator('input[type=password]').count(), 0);
        assert(await page.getByText('Đăng ký không tự kết nối lịch hay cấp quyền vào môn học.', { exact: false }).isVisible());
        await page.screenshot({ path: path.join(output, `signup-${width}-${colorScheme}.png`), fullPage: true });
        results.push({ width, colorScheme, overflow: false, images: 'ok', googleConfigured: ready });
        if (width === 1366 && colorScheme === 'light') {
          // Verify the real start endpoint, but never complete somebody's consent.
          await page.route('https://accounts.google.com/**', route => route.fulfill({
            status: 200, contentType: 'text/html', body: '<h1>OAuth redirect intercepted for QA</h1>',
          }));
          await page.getByLabel('Gmail của bạn', { exact: false }).fill('pacewise.qa@gmail.com');
          const outgoing = page.waitForRequest(request => request.url().startsWith('https://accounts.google.com/'));
          const gateway = page.waitForRequest(request => request.method() === 'POST'
            && request.url().includes('/private/dispatch'));
          await page.getByRole('button', { name: 'Tiếp tục với Google' }).click();
          const google = new URL((await outgoing).url());
          assert.equal(google.pathname, '/o/oauth2/v2/auth');
          assert.equal(google.searchParams.get('scope'), 'openid email profile');
          assert.equal(google.searchParams.get('code_challenge_method'), 'S256');
          assert(google.searchParams.get('state').startsWith('signup.'));
          assert(!(await gateway).postData().includes('pacewise.qa@gmail.com'));
          const binding = (await context.cookies('http://localhost:5173'))
            .find(cookie => cookie.name === 'pacewise_google_signup');
          assert(binding?.httpOnly && binding.sameSite === 'Lax');
          results.push({ googleStart: 'encrypted request, PKCE, state and HttpOnly binding verified', consent: 'not completed' });
        }
        await context.close();
      }
    }
    for (const role of ['student', 'teacher']) {
      const context = await browser.newContext();
      const page = await context.newPage();
      await page.goto('http://localhost:5173/app#/login');
      await page.getByLabel('Email', { exact: true }).fill(`${role}@canvas.local`);
      await page.getByLabel('Mật khẩu', { exact: true }).fill('demo123');
      await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
      await page.waitForURL(role === 'student' ? '**/app#/plan' : '**/app#/instructor');
      await page.getByRole('button', { name: 'Đăng xuất PaceWise', exact: true }).first().click();
      await page.waitForURL('**/app#/login');
      await page.goto(role === 'student' ? 'http://localhost:5173/app#/plan' : 'http://localhost:5173/app#/instructor');
      await page.waitForURL('**/app#/login');
      results.push({ role, existingAccount: 'login ok', logout: 'protected route denied after logout' });
      await context.close();
    }
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
