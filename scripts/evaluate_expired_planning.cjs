/* Synthetic browser scenarios. Independent backend validation lives in pytest. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { fixture } = require('./evaluate_responsive_ui.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5174';
const output = path.resolve(__dirname, '../evals/reports/expired-planning-ui-2026-10-10');
async function evaluate() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const [width, height] of [[390, 844], [1366, 900]]) {
      const context = await browser.newContext({ viewport: { width, height } });
      await fixture(context, 'student');
      const tasks = ['past', 'same-day', 'future'].map(id => ({ id, courseId: '1', title: id,
        deadline: id === 'past' ? '2026-10-06' : id === 'same-day' ? '2026-10-10' : '2026-10-11',
        dueAt: id === 'past' ? '2026-10-06T17:11:00+07:00' : id === 'same-day' ? '2026-10-10T10:45:00+07:00' : '2026-10-11T23:59:00+07:00',
        estimateMin: 60, loggedMin: 0, status: 'todo', priority: 'high', objective: 'Explain' }));
      const history = { id: 'history', taskId: 'past', date: '2026-10-06', start: '15:00', end: '16:00', status: 'history' };
      const futureBlock = { id: 'safe', taskId: 'future', date: '2026-10-10', start: '15:00', end: '16:00', milestoneTitle: 'Current work' };
      const shortfalls = [{ taskId: 'past', missingMin: 540 }];
      const input = { goal: '', tasks: [], availability: [], unavailable: [], preferred: 'evening' };
      const stale = { input, createdAt: 'old', weekStart: '2026-10-05', blocks: [history], reasons: [], assumptions: [],
        feasibility: { feasible: false, availableMin: 60, requiredMin: 600, deficitMin: 540, remainingMin: -540, shortfalls } };
      let state = { plan: { id: 'qa-plan', weekStart: '2026-10-05', blocks: [history], version: 1 }, planDraft: stale, unavailable: [] };
      let version = 1, analyses = 0;
      await context.route('**/api/v1/workspace', async route => {
        if (route.request().method() === 'PUT') { state = route.request().postDataJSON().state; version++; }
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ state, version }) });
      });
      await context.route('**/api/v1/lms/sync', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({
        courses: [{ id: '1', code: 'QA', name: 'QA course', tone: 'primary' }], tasks, courseData: {}, assessments: [], guidance: [] }) }));
      await context.route('**/api/v1/chat', async route => {
        const body = route.request().postDataJSON();
        assert.equal(body.workflow, 'plan');
        let data;
        if (body.context.planning_stage === 'goal_proposal') {
          assert.deepEqual(body.context.goals.map(g => g.task_id ?? g.taskId), ['future']);
          data = { weekly_goals: [{ id: 'g', title: 'Current goal', taskIds: ['future'], confirmed: false }] };
        } else {
          assert.deepEqual(body.context.plan_input.tasks.map(t => t.taskId), ['future']); analyses++;
          data = { plan_draft: { ...stale, input: body.context.plan_input, blocks: [history, futureBlock],
            createdAt: 'new', expiredTasks: tasks.slice(0, 2).map(t => ({ taskId: t.id, title: t.title, deadline: t.dueAt, status: 'overdue_unresolved' })),
            feasibility: { feasible: true, availableMin: 60, requiredMin: 60, deficitMin: 0, remainingMin: 0, shortfalls: [] } } };
        }
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ workflow: 'plan', status: 'awaiting_student', response: 'Review', output: data, source_refs: [] }) });
      });
      const page = await context.newPage();
      const errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.clock.setFixedTime(new Date('2026-10-10T11:00:00+07:00'));
      await page.goto(`${base}/app#/plan`);
      await page.getByText('Bản nháp cũ · cần tính lại capacity', { exact: true }).waitFor();
      assert.equal(await page.getByText('Thiếu 9 giờ capacity', { exact: true }).count(), 0);
      assert.equal(await page.getByRole('button', { name: 'Xác nhận phần lịch hợp lệ', exact: true }).count(), 0);
      await page.getByRole('button', { name: 'AI phân tích lại', exact: true }).click();
      const dialog = page.getByRole('dialog', { name: 'Mục tiêu tuần AI đề xuất' });
      await dialog.waitFor(); await dialog.getByRole('checkbox').check();
      await dialog.getByRole('button', { name: 'Xác nhận và lập lịch', exact: true }).click();
      await page.getByText('2 nhiệm vụ đã quá hạn — không tính vào capacity tương lai', { exact: true }).waitFor();
      assert.equal(analyses, 1); assert.equal(errors.length, 0, errors.join('\n'));
      assert(await page.getByRole('button', { name: 'Áp dụng kế hoạch', exact: true }).isEnabled());
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      fs.mkdirSync(output, { recursive: true }); await page.screenshot({ path: path.join(output, `${width}-${height}.png`) });
      results.push({ width, height, passed: true, case: 'stale expired capacity refreshed; same-day and historical pins excluded; new draft still requires confirmation' });
      await context.close();
    }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ mode: 'offline fixture / headless Edge', results }, null, 2));
    console.log(JSON.stringify({ passed: results.length, output }));
  } finally { await browser.close(); }
}
evaluate().catch(error => { console.error(error); process.exitCode = 1; });
