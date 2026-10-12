# Standalone PaceWise verification — 2026-10-10

## Result

PaceWise now owns accounts and course records in the `course_source` schema of
its existing PostgreSQL database. Both simulator API and simulator PostgreSQL
are stopped. The main backend is attached only to `pacewise_default`.
The original accounts/passwords continue to work; no separate LMS website,
source database service or network bridge is needed.

## Data preservation

- Imported all 66 source tables / 15,099 rows. Every table's canonical row hash
  matches the original snapshot, including after final live verification.
- Preserved original identifiers, password hashes, enrollment/access records
  and source sequence high-water marks. Repeating an identical import is a
  verified no-op; a different populated destination is rejected.
- At cutover, all 33 existing PaceWise tables / 31,169 rows matched their
  pre-cutover checksums. Plans, study history and existing stores were not reset.
- Copied four uploaded files and one bundled file with matching SHA256 hashes.
- Private backups and original stopped volumes remain available. They contain
  personal data and credential hashes and must not be committed or published.

## Checks performed

| Check | Result |
| --- | --- |
| Full isolated backend suite | 735 passed |
| Frontend suite | 361 passed across 77 files |
| Frontend TypeScript / production builds | Passed |
| Lint for native source, upload, migration QA and changed tests | Passed |
| Original student/instructor login and workspace | Passed with simulator API and DB stopped |
| Logout revocation and replay of old cookie | Denied after logout, both roles |
| Live student accessing instructor functions | Denied |
| Confirmed Do preparation | Nine existing blocks prepared successfully |
| Original PDF download | Passed |
| Teacher course, recurring lessons, tasks, weights, chapter materials, profile | Passed on real PostgreSQL inside a rolled-back outer transaction |
| Real browser, student mobile / teacher desktop | Passed; zero legacy requests and zero page errors |
| Concurrent login/logout smoke | 20 clients passed; not evidence of 1,000-user capacity |

Do timing/completion, chapter isolation, upload ticket replay, invalid PDF cleanup,
ownership enforcement and migration rejection/idempotency also have native
in-process regression coverage with outbound HTTP forbidden.

The PDF UI now supports up to 20 selected files and 50 MB per file by default.
Native upload streams original bytes using a session-bound, single-use opaque
ticket; extraction/indexing remains asynchronous. Student access remains checked.

## QA fixture incident and recovery

A final local test invocation accidentally loaded the deployment `.env` database.
Some existing fixtures cleared/recreated rows instead of using an isolated store.
This was detected, writers were stopped, and a separate private snapshot of the
affected state was saved before repair.

Twelve affected tables were transactionally reconciled to the pre-cutover
snapshot. Their full row checksums matched the baseline before commit; all other
tables were unchanged by repair. Source data remained at its original checksum.
The recovery snapshot is retained, and the counts-only recovery report is linked
below. Subsequent live/browser checks were rerun successfully after recovery.

`tests/conftest.py` now unconditionally selects a fresh temporary SQLite database
before importing the application and disables LangSmith for tests. Deployment
database settings can no longer select the test fixtures' target. The full
735-test suite passed on that isolated store.

## Evidence

- [Live API checks](../evals/reports/standalone-live-2026-10-10.json)
- [Browser checks](../evals/reports/standalone-browser-2026-10-10/results.json)
- [Concurrent authentication smoke](../evals/reports/standalone-auth-pool-2026-10-10.json)
- [Backend JUnit report](../evals/reports/standalone-backend-2026-10-10.xml)
- [Recovery verification](../evals/reports/standalone-qa-recovery-2026-10-10.json)
- [Runtime, migration and production restore instructions](pacewise-standalone-migration.md)

## Boundaries

This validates standalone local Docker operation, not an AWS deployment, LLM
grading quality or 1,000 simultaneous learners. Existing Google and LangSmith
configuration was preserved; no new Google OAuth grant was performed here.
Image-only PDFs still need OCR. Long multi-chapter books need accurate chapter
mapping or splitting; uploading a book under one chapter does not create
page-level chapter isolation automatically. Production requires HTTPS, restricted
service ports and protected restoration of both database schemas, course files,
vector data and existing encryption/signing keys.
