# Phase 2 — Blackboard and orchestration foundation

Date: 2026-10-11. Scope: Phase 2 only. Accepted starting point: `7e17747` (Phase 1), retaining security baseline `d3dfea2`.

The control plane is implemented and locally validated alongside the existing engines. It does **not** replace the production Engine 1/2/3 pipelines or implement dynamic legal intelligence. No AWS calls, infrastructure changes, deployments, or pushes were performed during this phase.

## 1. Commits

- `c381bae` — versioned Blackboard, contracts, registry, local process locking; first 9 tests passed.
- `6a74209` — durable scheduler, input bridge, administrator diagnostics, scheduler/integration regressions.
- `1f438f4` — source-conflict decisions, stale-result fencing, dependency versions, actual process restart validation.
- This report is committed separately after validation; its commit is the final Phase 2 checkpoint.

These are local commits on the existing `main` branch. Nothing was pushed.

## 2. Every changed or added file

| File | Change |
| --- | --- |
| `backend/adapters/mock/database.py` | Use shared process/file locking, including initialization. |
| `backend/adapters/mock/file_lock.py` | New bounded Windows/POSIX locking implementation for local JSON persistence. |
| `backend/main.py` | Register the administrator diagnostics router. |
| `backend/models/orchestration.py` | New agent, result, provenance and future legal-record contracts. |
| `backend/routes/cases.py` | After authorization, lazily synchronize the sidecar when opening a case. Citizen projection remains unchanged. |
| `backend/routes/orchestration.py` | New administrator-only diagnostics GET. No execution or mutation HTTP endpoints. |
| `backend/services/agent_registry.py` | New registry, graph expansion, pack selection and concurrency compatibility. |
| `backend/services/blackboard.py` | Add an isolated Phase 2 synchronization bridge; preserve existing legacy helpers. |
| `backend/services/case_blackboard.py` | New versioned persistence, references, changes, staleness, conflicts, overrides and Case File provenance. |
| `backend/services/ingestion.py` | Synchronize references after successful Phase 1 ingestion. |
| `backend/services/orchestrator.py` | New scheduling, claims, retries, checkpoints, output validation, review and diagnostics. |
| `backend/tests/test_blackboard.py` | 10 tests for persistence, history, conflicts, registry and failures. |
| `backend/tests/test_orchestrator.py` | 25 non-legal scheduler acceptance/regression tests. |
| `backend/tests/test_orchestration_integration.py` | 5 HTTP permission and Phase 1 integration tests. |
| `docs/phase2-orchestration-report.md` | This report. |

The existing untracked `output/` directory was left untouched and uncommitted.

## 3–4. Reused components and new modules

Reused the existing `DatabaseAdapter` interface and atomic `mutate`, local JSON adapter, authentication, administrator checks, Phase 1 RawCasePackage, legacy Blackboard helpers, citizen allowlists and existing engine dispatch. The DynamoDB adapter and interface were not changed.

New modules are the lock, orchestration models, registry, versioned Blackboard, orchestrator, diagnostics router and three test modules listed above. The existing local adapter needed process locking because its previous per-instance thread lock did not protect multiple processes writing the same file.

## 5. Blackboard schema

One new control-plane head per case points to a committed snapshot. A snapshot contains:

- Schema version, case ID and Blackboard version.
- Identity references: origin, stage, status, owner/creator, client/advocate references, language, workflow state, active engine and current legacy Case File version.
- Input references: saved input version, raw-package version/input version/fingerprint, canonical/original text references, source IDs, actual uploaded evidence IDs, declaration references and extraction-failure references.
- Empty future sections for facts, incidents, timeline, parties, legal issues, legal sources and evidence mapping. No invented legal content is seeded.
- Uploaded-evidence references and extraction/review metadata; declarations do not receive uploaded Evidence IDs.
- Field versions, node contracts/execution checkpoints, conflicts, protected human fields, optional Case File derivation metadata and run metadata.

Future typed records support provenance, actor/agent, confidence, review, verification, advocate approval, timestamps, versions, uncertainty and staleness. Legal-source verification supports CANDIDATE, PENDING, VERIFIED, REJECTED, OUTDATED and NOT_APPLICABLE. Defining these schemas does not verify any law.

## 6. Versioning and history

`case_board_heads` holds a small current pointer. `case_board_snapshots` holds immutable snapshots linked to their predecessors. Each meaningful committed change records actor, time, reason, change type, previous/current version, changed paths and affected outputs. Human changes include before/after values.

A snapshot is saved before an atomic compare-and-swap advances the head. Interrupted or losing proposals cannot become visible as committed history. History reads are paginated, with a maximum of 100 events per call. Current state requires the head and its snapshot, not replay of the history chain.

This version sequence is separate from the retained legacy `cases.board_version`. Existing routes and engines keep their accepted behavior while later phases migrate agents. The new Blackboard is authoritative for new orchestration outputs; legacy outputs are not silently copied or claimed as migrated.

Raw text/binaries are not copied into the new board. References carry versions and a fingerprint. Historical board reconstruction does not recreate historical raw text that the legacy case record no longer retains; a future agent must use the referenced version, not silently substitute a newer raw package.

## 7. Agent contract

Contracts declare type, semantic version, engine, purpose, required/optional inputs, reads, writes, dependencies, declarative conditions, pack, concurrency permission, timeout, retry policy/count/delay, idempotency behavior, stale dependencies, human-review requirement, failure behavior, supported languages, external capabilities and internal visibility.

An implemented registration must supply a validator for every declared output. Completion requires exactly the declared outputs, successful validation, matching dependency versions and a successful durable commit. A returned function or placeholder registration is insufficient.

## 8. Registry

The registry rejects duplicate names and invalid versions, discovers agents, exposes metadata and availability, expands dependencies, detects cycles and selects registered packs. REGISTERED, IMPLEMENTED, AVAILABLE, ENABLED and LIVE_VALIDATED are distinct fields.

**Production agent registrations: none.** `production_registry()` deliberately returns an empty registry. Phase 1 ingestion is a real data bridge, not a newly registered legal agent. A/B/C/D and other synthetic agents exist only in tests.

## 9–11. Orchestrator, graph and eligibility

`start` persists a plan from selected registrations and their prerequisites. Plans can add a selected pack without losing completed work. Graph construction is generic; no legal stage list is embedded in the scheduler. Plans are bounded to 64 nodes.

`refresh` checks dependencies, conditional activation, required inputs, availability, enabled state, language and external capabilities. Conditions can skip irrelevant work. A skipped dependency does not manufacture missing required input for its dependents.

`tick` runs one eligible batch. Completed prerequisites remain stored; blocked or paused branches do not prevent unrelated work. All required states are represented and tested: WAITING, READY, RUNNING, COMPLETED, FAILED, BLOCKED, NEEDS_USER_INPUT, NEEDS_DOCUMENT, REVIEW_REQUIRED, CONFLICT_FOUND, STALE, SKIPPED and NOT_IMPLEMENTED.

No semantic domain selection, specialist-team reasoning or legal decisions were implemented. Generic pack selection/conditions are ready for those future agents.

## 12. Concurrency

Workers claim nodes through a version-checked durable mutation. Running peers must declare concurrency safe and have no overlapping writes or write/read conflicts. Independent writes rebase against the latest snapshot; they do not replace another worker's state with an old copy.

Per-controller concurrency defaults to four and is capped at eight. A process-wide eight-slot bound also limits actual handler calls. A timed-out handler keeps its slot until it exits, preventing repeated timeouts from creating unlimited threads. Future external-provider handlers must set their own provider timeouts.

Local persistence uses OS locks plus a shared per-path thread lock. Multiple independent Python processes were tested. The existing DynamoDB adapter's atomic mutation is reused by contract, but was not live tested.

## 13. Idempotency

Execution identity derives from case, agent/version, watched input/dependency versions, requested action and explicit human-review generation. Atomic claims prevent duplicate workers from dispatching the same current execution. Attempt tokens fence late workers. Repeated completion and resume do not append duplicate committed output/history.

Handlers receive the durable idempotency key for provider calls. Exactly-once external effects cannot be guaranteed after a provider accepts a request and the worker crashes before checkpointing; future providers must support the key where possible. Local committed outputs remain protected from duplication.

## 14. Checkpoint and resume

Plans, claims, attempts, dependency versions, leases, output versions, pauses, requests and results are persisted. A new orchestrator instance or process can continue from the same adapter. Expired leases become retryable failures within the configured retry budget; old attempt tokens cannot commit.

Acceptance tests interrupt after B, construct a new adapter/controller, and also start an actual new Python process. A and B retain their execution IDs and single attempts; only unfinished C/D continue.

No production sweeper, new queue, Lambda action or scheduler infrastructure was provisioned. Calling `tick` resumes persisted work. Later approved agent migration must connect the durable controller to the production worker lifecycle.

## 15. Retry policy

Only explicit transient failures or expired leases/timeouts are eligible for automatic retry. Retry counts, next eligible time and terminal failure are durable. Policies support no retry or transient-only retry; retries are bounded to five with exponential delay. Invalid output and ordinary terminal exceptions do not silently retry. The last failure remains observable after a successful retry.

## 16. Targeted staleness and Case File provenance

Invalidation follows declared field paths and recursively affected output paths. Explicit subfield reads narrow dependencies; an edge without explicit field reads watches the upstream output paths. Unaffected siblings remain current.

Every new completed output has a new dependency version, even when its value equals the previous output. This prevents legitimate reruns from incorrectly consuming an old execution's retry budget. Results based on changed input are fenced before publication.

Future Case File provenance must include board/input versions and facts, parties, timeline, legal issues, legal sources and evidence-mapping versions. Changes to direct or derived dependencies mark that record STALE without generating a new Case File. No new professional Case File is generated in Phase 2.

## 17–18. Conflicts and advocate overrides

Conflicts retain competing values, source references, field, affected facts/agents, execution reference and human resolution. Source disagreements are not silently settled.

Protected human fields survive AI proposals. A conflicting proposal creates CONFLICT_FOUND and a review checkpoint without publishing the replacement. Explicit KEEP retains the reviewed value; REPLACE selects the proposed value; MERGE requires a supplied reviewed value. Values are validated again before completion. A changed human value invalidates an old decision rather than allowing stale approval.

Source conflicts can also be resolved before any field value exists. Their decisions become durable input to a targeted retry. There is no new public override endpoint: these internal service methods require an authorized caller when later integrated with the advocate workspace.

## 19–20. Compatibility and origins

Old cases initialize lazily without destructive migration or changes to their saved legacy data. Opening a case synchronizes references only after existing ownership/consent checks. Phase 1 ingestion synchronizes after its successful commit. A sidecar synchronization failure is logged internally and does not break accepted citizen reads or ingestion; diagnostics can retry synchronization.

All three origins use the same bridge: CITIZEN_SELF_SERVICE, CITIZEN_DIRECT_ADVOCATE and ADVOCATE_WALK_IN. Existing consent, guest claim and advocate access rules remain. Direct legal help does not automatically run any legal engine. Walk-in and self-service retain their existing dispatch behavior.

## 21. Security regression

All **10 security-hotfix tests passed**, including the 29 retired HTTP operations, citizen exclusion of private Engine 2/advocate notes/Output B, nested raw/translation scope filtering, revoked grants and sanitized technical errors.

The new `/api/admin/cases/{case_id}/orchestration` GET requires an authenticated administrator and the existing additional administrator token when configured. Citizens and advocates are denied. No execution or review mutation route was added. Citizen responses continue using the existing allowlists and do not contain the new private board or execution payloads.

## 22. Phase 1 regression

All **16 Common Input tests**, **6 input-layer tests** and **4 entry-route tests** passed within the full suite. Five new integration tests also cover the bridge, all origins, lazy initialization, authorization, failure isolation and an empty production registry.

## 23. Backend test runs

All runs below passed with zero failures. Counts increased as tests were added.

| Command / checkpoint | Result |
| --- | --- |
| `python -B -m unittest backend.tests.test_blackboard backend.tests.test_persistence -v` | 9 passed |
| `python -B -m unittest backend.tests.test_orchestrator -v` | 12 passed |
| `python -B -m unittest backend.tests.test_blackboard backend.tests.test_orchestrator backend.tests.test_common_input backend.tests.test_security_hotfix -q` | 46 passed |
| `python -B -m unittest backend.tests.test_orchestrator backend.tests.test_orchestration_integration -v` | 23 passed |
| First `npm run test:backend` | 117 passed |
| `python -B -m unittest backend.tests.test_orchestrator backend.tests.test_blackboard backend.tests.test_orchestration_integration -q` | 36 passed |
| Final `npm run test:backend` | **126 passed**, 48.731 seconds |
| Python AST parse of all 11 changed runtime modules | Passed |
| `.venv/Scripts/python.exe -m pip check` | Passed; no broken requirements |
| `git diff --check` | Passed |

Python unit commands used `.venv/Scripts/python.exe`. The final suite contains **40 new Phase 2 tests**: 10 Blackboard/registry, 25 scheduler and 5 integration tests. It also tests actual process locking/restart, CAS collisions, interruption before head publication, oversized checkpoint rejection and dynamic pack addition.

A pre-existing PyMuPDF `fitz` deprecation warning was emitted. It did not fail tests and was not refactored in this phase.

## 24. Frontend/build/browser

- `npm run build --prefix frontend`: passed, 1,922 modules transformed.
- `npm test`: **16 Playwright Chromium tests passed**, 33.1 seconds.
- Browser coverage includes authentication, normal case flow, separate Engine 2, protected documents, direct help, walk-in consent, Tamil input, duplicate uploads, input retry and browser microphone capture.
- Browser tests used the explicitly configured development/mock environment. They are not live AWS or live legal processing validation.
- No frontend source files were changed.

## 25. Synthetic graph acceptance

The non-legal INPUT → A → (B, C) → D graph passed dependency, READY/RUNNING/COMPLETED, concurrent B/C barrier, D wait, B-specific invalidation, unaffected A/C, checkpoint, duplicate-worker and restart assertions. Protected overrides and all three resolution decisions were tested separately. Test handlers never enter the production registry.

## 26. Blockers and practical limits

- **LOCAL VALIDATED — DYNAMODB LIVE ACCESS BLOCKED BY AWS SCP.** No DynamoDB calls or retries were made.
- Transcribe remains **BLOCKED BY AWS ORGANIZATIONS SCP**; no calls or retries were made.
- STS, S3 and Bedrock retain their previously reported Phase 1 connectivity; none were revalidated in this phase.
- Legal corpus remains NOT READY; no readiness flags, sources or retrieval code were changed.
- A snapshot is capped at 300 KB and plans at 64 nodes. Large agent results must become references; capacity failures cannot advance the head. Future scaling/retention work remains necessary.
- Immutable full snapshots trade storage for straightforward durable history. Losing CAS/crash proposals may leave unreachable records; no automatic garbage collector was added. Only committed head ancestry is treated as current history.
- The existing local JSON adapter still loads its database file to service reads. The new service does not replay all history, but local performance is not equivalent to DynamoDB. Its whole-file design was not replaced.
- Provider-side exactly-once calls, production recovery scheduling, historical raw-content archival and retention/purge integration for the new collections remain production-hardening work. No production readiness is claimed.
- If bridge synchronization fails, accepted legacy flows continue and internal logs record the pending synchronization; no success is invented for the new control plane.

## 27. Deliberately postponed

Phase 3 and later: real Fact/Timeline, Party/Relationship, Case Stage, Domain Router and Team Builder agents; evidence mapping intelligence; all Consumer, Labour, Property, Criminal, Civil and RTI specialist packs; statute/precedent retrieval, temporal law, jurisdiction/remedy, limitation and citation verification; Engine 2 closed-loop reasoning; Engine 3 generation and professional review migration; production worker integration and full live legal validation.

Git comparison confirmed **no changes** to Engine 1 reasoning, Engine 2 reasoning, Engine 3 generation, legal knowledge/retrieval, the real DynamoDB adapter, or frontend sources. Existing jobs and Lambda dispatch also remain unchanged.

## 28. Completion labels and explicit answers

| Label | Phase 2 assessment |
| --- | --- |
| IMPLEMENTED | Blackboard and orchestration control mechanics, side-by-side input bridge and admin diagnostics. |
| UNIT TESTED | Yes: 40 new tests; 126 total backend tests passed. |
| LOCAL INTEGRATION VALIDATED | Yes: existing local adapter, multiple processes, HTTP permissions, Phase 1 bridge and synthetic DAG. |
| LIVE CONNECTED | Not newly established for Phase 2. DynamoDB remains SCP-blocked. |
| LIVE INPUT VALIDATED | No new Phase 2 live validation. Phase 1 evidence remains separate. |
| END-TO-END VALIDATED | Local synthetic orchestration and existing development browser flows only. Full live legal end-to-end validation is pending. |
| LEGAL CORPUS READY | No. |

Explicit answers:

- Does the new orchestrator run real legal agents? **No.** Existing real/mode-dependent legacy engines remain on their existing routes.
- Which production agents are registered? **None.** The Phase 1 bridge is not described as a legal agent.
- Which future agents are contract-supported only? **All migrated Engine 1 agents, specialist packs, Engine 2 agents and Engine 3 agents listed above.** No stubs are reported as implemented intelligence.
- Can execution resume after interruption? **Yes**, locally validated, including a new Python process and expired-lease fencing.
- Can only affected descendants become stale? **Yes**, according to declared field dependencies; callers must declare those dependencies correctly.
- Can independent nodes execute safely in parallel? **Yes**, locally validated with concurrent handlers and version-checked commits.
- Can advocate-edited values survive reruns? **Yes**, with protected fields and explicit KEEP/REPLACE/MERGE resolution.
- Can old saved cases still load? **Yes**, through additive lazy initialization and unchanged citizen projections.
- Were Engine 1, Engine 2, Engine 3 or legal retrieval changed? **No.**

**STOP: Phase 2 ends here. Phase 3 has not started and requires explicit approval.**
