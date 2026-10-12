# Teacher course management — single-web demo

## Delivered behavior

PaceWise is the only browser UI needed. The existing simulator API and PostgreSQL remain internal; accounts, uploads and existing learning history were not migrated or reset.

- Teacher navigation has one **Môn học** page with **Buổi học**, **Nhiệm vụ & trọng số**, and **Học liệu** inside each course. Old course/material routes redirect here.
- Add courses, edit code/name/term, archive and restore. Enrollment of existing students is explicit and limited to the teacher's own roster. Only an unused course with no students/content/PaceWise learning history can be deleted. Keep at least one active course for the current demo authentication model.
- Lessons initially show ongoing/upcoming events. Past and cancelled events have separate filters. Weekly recurrence supports 1–16 occurrences. Edit/cancel a single future lesson or preview and confirm changes to the remaining future occurrences of its explicit series. Past occurrences and other series are preserved.
- Tasks support assignments, graded quizzes, midterm/final exams, precise deadlines, maximum points, draft/published states and chapter mapping. Assessment-group weights must total 100%. An empty quiz cannot be published.
- Materials support PDF upload and text guides with explicit chapter mapping. Do preparation can use an authorized, published page only in the task's mapped module; missing mapping does not trigger a cross-chapter fallback.
- A current-date demo scenario is previewed and explicitly confirmed; opening the page does not seed/reset data. Existing students must be selected when creating a course if they should see it.

## XLSX import and safe calendar cleanup

The download button provides `frontend/pacewise/public/templates/pacewise-schedule-template.xlsx`. The artifact-tool builder, renders and inspected workbook are under `outputs/teacher-course-management-20261010/`. All three sheets were rendered and checked; the exported workbook round-trips through the real parser. Dates/codes in the sample must be adjusted to the target course and test date.

| Sheet | Columns |
| --- | --- |
| Lessons | course_code, title, date, start_time, end_time, repeat_count, mode, location, meeting_url |
| Tasks | course_code, title, kind, deadline, points, published, chapter |
| Weights (optional) | course_code, group_name, weight |

- XLSX only; at most 5 MB and 500 input rows. No macros, workbook external links, formulas, unrecognized headers or implicit creation of unknown courses. Naive spreadsheet dates are interpreted in GMT+7. Parsing runs off the backend event loop and uses no LLM.
- Append or replace future lessons. Replacement only cancels lessons in courses containing lesson rows; a task-only sheet cannot remove classes. Existing tasks/materials are not deleted. Preview shows each change and all validation errors before confirmation.
- Cleanup supports one/all owned active courses and an optional date range. Only future lessons are cancelled, including enrollment copies. Past history, tasks, submissions and evidence remain.
- Confirm rechecks ownership, snapshot versions, deadlines/time, conflicts and scope. A changed/expired preview must be regenerated. Changes are one transaction; injected mid-import failure rolls back both cancellations and creations. Repeated confirmation or an already-applied identical workbook does not duplicate data.
- Cancellation history supports restore. This restores cancelled lessons only, not a full undo of imported data; conflicts, modifications and elapsed lesson times can block restoration.
- Course writes emit source change events and refresh membership without re-login. Student plans are not silently applied. A failed refresh after a successful write is shown as “saved; reload data”, not an invitation to create the course again.

## Startup data protection

The previous startup seeder could enroll synthetic evaluation students and generate submissions for any new course/assignment. Fixture selection is now centralized in `app/demo_seed_policy.py`: only known, untouched demo courses are eligible. Teacher writes mark the course lifecycle as managed; older teacher-task/lesson records also exclude that course. Restart does not add fake members, tasks or submissions to teacher-managed courses. No previously stored fixture/history was deleted.

## Verification

- PaceWise backend: **725 tests passed**, using an isolated SQLite test database and disabled cloud tracing for tests; `.env` was not changed.
- Simulator: **109 tests passed**; full suite includes course ownership/lifecycle, safe deletion, explicit enrollment, XLSX preview/confirm/idempotency, stale versions, partial-failure rollback, recurring-series scope, currently-running lesson overlap, and startup seed preservation.
- Frontend: **358 tests passed across 76 files**; TypeScript and production builds passed. The series editing test verifies that form submission only previews and a separate confirmation performs the write.
- Browser evaluation: **8 cases passed** (320/390/768/1366 px × light/dark), no page/form horizontal overflow or JavaScript errors; upcoming default, separate history, three course panels and preview/confirmation checked. Fixtures are synthetic, not real accounts.
- Docker backend/worker/frontend and internal LMS API were rebuilt/recreated without deleting volumes. Read-only smoke checks passed for backend-to-internal-API connectivity, three course sections, roster/history routes, student authoring denial, unauthenticated PaceWise access denial, health and the template download.

Reports: `evals/reports/teacher-courses-ui-2026-10-10/results.json`; browser runner: `scripts/evaluate_teacher_courses_ui.cjs`.

These checks cover the demo authoring workflow. They do not establish production concurrency, a complete Canvas replacement, or educational effectiveness in a real student pilot.
