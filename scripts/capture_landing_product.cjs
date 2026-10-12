/* Capture the actual app, using existing synthetic demo accounts, not a mockup. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const output = path.resolve(__dirname, '../landingpage/landing-assets');
  fs.mkdirSync(output, { recursive: true });
  try {
    for (const role of ['student', 'teacher']) {
      const context = await browser.newContext({ viewport: { width: 1120, height: 720 } });
      const page = await context.newPage();
      await page.goto('http://localhost:5173/app#/login');
      await page.getByLabel('Email', { exact: true }).fill(`${role}@canvas.local`);
      await page.getByLabel('Mật khẩu', { exact: true }).fill('demo123');
      await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
      await page.waitForURL(role === 'student' ? '**/app#/plan' : '**/app#/instructor');
      if (role === 'teacher') {
        await page.goto('http://localhost:5173/app#/instructor/courses');
        await page.getByRole('heading', { name: 'Môn học', exact: true }).waitFor();
        await page.getByRole('tab', { name: 'Nhiệm vụ & trọng số', exact: true }).click();
      } else {
        await page.locator('.calendar-page').waitFor();
      }
      await page.waitForTimeout(1800);
      // Synthetic account identifiers are not useful marketing content.
      await page.addStyleTag({ content: 'header [data-user-name], [data-user-email]{visibility:hidden!important}' });
      await page.evaluate(() => {
        const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walk.nextNode())) {
          if (node.textContent.includes('@canvas.local') || node.textContent.includes('Trần Gia An') || node.textContent.includes('Nguyễn Minh')) node.textContent = 'Tài khoản minh họa';
        }
      });
      await page.screenshot({ path: path.join(output, role === 'student' ? 'plan.png' : 'teacher.png') });
      await context.close();
    }
  } finally { await browser.close(); }
  console.log('Captured two current product views with synthetic account identifiers removed.');
})().catch(error => { console.error(error.message); process.exitCode = 1; });
