/* Real Docker browser smoke: reads only, original demo identities, no reseed. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const reports = [];
  const output = path.resolve(__dirname, '../evals/reports/standalone-browser-2026-10-10');
  fs.mkdirSync(output, { recursive: true });
  try {
    for (const role of ['student', 'teacher']) {
      const context = await browser.newContext({ viewport: role === 'student' ? { width: 390, height: 844 } : { width: 1366, height: 900 } });
      try {
        const page = await context.newPage(); let legacyRequests = 0; const errors = [];
        page.on('request', request => { if (new URL(request.url()).port === '8010') legacyRequests++; });
        page.on('pageerror', error => errors.push(error.message));
        await page.goto('http://localhost:5173/app#/login');
        await page.getByLabel('Email', { exact: true }).fill(`${role}@canvas.local`);
        await page.getByLabel('Mật khẩu', { exact: true }).fill('demo123');
        await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
        await page.waitForURL(url => !url.hash.includes('/login'), { timeout: 45000 });
        assert.equal(await page.getByRole('button', { name: 'Quay lại LMS' }).count(), 0);
        if (role === 'teacher') {
          await page.getByRole('link', { name: 'Môn học', exact: true }).click();
          await page.getByRole('tab', { name: 'Buổi học', exact: true }).waitFor({ timeout: 30000 });
          await page.getByRole('tab', { name: 'Học liệu', exact: true }).click();
          await page.getByText('Thêm PDF (≤ 50 MB/file)', { exact: true }).waitFor({ timeout: 30000 });
          await page.getByRole('link', { name: 'Thông tin giảng viên', exact: true }).click();
          assert.ok(await page.getByLabel('Họ tên', { exact: true }).inputValue({ timeout: 30000 }));
        } else {
          await page.getByRole('link', { name: 'Do', exact: true }).waitFor({ timeout: 30000 });
          await page.reload();
          await page.getByRole('link', { name: 'Do', exact: true }).waitFor({ timeout: 30000 });
        }
        await page.screenshot({ path: path.join(output, `${role}.png`), fullPage: true });
        assert.equal(legacyRequests, 0); assert.deepEqual(errors, []);
        await page.getByRole('button', { name: 'Đăng xuất PaceWise', exact: true }).filter({ visible: true }).first().click();
        await page.waitForURL(url => url.hash.includes('/login'), { timeout: 15000 });
        reports.push({ role, login_navigation_logout: 'passed', legacy_requests: legacyRequests, page_errors: errors.length });
      } finally { await context.close(); }
    }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ passed: true, results: reports }, null, 2));
    console.log(JSON.stringify(reports));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
