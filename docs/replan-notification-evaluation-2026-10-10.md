# Plan notification hand-off evaluation — 2026-10-10

## Behavior

- LMS changes, missed study blocks and imminent deadlines link to Plan, not the separate Recover option-selection page. The action is labelled “Xem cập nhật lịch”.
- Opening the notification automatically requests a Plan draft after workspace hydration. It does not require an additional analysis button or goal-selection dialog.
- Reanalysis includes open tasks in the normal rolling horizon, including newly added assignments. Affected future learner placements can move; elapsed history remains pinned.
- Matching, still-current drafts are reused. StrictMode and duplicate hand-offs must not produce duplicate analysis calls.
- The applied schedule remains unchanged until student confirmation. Only matching, fully feasible confirmation retires the handled LMS warnings; partial confirmation retains unresolved warnings.
- Deadline changes are compared to the exact timestamp, including earlier deadlines on the same day.
- Compact notification popovers close on navigation so they cannot cover the confirmation action.

This is automatic analysis **when opening a notification**, not a background re-plan worker or automatic schedule application. Legacy Recover routes remain available outside these hand-offs.

## Evidence

- Backend suite: 698 tests passed.
- Frontend suite: 346 tests passed; production build passed.
- After the final popover fix: ReminderCenter and StudySessionPage regression tests passed (9 tests).
- `scripts/evaluate_replan_notification_ui.cjs`: headless Edge at widths 390 and 1366, using synthetic API fixtures. Both verified one automatic Plan analysis, no Recover calls, inclusion of the new task, preservation of the applied schedule before confirmation, persistence of the confirmed replacement, and retirement of the resolved warning.
- The browser check waits for the workspace save response rather than assuming a delay shorter than the store's 750 ms debounce is sufficient.

The browser regression does not call a live LLM provider or mutate real learner plans. These results do not establish educational effectiveness, production-scale capacity, or live-provider grading quality.

## Follow-up: selected calendar block covering notifications

The browser regression was extended to select a 16:00–16:30 study block, close its details dialog and open the reminder popover. Before the fix, `elementFromPoint` at the overlap returned the calendar block rather than the popover. The selected block's `z-50` escaped the calendar and outranked the toolbar's `z-30` stacking context.

The shared calendar frame now has its own isolated stacking context. Selection, hover and focus stay within that frame; body-portalled dialogs are unaffected. The same overlap test passed at widths 390 and 1366 in both light and dark themes, along with the existing notification → Plan → confirmation checks.

Additional verification: 34 targeted frontend tests and production build passed; all 12 wheel/touch scroll cases passed across student/instructor roles and six viewport sizes. Deployment configuration tests passed (5), including the new contract that `/app` and `/index.html` serve `Cache-Control: no-store` without dropping the Referrer-Policy header. This avoids caching the HTML entry point across deployments; already-open tabs still require a reload to execute a new bundle.
