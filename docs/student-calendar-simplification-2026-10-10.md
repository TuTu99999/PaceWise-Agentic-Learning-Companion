# Student calendar simplification — 10/10/2026

## Scope

- Removed the toolbar “Thêm vào lịch” icon, its three-action menu, and the unused `PlanEntryModal` form. Existing task/personal panels remain the single entry points.
- Removed the LMS task panel's “Ưu tiên cá nhân” dropdown. New plan/weekly-goal requests no longer send that preference.
- The deterministic scheduler ignores legacy personal-priority values when creating new drafts. Compatibility fields remain readable; no stored plan, task or calendar data was deleted or automatically rewritten.
- Restored the existing mobile panel buttons previously hidden by the now-obsolete add-menu CSS. Kept calendar drag/move/resize, exact-minute editing, draft persistence, deadline checks and confirmed Do access.

## Verification

- Backend: **659 passed**, [JUnit](../evals/reports/calendar-simplify-backend-2026-10-10.xml).
- Targeted calendar UI: **21 passed**.
- Full frontend regression: **306 passed** across 68 files, [JUnit](../evals/reports/calendar-simplify-frontend-2026-10-10.xml). The old weekly-goal payload assertion was updated to require absence of `personal_priority` while retaining the LMS group weight.
- Browser workflow: **12 passed**, [results](../evals/reports/student-calendar-2026-10-10/results.json). Covers removed menu/priority, task panel access, durable drafts, exact deadlines, hidden-event conflicts and unaffected confirmed Do sessions at 390×844 and 662×432.
- Calendar responsive: **19 passed**, [results](../evals/reports/calendar-simplify-responsive-2026-10-10/results.json). Student/teacher calendars at 320–1920px, light/dark screenshots, scrolling to the final hour, navigation, mobile dialogs and low-height layout.
- Production build passed. Local backend/frontend images rebuilt and recreated; both healthy, `/health` and `/app` return HTTP 200. No database reset.

## Limits / follow-up

Browser checks use synthetic accounts and mocked API responses, not real learner data or Google/LLM calls. The broader all-page responsive script stopped on horizontal overflow on student Settings at 320px; this is outside the calendar-menu change and is not counted as a passing all-page check. Calendar-only evaluation is explicitly scoped with `CALENDAR_ONLY=true` and leaves default all-page evaluation unchanged.
