# Phase 3 — Source-grounded case understanding

Date: 2026-10-11. Accepted starting baseline: `28bf6b2`, retaining the security hotfix and Phase 1/2 work. Scope: Phase 3 only.

Seven production capabilities now execute through the dependency scheduler and existing worker dispatch. This is **case understanding**, not completed legal analysis. All live sample cases retain `REVIEW_REQUIRED` where information or normalization needs review, and `legal_foundation=PENDING`. No legal corpus, specialist team, Engine 2 reasoning or Engine 3 drafting was implemented in this phase.

## 1. Commits

- `e57f578`: multilingual source indexing, conservative date validation and stable-ID contracts; initial seven tests passed.
- `3e23a07`: production core handlers, durable worker integration, permissions and regression coverage.
- `c00cf3a`: grounding repairs, targeted clarification handling, safe public status and browser regression.
- `677bee0`: prevent relative date words from acquiring a date based on the worker clock; nine source tests passed.
- Validation scripts, recorded summaries and this report are committed as the final checkpoint after validation.

These are local commits on the existing `main` branch. No push, deployment, infrastructure provisioning or organization-policy change was performed. Existing untracked `output/` files were preserved.

## 2. Every changed or added file

Paths are relative to the repository root.

| File | Purpose |
| --- | --- |
| `backend/adapters/real/llm.py` | Bounded provider connection/read timeouts; existing Bedrock implementation reused. |
| `backend/lambda_handler.py` | Route Engine 1 jobs through the explicit legacy/core selector. |
| `backend/requirements.txt` | Pin dateparser 1.2.2 for conservative multilingual date interpretation. |
| `backend/models/understanding.py` | New strict, language-neutral provider candidate contracts. |
| `backend/models/understanding_outputs.py` | New persisted output validators, including IDs and no extra law fields. |
| `backend/routes/cases.py` | Opt-in configuration for new cases; allow supporting uploads after core understanding. |
| `backend/routes/engines.py` | Authorized, atomic core-path selection and explicit retry request. |
| `backend/routes/clarification.py` | Save core answers and resume affected work. |
| `backend/routes/orchestration.py` | Supply configured adapters to administrator registry diagnostics. |
| `backend/services/agent_registry.py` | Register real core capabilities and distinguish availability from implementation. |
| `backend/services/core_workflow.py` | New worker lease, strict source synchronization, snapshot and status lifecycle. |
| `backend/services/ingestion.py` | Select core processing without requiring translation or retrying blocked speech services. |
| `backend/services/input_layer.py` | Backwards-compatible switches for original-language reasoning and pending media. |
| `backend/services/jobs.py` | Local Engine 1 job selector. |
| `backend/services/orchestrator.py` | Prior owned outputs for identity matching; preserve explicit blocked state. |
| `backend/services/overview.py` | Safe core/legality status and citizen clarification projection. |
| `backend/services/understanding_agents.py` | Seven new real production handlers and their contracts. |
| `backend/services/understanding_sources.py` | New original-source grounding, synchronization, date and identity helpers. |
| `backend/tests/core_test_support.py` | Explicit test-only model double. |
| `backend/tests/test_core_contracts.py` | Stage, approximate date, unknown party, evidence and clarification edge cases. |
| `backend/tests/test_core_permissions.py` | Ownership, duplicate dispatch, legacy-path guard and safe response tests. |
| `backend/tests/test_orchestration_integration.py` | Update registry expectation while preserving no-auto-execution tests. |
| `backend/tests/test_understanding_agents.py` | Production-handler DAG, retries, identity, conflicts, clarification and failure tests. |
| `backend/tests/test_understanding_sources.py` | Original-script, grounding, date, identity and source-version tests. |
| `frontend/src/citizenLanguage.js` | Distinguish case understanding from completed legal analysis. |
| `frontend/src/pages/EngineCasePage.jsx` | Show pending legal foundation and allow input/retry after core processing. |
| `tests/redesign/workflow.spec.js` | Browser assertion that mock core processing stays blocked/review-required. |
| `scripts/validate-phase3-core.py` | Explicit opt-in live fictional multilingual worker validation and resume. |
| `scripts/validate-phase3-router.py` | Explicit opt-in live router component checks. |
| `scripts/check-phase3-validation.py` | Read-only semantic routing, strict schema and source-offset regression checks. |
| `artifacts/phase3_core_validation.json` | Latest live results plus earlier failed/intermediate runs. |
| `artifacts/phase3_router_validation.json` | Eight live router component results. |
| `docs/phase3-core-report.md` | This report. |

## 3–4. Production capabilities and status labels

| Agent | REGISTERED | IMPLEMENTED | UNIT TESTED | LOCAL INTEGRATION VALIDATED | LIVE BEDROCK VALIDATED | BLOCKED / REVIEW REQUIRED |
| --- | --- | --- | --- | --- | --- | --- |
| CASE_STAGE | Yes | Yes | Yes | Yes | Yes, five language samples | Ambiguous procedural facts retain review. |
| FACT_TIMELINE | Yes | Yes | Yes | Yes | Yes, five language samples | Unsupported date normalization remains pending; all assertions unverified. |
| PARTY_RELATIONSHIP | Yes | Yes | Yes | Yes | Yes, five language samples | Unknown names and uncertain roles remain explicit. |
| EVIDENCE_MAPPING | Yes | Yes | Yes | Yes | Yes, no-upload live branch | Uploaded support/contradiction branches locally tested, not newly live-upload validated. |
| CLARIFICATION | Yes | Yes | Yes | Yes | Yes, actual pause/resume | Two batches maximum; unknown answers preserved. |
| RECONCILIATION | Yes | Yes | Yes | Yes | Yes, non-conflict live branch | Conflicts and protected overrides locally validated; no claim of live conflict-resolution validation. |
| DOMAIN_ROUTER | Yes | Yes | Yes | Yes | Yes, five languages and eight component cases | Uncertain domain retains review; corpus remains unready. |

The runtime registry's `live_validated` field remains false by default: an offline test report does not automatically attest an arbitrary deployment/provider configuration. The table describes the observed validation in this workspace. Provider availability is reported separately. Mock mode cannot silently substitute sample reasoning; only explicitly injected test doubles can run in tests.

## 5–6. Dependency graph and owned paths

```text
Original Raw Case Package, strictly synchronized
 ├─ CASE_STAGE ────────────────────────┐
 └─ FACT_TIMELINE                      │
     ├─ PARTY_RELATIONSHIP ────────────┤
     └─ EVIDENCE_MAPPING ──────────────┤
              └─ RECONCILIATION       └─ CLARIFICATION
                      └────────────────────┬───────┘
             PARTY_RELATIONSHIP ──────────┤
                                         └─ DOMAIN_ROUTER
                                              └─ Understanding snapshot
                                                 Legal foundation PENDING
```

| Agent | Owned Blackboard output paths |
| --- | --- |
| CASE_STAGE | `case_understanding.stage` |
| FACT_TIMELINE | `facts`, `incidents`, `timeline` |
| PARTY_RELATIONSHIP | `parties`, `relationships` |
| EVIDENCE_MAPPING | `evidence_mapping` |
| CLARIFICATION | `clarification` |
| RECONCILIATION | `reconciliation` |
| DOMAIN_ROUTER | `domain_classification` |

Contracts drive graph expansion, reads, ownership, stale propagation and scheduling. CASE_STAGE and FACT_TIMELINE can run concurrently. PARTY_RELATIONSHIP and EVIDENCE_MAPPING can run concurrently after facts. RECONCILIATION and CLARIFICATION can overlap once their individual prerequisites complete. DOMAIN_ROUTER waits for party, clarification and reconciliation outputs. All agents read the current raw fingerprint and their scoped human-input path.

## 7–11. Persisted record schemas

Authoritative strict schemas are in `understanding.py` and `understanding_outputs.py`.

- **Fact:** server `fact_id`, semantic key/identity anchor, proposition, category, source references/source IDs/actual evidence IDs, original date expression and precision, optional checked normalized date, literal values, certainty, support state, unverified/review flags, execution/board version, superseded/stale flags.
- **Incident:** server `incident_id`, semantic key/anchor, description, Fact IDs, original source references, date/precision, unknown fields, party references, review and execution metadata.
- **Timeline:** server `timeline_id`, Incident ID and the incident's supporting Fact IDs, source/date/precision and review metadata. Unknown and relative events do not acquire invented dates.
- **Party:** server `party_id`, original-script name or null, role, supporting Fact IDs/source references, unknown attributes, identity/review/execution metadata. Relationships reference existing Party IDs and Fact IDs.
- **Evidence mapping:** actual uploaded IDs, unverified support/contradiction links with source spans, per-fact support state, and separate available declarations, unavailable evidence, unknown evidence and unknown details. A declaration never creates an E ID.

Every source reference retains source ID, original offsets, original wording, source hash and optional actual Evidence ID. A provider can select an indexed passage; the server copies the original text. Supplied excerpts, names and exact values must match literally. Provider output is still an **unverified interpretation** of those sources: exact grounding does not prove semantic truth or authenticate an upload.

## 12. Clarification model

Questions carry a semantic topic, need category, affected facts/agents, priority, essential flag, simple question/control and stable question ID. The citizen projection excludes internal affected-agent lists and model reasoning. Answers support ANSWER, UNKNOWN, NOT_AVAILABLE and LATER.

Only essential high-priority core questions pause execution, at most three per batch and two batches. Document suggestions cannot block readable core understanding and require an existing availability declaration; invalid requests are suppressed with internal diagnostics. Explicit unknown facts and known procedural stages prevent unnecessary blocking questions. Prior topics and overlapping fact/need references suppress reworded repeats, alongside the model's contextual check.

Typed answers are additional human sources. UNKNOWN/unavailable/later answers update clarification without regenerating established facts. Concrete answers invalidate their declared affected paths and downstream consumers. Tests prove a domain-only answer does not rerun fact or party extraction. This is conservative semantic suppression, not a claim of perfect paraphrase detection for every language.

## 13. Reconciliation and conflicts

Incompatible assertions retain both Fact IDs, propositions and source references. The handler returns a conflict checkpoint, blocking downstream routing until a recorded human KEEP/REPLACE/MERGE decision. It does not choose a source as true. Existing Phase 2 CAS/version checks and protected fields remain authoritative. A local test exercises conflict creation, preserved claims, human resolution and resumed reconciliation.

Conflict mutation remains a trusted internal Phase 2 API. A new advocate conflict-resolution UI/API was not added in this phase; that workspace integration remains pending.

## 14. Domain schema

`primary_domain`, `primary_subdomain`, optional secondary domains, supporting Fact IDs and relationship IDs, confidence, ambiguity/review, reasons, execution ID, `legal_foundation=PENDING`, `legal_corpus_ready=false`.

Domains: CONSUMER, LABOUR_EMPLOYMENT, PROPERTY_TENANCY, CRIMINAL_POLICE, CIVIL_CONTRACT, RTI_ADMINISTRATIVE and OTHER_OR_UNCERTAIN. No statute, precedent or forum output contract is provided. Classification neither depends on a ready corpus nor launches a specialist team.

## 15–17. Stable IDs, reruns and overrides

Server-generated F/I/T/P IDs are matched by prior identity anchors, then unique semantic keys. New items receive monotonically increasing IDs; removed/unmatched records remain superseded and IDs are never recycled. Previous compact records are supplied to the provider so unchanged logical claims retain keys. Multiple distinct facts citing one paragraph remain distinct.

Ambiguous matches conservatively create reviewable records instead of silently merging them. Arbitrary model paraphrases can still produce superseded/new records; identity matching is not a universal semantic-equivalence guarantee. Tests verify reordered unchanged records, changed attributes with the same key, additions without renumbering and protected facts. Recorded live counts include historical superseded records after earlier experimental reruns.

Human-protected output cannot be overwritten by a rerun. Conflicting proposed values enter the existing review checkpoint. Persisted schemas are validated again after human conflict resolution before an agent publishes completion.

## 18–19. Orchestrator and worker integration

The explicit marker is `engine1_execution=ORCHESTRATED_CORE_V1`. Existing cases retain their working legacy path. New cases can opt in via `CASESEVA_ORCHESTRATED_CORE=true`; alternatively, the authorized `POST /api/cases/{id}/core-understanding` route selects it atomically for eligible cases. Existing legacy Case Files and running jobs cannot switch paths. The flag was not silently enabled in `.env`.

Local jobs and existing Lambda Engine 1 dispatch call the selector. Core processing prepares the current raw package, strictly synchronizes its version/evidence set/fingerprint, obtains a durable worker lease and starts the registered dependency graph. There is no second call to the legacy Engine 1 pipeline. Duplicate delivery cannot acquire the active lease. Existing node leases, claim tokens and version checks fence stale results.

Explicit retries reactivate failed work while preserving completed nodes. A bounded worker that cannot finish exposes a safe review/retry state rather than a permanent success or spinner. Snapshots reference the Blackboard version, raw-package version and output dependency versions. No completed legal Case File is fabricated.

## 20. Tamil refrigerator sample

The original Tamil fixture completed all seven handlers and routed to CONSUMER / NEW_CONSULTATION. Final stored counts: 31 facts, 5 incidents, 5 timeline records and 4 parties. Three evidence availability declarations were preserved; **zero evidence uploads** were invented. Two fictional clarification batches were explicitly answered UNKNOWN during live resume validation.

Initial runs failed because the model translated literal values, inserted inferred years into original expressions, or changed source quotations. These runs remain in the validation artifact. The final run passed strict schema, source-offset, domain and evidence checks after indexed selection and bounded correction improvements.

Tamil date expressions are retained verbatim. The date parser could not independently validate their ISO normalization, so normalized dates remain null with review required. Technician visit timing and defect cause remain unknown. This is a limitation, not a successful ISO-date normalization claim.

## 21–22. Cross-domain and live Bedrock results

| Typed sample | All seven completed | Domain / procedural stage | Stored F / I / T / P counts | Final public state |
| --- | --- | --- | --- | --- |
| English | Yes | CONSUMER / NEW_CONSULTATION | 15 / 3 / 3 / 3 | REVIEW_REQUIRED |
| Tamil | Yes | CONSUMER / NEW_CONSULTATION | 31 / 5 / 5 / 4 | REVIEW_REQUIRED |
| Hindi | Yes | CONSUMER / NEW_CONSULTATION | 25 / 10 / 10 / 3 | REVIEW_REQUIRED |
| Telugu | Yes | CONSUMER / NEW_CONSULTATION | 14 / 4 / 4 / 6 | REVIEW_REQUIRED |
| Tamil-English mixed | Yes | CONSUMER / NEW_CONSULTATION | 28 / 6 / 6 / 4 | REVIEW_REQUIRED |

These are fictional readable-text inputs with **real Bedrock reasoning and local persistence**. English/Hindi/Telugu/mixed stories share the refrigerator scenario; Tamil supplies a longer version. The equivalence check asserts the same domain and procedural interpretation, source fidelity, no invented uploads and pending legal foundation. It does not assert identical sentence-level extraction or fact counts.

Eight additional real router component calls passed: all six domains, uncertain input and a source-injected instruction to invent law/change classification. Those tests use explicitly authored grounded premises to isolate routing; they are not eight additional full case-pipeline validations. Secondary-domain structure is locally tested, not claimed live validated.

Model: `au.anthropic.claude-haiku-4-5-20251001-v1:0`, through the existing configured Bedrock adapter. Recorded core attempts including failed/intermediate runs: 109 responses, 751,770 input tokens, 118,468 output tokens. Router component checks: 8 responses, 10,766 input tokens, 2,057 output tokens. Combined: **117 recorded response attempts, 762,536 input tokens, 120,525 output tokens**. Transport retries without recorded responses are not included; these are observed usage counters, not a billing reconciliation.

Full fictional prompts, original sources and provider responses remain in ignored `.localdev/phase3-live/`; committed artifacts contain summaries. No production case content was used.

## 23–25. Verification

| Check | Result |
| --- | --- |
| Initial source tests | 7 passed. |
| Core/source/orchestrator/integration checkpoint | 54 passed. |
| Core permissions + security hotfix suite | 14 passed after fixing a missing safe overview field. |
| Expanded agent/contract/permission/security checks | 33 passed. |
| Final contract regression additions | 4 passed. |
| Full backend suite | 158 passed in the full suite; subsequent clock-independence guard validated by all 9 source tests. |
| Browser regression suite | 17 passed, including the new real blocked-status test; explicit mock test environment. |
| Frontend production build | Passed; Vite built 1,922 modules. |
| Python compile check | Passed. |
| Git whitespace check | Passed. |
| Offline recorded-live schema/source/equivalence check | Five language samples and eight router checks passed. |

Tests include protected advocate content, Output B isolation, nested scoped sharing, revoked grants and retired route tombstones from the accepted security baseline. Existing retired preview/approval endpoints remain authenticated 410 tombstones, not reopened processing paths. No Engine 2 or Engine 3 logic file changed.

Useful commands:

```text
npm run test:backend
npm test
npm run build --prefix frontend
.venv/Scripts/python.exe -B scripts/check-phase3-validation.py
```

The two `validate-phase3-*.py` scripts require explicit `--live` and make billed provider calls. Do not rerun them merely to read the saved results.

## 26. Capability labels and remaining limitations

| Capability | Actual status |
| --- | --- |
| Core understanding handlers | IMPLEMENTED, UNIT TESTED, LOCAL INTEGRATION VALIDATED. |
| Bedrock typed-text pipeline | LIVE CONNECTED and LIVE INPUT VALIDATED for the five recorded samples. |
| Browser/API workflow | END-TO-END VALIDATED locally with explicit test-mode providers; deployed live frontend-to-AWS regression not claimed. |
| Persistence | **LOCAL VALIDATED — DYNAMODB LIVE ACCESS BLOCKED BY AWS SCP.** Adapter/interfaces preserved; no retry or bypass attempted. |
| S3 | Previously live connected; not newly tested by these text-only Phase 3 runs. |
| OCR | Existing Phase 1 implementation/regressions preserved. No new OCR provider/language live validation; installed OCR language coverage is not universal. |
| Speech/transcription | Existing recording preserved; live service blocked by SCP as previously established. No retry attempted. |
| Other languages | Architecturally language-neutral; NOT LIVE VALIDATED. Unsupported readings pause for review. |
| Exact date normalization | English exact-date tests pass. Unvalidated Tamil forms remain original text plus review-required null normalization. |
| Legal knowledge | **LEGAL CORPUS READY: NO.** No verified-law or legal-completion claim. |

Provider output remains probabilistic. Semantic entity/event interpretation needs review even where exact source offsets pass. Strict validation can block a new input after bounded correction; no canned output replaces it. Long input beyond 160 passages/65,000 characters needs chunking/review instead of silent truncation. Core execution is opt-in. The complete citizen/advocate presentation of these new records, multilingual UI wording and a professional conflict-resolution workspace are not delivered by this core phase.

## 27. Phase 4 boundary and direct answers

All seven named production agents are registered and were actually executed by the dependency-driven Master Orchestrator. Independent branches can overlap as described above. Clarification can pause and resume affected work. Uploaded evidence remains separate from declarations. Routing works with legal corpus unavailable. An invented E ID or an overwrite of a protected advocate value is rejected or paused for review.

No statute/precedent retrieval or memory-generated law was accepted as established law. Full Engine 1 is **not legally complete**. Phase 4 still requires dynamic specialist/domain packs, legal issue identification, authoritative retrieval, citation verification, temporal applicability and the subsequent verified legal foundation. Those systems and Engine 2/3 migrations were not started.

**Stop after this Phase 3 report. Phase 4 requires explicit approval.**
