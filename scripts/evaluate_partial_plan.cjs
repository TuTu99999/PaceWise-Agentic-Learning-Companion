/* Offline browser fixtures. Actual server validation is tested separately by pytest. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { fixture } = require('./evaluate_responsive_ui.cjs');
const base = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5174';
const output = path.resolve(__dirname, '../evals/reports/partial-plan-ui-2026-10-10');
async function evaluate() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const [width, height] of [[390, 844], [662, 432], [1366, 900]]) {
      const context = await browser.newContext({ viewport: { width, height } });
      await fixture(context, 'student');
      const old = { id: 'old', taskId: 'task-1', date: '2026-10-10', start: '10:00', end: '11:00', milestoneTitle: 'Ca đã xác nhận' };
      const safe = { id: 'safe', taskId: 'task-1', date: '2026-10-10', start: '15:00', end: '16:00', milestoneTitle: 'Ca hợp lệ mới' };
      const bad = { ...safe, id: 'bad', taskId: 'bad-task', start: '17:00', end: '18:00', milestoneTitle: 'Ca vượt deadline' };
      const partial = { canConfirm: true, blockIds: ['safe'], scheduledWorkMin: 60, requiresAcknowledgement: true,
        shortfalls: [{ taskId: 'task-1', missingMin: 540 }, { taskId: 'bad-task', missingMin: 60 }],
        excludedBlocks: [{ blockId: 'bad', taskId: 'bad-task', reasons: [{ code: 'AFTER_DEADLINE' }] }] };
      const draft = { createdAt: 'qa-draft', weekStart: '2026-10-05', blocks: [safe, bad], reasons: [], assumptions: [],
        input: { goal: '', tasks: [], availability: [], unavailable: [], preferred: 'evening' },
        feasibility: { feasible: false, availableMin: 60, requiredMin: 660, deficitMin: 600, remainingMin: -600, shortfalls: partial.shortfalls },
        qualityEvaluation: { canConfirm: false, releaseReady: false, score: 60, checks: {}, metrics: {}, partialConfirmation: partial,
          violations: [{ code: 'AFTER_DEADLINE', blockId: 'bad' }], blockingErrors: [{ code: 'AFTER_DEADLINE', blockId: 'bad' }] } };
      let state = { plan: { id: 'qa-plan', weekStart: '2026-10-05', blocks: [old], version: 1 }, planDraft: draft, unavailable: [] };
      let version = 1, confirmationCalls = 0, timerStarts = 0;
      await context.route('**/api/v1/workspace', async route => {
        if (route.request().method() === 'PUT') { const body = route.request().postDataJSON(); assert.equal(body.expectedVersion, version); state = body.state; version++; }
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ state, version }) });
      });
      await context.route('**/api/v1/lms/sync', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({
        courses: [{ id: '1', code: 'TRR', name: 'Môn QA', tone: 'primary' }],
        tasks: ['task-1', 'bad-task'].map(id => ({ id, courseId: '1', title: id, deadline: '2026-10-10', dueAt: `2026-10-10T${id === 'task-1' ? '23:59' : '12:00'}:00+07:00`,
          estimateMin: 660, loggedMin: 0, status: 'todo', priority: 'high', objective: 'Tự giải thích' })), courseData: {}, assessments: [], guidance: [],
      }) }));
      await context.route('**/api/v1/chat', async route => {
        const body = route.request().postDataJSON();
        if (body.workflow === 'plan') {
          assert.equal(body.context.accept_partial_plan, true); assert.deepEqual(body.context.partial_block_ids, ['safe']);
          assert.equal(body.context.plan_confirmation_id, 'qa-draft'); confirmationCalls++;
          await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ workflow: 'plan', status: 'completed', response: 'Confirmed subset', source_refs: [],
            output: { confirmed_plan: { ...draft, blocks: [safe], confirmation: { ...partial, mode: 'partial', acknowledgedShortfall: true } } } }) });
        } else await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ workflow: 'do', response: '', source_refs: [], output: {} }) });
      });
      await context.route('**/api/v1/study-sessions/current?*', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ session: null, activeSession: null }) }));
      await context.route('**/api/v1/study-sessions', async route => {
        const body = route.request().postDataJSON(); assert.equal(body.blockId, 'safe'); assert.equal(body.courseId, 1); timerStarts++;
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'timer-qa', courseId: '1', taskId: 'task-1', blockId: 'safe', version: 1,
          status: 'running', observed_seconds: 0, checkpoint_at: '2026-10-10T01:00:00Z', date: '2026-10-10', planned_minutes: 60, heartbeatSeconds: 20,
          interruption_reason: 'none', length_feeling: 'not_reported', unobserved_gap: false }) });
      });
      const page = await context.newPage(); const errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.clock.setFixedTime(new Date('2026-10-10T08:00:00+07:00'));
      await page.goto(`${base}/app#/plan`);
      await page.getByTitle(/10:00–11:00 · Ca đã xác nhận/).click();
      assert(await page.getByRole('dialog').getByRole('button', { name: 'Bắt đầu Do', exact: true }).isEnabled());
      await page.keyboard.press('Escape');
      results.push({ width, height, case: 'existing confirmed plan remains usable during invalid draft', passed: true });
      await page.getByRole('button', { name: 'Xem bản nháp', exact: true }).click();
      await page.getByTitle(/17:00–18:00 · Ca vượt deadline/).click();
      assert(await page.getByRole('dialog').getByRole('button', { name: 'Bắt đầu Do', exact: true }).isDisabled());
      await page.keyboard.press('Escape');
      await page.getByLabel('Lịch ngày 2026-10-10', { exact: true }).click({ position: { x: 20, y: 24 } });
      await page.getByTitle(/15:00–16:00 · Ca hợp lệ mới/).click();
      await page.getByRole('button', { name: 'Xem và xác nhận phần lịch hợp lệ', exact: true }).click();
      let dialog = page.getByRole('dialog', { name: 'Xác nhận phần lịch hợp lệ' });
      await dialog.waitFor(); assert.equal(confirmationCalls, 0);
      assert((await dialog.innerText()).includes('9 giờ')); assert((await dialog.innerText()).includes('Không đổi deadline'));
      fs.mkdirSync(output, { recursive: true }); await page.screenshot({ path: path.join(output, `${width}-${height}-review.png`) });
      results.push({ width, height, case: 'invalid block disabled; explicit preview retains 9h shortfall', passed: true });
      await dialog.getByRole('button', { name: 'Xác nhận 1 giờ đã xếp', exact: true }).click();
      await page.waitForURL('**/study/task-1/session?blockId=safe');
      await page.getByRole('button', { name: 'Bắt đầu học', exact: true }).click();
      await page.getByText('Đang tự học', { exact: true }).waitFor();
      assert.equal(confirmationCalls, 1); assert.equal(timerStarts, 1); assert.equal(errors.length, 0, errors.join('\n'));
      for (let attempt = 0; attempt < 30 && !state.plan?.confirmation; attempt++) await page.waitForTimeout(100);
      assert.equal(state.plan.confirmation.mode, 'partial'); assert.equal(state.plan.feasibility.deficitMin, 600);
      assert.deepEqual(state.plan.blocks.map(b => b.id), ['safe']);
      await page.goto(`${base}/app#/plan`);
      await page.getByText(/Đang dùng phần lịch đã xác nhận/).waitFor();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      results.push({ width, height, case: 'explicit confirmation opens Do and preserves warning after return', passed: true });
      await context.close();
    }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ mode: 'offline fixtures; backend rules separately tested', results }, null, 2));
    console.log(JSON.stringify({ passed: results.length, output }));
  } finally { await browser.close(); }
}
evaluate().catch(error => { console.error(error); process.exitCode = 1; });
