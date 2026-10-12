/* Offline browser regression: synthetic API, no learner data or LLM call. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { fixture } = require('./evaluate_responsive_ui.cjs');
const base = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5174';

async function run() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const width of [320, 390, 1366]) {
      const context = await browser.newContext({ viewport: { width, height: 844 }, locale: 'vi-VN' });
      await fixture(context, 'student');
      await context.addInitScript(() => {
        window.__lmsStreams = [];
        window.EventSource = class extends EventTarget {
          constructor() { super(); window.__lmsStreams.push(this); }
          close() {}
        };
      });
      let calls = 0, revision = 1, fail = false;
      const task = { id: 'task-1', courseId: '1', title: 'Quan hệ hai ngôi và tính chất',
        deadline: '2099-10-11', estimateMin: 144, estimateIsAssumption: true, loggedMin: 0,
        status: 'todo', priority: 'high', objective: 'Mô tả toàn nhiệm vụ, không phải mục tiêu ca.' };
      const block = { id: 'block-1', taskId: task.id, date: '2099-10-10', start: '16:00', end: '16:30',
        status: 'confirmed', milestoneTitle: 'Đọc yêu cầu và rubric', rhythm: { sessionMinutes: 90, breakMinutes: 10 } };
      const resources = () => [{ id: 11, title: 'Slide chương 3', kind: 'slides', source_url: '/api/files/chapter3.pdf',
        latest_version: { version: revision, checksum_sha256: `version-${revision}` } }];
      await context.route('**/api/v1/**', async route => {
        const path = new URL(route.request().url()).pathname;
        let payload;
        if (path.endsWith('/lms/sync')) payload = { courses: [{ id: '1', code: 'DS201', name: 'Toán rời rạc', tone: 'primary' }],
          tasks: [task], courseData: { '1': { courseId: '1', modules: [], resources: resources(),
            calendarItems: [], plannerItems: [], appointmentGroups: [] } }, guidance: [], assessments: [], activeCourseId: '1' };
        else if (path.endsWith('/workspace')) payload = { state: { plan: { blocks: [block], weekStart: block.date } }, version: 1 };
        else if (path.includes('/study-sessions/current')) payload = { session: null, activeSession: null };
        else if (path.endsWith('/study-sessions/prepare')) {
          calls++;
          assert.deepEqual(route.request().postDataJSON(), { courseId: 1, blockId: 'block-1' });
          await new Promise(resolve => setTimeout(resolve, 350));
          if (fail) return route.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ detail: 'Quyền học liệu đã bị thu hồi' }) });
          payload = { action: 'prepare', status: 'ready', block_id: block.id, task_id: task.id, title: task.title,
            objective: block.milestoneTitle, planned_minutes: 30, resource_version: `version-${revision}`,
            scope: { status: 'mapped', module_ids: ['3'], module_names: ['Chương 3'], assignment_id: '7' },
            recommended_resources: [{ id: 'file:11', title: 'Slide chương 3', kind: 'slides', module: 'Chương 3',
              url: '/api/v1/lms-files/1/11/download', citation: '[Slide chương 3]' }], opening_prompt: '' };
        } else return route.fallback();
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(payload) });
      });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`${base}/app#/study/task-1/session?blockId=block-1`);
      await page.getByText('Slide chương 3', { exact: true }).waitFor();
      assert.equal(calls, 1, 'Initial render must prepare exactly once');
      assert(await page.getByText(block.milestoneTitle, { exact: true }).isVisible());
      assert(await page.getByText('30 phút', { exact: true }).isVisible());
      assert(!(await page.getByText(task.objective, { exact: true }).isVisible()));
      assert.equal(await page.getByText(/Nhịp đã xác nhận|Hoạt động: Chưa xác định/).count(), 0);
      assert(await page.getByRole('button', { name: 'Bắt đầu học' }).isEnabled());
      const notify = () => page.evaluate(() => window.__lmsStreams.forEach(stream => stream.dispatchEvent(new Event('lms.changed'))));
      await notify(); await page.waitForTimeout(500);
      assert.equal(calls, 1, 'Unchanged LMS sync must not refetch preparation');
      revision++; await notify();
      await page.getByText('Đang cập nhật…', { exact: true }).waitFor();
      assert(await page.getByText('Slide chương 3', { exact: true }).isVisible(), 'Refresh must retain current materials');
      await page.getByText('Đang cập nhật…', { exact: true }).waitFor({ state: 'hidden' });
      assert.equal(calls, 2);
      fail = true; revision++; await notify();
      await page.getByRole('button', { name: 'Thử tải lại học liệu' }).waitFor();
      assert.equal(await page.getByText('Slide chương 3', { exact: true }).count(), 0, 'Permission failure must clear old sources');
      fail = false; await page.getByRole('button', { name: 'Thử tải lại học liệu' }).click();
      await page.getByText('Slide chương 3', { exact: true }).waitFor();
      assert.equal(calls, 4);
      const overflow = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        nodes: [...document.querySelectorAll('main *')].filter(node => node.getBoundingClientRect().right > innerWidth + 1)
          .slice(0, 8).map(node => ({ tag: node.tagName, class: node.className, right: node.getBoundingClientRect().right })) }));
      assert(overflow.scrollWidth <= width + 1, `Do must not overflow the viewport: ${JSON.stringify(overflow)}`);
      assert.deepEqual(errors, []);
      results.push({ width, initialRequests: 1, unchangedSyncRequests: 0, refreshRetainsSources: true,
        revokedSourcesCleared: true, retryWorks: true, sessionObjective: true, detailsCollapsed: true });
      await context.close();
    }
    console.log(JSON.stringify({ mode: 'offline fixtures / headless Edge', results }));
  } finally { await browser.close(); }
}
run().catch(error => { console.error(error.stack); process.exitCode = 1; });
