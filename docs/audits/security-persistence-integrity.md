# Security and persistence integrity hardening

Baseline verified: `672c937ef3c655af5cba0b9b5120fab159503228`.
Tracked checkout was clean; `output/` was already untracked. Current checkout was
used directly; no competing implementation or checkout reset. Local commit only.
The commit containing this report is the final implementation commit; its exact
hash is returned in the chat (a commit cannot contain its own hash).

## Deployment and pre-change reproduction

Read-only `hello` against configured local database `caseseva` returned no
`setName`, no mongos `msg`, logical session timeout 30 minutes, max wire version 25.
This is a standalone deployment: multi-document transactions are unavailable.
Sessions alone do not imply transaction support. No transaction-backed atomicity
is claimed and no transaction deployment/configuration change was attempted.

Before editing, synthetic UUID-database tests of the baseline demonstrated:

- Failing bootstrap marker insertion left one active admin with no bootstrap.
- Barrier-synchronized bootstrap requests both inserted users: one succeeded,
  the other raised DuplicateKeyError at the marker, leaving two admins.
- Failing additional-reviewer audit insertion left an active unaudited target.
- Saving the same authority version ID with different text replaced history.
- Synchronizing both head replacements after their pre-check let both competing
  writers return success, silently losing one head update.

Only temporary databases were written during these reproductions and they were
removed in `finally`. Machine-readable observations and baseline/after checks are
in `security-persistence-integrity-state.json`.

## Provisioning design and invariants

This is a fail-closed audit-before-identity protocol, not a multi-document
transaction. Both writes request majority acknowledgement and journaling. On a
standalone, this supplies durable local ordering, not replication availability.

1. Validate new identity, PHASE4_REVIEW_ONLY scope and workflow method. Normalize
   email. Reject audit fields that could override reserved identity bindings.
2. Enforce unique user ID/email indexes even if startup index setup was omitted.
   Reject existing identity/email rather than updating or promoting an account.
3. Insert an immutable audit reservation, using bootstrap `_id=one-time` or the
   new user's ID for additional provisioning. It records user ID, normalized
   email, provisioning metadata and `AUDIT_BEFORE_IDENTITY_V1` protocol.
4. Only after acknowledged audit insertion, insert the active user. This single
   document insert is the activation/commit point. No audit write follows it.

A reservation plus its matching user denotes completion; a reservation without
that user denotes an incomplete/failed attempt. There is no mutable COMMITTED
flag and therefore no second commit window. Claims are never automatically
removed or overwritten, including after ambiguous acknowledgement failures.
An interrupted bootstrap may consume the one-time claim without creating a user.
This deliberately sacrifices availability to preserve the security invariant.

Bootstrap and onboarding duplicates return explicit failures, including network
retries after a successful but unacknowledged identity write. They do not silently
claim success or create duplicate identities. A failure before the audit insert
can be retried normally. A retained claim needs separately authorized investigation;
this task provides no automatic repair or takeover operation.

Onboarding validates the session against the stored user and matching review
provisioning audit, checks completed bootstrap provenance, and validates
`authorized_by` against the authenticated account. Client metadata alone and a
manually inserted role-only admin cannot authorize onboarding. Bootstrap history
is untouched by onboarding. Mongo adapter mutation/deletion of bootstrap,
provisioning and legal-history collections is now rejected.

## Constraints

All Mongo collections already enforce `_id` uniqueness. The protocol additionally
uses unique `users.id` (new sparse index), the existing unique normalized
`users.email`, and the existing unique audit `id` indexes. These are ensured at
provisioning time, so pre-checks are not the concurrency boundary. Bootstrap's
fixed `_id` supplies the single claim; provisioning `_id` is the target user ID.

The parallel authority/review repository constructors ensure existing unique
`id` indexes for heads, versions, receipts and submissions, including legacy
records whose `_id` differs from `id`. Invalid duplicates cause index setup to
fail closed. The existing reviewer_identities ID/email indexes were audited;
provisioning currently authenticates users in `users`, not reviewer_identities.
No redundant lookup indexes were added. No indexes were created on the real DB.

## History, CAS and service compatibility

Authority versions, review receipts and submissions now use insert-only history.
A new ID inserts. An identical canonical BSON payload is idempotent success;
object key order is immaterial. A different payload raises HistoryConflict and
preserves the stored record. BSON round-trip normalization compares actual Mongo
storage semantics, including datetime precision and scalar types.

Receipt tests cover source ID/digest, reviewer ID, decision, note/rationale,
reviewed_at and expected/input authority revision. Saving a receipt has no head
mutation side effect. Existing receipt IDs cannot be repurposed. Revision requests
are represented by immutable NEEDS_NEW_REVISION receipts and version/submission
history in the active service, rather than a separate repository method. The
Mongo adapter also rejects update/delete on legal_revision_requests. Audit events
already use insert-only UUIDs; repeated fixed-ID insertion is tested to fail.

Ingestion request creation also uses insert-only semantics so re-saving cannot
reset existing workflow history. Its explicit update method remains mutable for
workflow processing and rejects identity changes. This does not connect ingestion
prework to production or make mutable workflow events immutable.

Head initialization with expected_version=None is create-only. Advancement uses a
single find_one_and_update matching `_id` and the expected version, with no upsert.
Missing/stale heads raise VersionConflict; competing advancements from the same
version have exactly one winner. Internal `_revision` increments and unrelated
head metadata are preserved, allowing subsequent DatabaseAdapter CAS mutations.
Ambiguous head-write acknowledgements require a read; stale retries fail rather
than being converted to silent success. Multi-record version/receipt/head writes
are not a single transaction and may leave unreferenced immutable history.

There is no separate backend/repositories/review_repository.py in this checkout;
ReviewRepository and MongoReviewRepository are in authority_repository.py.
AuthorityReview/VerifiedCorpus still use DatabaseAdapter. Repository classes remain
future integration surfaces, not production-wired services. Tests exercise the
actual Mongo AuthorityReview revision-request flow, read its history through the
repositories, reject changed receipts and stale decisions, and verify head
interoperation in both directions. No production repository switch was made.

## Validation and isolation

- Full selected regression run: **118 tests passed** (31.606 seconds).
- After the final head metadata/revision compatibility adjustment: **40 targeted
  tests passed** (28 new integrity tests plus 12 existing Mongo persistence tests).
- Suites: test_persistence_integrity, test_review_admin_bootstrap,
  test_additional_review_admin, test_authority_review, test_authority_revision,
  test_security_hotfix, test_mongo_persistence, test_genericity_audit,
  test_current_genericity_audit, test_blackboard, test_review_continuation,
  test_review_client_diagnostics. Executed with `.venv/Scripts/python.exe -m unittest`.
- New tests cover concurrent bootstrap/onboarding, duplicate IDs/emails, failed
  audit writes, failure after claim and before activation, ambiguous audit/user
  acknowledgements, safe retries, forged authorizers, missing bootstrap, identity
  constraint enforcement without startup setup, history conflict/idempotency,
  receipt binding/replay safety, concurrent initial/advancing heads, stale writes,
  insert-only audit events and active-service interoperability.
- `python -m compileall -q backend scripts engineering_prework` passed.
- `git diff --check` passed. Existing websocket deprecation warnings are unrelated.

All Mongo test writes used UUID-named temporary databases and synthetic records.
The existing isolated persistence migration fixture remains synthetic, with its
S3 probe mocked and its manifest confined to a temporary root. No S3 probe,
real-upload copying, real manifest rewrite or AWS operation was performed.

The initial broader run uncovered three preflight failures in the optional
continuation suite. That unchanged legacy suite copied legal JSON from the local
bundle into temporary files and expected an obsolete hardcoded head/receipt. It
stopped before any source post; temporary copies were cleaned up. This was a test
isolation deviation, not a mutation of real review state. Its fixture was replaced
with a fully synthetic revision-request flow and the final run passed. No real
receipt was replayed. Production continuation code was not changed. The original
JSON hashes remained identical throughout.

## Before/after safety evidence

| Collection/count | Before | After |
| --- | ---: | ---: |
| users | 210 | 210 |
| users with admin role | 0 | 0 |
| reviewer_identities | 4 | 4 |
| review_admin_bootstrap | 1 | 1 |
| review_admin_provisioning | 3 | 3 |
| legal_authority_heads | 14 | 14 |
| legal_authority_versions | 21 | 21 |
| legal_authority_reviews | 3 | 3 |
| legal_review_submissions | 17 | 17 |
| legal_revision_requests | 0 | 0 |
| audit_events | 4 | 4 |

Authority JSON SHA-256 before and after:
`b96220116ac40a01b4f96e6b620edc7eebfa35d39d11dfb33b677b9bf67716c3`.

Identity JSON SHA-256 before and after:
`bd055fe4bd996aba38a243fbb3572f68646be7cd469e0382a3b57920a9a15b17`.

Real collection index inventories also match. Real Mongo inspection used counts
and index metadata only; no identity documents or credentials were printed.
Counts are not a cryptographic proof of all Mongo document bytes; no claim of a
transactionally consistent real-data snapshot is made.

## Remaining limitations

- Incomplete reservations remain blocked. No automated recovery or production
  migration was run. Existing deployment identity/schema inconsistencies are not
  repaired by this task; stricter onboarding fails closed on missing provenance.
- Unique email enforcement assumes the application's normalized email writes.
  Arbitrary non-normalized direct database writes are outside this workflow.
- Application append-only rules cannot prevent a privileged database operator
  from editing/deleting documents, forging full identity/audit/session state, or
  dropping indexes. Compass edits are not an authenticated provisioning workflow.
- Session authorization is checked at invocation; concurrent logout/revocation is
  not a multi-document transaction with provisioning. No new revocation protocol.
- Repository head CAS is based on the expected immutable version ID. It is not a
  transaction covering version insertion, review, authorization and head change.
- Existing deployment startup/provider, storage and ingestion limitations from
  the genericity audit are unchanged. The prior ingestion-provenance hardening
  commit and its files are preserved. No legal correctness or coverage claim.

## Explicit answers

Can two concurrent bootstrap requests create two review administrators?
**No, through the hardened provisioning workflow.** Only one fixed bootstrap claim
can be inserted, and user activation follows that claim.

Can a partial provisioning failure leave an active admin without the required
audit/bootstrap state? **No, through this workflow.** The durable audit precedes
activation; a failure can leave an inactive reservation instead.

Can an existing authority version or review receipt be overwritten with a
different payload? **No, through these repository/adapter history APIs.**
Conflicting immutable IDs fail.

Can two concurrent authority-head updates silently overwrite one another?
**No, when advancing from the same expected version through the repository CAS.**

Was any real legal authority or review state changed? **No.**

## Changed files

- backend/adapters/mongo/database.py
- backend/database/mongo_indexes.py
- backend/repositories/authority_repository.py
- backend/repositories/immutable.py
- backend/tests/test_persistence_integrity.py
- backend/tests/test_review_continuation.py
- docs/audits/security-persistence-integrity.md
- docs/audits/security-persistence-integrity-state.json

No real review history was rewritten by this task.

No legal authority was approved or modified by this task.

Engine 2 was NOT started.

Phase 5 was NOT started.
