# Instructor tab navigation — 09/10/2026

## Fix

The instructor pages previously each owned a `useInstructorData` controller. Route changes unmounted that controller, reset its loading/revalidation lifecycle and could replay an older cache over local review decisions. A root-level Suspense boundary could also hide the navigation shell while a lazy route resolved. The material-index status card discarded its loaded result on every mount.

The instructor layout now owns one `InstructorDataProvider`. Overview, assessment design and review queue consume its shared status and refresh action instead of starting page-owned requests. Initial data loading is distinct from background refresh; even a loaded empty cohort remains visible during refresh. The controller lives across tab changes, including when session storage is disabled.

- LMS revision changes, explicit refresh, reconnect/visibility and a visible-page 60-second safety poll revalidate data without replacing it with a full-page loader.
- User/course-scoped cache restoration occurs on scope changes, not every tab mount. Late responses from another course are ignored. Forbidden/unauthenticated responses clear cached instructor data.
- Route Suspense is bounded inside the content outlet, keeping sidebar/navigation usable while a route chunk loads. Instructor route preload failures are caught and may be retried.
- LMS material status uses an authenticated-layout-lifetime cache keyed by user and course. A fresh result (15 seconds) displays immediately on return. Stale results display while revalidating. The cache is discarded with the layout on logout; another course's files are not displayed while loading.

## Executed checks

- **224 frontend tests passed / 55 files**, including the added navigation, material status and controller regression cases: [JUnit](../evals/reports/instructor-navigation-performance-2026-10-09.xml).
- TypeScript typecheck passed. Production build passed: 118 modules, main JS 355.59 kB / 112.94 kB gzip.
- Docker frontend rebuilt/recreated without changing backend or database services.
- `git diff --check` passed.

Specific regression assertions:

1. Switching overview → review → assessment consumers under one mounted provider makes **one** overview request, with no cache replay on tab switches, even with storage writes blocked.
2. Manual refresh keeps a previously loaded empty cohort visible (`loading=false`, `refreshing=true`).
3. An LMS revision refresh does not dispatch the old cached snapshot over local decisions; only the newly returned snapshot is applied.
4. A deliberately unresolved lazy route keeps the sidebar and logout control visible; the whole-app fallback does not replace the shell.
5. Returning to the material card within 15 seconds shows the prior result immediately and makes no second status request.
6. Returning with stale material data keeps the prior result visible until the new response arrives.
7. A course change does not show the prior course's PDF while waiting for the new result.
8. Existing tests still cover revoked access, scope-switch races, refresh failures/retry, instructor navigation, schedule display and logout.

## Boundaries

Cold login, an uncached course and a full browser reload still need authenticated server data. This fix removes redundant **tab-navigation** loading; it does not fabricate data or promise zero first-load network latency. Tests above are component/request-behavior checks, not a real-device p95 navigation benchmark or a 1,000-user load test. No backend implementation changed in this fix.
