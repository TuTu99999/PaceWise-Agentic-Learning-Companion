# Landing, Google signup and customer-field encryption

Implemented on 11 October 2026; existing accounts and record IDs are preserved.

## Account flow

Landing → Sign up → enter Gmail → Google verifies the account → PaceWise student
session → Settings. Typing an email is only a login hint, not proof of identity.
Only Google-verified Gmail identities create accounts. The server ignores client
role claims; new users are students with **no automatic course enrollment**.

The OAuth flow uses state, an HttpOnly browser-binding cookie, PKCE S256 and a
single-use, ten-minute state record. Start requests share the existing per-IP
login rate limit. Reusing an OAuth callback fails. An existing native account
with the same email is not silently linked; use its existing login instead.

Signup requests only `openid email profile`. It does not retain a Google access
token, connect Calendar, or export a plan. Calendar consent remains a separate
action in Settings. Both flows use the already configured Google callback URI.
See [Google's server-side OAuth documentation](https://developers.google.com/identity/protocols/oauth2/web-server).

The current course enrollment picker is based on existing course membership. It
does not yet provide a self-service invite flow for an entirely new Google user.
Do not give all new signups access to demo courses to work around that limitation.

## Encryption scope and deployment requirements

SQLAlchemy encrypts account names and emails, Google subjects, session identity
fields, profile fields, workspace JSON and learner-memory JSON before SQL writes.
Names and JSON use randomized AES-GCM; searchable email/subject fields use AES-SIV
with purpose-bound authentication. Deterministic fields reveal equality, not the
original value. Database primary/foreign keys remain unchanged.

Legacy rows are migrated under a database transaction/advisory lock, without
changing record IDs or relations. The migration is idempotent. Existing encrypted
rows are authenticated at startup so a missing/wrong key fails rather than
silently overwriting data. Notification opt-in has a derived boolean column;
jobs no longer attempt JSON queries against encrypted workspace text.

The 64-byte key lives outside SQL at `CUSTOMER_DATA_KEY_FILE`, by default
`./data/customer-data.key`. Backend and worker must share this persistent file.
Production requires it to be mounted before startup. **Do not delete/recreate it
on deploy. Back it up separately under restricted access.** Losing the key makes
encrypted rows and the encrypted backup unreadable. Automatic key rotation is
not implemented; changing the key requires a controlled re-encryption migration.

Private JSON API envelopes remain encrypted in transit; direct plaintext API
access is blocked when `PRIVATE_API_REQUIRED` is enabled (verified locally).
`APP_ENV=production` now forces encrypted API transport, HTTPS enforcement and
Secure session cookies. Production must terminate TLS at a trusted reverse proxy,
forward the correct protocol, and prevent direct public access to backend/DB.
The local demo still uses HTTP on localhost. Browser-side decryption cannot hide
data from its authorized owner or from injected JavaScript; TLS, authorization,
CSRF defenses and XSS prevention remain necessary.

This is **not** a claim that every database column or external store is
application-encrypted: raw evidence/audit records, graph checkpoints, PDF files
and vector-store contents are outside this field-encryption migration. Use
encrypted PostgreSQL/EBS/object storage and TLS for internal connections in a
production deployment, plus an audit of those stores before accepting real
student data. No FERPA-compliance certification is claimed.

## Backup and verification

Before migration, a read-only PostgreSQL dump was encrypted and round-trip
verified: `data/backups/before-customer-encryption-20261011T020349Z.pwdb`.
The dump contains 240,119,249 SQL bytes; SHA-256:
`0af05ddc22b1c4d7750e13286276784c975025e99237e1291df1527e93b33d0e`.
It was never written as plaintext SQL. The backup format is the header
`pacewise-db-backup:v1\n`, a 12-byte nonce, then AES-GCM ciphertext using the first
32 bytes of the customer key and the header as authenticated data. A restore
must decrypt with the original key and restore into an isolated database first;
do not overwrite the live database without checking the restored application.
This check proves backup decryptability, not a full disaster-recovery rehearsal.

Runtime count-only verification found all 29 account names/emails, 1,163 session
identity records, 4 workspaces and 7 learner-memory records encrypted, plus
existing user profile fields. No field values or keys were printed.

Validation:

- Backend regression: 115 tests passed before the final transport-policy test.
- Final OAuth/encryption/Calendar/privacy/transport subset: 39 passed.
- Frontend full suite: 389 passed; the subsequent signup retry case passed in
  a five-test targeted rerun.
- Browser: 320/390/768/1366 px, light/dark; no horizontal overflow or broken
  landing images. Existing student and teacher accounts logged in successfully;
  logout denied protected routes afterward.
- Live signup start: encrypted request, Google-only redirect destination,
  identity-only scopes, state, PKCE and HttpOnly browser cookie verified. The
  outgoing Google page was intercepted for QA; no consent/account was created.
- Google consent with a real account has **not** been completed by the agent.
  The user must perform that consent; Cloud test-user/consent settings still apply.

Landing now uses actual, synthetic-demo-account product screenshots rather than
unrelated illustrations. It removes unsupported sandbox/account/pricing promises
and keeps Plan → Do → Reflect, teacher use, privacy and concise signup guidance.

## Updated Excel schedules

Both `outputs/pacewise-eight-courses-20261011/*.xlsx` retain the importer-compatible
`Lessons` and `Tasks` tabs and all source chapters. Schedule starts 05/10/2026,
Monday–Saturday. Every session is 180 minutes; shared daily slots are 08:00–11:00,
11:30–14:30 and 15:00–18:00, without conflicts across all eight courses.
DSA/RTOS use three weekly teaching sessions then an exercise-review session;
the other courses use two teaching sessions then exercise review. Exams are
after taught content; the semester extends through February for longer courses.

The real importer accepted 255 lessons and 81 tasks on disposable SQLite,
including historical lessons, and retried confirmations without duplication.
Source PDF names remain in chapter-cell notes. Existing workbook versions were
copied to `E:/Gate - AI/outputs/pacewise-eight-courses-20261011/before-3h-nhom-*.xlsx`.
Loading both packs for one student creates up to 54 contact hours per week:
this is dense demo input, not a recommendation for a real academic workload.
