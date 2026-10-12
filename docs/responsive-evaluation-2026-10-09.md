# PaceWise responsive redesign — 2026-10-09

## Changes

- Shared student/teacher calendar measures its available container with ResizeObserver, including space consumed by navigation/panels. Below 360px: one day; 360–559px: two; 560–839px: three; from 840px: the entire date range. These are **calendar widths**, not device widths.
- A seven-day picker retains access to every date, including Sunday. Parent date/week changes reset the visible window correctly. Resizing only changes presentation, not event dates or durations.
- Task and personal panels dock only when the board has at least 1400px; otherwise accessible dialogs expose the same controls. Removed the rigid 860px minimum and full-height panels stacked above/below the calendar.
- Toolbar groups wrap instead of squeezing controls. The smallest screens retain the full date field; Today becomes an accessible clock button. Teacher course filter gets its own row.
- Tablet teacher navigation uses an icon rail; mobile bottom navigation reserves device safe-area space. Short landscape windows allow page scrolling while maintaining a usable timetable.
- Mobile month cells display event counts, with drill-down to the selected date.
- Dialog bodies scroll independently; titles/actions remain accessible. Mobile form font size prevents common input auto-zoom.
- Mobile theme toggle synchronizes with the desktop toggle. Dark timetable axes, grid lines and event colors use appropriate contrast; brand-button foregrounds stay white.
- Do chat history is a dialog in narrow containers rather than occupying most of the screen. The composer stays above the bottom navigation. Mobile reminder popover is viewport-aligned.

## Verification

| Check | Actual result |
| --- | --- |
| Full frontend regression suite | 239 tests passed across 56 files |
| Production build | Passed; main JS about 360.30 kB, 114.40 kB gzip; no chunk-size warning |
| Browser UI evaluation | 42 checks passed in headless Microsoft Edge with synthetic API fixtures |
| Calendar sizes | 320×740, 390×844, 430×932, 768×1024, 1024×768, 1366×900, 1920×1080, both roles |
| Themes | Light/dark screenshots for both calendars at all seven sizes |
| Phone interactions | Sunday selection; student exact-time dialog; teacher lesson dialog |
| Landscape | 844×390, both roles; calendar remains usable through page scrolling |
| Other pages | Do, Settings, Reflect and five instructor tabs at 320, 768, 1366px |
| Chat | Composer width and bottom-navigation clearance; history open/Escape close |
| Docker | Rebuilt only frontend; `/app` returns HTTP 200 with new responsive CSS |

Artifacts:

- [Frontend JUnit report](../evals/reports/responsive-frontend-2026-10-09.xml)
- [Browser results](../evals/reports/responsive-ui-2026-10-09/results.json)
- [Student phone, light](../evals/reports/responsive-ui-2026-10-09/student-390-light.png)
- [Student phone, dark](../evals/reports/responsive-ui-2026-10-09/student-390-dark.png)
- [Teacher phone](../evals/reports/responsive-ui-2026-10-09/instructor-390-light.png)

## Reproduce

Run the frontend development server on a separate port:

```powershell
cd frontend/pacewise
npm.cmd run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

In another terminal, run `scripts/evaluate_responsive_ui.cjs` from the repository root. It needs Playwright resolvable as `playwright` or via `PLAYWRIGHT_MODULE`, and Microsoft Edge installed. The script intercepts all backend requests with synthetic fixtures; it never logs into a real account, contacts an AI provider, or changes LMS/student records.

```powershell
node scripts/evaluate_responsive_ui.cjs
```

## Limits

This validates browser layout and existing frontend behavior, not LMS authoring correctness, AI quality, real-device iOS/Android behavior, or backend production load. All browser-evaluation APIs are mocked only inside the test browser. Application encryption/authentication configuration was not disabled or changed. No backend/database service was restarted for this UI change.
