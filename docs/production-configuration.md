# Production configuration contract

## Release gate

From a clean checkout, install the locked dependency sets and run every
blocking check with one command:

```bash
python scripts/release_gate.py --install
```

The gate runs Ruff, backend coverage tests, deterministic AI evaluations, LMS
compatibility tests, frontend tests/typecheck/build, dependency audits, Docker
builds, and Trivy image scans. `--skip-container-scan` is available only for a
local diagnostic when Docker or Trivy is unavailable; CI never skips scans.

## Runtime secrets

PaceWise does not read `.env`, `.env.local`, `.env.test`, `.env.staging`, or
`.env.production` when `APP_ENV=staging` or `APP_ENV=production`. ECS must inject non-secret environment values from
the task definition and secret values from AWS Secrets Manager or SSM Parameter
Store. `.env` is excluded from both Git and the Docker build context.

Required staging and production properties include:

- PostgreSQL plus `DATABASE_SCHEMA_REVISION=20261015_01`;
- standalone PaceWise course source (no LMS simulator dependency);
- S3 course material storage with a KMS key;
- remote Qdrant with no local vector-store fallback;
- explicit HTTPS CORS and Google OAuth URLs;
- secure session cookies, trusted proxy CIDRs, strong session and metrics
  secrets, and the configured model provider key.
- separate SQS ingestion/notification queues, each configured in AWS with its
  own DLQ redrive policy; messages contain opaque job IDs only.

For the shared demo catalog, set both `GOOGLE_SIGNUP_ENABLED=true` and
`GOOGLE_SIGNUP_AUTO_ENROLL_COURSES=true`. A verified Gmail student is then
idempotently enrolled into each active, published standalone course taught by
`GOOGLE_SIGNUP_AUTO_ENROLL_TEACHER_EMAIL` (the demo default is
`teacher1@pacewise.edu.vn`). This
grants access to the course tasks and published PDF/Word resources and creates
the student's copies of teacher-managed class sessions. Course creation,
Excel import, course restoration, Google sign-in, and the live course sync all
reconcile membership, so neither the teacher nor the student accepts an
invitation. Disable the auto-enroll flag before using isolated cohorts or a
multi-tenant catalog.

The ECS task should map Secrets Manager values through the container `secrets`
array, for example:

```json
[
  {"name":"PACEWISE_SESSION_SECRET","valueFrom":"<session-secret-arn>"},
  {"name":"OPENAI_API_KEY","valueFrom":"<model-provider-secret-arn>"},
  {"name":"GOOGLE_CLIENT_SECRET","valueFrom":"<google-client-secret-arn>"},
  {"name":"GOOGLE_TOKEN_ENCRYPTION_KEY","valueFrom":"<google-token-key-arn>"},
  {"name":"METRICS_BEARER_TOKEN","valueFrom":"<metrics-token-arn>"}
]
```

Mount the 64-byte customer data key from a protected secret volume and point
`CUSTOMER_DATA_KEY_FILE` at it. Do not place secret values in task-definition
environment entries.

Run the schema job before the API deployment:

```bash
python -m scripts.migrate_database
```

For existing local/DB-backed files, first run the S3 migration in dry-run mode,
then apply it. Purging PostgreSQL bytes and deleting local files are separate,
explicit operations and happen only after object verification:

```bash
python scripts/migrate_course_materials_to_s3.py
python scripts/migrate_course_materials_to_s3.py --apply
python scripts/migrate_course_materials_to_s3.py --apply --purge-db-bytes --delete-local
```

Deploy order is: Alembic one-shot task → API/worker task replacement. API and
workers refuse to start on a schema revision mismatch. PDF/RAG and notification
workers are separate ECS services; leases and heartbeats protect live work,
while expired work is retried with a bounded attempt count.

The API and worker refuse to create or alter deployed tables during startup.
`/livez` reports only process liveness. `/readyz` checks PostgreSQL revision,
S3 and Qdrant with bounded timeouts; third-party model and Google APIs are not
readiness dependencies.
