/* Real Docker/browser smoke test. Prints statuses only, never tokens or profile data. */
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge', headless: true });
  const results = [];
  try {
    for (const role of ['student', 'teacher']) {
      const context = await browser.newContext({ viewport: role === 'student'
        ? { width: 390, height: 844 } : { width: 1366, height: 900 } });
      try {
        const page = await context.newPage();
        let requestsToLmsWeb = 0;
        page.on('request', request => {
          if (new URL(request.url()).port === '8010') requestsToLmsWeb++;
        });
        await page.goto('http://localhost:5173/app#/login');
        await page.getByLabel('Email', { exact: true }).fill(`${role}@canvas.local`);
        await page.getByLabel('Mật khẩu', { exact: true }).fill('demo123');
        await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
        await page.waitForURL(url => !url.hash.includes('/login'), { timeout: 60000 });
        assert.equal(await page.getByRole('button', { name: 'Quay lại LMS' }).count(), 0);
        if (role === 'teacher') {
          await page.getByRole('link', { name: 'Thông tin giảng viên', exact: true }).click();
          await page.getByLabel('Họ tên (LMS)', { exact: true }).waitFor({ timeout: 30000 });
          assert.ok(await page.getByLabel('Họ tên (LMS)', { exact: true }).inputValue());
          await page.getByRole('link', { name: 'Nhiệm vụ học tập', exact: true }).click();
          await page.getByRole('button', { name: /Thêm nhiệm vụ/ }).waitFor({ timeout: 30000 });
        } else {
          await page.getByRole('link', { name: 'Do', exact: true }).waitFor({ timeout: 30000 });
          await page.reload();
          await page.getByRole('link', { name: 'Do', exact: true }).waitFor({ timeout: 30000 });
        }
        assert.equal(requestsToLmsWeb, 0);
        await page.getByRole('button', { name: 'Đăng xuất PaceWise', exact: true }).filter({ visible: true }).first().click();
        await page.waitForURL(url => url.hash.includes('/login'), { timeout: 30000 });
        results.push({ role, login: 'passed', data_and_navigation: 'passed', logout: 'passed', requests_to_lms_web: 0 });
      } finally { await context.close(); }
    }
    console.log(JSON.stringify({ target: 'real_local_docker', results }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
