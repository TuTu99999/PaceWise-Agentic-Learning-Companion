/* Native wheel and touch regression checks. Synthetic accounts only. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { fixture, exerciseCalendarScroll } = require('./evaluate_responsive_ui.cjs');
const base = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5174';

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const role of ['student', 'instructor']) {
      for (const [width, height] of [[390, 844], [662, 432], [844, 390], [1024, 768], [1366, 900], [1920, 1080]]) {
        const context = await browser.newContext({ viewport: { width, height }, hasTouch: true, isMobile: true });
        await fixture(context, role);
        await context.route('**/api/v1/workspace', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({
          state: { plan: { weekStart: '2026-10-05', blocks: [], createdAt: '2026-10-05T08:00:00+07:00' },
            unavailable: [{ id: 'qa-sleep', date: '2026-10-05', weekday: 0, start: '00:00', end: '07:00', label: 'Sleep QA', category: 'sleep', source: 'personal' }] }, version: 1,
        }) }));
        const page = await context.newPage();
        await page.goto(`${base}/app#/${role === 'student' ? 'plan' : 'instructor/schedule'}`);
        const scroller = page.getByLabel('Cuộn theo giờ');
        await scroller.waitFor();
        const wheel = await exerciseCalendarScroll(page);
        const surface = wheel.singlePageScroll ? page.locator('.calendar-page') : scroller;
        await surface.evaluate((node) => { node.scrollTop = 0; });
        const box = await surface.boundingBox();
        const nav = await page.locator('.mobile-bottom-nav').boundingBox();
        const top = Math.max(box.y, 64) + 16;
        const bottom = Math.min(box.y + box.height, nav?.y ?? height) - 16;
        assert(bottom - top >= 80, `${role}@${width}x${height}: timeline is clipped to ${bottom - top}px`);
        const x = box.x + Math.min(100, box.width * 0.4);
        const cdp = await context.newCDPSession(page);
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y: bottom }] });
        for (let step = 1; step <= 10; step++) {
          await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: bottom - (bottom - top) * step / 10 }] });
          await page.waitForTimeout(16);
        }
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
        await page.waitForTimeout(250);
        const touchScrollTop = await surface.evaluate((node) => node.scrollTop);
        assert(touchScrollTop > 0, `${role}@${width}x${height}: native touch swipe does not scroll`);
        const axes = await scroller.evaluate((node) => ({ x: getComputedStyle(node).overflowX,
          y: getComputedStyle(node).overflowY, documentWidth: document.documentElement.scrollWidth }));
        assert(['hidden', 'clip'].includes(axes.x), `${role}@${width}: horizontal scrollbar is enabled`);
        assert(axes.documentWidth <= width + 1, `${role}@${width}: page overflows horizontally`);
        if (height <= 600) assert(axes.y === 'visible' && wheel.singlePageScroll,
          `${role}@${width}: short window gained a nested vertical scroller`);
        await page.mouse.move(x, (top + bottom) / 2);
        await page.mouse.wheel(360, 0);
        await page.waitForTimeout(100);
        const horizontalOffsets = await scroller.evaluate((node) => ({ timeline: node.scrollLeft,
          page: node.closest('.calendar-page').scrollLeft, document: document.scrollingElement.scrollLeft }));
        assert(Object.values(horizontalOffsets).every(value => value === 0), `${role}@${width}: sideways scrolling is possible`);
        console.log(JSON.stringify({ role, width, height, ...wheel, touchScrollTop, axes, horizontalOffsets, passed: true }));
        await context.close();
      }
    }
  } finally { await browser.close(); }
})().catch((error) => { console.error(error.message); process.exitCode = 1; });
