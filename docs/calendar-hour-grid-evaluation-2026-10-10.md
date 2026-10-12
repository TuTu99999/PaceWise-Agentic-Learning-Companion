# Large hourly grid — 2026-10-10

## Compact-size revision after user feedback

Current hour height is **80px**, reduced from the original 120px by one third. Each positive-duration event still scales exactly by `80 / 60` pixels per minute; a 66-minute session is now 88px high. Compact entries use reduced vertical padding to keep their time label readable without inflating their duration. Half-hour dividers remain removed.

The revision passed 26 targeted geometry/component tests, native cross-date mouse dragging (10:26–11:32, unchanged 66-minute duration), and all six wheel/touch cases. Frontend Docker was rebuilt. The 120px values and full-suite results below record the initial revision, not a new complete suite at 80px.

## Initial 120px revision

- One hour is one 120px cell. The former half-hour dashed divider is removed.
- Rendering, initial focus, dragging and resizing share the same scale: one minute equals two CSS pixels. Drag/resize rounding is one minute, not five/thirty minutes. Moving an event preserves its duration and grabbed position.
- Positive-duration events retain their exact height when selected. Examples: 15 minutes = 30px; 19:07–20:13 = 132px; 21:03–21:10 = 14px. Only invalid legacy zero-duration events retain a readable placeholder rather than pretending to occupy fifteen minutes.
- The shared student/teacher grid changes visually; teacher read-only behavior and deadline/conflict validation are unchanged.

## Executed validation

- Full frontend suite: **289 passed, 64 files**; [JUnit](../evals/reports/calendar-hour-grid-frontend-2026-10-10.xml).
- Geometry tests round-trip every minute of the 24-hour grid, check short/long durations, a hidden morning range, scrolled coordinates and grabbed offsets.
- Real HTML5 mouse drag: 10:07–11:13 moved across dates to **10:26–11:32**, retaining 66 minutes, a 17-minute grabbed offset and the unchanged confirmed plan. Reproduce with `scripts/evaluate_calendar_drag.cjs`.
- Browser draft/deadline/filter/Do regression: **12 passed**, synthetic fixtures.
- Native wheel/touch regression: **6 passed**, student/teacher at 390×844, 662×432, 844×390.
- TypeScript/production build passed locally and in Docker. Local frontend image rebuilt/recreated on port 5173.

All browser cases use synthetic data. Native mouse dragging is verified in headless Edge; touch cases verify scrolling, not universal mobile HTML5 drag support. Exact-time dialogs remain available on touch devices.
