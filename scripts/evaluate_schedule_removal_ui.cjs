/* Synthetic browser regression: all API calls intercepted; no real deletions. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { fixture } = require('./evaluate_responsive_ui.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5174';
const output = path.resolve(__dirname, '../evals/reports/schedule-removal-ui-2026-10-10');

async function main() {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const theme of ['light', 'dark']) for (const [width, height] of [[390, 844], [1366, 900]]) {
      const context = await browser.newContext({ viewport: { width, height }, locale: 'vi-VN' });
      await fixture(context, 'instructor');
      const courses = [{ id: 1, code: 'CS101', name: 'Môn kiểm thử', archived: false, version: 'v1', term: 'QA' }];
      const lesson = (id, title, year) => ({ id, title, starts_at: `${year}-01-01T09:00:00+07:00`,
        ends_at: `${year}-01-01T10:00:00+07:00`, mode: 'offline', version: 'v1', cancelled: false,
        description: '', location: '', meeting_url: '', resource_ids: [] });
      let lessons = [lesson(1, 'Buổi cũ kiểm thử', '2000'), lesson(2, 'Buổi mới kiểm thử', '2070')];
      const batches = new Map(); const calls = [];
      await context.route('**/api/v1/instructor/manage/**', async (route) => {
        const url = new URL(route.request().url()); const request = route.request().postDataJSON();
        calls.push(url.pathname);
        let body = {};
        if (url.pathname.endsWith('/manage/courses')) body = courses;
        else if (/\/courses\/1$/.test(url.pathname)) body = { lessons, tasks: [], materials: [], resources: [], weights: { groups: [], version: 'v1' } };
        else if (url.pathname.endsWith('/schedule/history')) body = [...batches.values()].filter((item) => item.applied);
        else if (url.pathname.endsWith('/schedule/preview')) {
          assert.equal(request.mode, 'remove');
          const selected = lessons.filter((item) => (!request.lesson_ids || request.lesson_ids.includes(item.id))
            && (request.period !== 'past' || Date.parse(item.ends_at) <= Date.now()));
          body = { ticket: `ticket-${batches.size}`, mode: 'remove', applied: false, courses: ['1'],
            counts: { removed_lessons: selected.length }, errors: [], items: [], cancellations: selected.map((item) => ({ ...item, course_id: 1 })) };
          batches.set(body.ticket, body);
        } else if (url.pathname.endsWith('/schedule/confirm')) {
          body = batches.get(request.ticket); body.applied = true;
          lessons = lessons.filter((item) => !body.cancellations.some((removed) => item.id === removed.id));
        } else if (url.pathname.endsWith('/schedule/restore')) {
          body = batches.get(request.ticket); body.restored = true;
          lessons = [...lessons, ...body.cancellations];
        }
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
      });
      const page = await context.newPage(); const errors = [];
      page.setDefaultTimeout(12000);
      page.on('pageerror', (error) => errors.push(error.message));
      await page.goto(`${base}/app#/instructor/courses`);
      await page.getByRole('heading', { name: 'CS101 · Môn kiểm thử' }).waitFor();
      await page.evaluate((value) => { document.documentElement.dataset.theme = value; }, theme);
      await page.getByLabel('Lọc buổi học').selectOption('past');
      await page.getByRole('button', { name: 'Xóa buổi Buổi cũ kiểm thử', exact: true }).click();
      assert(!calls.some((value) => value.endsWith('/schedule/confirm')), 'Opening removal must not commit');
      await page.getByRole('button', { name: 'Xác nhận xóa 1 buổi', exact: true }).click();
      await page.getByRole('dialog').waitFor({ state: 'hidden' });
      assert(!(await page.getByText('Buổi cũ kiểm thử', { exact: true }).count()));
      await page.getByRole('button', { name: 'Nhập Excel / dọn lịch', exact: true }).click();
      await page.getByRole('tab', { name: 'Dọn lịch', exact: true }).click();
      await page.getByLabel('Phạm vi buổi học').selectOption('all');
      await page.getByRole('button', { name: 'Xem trước xóa tất cả trong phạm vi' }).click();
      const confirm = page.getByRole('button', { name: 'Xác nhận xóa các buổi đã chọn' });
      assert(await confirm.isDisabled());
      await page.getByLabel('Tôi đã kiểm tra đúng môn, thời gian và các thay đổi ở trên.').check();
      await confirm.click();
      await page.getByText(/Đã xóa khỏi lịch/).waitFor();
      await page.getByRole('tab', { name: 'Lịch sử / khôi phục', exact: true }).click();
      page.once('dialog', (dialog) => dialog.accept());
      await page.getByRole('button', { name: 'Khôi phục buổi học', exact: true }).first().click();
      await page.getByText(/Đã khôi phục/).waitFor();
      await page.getByRole('tab', { name: 'Dọn lịch', exact: true }).click();
      await page.getByLabel('Phạm vi buổi học').selectOption('past');
      await page.getByRole('dialog').getByRole('button', { name: 'Xóa buổi Buổi cũ kiểm thử', exact: true }).waitFor();
      const geometry = await page.getByRole('dialog').evaluate((node) => ({ width: node.clientWidth, scroll: node.scrollWidth }));
      assert(geometry.scroll <= geometry.width + 1, 'Removal dialog must not overflow horizontally');
      assert.deepEqual(errors, []);
      await page.screenshot({ path: path.join(output, `removal-${theme}-${width}.png`), fullPage: true });
      results.push({ theme, width, height, pastLessonHasDelete: true, previewBeforeCommit: true,
        singleAndBulkRemoval: true, explicitBulkAcknowledgement: true, restoredOldLessonVisible: true,
        noHorizontalOverflow: true, pageErrors: errors });
      await context.close();
    }
  } finally { await browser.close(); }
  fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
  console.log(JSON.stringify({ passed: results.length, output, syntheticOnly: true }));
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
