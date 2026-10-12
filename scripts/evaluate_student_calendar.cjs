/* Browser regression checks with synthetic accounts, never production learner data. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { fixture } = require('./evaluate_responsive_ui.cjs');
const base = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5174';
const output = path.resolve(__dirname, '../evals/reports/student-calendar-2026-10-10');
async function evaluate() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const [width, height] of [[390, 844], [662, 432]]) {
      const context = await browser.newContext({ viewport: { width, height }, hasTouch: true, isMobile: true });
      await fixture(context, 'student');
      const blocks = [{ id: 'b1', taskId: 't1', date: '2026-10-10', start: '10:00', end: '11:00' },
        { id: 'b2', taskId: 't2', date: '2026-10-10', start: '15:00', end: '16:00' }];
      let workspace = { plan: { id: 'p', weekStart: '2026-10-05', blocks, version: 1, savedAt: '2026-10-05T00:00:00Z' },
        availability: Array.from({ length: 7 }, (_, weekday) => ({ weekday, enabled: true, start: '00:00', end: '24:00' })),
        unavailable: [{ id: 'meal', date: '2026-10-10', weekday: 5, start: '13:00', end: '14:00', source: 'manual', category: 'meal', label: 'Ăn trưa QA' }] };
      let version = 1;
      await context.route('**/api/v1/workspace', async (route) => {
        if (route.request().method() === 'PUT') {
          const request = route.request().postDataJSON();
          assert.equal(request.expectedVersion, version, 'Lost optimistic workspace version');
          workspace = request.state; version++;
        }
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ state: workspace, version, updatedAt: new Date().toISOString() }) });
      });
      await context.route('**/api/v1/lms/sync', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({
        courses: [{ id: '1', code: 'TRR', name: 'Toán rời rạc', tone: 'primary' }],
        tasks: ['t1', 't2'].map((id) => ({ id, courseId: '1', title: id === 't1' ? 'Quan hệ QA' : 'Bài tiếp theo QA',
          deadline: id === 't1' ? '2026-10-10' : '2026-10-11', dueAt: id === 't1' ? '2026-10-10T12:00:00+07:00' : undefined,
          estimateMin: 120, loggedMin: 0, status: 'todo', priority: 'high', objective: 'Giải thích' })),
        courseData: {}, guidance: [], assessments: [],
      }) }));
      const page = await context.newPage();
      await page.clock.setFixedTime(new Date('2026-10-10T08:00:00+07:00'));
      const errors = []; page.on('pageerror', (error) => errors.push(error.message));
      await page.goto(`${base}/app#/plan`);
      await page.locator('[data-calendar-source="pacewise"]').first().waitFor();
      assert.equal(await page.getByLabel('Chọn ngày', { exact: true }).inputValue(), '2026-10-10');
      await page.waitForTimeout(100);
      const focus = await page.evaluate(() => {
        const timeline = document.querySelector('[aria-label="Cuộn theo giờ"]');
        const short = getComputedStyle(timeline).overflowY === 'visible';
        return (short ? document.querySelector('.calendar-page') : timeline).scrollTop;
      });
      assert(focus > 400, 'Calendar initially opens at midnight');
      results.push({ width, height, case: 'today and useful hour', scrollTop: focus, passed: true });
      await page.getByTitle('10:00–11:00 · Quan hệ QA').click();
      let dialog = page.getByRole('dialog', { name: 'Chi tiết ca tự học' });
      await dialog.getByRole('button', { name: 'Bắt đầu Do' }).waitFor();
      await dialog.getByLabel('Bắt đầu', { exact: true }).fill('10:07');
      await dialog.getByLabel('Kết thúc', { exact: true }).fill('11:07');
      await dialog.getByRole('button', { name: 'Lưu giờ chính xác' }).click();
      await page.getByText('Đã lưu nháp · chưa áp dụng.', { exact: true }).waitFor();
      assert.equal(workspace.plan.blocks[0].start, '10:00');
      assert.equal(workspace.calendarDraft.blocks[0].start, '10:07');
      await page.reload();
      await page.getByTitle('10:07–11:07 · Quan hệ QA').click();
      dialog = page.getByRole('dialog', { name: 'Chi tiết ca tự học' });
      assert.equal(await dialog.getByRole('button', { name: 'Bắt đầu Do' }).isDisabled(), true);
      results.push({ width, height, case: 'reload restores draft, not applied plan', passed: true });
      await dialog.getByLabel('Bắt đầu', { exact: true }).fill('17:00');
      await dialog.getByLabel('Kết thúc', { exact: true }).fill('18:00');
      await dialog.getByRole('button', { name: 'Lưu giờ chính xác' }).click();
      await page.getByText('Ca tự học phải kết thúc trước hoặc đúng giờ deadline.', { exact: true }).waitFor();
      assert.equal(workspace.calendarDraft.blocks[0].start, '10:07');
      await page.keyboard.press('Escape');
      while (await page.getByRole('button', { name: 'Đóng thông báo', exact: true }).count()) await page.getByRole('button', { name: 'Đóng thông báo', exact: true }).first().click();
      await page.getByLabel('Lịch ngày 2026-10-11', { exact: true }).click({ position: { x: 20, y: 50 } });
      results.push({ width, height, case: 'deadline 12:00 rejects 17:00 session', passed: true });
      await page.getByTitle('15:00–16:00 · Bài tiếp theo QA').click();
      dialog = page.getByRole('dialog', { name: 'Chi tiết ca tự học' });
      await dialog.getByRole('button', { name: 'Bắt đầu Do' }).waitFor();
      await page.keyboard.press('Escape');
      results.push({ width, height, case: 'unrelated confirmed Do stays available', passed: true });
      await page.getByRole('button', { name: 'Lọc và hiển thị lịch' }).click();
      await page.getByLabel('Hiện lịch cá nhân và giờ tự học ưu tiên').uncheck();
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('[data-calendar-source="busy"]').count(), 0);
      await page.getByTitle('15:00–16:00 · Bài tiếp theo QA').click();
      dialog = page.getByRole('dialog', { name: 'Chi tiết ca tự học' });
      await dialog.getByLabel('Bắt đầu', { exact: true }).fill('13:00');
      await dialog.getByLabel('Kết thúc', { exact: true }).fill('14:00');
      await dialog.getByRole('button', { name: 'Lưu giờ chính xác' }).click();
      await page.getByText('Khung giờ này trùng lịch LMS hoặc lịch cá nhân.', { exact: true }).waitFor();
      await page.keyboard.press('Escape');
      results.push({ width, height, case: 'hidden personal events still prevent overlap', passed: true });
      assert.equal(await page.getByRole('button', { name: 'Thêm vào lịch', exact: true }).count(), 0);
      assert.equal(await page.getByRole('button', { name: 'Thêm ca tự học', exact: true }).count(), 0);
      // The existing task panel remains the single route on narrow screens.
      await page.getByRole('button', { name: 'Nhiệm vụ', exact: true }).click();
      await page.getByRole('dialog', { name: 'Nhiệm vụ học tập' }).getByLabel('Chọn nhiệm vụ').waitFor();
      assert.equal(await page.getByRole('combobox', { name: /Ưu tiên cá nhân/ }).count(), 0);
      await page.keyboard.press('Escape');
      assert.equal(errors.length, 0, errors.join('\n'));
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Horizontal overflow');
      fs.mkdirSync(output, { recursive: true });
      await page.screenshot({ path: path.join(output, `${width}-${height}.png`) });
      results.push({ width, height, case: 'no duplicate add menu or personal priority; task panel accessible without overflow', passed: true });
      await context.close();
    }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ mode: 'offline browser fixtures', results }, null, 2));
    console.log(JSON.stringify({ passed: results.length, output }));
  } finally { await browser.close(); }
}
evaluate().catch((error) => { console.error(error); process.exitCode = 1; });
