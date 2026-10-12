# Student calendar editing — evaluation 2026-10-10

## Implemented behavior

- The calendar opens on today's date in GMT+7. On small screens the readable day window follows that date; initial scrolling targets an upcoming learning activity, or the current hour if none is available. Overnight/sleep events remain accessible by scrolling upward. Data updates in the same visible date window do not repeatedly reset the user's scroll position.
- Mobile actions are grouped under `+`: add a self-study session, personal/preferred study time, or inspect tasks. Display controls support all/per-course filtering, personal-calendar visibility, and week/month/next-seven-day views.
- The legend explains LMS events, preferred study availability, scheduled self-study sessions, and drafts. Preferred windows are explicitly not sessions that launch Do. User-facing terminology is `Ca tự học`.
- Dragging, resizing, adding, deleting, and exact-minute edits update `calendarDraft` in the authenticated workspace. They do not mutate the confirmed `plan`. A new AI proposal supersedes the raw draft; explicit confirmation applies the proposal.
- Draft saves show pending/saved/error states, serialize concurrent writes, retain newer edits, and support retry after network failure. Reload while a draft is unsaved raises the browser's standard confirmation. Users should wait for `Đã lưu nháp` before reloading; confirmed reload during an outage can still discard unsaved in-memory edits.
- Exact `dueAt` is checked in GMT+7/UTC before accepting an edit. Only genuinely date-only deadlines use an end-of-day fallback. Validation includes hidden events and candidate dates outside the currently displayed week.

## Per-session Do policy

An unrelated draft change does not invalidate every confirmed session. A session is usable if its task/time/milestone still match the confirmed plan, its task remains active, it does not exceed the current deadline, and it does not conflict with current hard constraints. Preferred self-study availability is not a hard conflict.

A moved/new session needs analysis and confirmation. Historical/tentative sessions are not eligible. Existing demo behavior allowing confirmed future sessions to open early is preserved; expired sessions are not reopened automatically. The direct Do route also rechecks current deadline/constraint eligibility, without preventing an already-running session from finishing.

## Executed checks

| Check | Actual result |
| --- | --- |
| Complete frontend suite | 276 passed, 63 files |
| TypeScript + production build | Passed locally and in Docker |
| Backend LMS/workspace integration suite | 14 passed, isolated SQLite test database |
| Browser editing workflow | 12 passed: 6 cases each at 390×844 and 662×432 |
| Native browser wheel/touch regression | 6 passed across student/teacher at 390×844, 662×432, 844×390 |
| Broader responsive regression | 43 passed |

The browser editing checks executed real UI actions against synthetic HTTP fixtures: initial today/hour positioning, exact-minute edit followed by reload, unchanged applied plan, deadline rejection, unchanged session retaining Do access, hidden busy-event conflict rejection, and add-menu/layout checks. No real learner record or LLM/provider call was used.

Autosave regression tests cover React StrictMode, an edit arriving during an in-flight save, premature-reload warnings, and explicit retry after failure. The StrictMode check exposed and fixed a mounted-state flag that prevented persistence status from updating in development.

## Evidence and reproduction

- [Frontend JUnit](../evals/reports/student-calendar-frontend-2026-10-10.xml)
- [Backend JUnit](../evals/reports/student-calendar-backend-2026-10-10.xml)
- [Browser workflow results](../evals/reports/student-calendar-2026-10-10/results.json)
- [Phone screenshot](../evals/reports/student-calendar-2026-10-10/390-844.png)
- Browser scripts: `scripts/evaluate_student_calendar.cjs`, `scripts/evaluate_calendar_scroll.cjs`, `scripts/evaluate_responsive_ui.cjs`. They require Playwright and the test Vite server on port 5174; optional `PLAYWRIGHT_MODULE` and `RESPONSIVE_BASE_URL` override those locations.

Docker backend/frontend were rebuilt and recreated for the local demo. This validates technical behavior with controlled fixtures, not physical-phone compatibility across every device or educational outcomes with real learners.
