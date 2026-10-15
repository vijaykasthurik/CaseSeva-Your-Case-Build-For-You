# Administrator promotion recovery

`python -m backend.admin_command --email <existing-email>` remains supported.
`--user-id <existing-id>` selects the same service by account ID and still
checks normalized email uniqueness. Neither command asks for a password.
The command loads only the database, without seeding demo users or initializing
storage, authentication, media, or workflow providers.

Only an existing client is eligible. Advocates require a separate platform
administrator identity. Public signup still rejects the admin role. This
operation neither grants LEGAL_AUTHORITY_REVIEW nor changes legal data.

The service reserves one immutable `admin_role_audit` intent per user before
elevation. Mongo enforces this with a unique user_id index, including existing
random-ID legacy intents, and acknowledges new intents with majority/journal
write concern. Mock reserves under its file lock. Duplicate historical intents
fail closed; they are never removed or rewritten. This deliberately does not
implement re-promotion after a later demotion.

The user role and `admin_role_intent_id` are applied in the same user mutation.
An intent alone is not proof of application. The account reference records the
applied intent. A failure before application leaves an intent that the next run
reuses. Already-admin runs make no application or audit writes, including after
a lost success response. Stale, conflicting, or ambiguous state stops the
operation with an operator error. Resolve the underlying conflict through a
reviewed supported workflow; the command does not recommend database edits.

New intents contain a SHA-256 fingerprint of the observed account, including
mutation metadata, but no plaintext credentials or password hashes. Recovery
rejects a changed fingerprint. Original CLI intents lack a historical snapshot;
compatibility is restricted to matching client-to-admin OPERATOR_CLI intents on
legacy clients without mutation metadata, applied references, or capabilities.
This cannot reconstruct undetectable historical edits made by an unversioned
writer before recovery begins. The full observed record is protected against
concurrent changes during recovery. Any visible evidence of mutation fails
closed instead of silently treating an old intent as a fresh authorization.

The CAS bug was a missing `_revision` interpreted as zero, then matched against
stored `_revision: 0`. Mongo distinguishes absent from zero, so all 50 retries
missed. Explicit null would instead fail revision arithmetic. `version` and
`updated_at` were not the adapter's CAS fields. Current adapter signup initializes
the revision, but the separate user repository and legacy/imported records can
omit it; the historical insertion path cannot be proven from the user document.

Mongo mutations now match `_id` plus exact observed BSON document equality using
`$expr`, `$$ROOT`, and `$literal`, preserving the original stored `_id` even when
lookup used a separate application ID. This distinguishes missing and null,
detects added/removed fields, and protects against repository writers that do
not increment revisions. A successful legacy mutation initializes `_revision`
to 1; subsequent mutations increment it. Invalid revisions fail closed. Retry
limits are unchanged. The service rejects a changed account on a CAS retry;
it never overwrites an incompatible state. No transaction or new collection is
required on standalone Mongo.

The recovery suite uses temporary mock files and uniquely named disposable
local Mongo databases. It covers normal promotion, preserved identity/password,
immutable intent reuse, simulated failure before CAS and after commit, concurrent
promoters, concurrent raw Mongo writes, missing/null legacy metadata, stale and
ambiguous history, CLI idempotence, signup rejection, and login after promotion.
Every promotion fixture checks that authority/review collections stay unchanged.
