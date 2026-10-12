# Chapter PDF upload and processing — 2026-10-10

## Delivered

- Default 50 MB/file, configurable; up to 20 selected files, uploaded sequentially.
- Direct binary upload with an encrypted session-bound ticket/receipt, no base64
  PDF in JSON. The instructor can set a different chapter for each selected file.
- Per-file upload state and persistent queued/processing/ready/failed states.
  Failed uploads can be retried individually without resending successful files.
  Failed extraction/indexing has an authorized current-version retry action.
- A durable bounded queue. Per-course admission counts reserved upload tickets;
  the full queue returns 429 and Retry-After. Default backlog is 100 and worker
  batch is four per stage, sequential within one worker instance.
- Default budgets: 1000 pages, 2000 final citation chunks, four million text
  characters, 120 seconds per extraction/indexing stage. Subprocesses are
  terminated on timeout; extraction subprocesses are also terminated on cancel.
- No DB connection is held across download, extraction or embedding.
- Same bytes in the same chapter reuse the existing resource. Different chapter
  mappings are not merged. Qdrant reuses existing vectors for unchanged content,
  including after process restart.
- Sync does not reset unchanged failed jobs to an unlimited retry loop. Automatic
  retries are bounded; retry requires live instructor permissions, matching file
  version and a 30-second cooldown.

The deployment assumes one chapter per PDF, as requested. No page-range editor
was added. Do/chat continue to use assignment-to-module-to-file links, not a
title-based fallback into unrelated chapters. Scanned PDFs still require OCR.

## Verification

- Full backend suite: **745 passed**, using isolated temporary SQLite stores.
- Full frontend suite: **365 passed**, 78 test files. TypeScript and production
  Docker builds passed.
- Tests cover per-file chapter selection, upload retry isolation, stale course
  UI responses, hash deduplication, separate chapter mappings, queue admission,
  stale-version/role/cooldown rejection, chunk/text limits, and terminating real
  subprocesses on extraction/index timeout and cancellation. Disconnecting during
  upload registration cannot delete the binary of a committed source record.
- Existing PDF lifecycle regression still covers updates, revocation, restoration,
  deletion, authenticated downloads and unchanged embedding reuse using actual
  PDF parsing and deterministic in-memory vector fixtures.
- Real Docker worker parsed a structurally valid **6,292,144-byte PDF**, embedded
  it with the real model, and indexed it in Qdrant. Repeating in a new subprocess
  returned `unchanged`. Its isolated QA vectors were removed afterward; the test
  did not write to any course or learning-history table.

Evidence: [backend JUnit](../evals/reports/pdf-queue-backend-2026-10-10.xml),
[real worker report](../evals/reports/pdf-worker-live-2026-10-10.json).
Real login/logout/Do/browser smoke was also rerun with simulator stopped.

Known infrastructure warning: the installed Qdrant client reports a version
mismatch with the existing server. The real index/reuse/delete smoke passed;
aligning those versions is separate from this upload change. This is not a
1,000-user load benchmark, OCR implementation or Google API test.
