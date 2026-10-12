/* Synthetic API regression; no learner plan edits or provider calls. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { fixture } = require('./evaluate_responsive_ui.cjs');
const base = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5174';

async function run() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const [width, theme] of [[390, 'light'], [390, 'dark'], [1366, 'light'], [1366, 'dark']]) {
      const context = await browser.newContext({ viewport: { width, height: 844 }, locale: 'vi-VN' });
      await context.addInitScript(theme => localStorage.setItem('pacewise-theme', theme), theme);
      await fixture(context, 'student');
      const applied = { id: 'applied', weekStart: '2026-10-05', version: 1, savedAt: '2026-10-10T01:00:00Z',
        blocks: [{ id: 'old', taskId: 'task-1', date: '2026-10-10', start: '16:00', end: '16:30' }] };
      const tasks = [{ id: 'task-1', courseId: '1', title: 'Bài tập cũ', deadline: '2026-10-12',
        estimateMin: 30, loggedMin: 0, status: 'todo', priority: 'high', objective: '' },
        { id: 'task-new', courseId: '1', title: 'Quiz mới', deadline: '2026-10-12',
          estimateMin: 30, loggedMin: 0, status: 'todo', priority: 'high', objective: '' }];
      const impact = { id: 'new-quiz', kind: 'assignment_added', title: 'Có deadline mới', message: 'Quiz mới vừa được thêm.',
        taskId: 'task-new', courseId: '1', deficitMin: 30, affectedBlockIds: [], detectedAt: '2026-10-10T09:59:00+07:00' };
      let generated = 0, confirmed = 0, draft, workspace = { plan: applied, planImpacts: [impact] };
      await context.route('**/api/v1/**', async route => {
        const path = new URL(route.request().url()).pathname;
        let payload;
        if (path.endsWith('/workspace')) {
          if (route.request().method() === 'PUT') workspace = route.request().postDataJSON().state;
          payload = { state: workspace, version: 1, updatedAt: null };
        } else if (path.endsWith('/lms/sync')) payload = { courses: [{ id: '1', code: 'TRR', name: 'Toán rời rạc', tone: 'primary' }],
          tasks, courseData: { '1': { courseId: '1', modules: [], resources: [], calendarItems: [], plannerItems: [], appointmentGroups: [] } },
          guidance: [], assessments: [], activeCourseId: '1' };
        else if (path.endsWith('/chat')) {
          const body = route.request().postDataJSON();
          assert.equal(body.workflow, 'plan', 'Notification must not invoke Recover');
          if (body.context.plan_input) {
            generated++;
            assert.deepEqual(body.context.plan_input.tasks.map(task => task.taskId), ['task-1', 'task-new']);
            draft = { input: body.context.plan_input, createdAt: 'test-replan', weekStart: '2026-10-05',
              blocks: [{ id: 'replacement', taskId: 'task-1', date: '2026-10-11', start: '10:00', end: '10:30' },
                { id: 'new-quiz-block', taskId: 'task-new', date: '2026-10-11', start: '11:00', end: '11:30' }],
              reasons: [], assumptions: [], feasibility: { feasible: true, availableMin: 120, requiredMin: 60,
                remainingMin: 60, deficitMin: 0, shortfalls: [] } };
            payload = { workflow: 'plan', status: 'awaiting_student', response: 'Bản cập nhật lịch', source_refs: [], output: { plan_draft: draft } };
          } else {
            confirmed++;
            payload = { workflow: 'plan', status: 'completed', response: 'Đã xác nhận', source_refs: [], output: { confirmed_plan: draft } };
          }
        } else return route.fallback();
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(payload) });
      });
      const page = await context.newPage();
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      await page.clock.install({ time: new Date('2026-10-10T10:00:00+07:00') });
      await page.goto(`${base}/app#/plan`);
      const selectedBlock = page.locator('article[data-calendar-source="pacewise"][title^="16:00–16:30"]');
      await selectedBlock.click();
      await page.getByRole('button', { name: 'Đóng', exact: true }).last().click();
      assert.equal(await selectedBlock.getAttribute('aria-pressed'), 'true');
      await page.locator('summary[aria-label^="Nhắc việc"]').click();
      const overlay = await page.locator('.reminder-popover').evaluate(popover => {
        const popup = popover.getBoundingClientRect();
        const block = document.querySelector('article[data-calendar-source="pacewise"][aria-pressed="true"]');
        const rect = block.getBoundingClientRect();
        const left = Math.max(popup.left, rect.left), right = Math.min(popup.right, rect.right);
        const top = Math.max(popup.top, rect.top), bottom = Math.min(popup.bottom, rect.bottom);
        const overlaps = right > left && bottom > top;
        return { overlaps, popupOnTop: !overlaps || popover.contains(document.elementFromPoint((left + right) / 2, (top + bottom) / 2)) };
      });
      if (width === 390) assert(overlay.overlaps, 'Mobile fixture must reproduce the selected block under the popover');
      assert(overlay.popupOnTop, 'Selected calendar blocks must not cover or intercept the reminder popover');
      const link = page.getByRole('link', { name: 'Xem cập nhật lịch' });
      await link.waitFor();
      assert((await link.getAttribute('href')).includes('/plan?reanalyze=lms'));
      await link.click();
      await page.getByRole('button', { name: 'Áp dụng kế hoạch', exact: true }).waitFor();
      assert.equal(generated, 1);
      assert.equal(confirmed, 0);
      assert(!page.url().includes('/recover'));
      await page.waitForTimeout(700);
      assert.equal(workspace.plan.id, 'applied', 'Draft must not replace the active plan');
      const savedPlan = page.waitForResponse(response => {
        const request = response.request();
        if (request.method() !== 'PUT' || !new URL(request.url()).pathname.endsWith('/workspace')) return false;
        return request.postDataJSON()?.state?.plan?.blocks?.some(block => block.id === 'new-quiz-block');
      });
      await page.getByRole('button', { name: 'Áp dụng kế hoạch', exact: true }).click();
      await savedPlan;
      assert.equal(confirmed, 1);
      assert(workspace.plan.blocks.some(block => block.id === 'new-quiz-block'));
      assert.equal(workspace.planImpacts.length, 0, 'Resolved warning should retire only after confirmation');
      assert.deepEqual(errors, []);
      results.push({ width, theme, popupAboveSelectedBlock: overlay.popupOnTop, opensPlan: true, automaticAnalyses: generated, preservedUntilConfirm: true,
        newTaskIncluded: true, warningRetiredAfterConfirm: true, recoverCalls: 0 });
      await context.close();
    }
    console.log(JSON.stringify({ mode: 'synthetic APIs / headless Edge', results }));
  } finally { await browser.close(); }
}
run().catch(error => { console.error(error.stack); process.exitCode = 1; });
