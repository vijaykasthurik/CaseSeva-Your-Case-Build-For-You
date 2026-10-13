# Phase 4 — Dynamic teams and verified legal foundation

Report finalized: 13 October 2026 (Asia/Calcutta). Recorded implementation and validation runs: 12 October 2026. Scope: Phase 4 only.

**Current status: PHASE 4 PARTIAL — INDEPENDENT ADMIN REVIEW REQUIRED.** Official retrieval now succeeded for four genuine government PDFs, producing 14 pending authority records. The review gate and immediate source invalidation checks are implemented. The user chose “Prepare the bundle for my admin review”; no review decision, identity or timestamp has been fabricated. No genuine-law proposition or Case File is yet validated. The Tamil case and all six specialist packs are preserved. **Sections 38–43 supersede earlier connectivity, regression and remaining-work statements; sections 1–37 describe the prior checkpoint.**

## 1. Accepted baseline

Verified starting HEAD: `851306b`. Security Hotfix and Phases 1–3 are preserved. DynamoDB and Transcribe were not retried. Engine 2/3 reasoning and document-generation implementations were not changed.

## 2. Phase 4 commits

- `3c8ef45`: dynamic specialist registration, issue planning, authority gates, worker continuation, permission/status integration and initial regression coverage.
- `c334cf1`: reviewed-authority revalidation, temporal foundation gate, current Case File publication and legacy Engine 2 isolation.
- `fbd5798`: immutable specialist artifacts, bounded snapshot migration, artifact security tests and concurrent-input guard.
- The validation/report commit is identified in Git history and the delivery message.

Commits are local on the existing `main` branch. No push, deployment, replacement database or paid infrastructure provisioning was performed. Existing untracked `output/` content was preserved.

## 3. Every changed or added file

Paths below are relative to the repository root.

| File | Change |
| --- | --- |
| `backend/adapters/real/official_sources.py` | Bounded official-host discovery download, redirect checks, extraction and hashes; downloads remain pending review. |
| `backend/models/legal_foundation.py` | Strict team, specialist, issue, authority and application candidates. |
| `backend/models/legal_outputs.py` | Persisted team, issue, citation and application validation. |
| `backend/routes/cases.py` | Permit supporting uploads while legal foundation needs review; block simultaneous input retries during legal processing. |
| `backend/routes/engines.py` | Authorized opt-in legal continuation/retry; prevent legacy Engine 2 consuming Phase 4 files. |
| `backend/routes/orchestration.py` | Administrator diagnostics use the case's dynamic registry. |
| `backend/services/agent_registry.py` | Optional granular output registration. |
| `backend/services/core_workflow.py` | Dispatch Phase 4 through the existing worker selector and isolate active plans. |
| `backend/services/legal_artifacts.py` | Immutable, case-bound specialist records; checked references and protected-field-preserving compaction. |
| `backend/services/legal_checks.py` | Retrieval, temporal, citation, application, jurisdiction, limitation and evidence-law gates. |
| `backend/services/legal_registry.py` | Dynamic dependency contracts and final foundation assembly. |
| `backend/services/legal_team.py` | Model-backed team/specialist/issue handlers, grounding and deduplicated original-language context. |
| `backend/services/legal_workflow.py` | Durable staged continuation, bounded retries, Case File publication and safe status. |
| `backend/services/orchestrator.py` | Explicit replacement of active plans, inactive-node fencing and granular map writes. |
| `backend/services/overview.py` | Safe legal status and suppression of outdated Phase 4 Case Files. |
| `backend/services/specialist_packs.py` | Six packs containing 38 named specialist capabilities. |
| `backend/services/verified_corpus.py` | Immutable source revisions, retrieval filters, granular readiness and case source fingerprints. |
| `backend/tests/legal_test_support.py` | Explicitly fictional authority and deterministic model doubles. |
| `backend/tests/test_legal_artifacts.py` | Artifact integrity, case isolation, protected fields and bounded compaction. |
| `backend/tests/test_legal_checks.py` | Temporal, citation, jurisdiction, limitation, evidence and reviewed-output regressions. |
| `backend/tests/test_legal_foundation.py` | Full local worker, six packs, missing corpus, source updates, resume and Case Files. |
| `backend/tests/test_legal_permissions.py` | Ownership, dispatch, safe projections and Engine 2 isolation. |
| `backend/tests/test_legal_team.py` | Selection, RTI conditions, stable issue IDs, Tamil originals and source-scoped updates. |
| `frontend/src/api.js` | Legal-foundation request helper. |
| `frontend/src/citizenLanguage.js` | Safe legal-processing and review status messages. |
| `frontend/src/pages/EngineCasePage.jsx` | Opt-in source check, retry state and separate Engine 2 availability. |
| `scripts/validate-phase4-foundation.py` | Bounded fictional live validation with resume and reused Phase 3 checkpoints. |
| `artifacts/phase4_live_validation.json` | Recorded live outcomes, failures, token counts and limitations. |
| `docs/phase4-legal-foundation-report.md` | This report. |

## 4–7. Team builder, selection model, agents and packs

The existing Master Legal Orchestrator remains the scheduler. The model chooses catalog keys using supported Fact IDs and domain context. Unknown agents, unsupported domains, duplicate selections and invented IDs fail validation. A selected team becomes a dependency graph; unselected specialists do not execute.

| Pack | Registered specialist capabilities |
| --- | --- |
| Consumer (6) | Consumer Domain; Transaction; Product Defect; Warranty/Refund/Replacement; Consumer Evidence; Consumer Remedy |
| Labour/Employment (6) | Labour Domain; Employment Relationship; Wage Entitlement; Employment Document; Wage Evidence; Employment Remedy |
| Property/Tenancy (7) | Property Domain; Ownership/Title; Property Document; Land Records; Possession; Boundary/Survey; Rent/Deposit |
| Criminal/Police (8) | Criminal Domain; Criminal Incident; Offence Mapping; FIR/Complaint; Legal Ingredient; Digital Evidence; Medical Evidence; Witness |
| Civil/Contract (6) | Contract Relationship; Clause; Performance/Breach; Payment; Damages/Relief; Notice |
| RTI/Administrative (5) | Public Authority; RTI Eligibility; Request Structuring; Exemption Risk; RTI Appeal Foundation |

All 38 have registered model-backed handlers with distinct task instructions; they are not 38 separately trained models. Their initial outputs are factual questions and observations with `PENDING_SOURCE`, not verified legal conclusions. Statutory application happens after independent retrieval and verification. Boundary/survey, rent/deposit, medical, digital and witness selection is model-driven using supported facts; this is not an independently verified semantic classifier.

Secondary RTI requires a stated reason, supported public-record Fact IDs and references to actually unavailable records. An uploaded record cannot satisfy that unavailable-record gate. The model's assessment that a record is necessary/public remains reviewable. Uncertain primary domains pause for review.

## 8. Legal issue schema

Issues contain stable server IDs (`L001` onward), semantic keys, statement/category/domain, supporting and contradicting Fact IDs, Party/Evidence IDs, date facts, specialist origins, retrieval query, jurisdiction grounding, optional limitation/precedent flags, unknowns, fingerprint/version and supersession. Repeated unchanged issues keep their IDs/version. Duplicate keys and invented references fail closed. At most four issues are processed per pass; an explicit further-issues flag prevents silent completion when more issues need review.

## 9–11. Source schema, architecture and hierarchy

Authority records carry source/family/type, domain/jurisdiction, title, section or court/citation, registered HTTPS URL, original language/text, exact quotation offsets, hashes, retrieval timestamp, effective interval, temporal supporting records, corpus version and independent review metadata. A working translation does not replace the original.

The existing `LegalKnowledge` registry and database interface are reused. Immutable authority versions have separate current heads. Specialist artifacts and legal Case Files also use the same database interface; there is no replacement persistence architecture or new cloud infrastructure.

Only enabled, reviewed PRIMARY registry records with matching text, identity, quote, hash and freshness can pass the authority gate. Unreviewed/secondary/discovered text remains pending. Existing consumer/labour summaries were not promoted to authority. Automated nationwide source ingestion, judgment treatment history and maintained state-specific coverage are not complete.

## 12–14. Retrieval, hybrid search and embeddings

Implemented retrieval is Unicode lexical overlap over title/excerpt, filtered by domain, jurisdiction and source type, returning versioned candidates. Temporal supporting documents participate in dependency fingerprints. No keyword match alone verifies a legal proposition. Candidate limits are bounded.

**No vector index, hybrid retrieval, Legal-BERT or embedding service was implemented or claimed.** Cross-language semantic retrieval against a populated multilingual legal corpus still requires live validation. Runtime retrieval searches the reviewed local corpus; the separate official downloader does not silently publish scraped text.

## 15. Temporal law

Non-judgment authority needs exact, non-conflicted event dates, reviewed effective intervals and verified temporal supporting records. Unknown/approximate dates remain pending. Pre-commencement and post-expiry dates are not applicable; mixed intervals require review. Full historical statutory transition mappings, including criminal-law transitions, await corpus curation.

## 16. Jurisdiction and remedy

The handler uses reviewed, quoted source rules. Jurisdiction needs grounded location facts. Conditional rules require a review decision tied to the source version and required factual inputs. Missing forum/remedy bases remain review-required. No universal forum or amount threshold is invented. Interpretation remains advocate-reviewable even when source support is verified.

## 17. Limitation

Only selected issues invoke limitation. A computation requires a reviewed source rule, an exact non-conflicted trigger from that issue's date facts, source-version-bound review and reviewed exclusions. Missing/ambiguous triggers produce no deadline. Conflicting computations require review. No production limitation rule set has been independently curated yet.

## 18. Precedents

Selected issues may retrieve judgment candidates. Verification checks official identity, court, citation, original text, current source revision and freshness. Fake judgments fail. Citation existence is not a finding that a decision is binding, still good law or applicable. Production court hierarchy, subsequent treatment and ratio analysis remain pending source coverage; no live precedent proposition was established.

## 19. Citation verification

Fabricated titles, sections, citations, quotes, hashes, stale source versions, mismatched domains/jurisdictions and missing temporal support are rejected or held pending. Application output is independently revalidated at the persisted-output boundary, including after human conflict resolution. Model confidence cannot establish authority.

## 20. Evidence-to-law mapping

Each quoted legal element maps to specific supporting/contradicting Fact IDs and unknowns. Unmapped elements are not assigned every case fact. Fact support remains distinct from legal-element satisfaction, which requires advocate review. Declared, unavailable and unknown evidence retain separate references to existing evidence records; no upload is invented.

## 21. Legal foundation

The foundation records per-issue readiness, verified source IDs, grounded fact/evidence IDs, law excerpts, unresolved issues, further-issue review, understanding/team references and execution provenance. A handler finishing with pending findings is not legal completion. At least applicable non-judgment authority and the relevant temporal, jurisdiction, evidence and limitation gates are required for Case File readiness.

## 22. Versioned Engine 1 Case File

An immutable Case File is produced only after the foundation gates pass and unresolved protected-field conflicts are absent. It records input/board/dependency versions, source revisions and an advocate-review requirement. Snapshot publication is idempotent and the Blackboard receives provenance. Citizens receive an explicit safe overview; pending/outdated Phase 4 files are hidden. The complete path was validated with **fictional test authority only**, not live production law.

## 23. Targeted staleness

Issue-level source fingerprints include matching source revisions, temporal dependencies and freshness. Tests show an unrelated source/query does not invalidate another issue and a source update does not rerun core understanding or specialists. Issue output maps use granular writes; changed optional branches receive distinct contract identities.

**Remaining engineering gap:** inherited whole-map core writes and transitive invalidation can conservatively rerun more legal work after fact changes than the ideal per-fact minimum. Precise semantic reuse across those existing contracts is not complete. The current behavior favors invalidation over stale legal output; it is not reported as fully optimized targeted staleness.

## 24–25. Restart, resume and advocate protection

The existing scheduler supplies dependency eligibility, claims, leases, version fencing, bounded retries, parallel eligible handlers and persisted checkpoints. Explicit retry resets failed work without replaying successful live specialists. Replaced plans deactivate obsolete nodes and fence their claims. KEEP/REPLACE/MERGE protection continues through the existing conflict mechanism; Phase 2/3 protection regressions pass.

Large specialist results now have immutable case-bound references. Integrity/case checks reject tampering or cross-case references. Existing protected specialist content is not compacted or overwritten. The original immutable snapshot retains prior values, avoiding duplication in compaction audit events.

The local JSON adapter becomes slow as snapshot history grows. The final resumed Tamil run took 572.2 seconds and used one additional model call. Its final Blackboard was 252,040 bytes, below the unchanged 300,000-byte snapshot guard before wrapper/event overhead. Larger-case performance and capacity remain production-hardening work; DynamoDB was not used to conceal this limitation.

## 26–28. Languages, cross-domain tests and Tamil result

Original Tamil excerpts are deduplicated, not replaced by translations. Tests assert original text preservation. Domain routing is not a hard-coded English keyword switch.

Six domain packs passed deterministic selection/worker tests with explicit model doubles. This proves contracts and execution selection, **not live legal expertise across six domains**. Full cross-domain live authority validation remains pending.

The fictional Tamil refrigerator case reused its recorded Phase 3 understanding. Real Bedrock selected Transaction, Product Defect, Warranty/Refund/Replacement, Consumer Evidence and Consumer Remedy; five specialists completed and four stable legal issues were created. All active handlers eventually finished, but authority-dependent outputs remained pending. Final case status: `LEGAL_CORPUS_NOT_READY`; `legal_foundation_status=REVIEW_REQUIRED`; no Case File; no verified live law; no Engine 2/3 execution.

The validation record accounts for 11 application-level model calls (181,166 input tokens and 23,410 output tokens); no monetary cost is inferred. Provider transport retries are not separately counted. Live failures were retained in the validation record: invalid agent display names/length limits, an observation-count limit, and snapshot capacity. Catalog-enumerated selection, bounded schema adjustments and immutable artifact references addressed the observed code failures. Resume reused successful reasoning. A completed handler label never converts missing corpus coverage into successful legal verification.

## 29–30. Authoritative-source and fabrication validation

One bounded download from the official India Code PDF URL timed out. It was recorded as `BLOCKED`, not LIVE CONNECTED or SOURCE VERIFIED. Source registry enable/review flags were not fabricated. No downloaded document was promoted to law.

Local tests cover title/section/quote/citation mismatch, invented judgment court/citation, content hashes, section offsets, unreviewed registries, freshness, wrong jurisdiction/domain, historical intervals and missing temporal support. These use explicitly fictional `example.test` authority isolated in temporary databases.

## 31–33. Test and build results

- Existing orchestrator/Blackboard checks: **35 passed**.
- First complete backend regression: **185 passed**.
- Subsequent complete backend regression: **193 passed** in 320.820 seconds.
- New immutable-artifact regressions added afterward: **4 passed**.
- Final Phase 4 regression across foundation, checks, permissions, team and artifacts: **38 passed** in 417.070 seconds.
- Browser regression (`npm test`): **17 passed**; explicit development/mock backend, not live legal verification.
- Frontend (`npm --prefix frontend run build`): **passed**.
- Targeted checks during development: 10 foundation; 16 checks/permissions; 6 team; 25 permissions/core/orchestration; 23 checks/security; 16 foundation/team; 25 publication/permissions/checks/team; 20 publication/checks/team — all passed on their tested checkpoints. Earlier aggregate fixture execution was stopped and rerun after isolating per-domain test databases; it was not counted as a pass.
- Final permission/common-input regression after the concurrent-input guard: **21 passed**.
- `git diff --check`: passed at final delivery.

The 193-test full regression preceded the final reference-storage adjustment; the final Phase 4 suite and four artifact tests validate that adjustment. No claim is made that browser tests used real Bedrock or verified legal sources. Security coverage retains private Output B/internal-note exclusion, scoped nested content restrictions, revoked access denial, retired-route tombstones and safe technical-error projection.

## 34–35. Live services and blockers

| Capability | Status in this phase |
| --- | --- |
| Bedrock | LIVE CONNECTED; LIVE INPUT VALIDATED for Tamil selection/specialists/issues, with recorded retries and limits |
| Local persistence | LOCAL VALIDATED through existing adapter |
| DynamoDB | **LOCAL VALIDATED — DYNAMODB LIVE ACCESS BLOCKED BY AWS SCP**; adapter preserved; no retry |
| Transcribe | Prior AWS SCP blocker preserved; not retried |
| India Code download | BLOCKED by timeout during this validation |
| Reviewed production legal corpus | NOT READY; no live authority established |
| S3/STS | Prior accessible-service results preserved; not independently retested in Phase 4 |
| Gazettes / judgments | No live ingestion or proposition validation claimed |

No organization policy, IAM permission, database design or infrastructure was changed to bypass a blocker.

## 36. Readiness by domain/source

| Domain or source family | Registration/implementation | Legal corpus readiness |
| --- | --- | --- |
| Consumer | 6 specialists and generic legal checks implemented/tested; 5 specialists live validated | NOT READY; legacy summaries remain unverified; official download timed out |
| Labour/Employment | 6 specialists registered/implemented; deterministic tests | NOT READY; reviewed applicable versions/rules missing |
| Property/Tenancy | 7 specialists registered/implemented; deterministic tests | NOT READY; state, record and statutory coverage missing |
| Criminal/Police | 8 specialists registered/implemented; deterministic tests | NOT READY; historical/current statutory transition corpus missing |
| Civil/Contract | 6 specialists registered/implemented; deterministic tests | NOT READY; reviewed provisions/remedies and relevant precedent coverage missing |
| RTI/Administrative | 5 specialists registered/implemented; deterministic tests | NOT READY; reviewed authority/procedure/exemption corpus missing |
| India Code registry | Existing PRIMARY registration retained, disabled/unreviewed | BLOCKED/PENDING; no verified imported provisions |
| Gazette registry | Existing PRIMARY registration retained, disabled/unreviewed | PENDING; no reviewed commencement/amendment records |
| Supreme Court registry | Existing PRIMARY registration retained, disabled/unreviewed | PENDING; no verified judgments or treatment history |
| Other configured legal domains | Existing registry entries preserved | PENDING; not silently mapped to Consumer/Labour |

Labels are distinct: **REGISTERED** describes discovery; **IMPLEMENTED** describes code; **UNIT TESTED** and **LOCAL INTEGRATION VALIDATED** describe deterministic checks; **LIVE VALIDATED** applies only to the specific provider behavior observed. **SOURCE VERIFIED**, **END-TO-END VALIDATED with real law**, and **LEGAL CORPUS READY** are not claimed for production. Human interpretation remains **REVIEW REQUIRED**.

## 37. Exact remaining work before Engine 2

Within Phase 4: acquire and independently review official authority records; establish version/temporal/state/court coverage; validate live applications, jurisdiction, limitation and precedents against that corpus; broaden live cross-domain cases; complete fine-grained fact-change reuse; validate larger-case performance and capacity. These remain explicit requirements, not completed features.

Engine 2 itself remains a separately approved phase: consume the current source-backed Case File, implement the adversarial closed loop and evidence challenges under current permissions, preserve advocate-only arguments, and verify rerun/staleness behavior. The legacy Engine 2 route is blocked for Phase 4 cases so it cannot substitute for that work. Engine 3 and professional document work remain outside this phase.

Stop after this report. No subsequent implementation phase is authorized by this delivery.

## 38. Continuation: independent review and genuine source acquisition

Continuation baseline: `5a1ca39`; implementation checkpoint: `b85a9e6`; genuine-source bundle and validation checkpoint: `92c418a`. Scope remains Phase 4 only. The user explicitly selected preparation of the bundle for their admin review. Source approval has therefore **not** been performed on the user's behalf.

| Label | Observed result |
| --- | --- |
| IMPLEMENTED | Persisted official-ingestion lifecycle, bounded retry, canonical/final URLs, hashes and original text; authenticated independent admin review; immutable review receipts bound to source content; current-source and temporal-support manifests on published Case Files; citizen/shared read-time revalidation; explicit capacity review stop. |
| UNIT TESTED | Review authorization, self-review rejection, fake review metadata, original-download binding, source revision/freshness/revocation/support removal, negative citations, artifact integrity and bounded large outputs. Fictional test authorities remain explicitly test-only. |
| LOCAL INTEGRATION VALIDATED | Existing local database adapter, deterministic foundation/publication workflow, all six packs and permission regressions. No database replacement. |
| LIVE BEDROCK VALIDATED | Prior Tamil five-specialist/four-issue checkpoint reused unchanged. New RTI team, three specialists and four issues completed in five calls: 13,286 input and 5,283 output tokens. This is a Phase 4 component run over the existing authored RTI premise and recorded domain classification, not a new full Phase 3 case. |
| OFFICIAL SOURCE LIVE CONNECTED | Four original government PDF downloads succeeded: three Department of Consumer Affairs documents and one Central Information Commission RTI compilation. Original extracted text, raw/text SHA-256, canonical/final URLs and retrieval timestamps are persisted. India Code attempts remain recorded retryable timeouts. |
| SOURCE VERIFIED | **Zero genuine records.** Fourteen records passed mechanical identity checks and await independent review. No downloaded source was automatically approved. |
| REAL-LAW CASE FILE VALIDATED | **No.** Publication and hiding are tested with fictional authority only. Genuine-law positive temporal/citation/jurisdiction/publication acceptance is still blocked by review and missing case facts. |
| LEGAL CORPUS COVERAGE | Consumer: nine pending candidates. RTI: five pending candidates. Neither acceptance corpus is READY. All other domains and nationwide coverage remain NOT READY. |
| BLOCKED | Genuine-source positive acceptance requires actual review, supported temporal metadata and source-bound applicability. The undated/location-unknown RTI fixture cannot establish a forum or deadline. No genuine judgment path has been validated. |
| REVIEW REQUIRED | User/admin review of exact PDF excerpts, version/amendment coverage, temporal scope and structured rules. Legal interpretation and case evidence remain advocate-reviewable. |

Persistence label: **LOCAL VALIDATED — DYNAMODB LIVE ACCESS BLOCKED BY AWS SCP.** DynamoDB and Transcribe were not retried. No S3/STS revalidation, organization changes, deployment or Engine 2/3 implementation occurred in this continuation.

### Actual official documents and candidate coverage

| Original official download | Pending records | Important review requirement |
| --- | --- | --- |
| [Consumer Protection Act 2019, issuing department PDF](https://consumeraffairs.gov.in/public/upload/files/CP%20Act%202019_1732700731.pdf) | `cpa2019_s2_7`, `cpa2019_s2_10`, `cpa2019_s2_11`, `cpa2019_s34`, `cpa2019_s39`, `cpa2019_s69` | Original enactment text, not a claim of current consolidated law. Check exact extraction, exclusions and amendments. The original section 34 amount cannot be used independently of the later jurisdiction rules. |
| [S.O. 2351(E), commencement notification](https://consumeraffairs.gov.in/public/upload/files/Act%20into%20force_1732702865.pdf) | `cpa_commencement_2351` | Candidate 20 July 2020 date is grounded in the actual notification, but applies only to its listed provisions and exclusions. `temporal_reviewed` remains false. Department-hosted Gazette text does not prove live eGazette connectivity. |
| [G.S.R. 912(E), jurisdiction rules 2021](https://consumeraffairs.gov.in/public/upload/files/232278_1732705029.pdf) | `cpa_jurisdiction2021_r1`, `cpa_jurisdiction2021_r3` | Rule 1 links commencement to publication. Header/notification say 30 December; digital upload/signature identifier says 31 December. Effective date is intentionally unresolved for admin review; no date was guessed. |
| [RTI Act, official CIC compilation](https://cic.gov.in/sites/default/files/RTI_English.pdf) | `rti2005_s1`, `rti2005_s3`, `rti2005_s6`, `rti2005_s7`, `rti2005_s19` | Compilation identifies its version as 18 November 2025. Review commencement under section 1(3), immediate versus delayed provisions and relevant amendment history. No deadline follows from the existing fixture's unknown application date. |

All four final URLs matched the canonical URLs. Hashes, retrieval times, source IDs and immutable draft revision IDs are in [the review manifest](../artifacts/phase4_authority_review_manifest.json). The two failed India Code requests also remain listed there; they were not converted into source records. All registry-wide `enabled`/readiness settings remain false. Record-specific admin approval does not enable legacy summaries or other records.

### Review handoff

The concrete local bundle is [REVIEW.md](../.localdev/phase4-authority-review/REVIEW.md), with exact extracted excerpts and original PDF links. [review-records.json](../.localdev/phase4-authority-review/review-records.json) contains full source text, offsets and draft metadata. The existing local database adapter stores these in `.localdev/phase4-authority-review/database.json`; this isolated validation database is not automatically copied into the running application's database.

The review backend exposes authenticated admin-only `GET /api/admin/authorities`, `POST /api/admin/authorities`, and `POST /api/admin/authorities/{source_id}/review`. The last accepts `expected_version`, `decision` and `note`; identity/time are derived from the authenticated persisted administrator and server clock. A configured extra admin token is enforced. No account was created/promoted or credential copied into the bundle. An authorized application instance must use the validation database (or deliberately import its pending source/ingestion records) before that API can review these particular revisions. This handoff is an API/internal workflow; a new admin review UI is not claimed.

Before approval, correct unresolved temporal/rule metadata by submitting a new revision. The exact reviewed revision must then be approved by an independent administrator; the submitter cannot approve their own revision. A changed revision requires another review. No reviewer-supplied name or timestamp is accepted. Reject/stale decisions revoke current usability. Historical decisions remain available for audit.

## 39. Case continuity, staleness and capacity findings

**Tamil refrigerator:** no Phase 3, team, specialist or issue generation was rerun. Focused retrieval/temporal/citation handlers were executed against the existing four issues and the new pending corpus without mutating the saved case. Their decisions establish no law. Unknown technician date, unknown defect cause, absent evidence and unknown seller/location facts remain unresolved. The saved case retains `LEGAL_CORPUS_NOT_READY`; no Case File was generated. This continuation is not a full worker rerun or genuine-law end-to-end success.

**Second domain:** reused the exact RTI premise from `scripts/validate-phase3-router.py` and its recorded successful domain classification. Real Bedrock selected `PUBLIC_AUTHORITY`, `REQUEST_STRUCTURING` and `RTI_APPEAL_FOUNDATION`, then produced four RTI issues. The fixture does not state a location or submission date; all issues correctly retain unknown jurisdiction, so case-specific retrieval is gated. A separate explicit national-jurisdiction filter probe returns only RTI candidates for RTI and only Consumer candidates for Consumer. That probe does not manufacture a jurisdiction fact in the case. Findings are recorded in [the pending-source validation artifact](../artifacts/phase4_pending_authority_validation.json).

**Read-time invalidation:** new Case Files store exact authority revisions, including transitive commencement dependencies. Both citizen projections and scoped advocate sharing validate the current manifest. Expired text, changed revision, rejected/stale review, missing temporal support or absence of a validation context hides the file immediately, even if a cached case flag still says current. Assembly validates authority before reusing an existing Case File. Historical files without a manifest are conservatively hidden until rebuilt. These positive/negative publication checks currently use fictional test authorities; real-law publication is not claimed.

**Targeted reuse:** changing a matched source changes only matching `corpus_inputs.<issue>` fingerprints; unrelated fingerprints remain unchanged. A leaf-fact dependency regression proves Fact A invalidates its application while a separately declared Fact B application and citation stay current. **Full core-to-team-to-issue invalidation remains conservative:** whole-map Phase 3 outputs and team/planner dependencies may rerun more work. There was no Phase 2/3 scheduler rewrite, and the isolated leaf test is not a claim of complete per-fact reuse through the whole graph.

**Capacity:** the preserved live Tamil board remains 252,040 bytes against the unchanged 300,000-byte checkpoint limit (the saved wrapper/event consumes additional space). A new twelve-specialist multilingual synthetic case holds more than 300,000 bytes of original output through immutable references and round-trips every observation unchanged. An intentionally oversized inline write raises a typed capacity failure and leaves the committed head unchanged. Worker capacity failures produce `LEGAL_FOUNDATION_REVIEW_REQUIRED`, internal `legal_capacity_review_required=true`, and no Case File. Public messages remain safe. Large inline legal applications can still need capacity review; no universal large-case completion or silent truncation is claimed.

## 40. Final verification for this continuation

The final complete backend run passed **207 tests in 446.322 seconds**, after all implementation changes. The saved terminal log ends in `OK`. Earlier 193-test results are historical and are **not** the final regression for this continuation. No application or test code changed after this run; only this report was finalized.

| Check | Result |
| --- | --- |
| Focused authority/checks/corpus/team/artifact suite | 33 passed after fixing the test download's raw-hash fixture. |
| Foundation worker and Phase 4 permission suite | 12 passed in 203.276 seconds. |
| Final focused authority/artifact/team/capacity checks | 20 passed in 8.333 seconds. |
| Complete backend suite after implementation changes | **207 passed in 446.322 seconds**, `python -B -m unittest discover -s backend/tests -t . -q`; includes Phase 1/2/3/4, permission/security, authority/citation and artifact tests. |
| Browser regression: `npm test` | 17 passed in 56.6 seconds; existing local development/mock browser configuration, not live-law acceptance. |
| Frontend production build | Passed, Vite 6.4.3, 1,922 modules. |
| Python compile/import | All 150 backend/script Python files compiled in memory; application and changed service imports passed. |
| `git diff --check` | Passed. |

Intermediate failures were a missing import of the new fictional review helper (22-test run: one error) and a mock download fixture's inconsistent raw hash (29-test run: one error). Both were fixed and their focused checks passed. Neither was worked around by weakening production review. Network failures were preserved separately as retryable requests. No new Bedrock call was spent on source application while its required review gate was closed.

## 41. Every changed/added file in this continuation

| File | Purpose |
| --- | --- |
| `backend/adapters/real/official_sources.py` | Bounded retries, final destination validation, download-stage callback and retrieval hashes. |
| `backend/models/legal_foundation.py` | Explicit lifecycle, ingestion reference and server-owned review metadata. |
| `backend/services/authority_review.py` (new) | Persisted ingestion, identity checking, independent admin decisions and immutable receipts. |
| `backend/services/verified_corpus.py` | Exact receipt/content matching, per-record identity and subsection checks, revision CAS and granular readiness. |
| `backend/routes/authorities.py` (new) | Authenticated admin-only pending-source submission/list/review. |
| `backend/main.py` | Register review routes. |
| `backend/registries/sources.json` | Register exact Consumer Affairs/CIC official hosts for discovery; global readiness remains disabled. |
| `backend/services/legal_visibility.py` (new) | Source/temporal manifests and immediate read-time hiding. |
| `backend/services/legal_workflow.py` | Revalidate before Case File reuse, record manifests and explicit capacity review. |
| `backend/services/case_blackboard.py` | Typed capacity exception; unchanged size guard, persistence and invalidation algorithm. |
| `backend/services/overview.py` | Database-aware citizen projection and safe review status when a source is no longer current. |
| `backend/services/sharing.py` | Database-aware scoped Case File projection. |
| `backend/routes/cases.py`, `backend/routes/engines.py`, `backend/routes/advocates.py` | Pass existing database context into public/shared projections. |
| `backend/tests/legal_test_support.py` | Explicit fictional ingestion/admin-review fixture through production gate. |
| `backend/tests/test_authority_review.py` (new) | Review, ingestion, receipts, redirects, invalidation and admin-permission regressions. |
| `backend/tests/test_legal_foundation.py`, `backend/tests/test_legal_checks.py` | Migrate fixture authorities through review; retain negative checks and add capacity status regression. |
| `backend/tests/test_legal_team.py` | Reviewed fixture source changes and isolated leaf-fact invalidation regression. |
| `backend/tests/test_legal_artifacts.py` | Twelve-specialist multilingual payload and over-capacity atomicity check. |
| `scripts/prepare-phase4-authority-review.py` (new) | Deterministically prepare genuine downloaded pending excerpts; never approve them. |
| `scripts/validate-phase4-authority-candidates.py` (new) | Reuse Tamil understanding; check pending corpus and bounded optional RTI component calls. |
| `artifacts/phase4_authority_review_manifest.json` (new) | Public-source provenance, candidate revisions and preserved timeout requests. |
| `artifacts/phase4_pending_authority_validation.json` (new) | Actual pending-source checks and focused live RTI results. |
| `docs/phase4-legal-foundation-report.md` | Updated findings, evidence, limits and handoff. |

Generated, ignored local files: validation database and lock files, review-records JSON, REVIEW.md, RTI component/provider logs, backend/browser logs and ordinary build/test output. Raw provider prompts/logs remain local. Existing untracked `output/` content is untouched.

## 42. Explicit acceptance answers

1. **Genuine records independently reviewed:** none yet; 14 genuine candidates prepared for the user's admin review.
2. **Exact URLs/families:** the four Consumer Affairs/CIC links in section 38; two timed-out India Code URLs are retained in the manifest. No unrelated websites were promoted.
3. **SOURCE VERIFIED propositions:** zero genuine propositions; all remain pending.
4. **Consumer acceptance Case File:** not produced.
5. **Genuine law versus fixture publication:** successful publication tests use clearly fictional authority. No genuine-law publication claim.
6. **Second domain:** RTI/Administrative official source download and live Phase 4 team/specialist/issue components succeeded; reviewed legal-source acceptance remains pending.
7. **Domains not corpus-ready:** all six. Consumer/RTI have a narrow pending acceptance bundle; Labour, Property, Criminal and Civil lack reviewed acceptance coverage. Nationwide corpus is not ready.
8. **Reviewed temporal dates:** no genuine date approved. Consumer commencement date is source-grounded but unreviewed. Rules/RTI effective dates remain unresolved. Applicable/out-of-range/unknown-date tests pass with fictional authority only.
9. **Reviewed jurisdiction/remedy:** not with genuine approved authority yet. Genuine rule/remedy excerpts are staged; source-bound interpretation and case facts still require review.
10. **Limitation:** no live deadline generated. Existing exact-trigger/source-version/exclusions tests remain; the undated RTI premise and unknown technician date do not become artificial deadlines.
11. **Fabrications rejected:** wrong title/Act, section, quote, citation, hash, jurisdiction, stale revision and invented judgment remain covered by regression checks. No fabricated judgment was used for live acceptance.
12. **Source revision targeting:** matching issue fingerprints change; unrelated source/issue fingerprints are preserved. Read-time manifests immediately hide dependent files. Full per-fact core propagation still conservatively over-invalidates.
13. **Final complete backend count after latest changes:** **207 passed**, zero failures/errors, 446.322 seconds. The old 193-test result is not used.
14. **Browser:** 17/17 passed.
15. **Frontend build:** passed.
16. **Before Engine 2:** independent review; resolve amendment/commencement/rule metadata; obtain missing jurisdiction/date/evidence facts without invention; prove genuine positive temporal/citation/jurisdiction/conditional-limitation and foundation/publication paths, second-domain legal acceptance and real-source invalidation; refresh final regressions after any further changes. Precedents remain pending unless actually needed and genuinely verified.

## 43. Stop gate

**Phase 4 remains PARTIAL / REVIEW REQUIRED.** The next action is review of the prepared bundle, not Engine 2. No Engine 2 or Engine 3 implementation began. No claim is made that review approval alone will resolve the Tamil case's missing facts or guarantee publication.


## 44. Revision-request continuation — 13 October 2026

This section supersedes the earlier review-API gap and regression counts for the current continuation. Scope is the user's revision-request workflow and inactive correction for record 1. Engine 2/3 and other phases were not started.

**IMPLEMENTED:** persisted `NEEDS_NEW_REVISION` receipts and separate `REVISION_REQUESTED` status, while preserving `REVIEW_PENDING`/unusable authority; server-owned reviewer/time; immutable revision/receipt history; parent/request lineage on corrected submission; fresh independent approval; inactive draft preparation; rejection of another submitter's draft attribution; admin-only history; existing local account-database connection with no provisioning or promotion.

**UNIT TESTED:** fixture-based authentication, revision requests, immutable history, corrected revisions, self-review rejection, old pending/new pending usability, inactive draft blocking, identity/time payload rejection, stale request replay, role revocation, absent admin refusal, draft attribution and compatibility with prior receipt signatures. Fictional test admins exist only in temporary test databases; none were created in the actual review/application data.

**LIVE CONNECTED:** no new cloud/service claim in this continuation. The account bridge was exercised with temporary local application accounts, not a real administrator. No formal receipt was recorded for the user's decision. No new AWS/Bedrock calls, DynamoDB retry, policy change, replacement database or credential import occurred. Persistence remains **LOCAL VALIDATED — DYNAMODB LIVE ACCESS BLOCKED BY AWS SCP**.

**LIVE INPUT VALIDATED:** existing genuine downloaded text retained. All 14 current candidates still pass identity/hash/boundary checks and remain unusable pending review. Focused retrieval/temporal/citation checks on the saved Tamil case's four issues establish zero verified citations. The authority database and saved case were byte-unchanged by these read-only checks. This is a negative-gate validation, not a positive legal acceptance.

**END-TO-END VALIDATED:** local browser regression only; authenticated real-admin review and genuine-law legal completion remain pending.

**LEGAL CORPUS READY:** NO. Current amendment coverage and provision-specific commencement for record 1 remain unresolved. Corrected metadata describes those gaps explicitly; it does not resolve them by assertion. Genuine positive citation, temporal applicability, remedy/jurisdiction, supported limitation, Consumer/RTI legal acceptance, real-source staleness and conditional Case File publication remain gated on independent review and sufficient case facts.

### Record 1 and authentication handoff

See [revision workflow and exact correction](phase4-revision-request-workflow.md) for complete old/new fields, exact unchanged excerpt and safe PowerShell commands. [The comparison artifact](../artifacts/phase4_record1_revision_draft.json) includes all 14 pending-state checks. Current head remains `d9804b732b3d855c06cf5c0143b721a5e9d0ad775092810c2f236150a51a024e`; inactive draft is `a36240fa45fbaa6d553f77f5f7824de82d6961c2b38df27c0235df74f946239e`. Neither is approved. The new draft has no authenticated submission event or formal review receipt. Earlier inactive preparation history is retained and explained in the handoff.

The isolated authority database has zero users and zero formal receipts. The review server can use an existing local application's password-authenticated admin without copying users or roles; login/logout creates ordinary sessions in that identity database. The current normal signup supports only client/advocate. There is no supported admin-creation command. If no genuine admin exists in another application database, an explicitly authorized provisioning workflow is the remaining blocker. No role-edit workaround or fabricated admin was introduced.

### Validation in this continuation

| Check | Result |
| --- | --- |
| Initial authority/revision/checks/corpus focused run | 26 passed in 11.245 seconds. |
| Focused run after external-account bridge | 28 passed in 14.497 seconds. |
| Final focused suite including draft attribution/receipt compatibility | 30 passed in 13.173 seconds. Command: `python -B -m unittest backend.tests.test_authority_review backend.tests.test_authority_revision backend.tests.test_legal_checks backend.tests.test_legal_foundation.CorpusTests -q`. |
| Complete backend regression after all code changes | **214 passed in 615.343 seconds**; `python -B -m unittest discover -s backend/tests -t . -q`. Includes existing Phase 1–4, review/security/permission and new revision regressions; final result `OK`. |
| Browser: `npm test` | 17 passed in 1.4 minutes, existing explicit development/mock configuration. |
| Frontend: `npm run build --prefix frontend` | Passed; Vite production build completed in 4.19 seconds. |
| Python compile/import | All 153 backend/scripts Python files compiled in memory; application, review modules and both review commands imported. |
| Current genuine-source gate checks | 14 identity-valid candidates, zero usable; four saved Consumer issues checked, zero positive verified citations; no case publication or live model call. |
| Draft/report consistency | Exact excerpt, original source text/hashes, offsets and jurisdiction unchanged; current head preserved; inactive draft has no submission; actual users/receipts remain zero. |
| Whitespace: `git diff --check` | Passed. |

A one-off read-only validation probe initially passed the wrapper's `version_id` into the strict source model and failed validation before any mutation. The probe was corrected to remove wrapper metadata; all checks then passed. No production validation was weakened. Earlier inactive draft preparation had recorded a preparer submission event; history was preserved, a regression was added, and the final inactive draft has no such event. No final test failures were ignored.

Logs: `.localdev/phase4-revision-backend-tests.log`, `.localdev/phase4-revision-browser-tests.log`, `.localdev/phase4-revision-frontend-build.log`. These are ignored local outputs, not evidence of real-admin or cloud acceptance.

### Every source-controlled file changed in this continuation

| File | Change |
| --- | --- |
| `backend/models/legal_foundation.py` | Revision status, lineage and correction metadata. |
| `backend/services/authority_review.py` | Persisted request decision, independent review guard, inactive submission, actor attribution and existing account DB connection. |
| `backend/services/verified_corpus.py` | Reject requested authorities, store inactive versions without advancing head, expose revision status. |
| `backend/routes/authorities.py` | Exact request decision, reject client-owned identity/time/lineage, admin-only history and account bridge. |
| `backend/tests/test_authority_revision.py` (new) | Seven regression tests with isolated fictional fixtures. |
| `scripts/serve-authority-review.py` (new) | Loopback-only review API against existing local identity and authority files; no provisioning. |
| `scripts/record-authority-review.py` (new) | User-run normal login and explicit decision, hidden local credential prompts, non-secret receipt output and logout. |
| `artifacts/phase4_record1_revision_draft.json` (new) | Exact old/new comparison, source excerpt, pending metadata and read-only validation results. |
| `docs/phase4-revision-request-workflow.md` (new) | Authentication commands, absent provisioning blocker, full correction and excerpt. |
| `docs/phase4-admin-review-checklist.md` | Replace historical API-gap statement with implemented workflow and authentication gate. |
| `docs/phase4-legal-foundation-report.md` | This scoped report and validation evidence. |

Ignored local files changed/created: authority database with inactive immutable draft history (current heads unchanged), record-1 reason and prepared source payload, normal lock files, regression logs, isolated browser test database/uploads, and build/test outputs. Existing untracked `output/` content is untouched.

Implementation checkpoint: `7992e76`. No push performed. Records 2–14 await individual authenticated decisions; none were automatically revised, approved or rejected. **STOP at the real-admin gate; Phase 4 remains PARTIAL / REVIEW REQUIRED.**


## 45. Explicitly authorized local admin provisioning — 13 October 2026

The user authorized a supported local provisioning workflow after confirming no legitimate admin account exists. This continuation supersedes section 44's missing-provisioning blocker. It does not provision a real account during implementation, record the user's review decision or activate the correction.

**IMPLEMENTED:** dedicated interactive `scripts/provision-review-admin.py --allow-admin-bootstrap`, existing auth password validation/hash storage through a controlled adapter method, server creation time and audit metadata, atomic one-time marker, duplicate/non-admin promotion refusal, project-root/virtual-environment/local-terminal/path checks, no HTTP bootstrap, no public admin signup, no automatic session. The review client now verifies the immutable receipt and can submit a corrected pending revision in the same authenticated local session without requesting approval.

**UNIT TESTED:** ten new bootstrap/auth/permission/sequence tests use fictional credentials in temporary databases only. Includes concurrent bootstrap protection, marker persistence after user deletion, secret-output checks, missing flag and unsafe invocation, normal admin login, non-admin endpoint denial, public signup denial, fresh revision and self-review refusal. Existing review/security tests are preserved.

**LIVE CONNECTED:** no real administrator yet. No new AWS/Bedrock connection claim and no cloud retries or infrastructure changes. Persistence remains LOCAL VALIDATED — DYNAMODB LIVE ACCESS BLOCKED BY AWS SCP.

**LIVE INPUT VALIDATED:** existing source data only; no new legal claims or amended text. Genuine corrected draft remains inactive and unusable, unchanged from section 44.

**END-TO-END VALIDATED:** the local authenticated bootstrap-to-review-to-new-revision sequence passes with temporary test accounts/fictional authority. Genuine user provisioning/login/review is PENDING, not claimed complete.

**LEGAL CORPUS READY:** NO. There is still no formal receipt or approved genuine authority. Engine 2 was not started; its existing visibility regression remains part of the unchanged browser suite.

### Commands and actual state

[Local provisioning guide](phase4-local-admin-bootstrap.md) provides exact PowerShell commands and the subsequent authenticated sequence. The command prompts for explicit confirmation, administrator email and hidden password locally. The password is not accepted as a command-line argument. No password, token, hash copy or fabricated admin is stored in source-controlled artifacts.

The new identity database path is `.localdev/phase4-authority-review/identity.json`. At implementation validation it **does not exist**: provisioning has not run. The authority database has zero users and zero formal receipts; original record-1 head `d9804b732b3d855c06cf5c0143b721a5e9d0ad775092810c2f236150a51a024e` remains current and corrected draft `a36240fa45fbaa6d553f77f5f7824de82d6961c2b38df27c0235df74f946239e` has no submission event. Account creation alone never changes authority state.

After the user provisions locally, start the loopback review server using the dedicated identity database. The user authenticates through a hidden password prompt; no password/token is needed in chat. The review client checks the server receipt's identity, timestamp, decision and input revision, then submits a new pending revision and rechecks that receipt unchanged. A new revision is never automatically approved. Request and submission are separate persisted operations; on a later failure the receipt remains and the old request cannot simply be replayed.

This is development/review provisioning, not production IAM/Cognito. It retains the existing local password hashing and storage model. Known remote invocation and network paths are refused; a malicious local process with filesystem/code access is outside that protection. No account promotion or bootstrap-reset command is provided.

### Checks run in this continuation

| Check | Result |
| --- | --- |
| Initial bootstrap + existing authority/revision focused suite | 23 passed in 9.466 seconds. |
| Expanded focused suite, including authenticated receipt/submission client | 24 passed in 10.408 seconds. |
| Final bootstrap suite after hidden-prompt hardening | 10 passed in 1.728 seconds. |
| Complete backend after all implementation changes | **224 passed in 515.282 seconds**; `python -B -m unittest discover -s backend/tests -t . -q`, final `OK`. |
| First browser suite, existing accumulated test DB | 15 passed, 2 failed: profile edit submitted the old name; processing-status poll exceeded five seconds while ENGINE1_RUNNING. |
| Browser recheck, same DB | 16 passed, 1 failed: same profile-edit assertion; status/visibility test passed. |
| Fresh-database browser check after backend completion | **17 passed in 33.9 seconds**; `npx playwright test --config .localdev/phase4-bootstrap.playwright.config.js`. Temporary config imports the unchanged normal suite, changing only local test database/storage/output paths and resolving paths. No assertions or timeouts changed. |
| Frontend production build | Passed; 1,922 modules, 2.88 seconds. |
| Python compile/import | 155 files compiled in memory; application and three provisioning/review commands imported without executing their entry points. |
| Real dataset check | Identity file absent, zero authority-db users/receipts, original head unchanged and corrected draft inactive. |
| `git diff --check` | Passed. |

The profile trace shows PATCH `/api/auth/me` submitted `Anita Sharma` and received that same saved name, although the test had entered `Updated Client Name`. This occurs in the unchanged profile page, which unconditionally applies asynchronous initial `getMe` responses to form state. No profile-page or test assertion was changed or weakened in this scoped provisioning phase. Browser failures are reported explicitly rather than counted as passes. The final fresh-database run after backend completion passed all 17 tests, including profile persistence and status/visibility. The earlier result is consistent with a timing-sensitive initial form-load race; no unrelated frontend fix is claimed.

Logs are local/ignored: `.localdev/phase4-bootstrap-backend-tests.log`, `phase4-bootstrap-browser-tests.log`, `phase4-bootstrap-browser-recheck.log`, `phase4-bootstrap-frontend-build.log`, and `phase4-bootstrap-browser-fresh.log`. The fresh run used an ignored temporary config and new isolated test DB; it did not reset the existing DB. Traces are in ordinary ignored Playwright output; do not publish raw authentication traces.

### Every changed source-controlled file

| File | Purpose |
| --- | --- |
| `backend/adapters/mock/auth.py` | Reuse existing credential rule and salted password hashing; controlled dedicated review-admin method, no bootstrap session. |
| `backend/adapters/mock/database.py` | Atomic new account/audit-marker insertion under local file lock, one-time and duplicate/role guards. |
| `scripts/provision-review-admin.py` (new) | Explicit flag, local environment checks, confirmation/email/hidden password prompts and safe output. |
| `scripts/record-authority-review.py` | Hidden-input safeguards, normal session identity, receipt verification and optional corrected-source submission without approval. |
| `backend/tests/test_review_admin_bootstrap.py` (new) | Ten isolated provisioning/authentication/security/sequence regressions. |
| `docs/phase4-local-admin-bootstrap.md` (new) | Exact user-run commands, safeguards, limits and subsequent real review steps. |
| `docs/phase4-revision-request-workflow.md` | Link the newly authorized provisioning path instead of the prior blocker. |
| `docs/phase4-legal-foundation-report.md` | This scoped report and results. |

Implementation checkpoint: `84ae944`. No push. Ignored regression databases/logs/build outputs were generated; the actual authority DB was only inspected, and the actual identity DB was not created. Existing untracked `output/` remains untouched.

**STOP after provisioning implementation/report. The user must create their real administrator locally before the conditional real review sequence can proceed. Remain in Phase 4; no Engine 2 work.**

## 46. Real administrator provisioned; HTTP 422 investigation

The user subsequently provisioned their administrator and started the review server. Their review command returned 422. Read-only inspection found **zero formal receipts, no requested state, no new source revision/submission**, and the original record-1 head and inactive correction unchanged. The real admin account is preserved. No bootstrap or review request was replayed.

[The detailed investigation](phase4-review-422-investigation.md) records the exact observed history, ruled-out conditions, safe client diagnostics, tests and check-only command. The historical 422 cause is **not yet established** because the old client discarded operation/error detail; no root cause is invented. The intended request succeeds against an isolated copy of the exact saved source with a fictional test identity.

Diagnostics checkpoint `ed5a3ff`: 28 focused tests passed; 156 Python files compiled; whitespace checks passed. Only the client, diagnostic tests and reports changed. The safe check-only command never posts a review or corrected source. Genuine review and legal completion remain pending. No Engine 2 work began.

### Follow-up after successful real access check

The user confirmed that check-only authentication/history access succeeds and the expected head matches, with zero receipts. A new real-HTTP regression runs the current client against Uvicorn on a temporary loopback port with the exact official record, rationale and corrected-source payload. The full request-to-corrected-submission sequence passes using a fictional temporary identity. The real authority and identity databases remain byte-for-byte unchanged. Live OpenAPI review-model comparison also matches the checkout; no unexpected query parameter was found.

Final focused regression: **29 passed in 8.881 seconds**, covering client diagnostics, provisioning, authority revisions and authority reviews. The new HTTP regression passed separately in 1.085 seconds. Only the regression and reports changed in this follow-up; no production fix is claimed because the alleged review-POST 422 cannot be reproduced. The original generic failure discarded the evidence needed to identify its exact operation/condition. No real review was replayed and no one-time state-changing retry is recommended while the user's root-cause stop condition remains unmet. Phase 4 and all real legal approvals remain pending.

## 47. Real revision request and corrected submission verified

The user authorized one controlled real retry and later supplied its successful console output. Read-only verification confirmed receipt `fbf2e5ba79e14d8e8e39dac7362b6ee2`, decision `NEEDS_NEW_REVISION`, server timestamp `2026-10-13T09:32:43.670594+00:00`, and new corrected head `fdd9c175c4fb253f74e3a5b8a4e846398e9efd871e770278fe79db0aec8fe14c`. The corrected revision is **REVIEW_PENDING / revision_status NONE / verification PENDING / approved false**. Its parent retains the requested state; receipt content binding and lineage were checked, with source excerpt/hash unchanged. The actual database was not modified by the assistant's verification.

The new transcript also supplies evidence unavailable earlier: the original failing command used the literal `<your admin email>`. That exact literal reproduces HTTP 422 in login email-format validation before any review POST. The earlier unknown-cause conclusions are historical and superseded by this evidence. The regression now uses the exact placeholder; no production rule was changed.

The server restart attempt failed because port 8012 was occupied; the existing server processed the successful retry. No second review retry is authorized or needed. The corrected source's submitter is the same actual admin who requested revision, so independent approval must come from a different genuine reviewer. No account was fabricated or promoted, and no authority approval occurred.

**LIVE AUTHENTICATED REVIEW REQUEST: VALIDATED. LIVE CORRECTED SUBMISSION: VALIDATED. LEGAL CORPUS READY: NO.** Amendment/commencement and other legal review gates remain open; successful administration is not legal completion. Remain in Phase 4, with no Engine 2 work. Exact receipt/revision metadata and limitations are in [the updated investigation](phase4-review-422-investigation.md).

## 48. Additional independent reviewer onboarding support

**IMPLEMENTED / UNIT TESTED. REAL SECOND ACCOUNT PROVISIONED: NO. INDEPENDENT HUMAN REVIEW: PENDING. LEGAL CORPUS READY: NO.**

The controlled local command authenticates the existing administrator and requires interactive confirmation, a different email and hidden new password/confirmation. It reuses application password validation and hashing. An atomic database operation rechecks the authenticated session/role, rejects duplicate accounts of any role, preserves the bootstrap marker and records authorization/creation audit metadata with the new account. No public signup or network provisioning endpoint was added. A different account is explicitly not proof of a different human reviewer.

Changed files:

- `backend/adapters/mock/auth.py`: controlled authenticated additional-admin service.
- `backend/adapters/mock/database.py`: atomic authorization, duplicate and bootstrap-history guards; account/audit persistence.
- `scripts/add-review-administrator.py`: local interactive command with hidden credentials and session cleanup.
- `backend/tests/test_additional_review_admin.py`: seven temporary-database onboarding/independence/security regressions.
- `docs/phase4-additional-reviewer-onboarding.md`: exact PowerShell command and user-run workflow.
- `docs/phase4-legal-foundation-report.md`: this report.

Validation:

- `python -B -m unittest backend.tests.test_additional_review_admin backend.tests.test_review_admin_bootstrap backend.tests.test_authority_revision backend.tests.test_authority_review backend.tests.test_review_client_diagnostics -q`: **36 passed**, including successful creation/authentication, authorization rejection, duplicate/no-promotion guards, secret-safe CLI, distinct IDs, bootstrap preservation, revocation race, new reviewer endpoint access and submitter self-approval rejection. Temporary HTTP reproduction remains covered; no real review replay.
- `python -B -m unittest backend.tests.test_core_permissions backend.tests.test_legal_permissions backend.tests.test_security_hotfix -q`: **19 passed**.
- `npm run build --prefix frontend`: **passed**.
- In-memory compilation of all **158 backend/script Python files**: **passed**.
- `git diff --check`: **passed**. Existing dependency deprecation warnings remain; no test failure.

Read-only checks confirmed one real administrator, the preserved bootstrap marker, unchanged corrected source head and existing immutable receipt. The actual onboarding command was not executed; no real account or authority state was changed. No AWS call was made. These results are focused regression validation, not a claim of full live legal completion.

The user must now run [the onboarding command](phase4-additional-reviewer-onboarding.md). After the second real reviewer is provisioned, prepare the requested read-only package for the existing corrected revision; stop before any decision. The corrected source remains pending and unusable. No Engine 2 work began.
