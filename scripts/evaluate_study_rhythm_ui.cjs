/* Real browser interactions, synthetic API only; not a learner pilot. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { fixture } = require('./evaluate_responsive_ui.cjs');
const base = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5174';
const output = path.resolve(__dirname, '../evals/reports/activity-rhythm-ui-2026-10-10');

async function evaluate() {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const [width, height] of [[390, 844], [1366, 900]]) {
      const context = await browser.newContext({ viewport: { width, height }, locale: 'vi-VN' });
      await fixture(context, 'student');
      const block = { id: 'b1', taskId: '1:a', date: '2026-10-10', start: '10:00', end: '11:00',
        activityType: 'concept', rhythm: { sessionMinutes: 60, breakMinutes: 10 } };
      const secondBlock = { ...block, id: 'b2', start: '11:15', end: '12:00' };
      const task = { id: '1:a', courseId: '1', title: 'Quan hệ QA', objective: 'Vận dụng',
        deadline: '2026-10-10', dueAt: '2026-10-10T12:00:00+07:00', estimateMin: 120, loggedMin: 0, status: 'todo', priority: 'high' };
      let workspace = { plan: { id: 'p1', weekStart: '2026-10-05', blocks: [block, secondBlock], version: 1, savedAt: '2026-10-10T00:00:00Z' },
        studyPreferences: { sessionMinutes: 60, breakMinutes: 10 }, routineProfile: null };
      let version = 1;
      let timer = null;
      let confirmations = 0;
      const events = [];
      await context.route('**/api/v1/workspace', async (route) => {
        if (route.request().method() === 'PUT') {
          const request = route.request().postDataJSON(); assert.equal(request.expectedVersion, version);
          workspace = request.state; version++;
        }
        await route.fulfill({ json: { state: workspace, version, updatedAt: '2026-10-10T08:00:00+07:00' } });
      });
      await context.route('**/api/v1/lms/sync', (route) => route.fulfill({ json: {
        courses: [{ id: '1', code: 'TRR', name: 'Toán rời rạc', tone: 'primary' }, { id: '2', code: 'CS', name: 'Lập trình', tone: 'primary' }], tasks: [task],
        courseData: {}, assessments: [], guidance: [],
      } }));
      await context.route('**/api/v1/chat', (route) => route.fulfill({ json: { output: { do_session: {
        action: 'prepare', status: 'ready', block_id: 'b1', task_id: '1:a', title: task.title,
        objective: task.objective, planned_minutes: 60, recommended_resources: [], opening_prompt: 'Mục tiêu QA',
      } }, response: 'Ready' } }));
      await context.route('**/api/v1/study-sessions**', async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.endsWith('/rhythm/proposal') && confirmations) return route.fulfill({ json: {
          status: 'insufficient_evidence', excludedCount: 2, proposal: null,
          comparison: { status: 'collecting', before: { sessions: 3, completionRate: 1, longSessionRate: 1, assistedAssessmentRate: 1,
              assessment: { application: { testedSessions: 3, passRate: 0 } } },
            after: { sessions: 1, completionRate: 1, longSessionRate: 0, assistedAssessmentRate: 0, assessment: {} } },
        } });
        if (url.pathname.endsWith('/rhythm/proposal')) return route.fulfill({ json: {
          status: 'trial_proposed', excludedCount: 2, current: { sessionMinutes: 60, breakMinutes: 10 },
          proposal: { id: 'fixture-proposal', courseId: 1, activityType: 'concept', preferences: { sessionMinutes: 45, breakMinutes: 10 },
            sourceRefs: ['do:s1', 'do:s2', 'do:s3'], assessmentEvidenceIds: [], requiresConfirmation: true },
        } });
        if (url.pathname.endsWith('/rhythm/confirm')) { confirmations++; return route.fulfill({ json: {
          preferences: { sessionMinutes: 45, breakMinutes: 10 }, scope: { courseId: 1, activityType: 'concept' }, planChanged: false,
        } }); }
        if (url.pathname.endsWith('/current')) return route.fulfill({ json: {
          session: url.searchParams.get('blockId') === 'b1' ? timer : null,
          activeSession: timer && ['running', 'paused'].includes(timer.status) ? timer : null,
        } });
        if (url.pathname.endsWith('/study-sessions')) {
          timer ??= { id: 'SS-fixture', courseId: '1', taskId: '1:a', blockId: 'b1', version: 1, status: 'running',
            observed_seconds: 180, checkpoint_at: '2026-10-10T01:00:00Z', date: '2026-10-10', planned_minutes: 60,
            interruption_reason: 'none', unobserved_gap: false, length_feeling: 'not_reported', heartbeatSeconds: 20 };
          return route.fulfill({ json: timer });
        }
        const command = route.request().postDataJSON(); events.push(command);
        assert.equal(command.expectedVersion, timer.version);
        timer = { ...timer, version: timer.version + 1,
          status: command.action === 'resume' || command.action === 'checkpoint' ? 'running' : command.action === 'complete' ? 'completed' : 'paused',
          interruption_reason: command.interruptionReason ?? (command.action === 'recover' ? 'unknown' : timer.interruption_reason),
          unobserved_gap: timer.unobserved_gap || command.action === 'recover',
          length_feeling: command.lengthFeeling ?? timer.length_feeling };
        if (command.action === 'complete') timer.evaluation = { action: 'complete', status: 'on_track', block_id: 'b1', task_id: '1:a',
          planned_minutes: 60, actual_minutes: 3, completion_percent: command.completionPercent, remaining_minutes: 30,
          blocker: command.blocker, blocker_note: command.note, needs_recovery: false, needs_understanding_check: false,
          next_action: 'Giữ lịch; đây không phải kết luận mức hiểu.' };
        await route.fulfill({ json: timer });
      });
      const page = await context.newPage(); page.setDefaultTimeout(10_000);
      await page.clock.setFixedTime(new Date('2026-10-10T08:00:00+07:00'));
      const errors = []; page.on('pageerror', (error) => errors.push(error.message));
      await page.goto(`${base}/app#/study/1%3Aa/session?blockId=b1`);
      await page.getByRole('button', { name: 'Bắt đầu học', exact: true }).click();
      await page.getByRole('button', { name: 'Tạm dừng', exact: true }).waitFor();
      await page.getByLabel('Nguyên nhân gián đoạn', { exact: true }).selectOption('unexpected');
      await page.getByRole('button', { name: 'Tạm dừng', exact: true }).click();
      await page.getByRole('button', { name: 'Tiếp tục', exact: true }).waitFor();
      assert.equal(timer.interruption_reason, 'unexpected');
      results.push({ width, case: 'pause records unexpected interruption', passed: true });
      await page.reload();
      await page.getByRole('button', { name: 'Tiếp tục', exact: true }).waitFor();
      assert.equal(await page.getByRole('timer').innerText(), '00:03:00');
      await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
      await page.getByRole('button', { name: 'Tạm dừng', exact: true }).waitFor();
      results.push({ width, case: 'reload restores checkpoint paused without absence', passed: true });
      await page.getByRole('button', { name: 'Hoàn thành', exact: true }).click();
      const review = page.getByRole('dialog', { name: 'Kết thúc phiên tự học' });
      await review.getByLabel('Cảm nhận độ dài phiên').selectOption('too_long');
      await review.getByRole('button', { name: '50%', exact: true }).click();
      await review.getByRole('button', { name: 'Lưu và kết thúc', exact: true }).click();
      await page.getByText('Giữ lịch; đây không phải kết luận mức hiểu.').first().waitFor();
      assert.equal(timer.length_feeling, 'too_long');
      assert.equal(timer.interruption_reason, 'unexpected');
      assert.equal(events.filter((item) => item.action === 'complete').length, 1);
      results.push({ width, case: 'short Reflect records feeling separately from knowledge', passed: true });
      await page.evaluate(() => { window.location.hash = '/study/1%3Aa/session?blockId=b2'; });
      await page.getByRole('button', { name: 'Bắt đầu học', exact: true }).waitFor();
      assert.equal(await page.getByRole('timer').innerText(), '00:00:00');
      assert.equal(await page.getByText('Đã hoàn thành', { exact: true }).count(), 0);
      results.push({ width, case: 'SPA block change clears previous completion and timer', passed: true });
      await page.goto(`${base}/app#/settings`);
      const confirm = page.getByRole('button', { name: 'Xác nhận thử nhịp mới' }); await confirm.waitFor();
      assert.equal(confirmations, 0); assert.equal(workspace.studyPreferences.sessionMinutes, 60);
      await confirm.click();
      await page.waitForFunction(() => document.querySelector('#study-rhythm') !== null);
      await page.waitForTimeout(1000);
      assert.equal(workspace.studyPreferences.sessionMinutes, 60); assert.equal(workspace.plan.id, 'p1');
      assert.deepEqual(workspace.studyPreferences.activityRhythms, [{ courseId: 1, activityType: 'concept', sessionMinutes: 45, breakMinutes: 10 }]);
      results.push({ width, case: 'confirmed trial changes only course/activity preference, not defaults or plan', passed: true });
      await page.getByText('Tiến độ và bằng chứng Assessment trước/sau', { exact: true }).click();
      await page.getByText('Vận dụng: 0% · 3 phiên được kiểm tra', { exact: true }).waitFor();
      assert.equal(await page.getByText('Nhớ sau một thời gian: Chưa kiểm tra', { exact: true }).count(), 2);
      assert.equal(await page.getByText('Hoàn thành ca: 100%', { exact: true }).count(), 2);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      results.push({ width, case: 'before/after distinguishes full completion, failed application and untested retention', passed: true });
      const scoped = page.getByRole('region', { name: 'Nhịp riêng theo môn và hoạt động' });
      await scoped.getByLabel('Môn áp dụng').selectOption('2');
      await scoped.getByLabel('Loại hoạt động').selectOption('coding');
      await scoped.getByLabel('Phiên riêng (phút)').fill('75');
      await scoped.getByLabel('Nghỉ riêng (phút)').fill('5');
      await scoped.getByRole('button', { name: 'Lưu nhịp riêng' }).click();
      await page.waitForTimeout(1000);
      assert.equal(workspace.studyPreferences.activityRhythms.length, 2);
      assert(workspace.studyPreferences.activityRhythms.some((item) => item.courseId === 2 && item.activityType === 'coding' && item.sessionMinutes === 75));
      await page.reload();
      await page.getByLabel('Môn áp dụng').selectOption('2');
      await page.getByLabel('Loại hoạt động').selectOption('coding');
      assert.equal(await page.getByLabel('Phiên riêng (phút)').inputValue(), '75');
      await page.getByLabel('Loại hoạt động').selectOption('concept');
      assert.equal(await page.getByLabel('Phiên riêng (phút)').inputValue(), '60');
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      await page.screenshot({ path: path.join(output, `${width}-settings.png`), fullPage: true });
      results.push({ width, case: 'manual activity preference survives reload without cross-course/type transfer or overflow', passed: true });
      workspace.planDraft = { input: { tasks: [], availability: [], unavailable: [], preferred: 'evening', goal: 'QA' },
        createdAt: '2026-10-10T01:00:00Z', blocks: [block], reasons: [], assumptions: [],
        feasibility: { availableMin: 30, requiredMin: 45, remainingMin: -15, feasible: false, deficitMin: 15,
          shortfalls: [{ taskId: '1:a', missingMin: 15 }] },
        durationAdjustments: Array.from({ length: 11 }, (_, i) => ({ taskId: `fixture-${i}`, studentRemainingMin: 30,
          baselineTargetMin: 30, proposedTargetMin: 45, sourceRefs: ['do:s1'], evidenceCount: 3, requiresConfirmation: true })) };
      workspace.calendarDraft = null;
      await page.goto(`${base}/app#/plan`); await page.reload();
      const summary = page.getByText('Có 11 đề xuất thời lượng — Xem chi tiết'); await summary.waitFor();
      assert.equal(await summary.evaluate((node) => node.closest('details').open), false);
      await page.getByText(/Quan hệ QA còn thiếu 15 phút trước hạn 12:00/).waitFor();
      assert.equal(await page.getByRole('button', { name: 'Áp dụng lịch & thời lượng đề xuất' }).isDisabled(), true);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      assert.equal(errors.length, 0, errors.join('\n'));
      await page.screenshot({ path: path.join(output, `${width}-draft.png`) });
      results.push({ width, case: '11 collapsed proposals, exact shortage, blocked confirmation', passed: true });
      await context.close();
    }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ mode: 'offline synthetic browser fixtures', results }, null, 2));
    console.log(JSON.stringify({ passed: results.length, output }));
  } finally { await browser.close(); }
}
evaluate().catch((error) => { console.error(error); process.exitCode = 1; });
