/* Synthetic browser evaluation: no real account, database write or AI/provider request. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { fixture } = require('./evaluate_responsive_ui.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = path.resolve(__dirname, '../evals/reports/teacher-courses-ui-2026-10-10');
const base = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5174';
const courses = [
  { id: 1, code: 'CS101', name: 'Nhập môn lập trình Python', term: 'Demo', archived: false, version: 'v1' },
  { id: 2, code: 'DS201', name: 'Toán rời rạc · Chương 3: Quan hệ hai ngôi', term: 'Demo', archived: false, version: 'v2' },
];
const lesson = (id, starts_at, ends_at) => ({ id, starts_at, ends_at, title: id === 1 ? 'Buổi cũ tháng 1' : 'Buổi hướng dẫn sắp tới',
  description: '', mode: 'offline', location: 'A101', meeting_url: '', cancelled: false, resource_ids: [], version: 'v1' });
const data = { tasks: [], lessons: [lesson(1, '2026-01-05T09:00:00+07:00', '2026-01-05T10:00:00+07:00'),
  lesson(2, '2027-01-12T09:00:00+07:00', '2027-01-12T10:00:00+07:00')], materials: [], resources: [], weights: { groups: [], version: 'v1' } };

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const theme of ['light', 'dark']) for (const [width, height] of [[320, 740], [390, 844], [768, 1024], [1366, 900]]) {
      const context = await browser.newContext({ viewport: { width, height }, locale: 'vi-VN', colorScheme: theme });
      await fixture(context, 'instructor');
      const calls = [];
      await context.route('**/api/v1/instructor/manage/**', async (route) => {
        const url = new URL(route.request().url()); calls.push({ method: route.request().method(), path: url.pathname });
        let response = {};
        if (url.pathname.endsWith('/manage/courses')) response = courses;
        else if (/\/courses\/\d+$/.test(url.pathname)) response = data;
        else if (url.pathname.endsWith('/roster')) response = [{ id: 2, name: 'Sinh viên kiểm thử' }];
        else if (url.pathname.endsWith('/history')) response = [];
        else if (url.pathname.endsWith('/preview')) response = { ticket: 'qa-ticket', applied: false, counts: { cancelled_lessons: 1 },
          errors: [], items: [], cancellations: [{ ...data.lessons[1], course_id: 1 }] };
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(response) });
      });
      const page = await context.newPage(); const errors = [];
      page.on('pageerror', (error) => errors.push(error.message));
      await page.goto(`${base}/app#/instructor/courses`);
      await page.getByRole('heading', { name: 'CS101 · Nhập môn lập trình Python' }).waitFor();
      await page.evaluate((value) => { document.documentElement.dataset.theme = value; }, theme);
      assert(await page.getByText('Buổi hướng dẫn sắp tới', { exact: true }).isVisible());
      assert(!(await page.getByText('Buổi cũ tháng 1', { exact: true }).count()), 'History is not the initial view');
      let geometry = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
      assert(geometry.scroll <= width + 1, `Course page overflows at ${width}: ${JSON.stringify(geometry)}`);
      await page.screenshot({ path: path.join(output, `courses-${theme}-${width}.png`), fullPage: true });
      await page.getByLabel('Lọc buổi học').selectOption('past');
      assert(await page.getByText('Buổi cũ tháng 1', { exact: true }).isVisible());
      await page.getByRole('tab', { name: 'Nhiệm vụ & trọng số', exact: true }).click();
      await page.getByRole('button', { name: 'Cấu hình trọng số' }).click();
      await page.getByRole('button', { name: 'Thêm nhóm' }).click();
      geometry = await page.getByRole('dialog').evaluate((node) => ({ width: node.clientWidth, scroll: node.scrollWidth }));
      assert(geometry.scroll <= geometry.width + 1, `Weights form overflows at ${width}: ${JSON.stringify(geometry)}`);
      await page.keyboard.press('Escape');
      await page.getByRole('tab', { name: 'Học liệu', exact: true }).click();
      await page.getByLabel('Chương / module của PDF').fill('Chương 1');
      assert(await page.getByLabel('Tải PDF môn học').isEnabled());
      await page.getByRole('button', { name: 'Thêm môn', exact: true }).click();
      await page.getByRole('textbox', { name: /Mã môn/ }).fill('NEW101');
      await page.getByLabel('Sinh viên kiểm thử').check();
      assert(!calls.some((call) => call.method === 'POST'), 'Opening forms must not mutate');
      await page.keyboard.press('Escape');
      await page.getByRole('button', { name: 'Nhập Excel / dọn lịch' }).click();
      await page.getByRole('tab', { name: 'Dọn lịch', exact: true }).click();
      await page.getByRole('button', { name: 'Xem các buổi sẽ hủy' }).click();
      const confirm = page.getByRole('button', { name: 'Xác nhận hủy các buổi đã chọn' });
      await confirm.waitFor(); assert(await confirm.isDisabled(), 'Explicit acknowledgement required');
      assert(!calls.some((call) => call.path.endsWith('/confirm')), 'Preview must never apply');
      await page.screenshot({ path: path.join(output, `cleanup-${theme}-${width}.png`), fullPage: true });
      assert.deepEqual(errors, []);
      results.push({ theme, width, height, defaultUpcoming: true, historySeparate: true, threeCoursePanels: true,
        noPageOverflow: true, noFormOverflow: true, previewDoesNotMutate: true, explicitConfirmation: true, pageErrors: errors });
      await context.close();
    }
  } finally { await browser.close(); }
  fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
  console.log(JSON.stringify({ passed: results.length, output }));
})().catch((error) => { console.error(error); process.exitCode = 1; });
