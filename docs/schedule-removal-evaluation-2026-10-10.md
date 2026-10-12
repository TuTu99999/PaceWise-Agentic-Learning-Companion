# Teacher schedule removal — 2026-10-10

## Cause

- Cleanup selected only lessons whose start time was in the future. Past lessons had no individual remove action and cancellation explicitly rejected them.
- Cleanup preview fingerprints represented filters alone. Reusing the filters could return an already-applied batch instead of selecting newly added lessons.

## Behavior

- In **Môn học → Nhập Excel / dọn lịch → Dọn lịch**, select past, future, or all lessons, the owned courses, and optional date boundaries. Blank boundaries mean no additional date restriction; the selected period still applies.
- Bulk and individual removal use a server-owned preview followed by explicit confirmation. Bulk confirmation also requires acknowledgement. Individual actions are available in the course lesson manager, including past and cancelled lessons.
- Removal archives the teaching event kind (`removed_class` / `removed_class_session`) for every linked occurrence copy. Teacher/student calendar reads exclude these records; attendance, dates, linked resources and database rows remain intact. Personal events, tasks, grades, learning evidence and other courses are not deleted.
- History supports undo for removed old lessons. Future restoration checks overlap; stale/expired previews and changed restore targets are rejected. Undo does not overwrite attendance recorded after removal.
- Existing future-only cancellation and Excel `replace_future` semantics remain unchanged. Existing non-removed lesson versions remain compatible with stored restore tickets.
- Cleanup fingerprints now include current course states and selected lesson versions. Confirmation retries remain idempotent, but another cleanup can select newly added lessons or remove restored lessons again.

## Verification

- Full backend suite: **756 passed**, using temporary SQLite databases protected by `tests/conftest.py`.
- Full frontend suite: **370 passed / 78 files**; TypeScript and Docker production build passed.
- Real native PostgreSQL API: individual past removal, bulk removal, repeat filters, retry, attendance preservation and old/future restoration passed inside an outer transaction. Rolled back; original source table row checksums remained unchanged. See `scripts/evaluate_schedule_removal_live.py`.
- Browser: **4 scenarios** (390px and 1366px, light/dark). Individual/bulk removal, acknowledgement, refresh, undo and horizontal layout passed with synthetic API fixtures only. See `evals/reports/schedule-removal-ui-2026-10-10/results.json`.
- Recreated backend, worker and frontend without removing volumes. Live standalone smoke passed for teacher/student login, logout/replay denial, authoring reads, confirmed Do preparation and preserved PDF download while the old simulator remained stopped.

No real teaching lesson, account, plan or learning history was removed during verification. PostgreSQL QA may advance sequences; these are harmless ID gaps, not lost records.

## Follow-up: Python still displayed videos, quizzes and exams

The preceding verification covered teaching lessons, not every event type displayed on the course calendar. Live inspection found 55 removed Python lessons but **28 still-visible calendar entries**: 12 lecture videos, 13 quizzes, two midterms and one final exam. There were no legacy `InstructorAction` schedules involved.

- Removal now covers the explicit course schedule allowlist: `class`, `class_session`, `lecture_video`, `quiz`, `midterm`, `final_exam`. Private/unsupported events and appointments remain outside this cleanup.
- Authoring snapshots expose a separate `calendar_events` list for cleanup. The lesson editor still uses only `lessons`; deleting a quiz calendar entry cannot turn it into an editable class or delete its graded assignment.
- All affected teacher/student copies use reversible `removed_<kind>` markers. Calendar sync filters the complete removed-kind list. Preview versions include the kind for non-lesson events; stale confirmation cannot change a different event type.
- Added bulk/single non-lesson regressions through the native calendar and final `/lms/sync` API, with real seeded task, PDF metadata and scored submission preserved. Undo restores original kinds. Focused backend suite: 28 passed; final removal suite: 13 passed. Frontend: 17 passed; TypeScript/build passed.
- PostgreSQL rollback QA and live standalone login/logout/Do/PDF smoke passed after Docker recreation.
- At the user's request to finish their already-confirmed all-period Python cleanup, **the remaining 28 entries (56 calendar copies) were removed via a fresh server preview/confirm**, after checking exact course, IDs, previous confirmation and untouched date filters. No hard deletion occurred; undo is available in history.
- Final database/calendar inspection: zero active Python course calendar entries across affected users. Checksums for courses, assignments, submissions, resources and course content were unchanged by this cleanup. Assignment deadlines and students' confirmed self-study plans are deliberately retained.
- Headless Edge against the actual Docker frontend: selecting Python shows zero events, stays empty after reload, no page errors, logout succeeds. No mocked calendar responses were used for this final UI check.
