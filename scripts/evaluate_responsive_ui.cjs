/* Offline browser layout evaluation. All API responses are synthetic; no real account or AI call. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5174';
const output = process.env.RESPONSIVE_REPORT_DIR
  ? path.resolve(process.env.RESPONSIVE_REPORT_DIR)
  : path.resolve(__dirname, '../evals/reports/responsive-ui-2026-10-09');
const courses = [{ id: '1', code: 'TRR', name: 'Toán rời rạc · Chương 3: Quan hệ hai ngôi', tone: 'primary' }];
const tasks = [{ id: 'task-1', courseId: '1', title: 'Chương 3: Quan hệ tương đương và quan hệ thứ tự',
  deadline: '2026-10-10', estimateMin: 120, loggedMin: 0, status: 'todo', priority: 'high', objective: 'Giải thích và áp dụng quan hệ hai ngôi' }];
const blocks = [{ id: 'block-1', taskId: 'task-1', date: '2026-10-05', start: '19:00', end: '20:00',
  status: 'planned', milestoneTitle: 'Chương 3: Giải thích quan hệ tương đương' }];
const calendarItems = [{ id: 'class-1', course_id: 1, type: 'event', title: 'Chương 3: Quan hệ hai ngôi',
  starts_at: '2026-10-05T09:07:00+07:00', ends_at: '2026-10-05T10:22:00+07:00', duration_minutes: 75,
  event_kind: 'class', editable: false, location: 'A101' }];
const courseData = { '1': { courseId: '1', calendarItems, modules: [], resources: [], plannerItems: [], appointmentGroups: [] } };
const teacherWorkspace = { schedule: [], courseStructure: { modules: [], knowledgeComponents: [] }, feedback: [],
  settings: { minimumGroupSize: 5, allowIndividualReview: false, requireStudentConsent: true, autoPublishApprovedResources: false } };
const results = [];

async function fixture(context, role) {
  await context.route('**/src/services/privateApi.ts*', (route) => route.fulfill({ contentType: 'application/javascript',
    body: 'export const privateApiEnabled=false; export async function encryptedFetch(){throw new Error("Offline UI evaluation only");}' }));
  await context.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    let data = {};
    if (url.pathname.endsWith('/auth/me')) data = { user: { id: 'qa-user', name: 'Tài khoản kiểm thử', email: 'qa@example.invalid', role, courseId: '1', courseIds: ['1'] } };
    else if (url.pathname.endsWith('/workspace')) data = { state: { plan: { weekStart: '2026-10-05', blocks, createdAt: '2026-10-05T08:00:00+07:00' } }, version: 1, updatedAt: null };
    else if (url.pathname.endsWith('/lms/sync')) data = { courses, tasks, courseData, guidance: [], assessments: [], activeCourseId: '1' };
    else if (url.pathname.endsWith('/instructor/overview')) data = { classGroups: [], groupStats: {}, reviewQueue: [], assessments: [], audit: [], guidance: [], lmsSummary: null,
      teacherWorkspace, privacy: { minimumGroupSize: 5, containsDirectIdentifiers: false } };
    else if (url.pathname.endsWith('/instructor/manage/courses/1')) data = { tasks: [], lessons: [], resources: [], weights: { groups: [], version: 'qa-version' } };
    else if (url.pathname.endsWith('/instructor/manage/profile')) data = { name: 'Giảng viên kiểm thử', email: 'qa@example.invalid', version: 'qa-version', details: { title: '', department: '', office: '', office_hours: '', bio: '', contact_url: '' } };
    else if (url.pathname.includes('/lms-files/status')) data = { files: [] };
    else if (url.pathname.endsWith('/lms/events/stream')) return route.fulfill({ contentType: 'text/event-stream', body: 'retry: 600000\n\n' });
    else if (url.pathname.includes('/google-calendar/status')) data = { connected: false, configured: false };
    else if (url.pathname.includes('/notifications/')) data = { enabled: false, configured: false };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
  });
}

async function geometry(page) {
  return page.evaluate(() => {
    const rect = (selector) => { const node = document.querySelector(selector); if (!node) return null;
      const box = node.getBoundingClientRect(); return { width: box.width, height: box.height, top: box.top, bottom: box.bottom }; };
    return { viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth,
      days: document.querySelectorAll('[aria-label^="Lịch ngày "]').length,
      calendar: rect('[aria-label="Cuộn theo giờ"]'), nav: rect('.mobile-bottom-nav'), board: rect('.calendar-board') };
  });
}

async function exerciseCalendarScroll(page) {
  const timeline = page.getByLabel('Cuộn theo giờ');
  const singlePageScroll = await timeline.evaluate((node) => getComputedStyle(node).overflowY === 'visible');
  const scroller = singlePageScroll ? page.locator('.calendar-page') : timeline;
  await scroller.evaluate((node) => { node.scrollTop = 0; });
  const before = await scroller.evaluate((node) => ({ top: node.scrollTop, height: node.clientHeight, content: node.scrollHeight }));
  const box = await scroller.boundingBox();
  const nav = await page.locator('.mobile-bottom-nav').boundingBox();
  const visibleBottom = Math.min(box.y + box.height, nav?.y ?? page.viewportSize().height);
  await page.mouse.move(box.x + box.width * 0.65, Math.max(box.y, 64) + Math.min(30, (visibleBottom - Math.max(box.y, 64)) / 2));
  await page.mouse.wheel(0, 360);
  await page.waitForTimeout(250);
  const after = await scroller.evaluate((node) => node.scrollTop);
  assert(before.content > before.height && after > before.top, `Calendar wheel does not scroll: ${JSON.stringify({ before, after, box, visibleBottom })}`);
  await scroller.focus();
  await page.keyboard.press('End');
  await page.waitForTimeout(200);
  const end = await scroller.evaluate((node) => node.scrollTop + node.clientHeight >= node.scrollHeight - 2);
  assert(end, 'Calendar cannot reach the final hour using the keyboard');
  const timelineEnd = await timeline.evaluate((node) => node.getBoundingClientRect().bottom);
  if (singlePageScroll) assert(timelineEnd <= visibleBottom + 2, 'Last calendar hour remains hidden behind the navigation');
  return { wheelScrollTop: after, reachesLastHour: end, singlePageScroll };
}

async function evaluateResponsiveUi() {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const role of ['student', 'instructor']) {
      const context = await browser.newContext({ colorScheme: 'light', locale: 'vi-VN' }); await fixture(context, role);
      const page = await context.newPage(); page.setDefaultTimeout(8000); const errors = [];
      page.on('pageerror', (error) => errors.push(error.message));
      for (const [width, height] of [[320, 740], [390, 844], [430, 932], [768, 1024], [1024, 768], [1366, 900], [1920, 1080]]) {
        await page.setViewportSize({ width, height });
        await page.goto(`${base}/app#/${role === 'student' ? 'plan' : 'instructor/schedule'}`);
        await page.getByLabel('Cuộn theo giờ').waitFor();
        await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
        const scrolling = await exerciseCalendarScroll(page);
        await page.getByLabel('Cuộn theo giờ').evaluate((node, hour) => { node.scrollTop = hour * Number(node.dataset.calendarHourHeight); }, role === 'student' ? 18 : 1);
        await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        const layout = await geometry(page);
        assert(layout.scrollWidth <= width + 1, `${role}@${width}: document overflows horizontally`);
        assert(layout.calendar.height >= 100, `${role}@${width}: calendar has no usable height`);
        if (width < 1024) assert(layout.calendar.bottom <= layout.nav.top + 1, `${role}@${width}: bottom navigation covers calendar`);
        assert(layout.days === (width < 390 ? 1 : width <= 430 ? 2 : width === 768 ? 3 : 7), `${role}@${width}: unexpected day count ${layout.days}`);
        assert.equal(errors.length, 0, `${role}@${width}: JS error ${errors[0]}`);
        if (role === 'instructor' && width === 1366) {
          const rail = page.locator('aside.app-sidebar');
          assert.equal(Math.round((await rail.boundingBox()).width), 72, 'Instructor rail must stay icon-only');
          const destination = rail.getByRole('link').nth(1);
          assert.equal((await destination.innerText()).trim(), '', 'Instructor tab name should not remain visible');
          await page.mouse.move(600, 10);
          await destination.hover();
          await page.waitForTimeout(250);
          assert.equal(await page.getByRole('tooltip').count(), 0, 'Tooltip must not appear on a brief hover');
          await page.getByRole('tooltip').waitFor();
          assert.equal(await page.getByRole('tooltip').innerText(), await destination.getAttribute('aria-label'));
          assert((await page.getByRole('tooltip').boundingBox()).x >= 72, 'Tooltip is clipped inside the rail');
          await page.screenshot({ path: path.join(output, 'instructor-icon-rail-tooltip.png'), animations: 'disabled' });
          await page.keyboard.press('Escape');
          assert.equal(await page.getByRole('tooltip').count(), 0, 'Escape must close the tooltip');
          results.push({ role, interaction: 'icon-only rail and delayed tooltip', passed: true });
        }
        await page.screenshot({ path: path.join(output, `${role}-${width}-light.png`), animations: 'disabled' });
        await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });
        await page.screenshot({ path: path.join(output, `${role}-${width}-dark.png`), animations: 'disabled' });
        results.push({ role, width, height, ...layout, scrolling, errors: errors.length, passed: true });
      }
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(`${base}/app#/${role === 'student' ? 'plan' : 'instructor/schedule'}`);
      await page.getByRole('button', { name: 'Xem ngày Chủ Nhật 11/10' }).click();
      await page.getByLabel('Lịch ngày 2026-10-11').waitFor();
      if (role === 'student') {
        assert.equal(await page.getByRole('button', { name: 'Thêm vào lịch', exact: true }).count(), 0);
        await page.getByRole('button', { name: 'Lịch cá nhân', exact: true }).click();
        const dialog = page.getByRole('dialog', { name: 'Thêm lịch cá nhân' });
        await dialog.getByLabel('Loại hoạt động').selectOption('self_study');
        await dialog.getByRole('button', { name: /Giờ tự học/ }).click();
        await page.getByRole('dialog').waitFor();
        assert(await page.getByRole('dialog').getByLabel(/Ngày/).count() > 0, 'Exact-date dialog unavailable');
      } else {
        await page.getByRole('button', { name: 'Quản lý buổi học', exact: true }).click();
        await page.getByRole('dialog').getByRole('button', { name: 'Thêm buổi học' }).click();
      }
      await page.screenshot({ path: path.join(output, `${role}-390-dialog.png`), animations: 'disabled' });
      const dialogBox = await page.getByRole('dialog').boundingBox();
      assert(dialogBox.x >= 0 && dialogBox.x + dialogBox.width <= 391 && dialogBox.y >= 0 && dialogBox.y + dialogBox.height <= 845, 'Dialog outside viewport');
      await page.keyboard.press('Escape');
      results.push({ role, interaction: 'Sunday navigation and mobile exact-time dialog', passed: true });
      await page.setViewportSize({ width: 844, height: 390 });
      await page.goto(`${base}/app#/${role === 'student' ? 'plan' : 'instructor/schedule'}`);
      await page.getByLabel('Cuộn theo giờ').waitFor();
      const landscape = await geometry(page);
      assert(landscape.scrollWidth <= 845 && landscape.calendar.height >= 100, 'Landscape squeezes calendar');
      assert(await page.locator('.calendar-page').evaluate((node) => node.scrollHeight > node.clientHeight), 'Short landscape should allow page scrolling');
      results.push({ role, interaction: 'short landscape scroll', passed: true });
      const routes = process.env.CALENDAR_ONLY === 'true' ? []
        : role === 'student' ? ['learn', 'settings', 'reflect'] : ['instructor', 'instructor/tasks', 'instructor/profile', 'instructor/assessment', 'instructor/review'];
      for (const width of [320, 768, 1366]) {
        await page.setViewportSize({ width, height: 900 });
        for (const route of routes) {
          console.log(`Checking ${role} ${route} @ ${width}`);
          await page.goto(`${base}/app#/${route}`);
          await page.locator('#main').waitFor();
          await page.waitForFunction(() => document.querySelector('#main')?.innerText.length > 80 && !document.querySelector('#main')?.innerText.includes('Đang mở trang…'));
          await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
          const layout = await geometry(page);
          assert(layout.scrollWidth <= width + 1, `${route}@${width}: horizontal overflow`);
          assert.equal(errors.length, 0, `${route}@${width}: JS error ${errors[0]}`);
          if (route === 'learn') {
            const input = page.locator('#question');
            const box = await input.boundingBox();
            const nav = await page.locator('.mobile-bottom-nav').boundingBox();
            assert(box.width >= 150, 'Chat input squeezed by history sidebar');
            if (width < 1024) assert(box.y + box.height <= nav.y, 'Chat input covered by bottom navigation');
            if (width < 1024) {
              await page.getByRole('button', { name: 'Mở lịch sử chat' }).click();
              await page.getByRole('dialog', { name: 'Lịch sử trò chuyện' }).waitFor();
              await page.keyboard.press('Escape');
              assert.equal(await page.getByRole('dialog').count(), 0, 'History dialog did not close');
            }
          }
          if (width === 320) await page.screenshot({ path: path.join(output, `${route.replaceAll('/', '-')}-320.png`), animations: 'disabled' });
          results.push({ role, route, width, scrollWidth: layout.scrollWidth, passed: true });
        }
      }
      await context.close();
    }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ mode: 'offline fixtures / headless Edge', results }, null, 2));
    console.log(JSON.stringify({ passed: results.length, report: path.join(output, 'results.json') }));
  } finally { await browser.close(); }
}
module.exports = { fixture, exerciseCalendarScroll };
if (require.main === module) evaluateResponsiveUi().catch((error) => { console.error(error.message); process.exitCode = 1; });
