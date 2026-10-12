# PaceWise standalone demo

The default `docker-compose.yml` now runs PaceWise without any LMS service,
external LMS network, web UI, or source database. Accounts and course records
live in the `course_source` schema of the existing PaceWise PostgreSQL database.
Plans, learner evidence, timer history, Google connections, traces and Qdrant
remain in their existing stores. IDs and PBKDF2 password hashes are preserved.

## Runtime boundary

- `src/course_source` owns the migrated course domain.
- Compatibility-shaped calls in `LMSClient` use an in-process ASGI adapter in
  `COURSE_SOURCE_MODE=standalone`. It performs no outgoing HTTP request.
- The internal app is not mounted, has no listening port or public documentation.
  Public facades still enforce session/CSRF, instructor role and live enrollment.
- Login is native `/api/v1/auth/login`. The old login path is an API alias only.
  Launch and browser bridge are disabled in standalone mode. Logout revokes the
  PaceWise session immediately, with no remote LMS request.
- Worker projects native course change events and processes derived learning
  resources; it does not seed or normalize migrated source records on restart.

## Cutover procedure

1. Build and test new images before interrupting the running demo.
2. Stop frontend, backend and worker, then stop simulator. Keep both PostgreSQL
   services running during the read-only snapshot and transactional import.
3. Create private PostgreSQL custom-format backups of BOTH databases and copy
   the source uploads and bundled mock files, including personal attachments.
4. Run `src/course_source/migration.py --export <private snapshot.jsonl.gz>` in
   the old DB environment. It reflects every source table under a repeatable-read
   snapshot. Snapshots contain personal data and credential hashes: never commit,
   publish, attach to chat, or place in frontend assets.
5. Run `python -m src.course_source.migration --import-snapshot <snapshot>` in
   the new backend environment. It checks all 66 tables/columns, copies rows in
   foreign-key order, verifies row counts AND canonical row hashes in the same
   transaction, then preserves source serial sequence high-water marks.
6. Empty destination is required. An exact second import is a verified no-op;
   a differing populated destination is rejected, never truncated/overwritten.
7. Start PaceWise alone, smoke-test BOTH roles, authoring, file ACLs, confirmed
   Do preparation/timer and local event projection. Check main-history inventory.
8. Stop the old source PostgreSQL after verification. Do not delete old volumes
   or uploaded files. The simulator directory is parked legacy/rollback code,
   not part of the PaceWise runtime image.

## Running after cutover

```powershell
docker compose up -d --build
```

Open `http://localhost:5173/app`. No `lms-simulator/docker-compose.yml`, external
network creation or Canvas account launch is needed. The original accounts and
passwords still work. Frontend and backend source mode must match.

For production, move the existing PaceWise DB with a protected backup/restore,
the `data/course-source` files and persistent signing/encryption keys. Reuse
those keys to preserve Google tokens and protected sessions. Do not restore
only the `public` schema: `course_source` is also required. Configure HTTPS and
restrict database/vector/monitoring ports; never publish the snapshot directory.

## PDF policy

Native upload accepts PDFs up to `COURSE_PDF_MAX_MB` (default 50 MB/file). UI
accepts up to 20 files in one selection, uploading sequentially. An encrypted
metadata request issues a session-bound, opaque, one-time binary upload ticket.
The browser sends the original file directly, not base64 inside JSON. The server
streams to owned storage, checks size/signature, rechecks live ownership, maps
the selected chapter and emits the index job. No DB connection is held during
the upload. Failed transfers remove only their new partial file.

Extraction is asynchronous/bounded by the existing worker. PDF page budget is
`COURSE_PDF_MAX_PAGES` (default 1000). Encrypted, corrupt or image-only PDFs may
fail extraction; scanned PDFs still need OCR, not implemented by this migration.
Each file has a durable queued/extracting/indexing/ready/failed state. The worker
claims a bounded batch (default four per stage) and releases DB connections
before extraction/embedding. Each stage runs in a disposable subprocess with a
hard default 120-second deadline, including model loading for embedding.
`COURSE_FILE_MAX_CHUNKS=2000` and `COURSE_FILE_MAX_TEXT_CHARS=4000000` bound derived
content; `COURSE_FILE_QUEUE_LIMIT=100` caps each course backlog, including reserved
upload tickets. Admission returns 429 with Retry-After when full.

Unchanged failed files are not endlessly retried by sync. Transient failures
have a three-attempt budget; instructors can explicitly retry a failed current
version (30-second cooldown and live permissions/version check). Restarted
workers recover expired extraction/index leases. Reuploading identical bytes
in the same chapter reuses the existing resource and discards only the redundant
new upload; different chapters retain distinct mappings. Existing vector IDs
are checked in Qdrant so unchanged content does not invoke embedding again,
even across subprocess restarts.
Multi-chapter books must be split or mapped accurately; tagging the whole book
as one chapter does not provide page-level chapter isolation.

## Rollback warning

Old volumes are preserved, but after cutover the old DB is a frozen historical
copy. Do NOT point PaceWise back to it casually: new standalone writes would be
missing. Controlled rollback requires downtime and reconciliation/restore.
The migration never deletes existing plans, learning history, original accounts
or simulator data.
