# Calendar scrolling and instructor profile regression — 2026-10-10

## Fixes

- Short windows previously nested a fixed 440px calendar inside an outer scrolling page. Its inner scroll could reach the bottom while final hours remained outside the visible page. Short windows now use one outer scroll surface, with a naturally sized timetable and sticky day header. Normal-height screens retain an independently scrolling timeline.
- Touch swipes are reserved for native scrolling, including on personal activities. Mouse/pen resize remains available; touch users edit exact times using the existing event dialog.
- The running backend image lacked `LMSClient.teacher_request`, although the frontend already called the instructor profile endpoint. Backend and LMS images were rebuilt, without removing database volumes. A subsequent read through the live backend/LMS service returned the expected `name`, `email`, `details`, and `version` fields; no profile values or secrets were printed.
- Profile reload after a save conflict now adopts the latest server revision instead of retaining the dirty draft. Inputs are locked while loading/saving. Late responses after navigation cannot repopulate the private profile cache.

## Evidence

| Check | Actual result |
| --- | --- |
| Calendar component + profile UI regression | 18 tests passed |
| Full frontend regression | 250 tests passed across 58 files |
| PaceWise profile API: session-derived identity, spoofed actor rejection, student denial | 6 tests passed |
| LMS profile: read/save/re-read, stale revision, recovery, invalid fields, service key/enrollment | 6 tests passed |
| Native wheel, keyboard End, and CDP touch swipe | 6 cases passed: student/instructor at 390×844, 662×432, 844×390 |
| Last hour visible above bottom navigation in short windows | Passed in the short-window cases; not just a positive `scrollTop` check |
| General responsive regression | 43 checks passed using synthetic API fixtures in headless Edge |
| Production frontend build | Passed inside Docker |
| Live backend → LMS profile read | Expected response schema received |

Browser fixtures test layout and gestures without accessing real student data. CDP touch input is emulated, not a physical-phone test. Profile writes were tested against isolated SQLite databases, not against a user's live profile.

## Reproduce

- Frontend: `npm test -- src/pages/instructor/InstructorProfilePage.test.tsx src/components/domain/PlanCalendarBoard.test.tsx`.
- PaceWise API: `python -m pytest tests/test_api/test_instructor_profile.py -q`, using a separate test `DATABASE_URL` and `PRIVATE_API_REQUIRED=false`.
- LMS: from `lms-simulator`, run `python -m pytest tests/test_teacher_profile.py -q`.
- Browser: start Vite on port 5174, set `PLAYWRIGHT_MODULE` to the installed Playwright module, then run `node scripts/evaluate_calendar_scroll.cjs` and `node scripts/evaluate_responsive_ui.cjs`.
