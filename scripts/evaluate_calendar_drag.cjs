/* Real HTML5 mouse dragging with synthetic data; no production accounts or AI calls. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { fixture } = require('./evaluate_responsive_ui.cjs');
const base = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5174';
async function evaluate() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 900, height: 900 } });
    await fixture(context, 'student');
    let workspace = { plan: { id: 'qa-plan', weekStart: '2026-10-05', version: 1, savedAt: '2026-10-05T00:00:00Z',
      blocks: [{ id: 'qa-block', taskId: 'qa-task', date: '2026-10-10', start: '10:07', end: '11:13' }] },
      availability: Array.from({ length: 7 }, (_, weekday) => ({ weekday, enabled: true, start: '00:00', end: '24:00' })) };
    let version = 1;
    await context.route('**/api/v1/workspace', async (route) => {
      if (route.request().method() === 'PUT') { workspace = route.request().postDataJSON().state; version++; }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ state: workspace, version, updatedAt: new Date().toISOString() }) });
    });
    await context.route('**/api/v1/lms/sync', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({
      courses: [{ id: '1', code: 'TRR', name: 'Toán rời rạc', tone: 'primary' }],
      tasks: [{ id: 'qa-task', courseId: '1', title: 'Drag QA', objective: 'Kiểm tra tọa độ', deadline: '2026-10-11', estimateMin: 180, loggedMin: 0, status: 'todo', priority: 'high' }],
      courseData: {}, guidance: [], assessments: [],
    }) }));
    const page = await context.newPage();
    await page.clock.setFixedTime(new Date('2026-10-10T08:00:00+07:00'));
    await page.goto(`${base}/app#/plan`);
    const event = page.getByTitle('10:07–11:13 · Drag QA');
    await event.waitFor(); await event.scrollIntoViewIfNeeded();
    const box = await event.boundingBox();
    const hourHeight = await page.getByLabel('Cuộn theo giờ').evaluate((node) => Number(node.dataset.calendarHourHeight));
    const pixelsPerMinute = hourHeight / 60;
    assert(Math.abs(box.height - 66 * pixelsPerMinute) < 0.02, 'Session height does not match its 66-minute duration');
    const target = await page.getByLabel('Lịch ngày 2026-10-11', { exact: true }).boundingBox();
    const grabbedMinutes = 17;
    const targetMinute = 10 * 60 + 26;
    await page.mouse.move(box.x + Math.min(30, box.width / 2), box.y + grabbedMinutes * pixelsPerMinute);
    await page.mouse.down();
    await page.mouse.move(box.x + Math.min(30, box.width / 2), box.y + grabbedMinutes * pixelsPerMinute + 8, { steps: 3 });
    await page.mouse.move(target.x + target.width / 2, target.y + (targetMinute + grabbedMinutes) * pixelsPerMinute, { steps: 8 });
    await page.mouse.move(target.x + target.width / 2, target.y + (targetMinute + grabbedMinutes) * pixelsPerMinute);
    await page.mouse.up();
    await page.getByText('Đã lưu nháp · chưa áp dụng.', { exact: true }).waitFor();
    const moved = workspace.calendarDraft.blocks[0];
    assert.equal(moved.date, '2026-10-11');
    assert.equal(moved.start, '10:26', 'Drop shifted away from the pointer position');
    assert.equal(moved.end, '11:32', 'Drop changed session duration');
    assert.equal(workspace.plan.blocks[0].start, '10:07', 'Dragging auto-applied an unconfirmed plan');
    console.log(JSON.stringify({ case: 'native drag across days with 17-minute grab offset', start: moved.start, end: moved.end, height: box.height, passed: true }));
  } finally { await browser.close(); }
}
evaluate().catch((error) => { console.error(error); process.exitCode = 1; });
