# Role boundaries and authority-review completion

Baseline: `23a1fc94f2129ffde5f15eaf961bd04fdb454a48`. Continued the existing checkout without reset, checkout, stash, revert or discarded work. The inherited state comprised 12 modified tracked files, new grant CLI and role-boundary tests, and pre-existing untracked `output/` artifacts. The inherited patch was saved locally in `output/role-boundary-inherited.patch` before further edits.

## Role and permission contract

Platform administration and legal review are separate responsibilities.

- Citizens provide inputs, receive Engine 1 understanding and choose whether to use Engine 2 or engage an advocate. Verified advocate assignment and explicit scoped citizen consent remain required for access.
- A verified advocate reviews the citizen case, makes versioned corrections, supplies comments and may rerun Engine 1 using current corrections. Case access does not require the separate master-corpus capability.
- Platform administrators verify/onboard advocates and manage operations. Administrator role alone cannot approve, reject, mark stale or request a legal-authority revision.
- New master-corpus decisions require an authenticated, persisted `advocate` account with `verification_status=VERIFIED` and `LEGAL_AUTHORITY_REVIEW`. Capability data must be a list of strings. The existing `permissions` list is accepted as an explicit compatibility alias; neither role nor historical provisioning implies permission.
- The persisted account is checked again for each decision; a revoked capability or withdrawn verification defeats an old identity snapshot. Expected version, independent submitter, source identity, immutable receipts, quarantine and VerifiedCorpus gates are preserved. Self-review is refused for every decision.

## Completed grant/revoke workflow

`POST` / `DELETE /api/admin/advocates/{id}/capabilities/legal-authority-review` use the normal authenticated administrator path, including `X-Admin-Token` when configured. Bodies require an exact action confirmation and a nonblank reason (maximum 1000 characters); extra fields are rejected.

Targets must exist and be advocates. Grant requires prior verification; revoke also works after verification is withdrawn. Neither operation promotes roles, changes authority content, creates review receipts or alters authority heads. Duplicate grant/revoke is idempotent. Responses expose only account identity, role, verification and capability lists.

An immutable `authority_reviewer_grants` intent is written before a compare-and-swap account update. The account stores the applied intent ID. Persisted administrator identity and target role/verification/capability state are checked; stale target state cannot be overwritten. Audit entries contain explicit IDs, reason, time and capability changes, not credentials or password hashes. Mock and Mongo adapters enforce append-only audit records; mock review receipts are also append-only.

`scripts/grant-legal-authority-review.py` targets the normal application server (default loopback port 8000). It requires a local interactive terminal, prompts for email/password, supports a hidden additional admin credential, requires explicit confirmation, encodes the target path and logs out on success/cancel/failure. It accepts no password or token argv flags and never echoes arbitrary server payloads. It never performs legal review. No real account was granted or revoked in this task.

## Inherited defects corrected

- Grant/revoke originally trusted the supplied admin role and updated access before writing audit. It now rechecks persisted identity, audits before access and rejects concurrent target changes.
- Responses and CLI error output were insufficiently constrained; grant CLI lacked terminal/hidden-input guarantees and did not reliably log out after cancellation/failure.
- The partial authority submit route blocked the authorized advocate correction-continuation workflow. Authorized advocates can submit a corrected pending candidate, but cannot independently review their own submission.
- Several tests retained `test-independent-admin` after changing the fixture identity. A new reviewer fixture lacked email, and a signup session was left open. These fixtures were corrected without loosening authorization.
- Placeholder tests and a corpus-revision test mislabeled as a citizen-correction test were replaced with actual case-review contract checks.
- Corpus-population test reviewer identities and assertions were updated to qualified advocates; no production ingestion implementation was connected or executed.
- Diagnostic tests now use synthetic authority and in-process HTTP transport, instead of copying genuine candidates or starting a live HTTP server.
- A pre-existing order-dependent test failure was reproduced with unchanged baseline test modules: password-reset test closed the shared cached Mongo client, causing provider-test cleanup to fail. The password-reset test now owns a separate client; its assertions are unchanged. Evidence: `output/role-boundary-baseline-order-failure.txt`.

## Case and engine contracts

Advocate corrections are first-class versioned case data.

The existing audit/override history retains the previous AI value, each advocate value, current value, actor, timestamp and reason. Engine 1 re-applies professional overrides; protected Blackboard writes raise conflicts instead of silently overwriting corrections. KEEP / REPLACE / MERGE remain deterministic. Existing dependency-based invalidation preserves unrelated work while substantive edits stale downstream analysis/documents.

Evidence edits now accept only annotations/comments, preventing replacement of original storage references or evidence identity. Original document bytes are not rewritten. The future document-version pipeline remains a contract, not a newly implemented editor.

Engine 2 remains optional.

Final advocate approval no longer requires rerunning stale optional Engine 2. Stale analysis is excluded from downstream approved content and does not require an unused Engine-2 consent scope. The exact disclosure remains: "Case Challenge / Argument Analysis was not run."

Engine 3 requires a current advocate-reviewed Engine 1 Case File.

The shared eligibility predicate checks current Case File, approval-version match, input-version match, E1 stale/running/failed state, processing errors, and existing Phase-4 authority currency gates. Existing document entry gates use it. These are contract/eligibility changes only; no Engine 2 or Engine 3 job was executed or implemented.

## Historical compatibility

Historical administrator identities, receipt bindings and password/bootstrap utilities remain intact. Existing receipts are validated by their immutable source bindings without retroactively applying today's role semantics. Their holders do not automatically qualify for new decisions. Historical procedure pages now point to this contract. The isolated review server may allow an administrator to inspect/prepare records; only a qualified advocate can make a new decision. The capability CLI operates through the normal application admin routes, not direct Mongo/JSON edits.

## Protected data

The manifest lists 12 curated candidates stored as inactive versions; these are distinct from the 14 existing authority heads. All 12 remain REVIEW_PENDING, with no review IDs and zero receipts for their source IDs; VerifiedCorpus continues to reject them. No candidate was activated, approved, rejected or marked stale.

| Collection | Before | After | Entire collection hash |
|---|---:|---:|---|
| legal_authority_heads | 14 | 14 | unchanged |
| legal_authority_versions | 36 | 36 | unchanged |
| legal_authority_reviews | 3 | 3 | unchanged |
| legal_review_submissions | 17 | 17 | unchanged |
| legal_revision_requests | 0 | 0 | unchanged |
| authority_reviewer_grants | 0 | 0 | unchanged |

Both protected file hashes are identical before and after:

- `.localdev/phase4-authority-review/database.json`: `b96220116ac40a01b4f96e6b620edc7eebfa35d39d11dfb33b677b9bf67716c3`.
- `.localdev/phase4-authority-review/identity.json`: `bd055fe4bd996aba38a243fbb3572f68646be7cd469e0382a3b57920a9a15b17`.

Read-only safety evidence is retained locally in `output/role-boundary-before.json`, `output/role-boundary-after.json`, and `output/role-boundary-curated-check.json`. No real identity credentials were read into the report, and no real capability change or genuine review decision occurred.

## Validation

Final runs: **182/182** broad role/review/provider/genericity/dynamic/multi-domain/Blackboard checks; **69/69** Mongo/persistence/corpus/media checks; **36/36** case-contract/legal-team/orchestrator checks. These are test executions across three groups, including overlapping coverage. `compileall` and `git diff --check` passed. Logs: `output/role-boundary-final-regressions.txt`, `output/role-boundary-mongo-regressions.txt`, `output/role-boundary-case-regressions.txt`. All tests use synthetic data and temporary files or unique disposable Mongo databases. The external-network guard permits only local Mongo for persistence tests and Windows asyncio internal socketpair wakeups. No AWS, S3 probe, legal-source fetch, bulk ingestion, genuine review or downstream-engine execution occurred. Migration tests use a mocked OFFLINE_TEST_NO_S3 result.

Initial inherited run: 68 tests, four failures; these were investigated and repaired. An initial runner setup also incorrectly blocked embedded Mongo tests; this was a harness error, not a product baseline failure. The independently reproduced cached-client ordering failure is documented above. No assertions were weakened to obtain green output.

## Limitations

- Standalone Mongo uses durable audit-before-CAS rather than a cross-collection transaction. A failed CAS can leave an unapplied audit intent; the account change ID distinguishes applied state. Operators must inspect an ambiguous failure before retrying.
- Qualifications are attested by the administrator through the audited reason after verification; no new credential-verification automation or frontend was built.
- Existing reviewed authority, source coverage and live reasoning availability remain independent of role permissions. No new legal coverage is claimed.
- Existing engine/draft code was not expanded. Only review/eligibility contracts were adjusted. Full future document editing and Engine 3 remain outside this task.

## Explicit answers

- Preserved and reviewed Antigravity partial work instead of resetting it: **Yes**.
- Is platform admin automatically a legal reviewer: **No**.
- Who reviews a citizen case: **The assigned verified advocate, after acceptance and citizen consent**.
- Who reviews the master corpus: **An authenticated verified advocate with explicit LEGAL_AUTHORITY_REVIEW, independent of the submitter**.
- Can an advocate rerun Engine 1 after corrections: **Yes, with source-input consent; current overrides are retained**.
- Can Engine 2 be skipped: **Yes**.
- Can corrections be silently overwritten: **No; override history and protected conflict resolution remain enforced**.
- Did a genuine authority decision occur: **No**.

No genuine legal authority was approved by this task.

Engine 2 was NOT started.

Phase 5 was NOT started.

Commit: local only; the final commit hash is supplied in the completion message. No push.

## Files changed

- `backend/adapters/mock/database.py`
- `backend/adapters/mongo/database.py`
- `backend/routes/advocates.py`
- `backend/routes/authorities.py`
- `backend/routes/documents.py`
- `backend/routes/review.py`
- `backend/services/authority_review.py`
- `backend/services/engine3.py`
- `backend/services/review_contracts.py`
- `backend/tests/legal_test_support.py`
- `backend/tests/test_authority_capability_cli.py`
- `backend/tests/test_authority_review.py`
- `backend/tests/test_authority_revision.py`
- `backend/tests/test_case_review_contracts.py`
- `backend/tests/test_mongo_authority_capability.py`
- `backend/tests/test_persistence_integrity.py`
- `backend/tests/test_review_admin_bootstrap.py`
- `backend/tests/test_review_admin_password_reset.py`
- `backend/tests/test_review_client_diagnostics.py`
- `backend/tests/test_review_continuation.py`
- `backend/tests/test_role_boundary_and_authority_permissions.py`
- `docs/phase4-admin-review-checklist.md`
- `docs/phase4-correction-continuation.md`
- `docs/phase4-local-admin-bootstrap.md`
- `docs/phase4-revision-request-workflow.md`
- `docs/role-boundary-authority-review.md`
- `engineering_prework/legal_source_ingestion/tests/test_corpus_population.py`
- `scripts/grant-legal-authority-review.py`
- `scripts/record-authority-review.py`
- `scripts/serve-authority-review.py`
