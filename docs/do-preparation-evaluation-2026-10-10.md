# Do preparation and focused session UI — 2026-10-10

Status: implemented and locally verified. This is an integration/behavior
evaluation, not evidence of improved learning outcomes or 1,000-user capacity.

## Implemented contract

`POST /api/v1/study-sessions/prepare` accepts only `courseId` and `blockId`.
The backend reads a server-confirmed block, validates student enrollment and the
current assignment/deadline, then reads that course's assignments, modules and
authorized file manifest. Database connections are released before LMS awaits.
No LLM or embedding call is needed to list materials; the tested path makes four
LMS metadata calls including enrollment validation.

Assignment/module membership determines scope before ranking. Slides precede
requirements/rubric/practice; videos supplement rather than fill every slot.
Sources are deduplicated by ID, content hash and canonical URL. Missing membership
returns `unmapped`, not materials guessed from similar titles in another chapter.
Do chat uses the same loader and allowlist for both vector retrieval and inline
sources. Previous graph citations are cleared; client-supplied scope is ignored.

The frontend keys preparation by learner, course, block and material revision.
Concurrent requests are shared; obsolete requests are aborted and late responses
ignored. An unchanged LMS sync does not refetch. Refresh retains the current card;
an unsuccessful permission refresh clears old sources and exposes retry. Completed
results are not cached across revisits: LMS rights must be validated again.

The main Do view shows the confirmed milestone and this block's duration. Whole
assignment description, deadline and estimate provenance are collapsed under task
details. The points × 12-minute demo estimate remains an explicit assumption, not
an AI-personalized estimate. Timer explanations and planning rhythm are collapsed;
save/recovery errors remain immediate. Ending the session does not claim the whole
assignment or knowledge has been mastered. Inline requirements/rubric excerpts are
readable through a disclosure, without injecting HTML.

The simulator now seeds explicit demo module membership idempotently and versions
the bundled chapter-3 PDF with its actual checksum. Authenticated downloads check
LMS permissions and directory boundaries. No LMS web needs to be public.

## Verification

| Check | Result |
| --- | --- |
| Backend suite, fresh isolated SQLite database | 696 passed |
| Frontend suite | 337 passed, 72 files |
| LMS simulator suite, isolated database | 88 passed |
| TypeScript + production Vite build | Passed |
| Final targeted prepare/chat/RAG checks | 39 passed |
| Headless Edge, synthetic APIs, 320/390/1366 px | Passed at all three widths |
| Live Docker encrypted API, existing confirmed DS201 block | 30-minute session; slides + assignment requirements + video |
| Live PDF through opaque authenticated PaceWise link | HTTP 200; PDF signature verified |
| Stable resource version across repeated live preparation | Passed |
| Unconfirmed block and logged-out access | Rejected (409 and 401 respectively) |
| Worker index of bundled chapter-3 slide | `indexed`, 12 chunks |

Browser regression verifies: one initial request, zero additional requests after
unchanged LMS sync, visible resources during refresh, removal after permission
failure, working retry, milestone objective, collapsed task details and no
horizontal overflow. Hook tests additionally verify cancellation on block change,
StrictMode request coalescing and independent consumers of the same request.

Live timing was approximately 726 ms for **two** sequential preparations on the
local Docker setup. This is one smoke observation, not a latency benchmark.
Two unrelated legacy slide entries remained unavailable; the bundled DS201 slide
used in the live smoke was indexed. No learner plan/timer/evidence was edited by
the smoke; only demo login/logout and read requests were performed.

## Repeatable checks and limits

- `scripts/evaluate_do_preparation_ui.cjs`: headless Edge, synthetic APIs against
  Vite on port 5174; set `PLAYWRIGHT_MODULE` to the installed Playwright package.
- `scripts/evaluate_do_preparation_live.py`: existing public demo account against
  Docker on port 5173; outputs statuses/counts, not identities or secrets. Requires
  an existing server-confirmed plan. Skips obsolete blocks; never manufactures one.
- Newly authored assignments/materials require explicit LMS module membership.
  Native LMS pages without a linked readable URL are not guessed or fetched by
  this file-focused preparation path.
- This evaluation did not score a live LLM answer, calibrate Assessment confidence,
  run a learner pilot, or benchmark concurrent-user capacity.

Backend, worker and frontend Docker containers were rebuilt/recreated with volumes
preserved. LMS remains an internal API service; its web UI was not enabled.
