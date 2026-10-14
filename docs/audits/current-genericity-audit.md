# Current-checkout genericity audit

Baseline: **4fab446**. Earlier reports were historical references only. This report
supersedes their blanket completeness claims. Scope: backend, repositories,
provider adapters, isolated retrieval/ingestion prework and operational scripts.
No production migration, authority decision, Engine 2 execution or Phase 5 work
was authorized or performed. Fixes are deliberately limited.

## Verdict: PARTIAL

The active Phase 4 authority/retrieval contracts are not dependent on Consumer
Protection section 2(7). Domain labels are open, issue IDs retain per-issue domain
metadata, and existing cross-domain/unknown-domain tests pass. However, arbitrary
domain labels do not imply a working specialist team, source acquisition, legal
coverage, or production hybrid retrieval. The newer ingestion prework contains
specific-law and judgment fixtures inside adapter implementations, not merely tests.

## Findings by severity

### High — remaining, larger work deferred

1. **Ingestion prework can manufacture official-looking provenance.**
   `engineering_prework/legal_source_ingestion/adapters/indiacode_adapter.py`
   discovery returns a fixed CPA/IT/Contract list. Fetch/extraction can produce
   placeholder text without a network fetch while describing it as retrieved
   official material. `discover_related_amendments` special-cases `cpa_2019`, builds
   an unverified notification URL, and returns `verified=True`. The judgment
   adapter similarly returns fixed case names/citations. These are not reliable
   source acquisition implementations. The prework remains isolated: no live
   authority was changed. Required future work: explicit test-fixture adapters,
   real authenticated provenance/fetch validation, and no derived reviewed state.
   Do not integrate these adapters or treat their harness success as legal evidence.

2. **Prework temporal graph is not a review gate.**
   `version_graph.py:is_temporally_valid_on` uses commencement/repeal dates without
   checking edge verification or complete supported-through coverage, then returns
   IN_FORCE. Document-level commencement is also insufficient for provision-specific
   exceptions. Keep separate from the active reviewed corpus. Requires a substantive
   temporal/provision model and negative tests; not redesigned here.

3. **Mongo admin provisioning is not atomic despite its docstrings.**
   `backend/adapters/mongo/database.py:104,133` performs authorization/duplicate
   checks, user insertion and marker/audit insertion separately. A race or partial
   failure can leave an admin without corresponding bootstrap/audit state.
   Database deployment/transaction or fail-closed reservation design needs a separate
   security change. No bootstrap/onboarding was executed in this audit.

4. **Parallel repository API does not preserve immutable review contracts.**
   `backend/repositories/authority_repository.py:54,75,146` uses check-then-replace
   for heads and upsert replacements for versions/reviews. This can overwrite
   history or lose concurrent head changes. No production service imports of these
   repository classes were found: active AuthorityReview uses DatabaseAdapter.
   Therefore this is an integration blocker, not evidence that existing receipts
   were overwritten. The active adapter's `create` rejects duplicate IDs.

5. **Factory couples persistence and processing truthfulness.**
   `backend/adapters/factory.py` may return mode='mongodb' with MockLLMAdapter and
   MockWorkflowAdapter; legality handlers commonly distinguish mock/live using
   `mode == 'mock'`. An unknown database-provider value can also fall through to
   AWS-backed defaults, while an unknown Mongo object-provider can become mock
   storage. Requires explicit validated provider configuration and independent
   processing capability/mode reporting. No false live-validation claim is made.

### Medium — fixed in this checkpoint

6. **Mongo URI isolation:** a singleton client reused the first deployment even
   when a later caller supplied a different URI. Replaced with a locked per-URI
   cache. Regression verifies distinct targets and same-target reuse without
   opening a network connection.

7. **GridFS literal key prefix:** regex characters in object keys expanded matches
   instead of following literal-prefix semantics. `re.escape` now protects prefixes;
   regression covers dots, brackets and wildcard-like input.

8. **Legacy fixture guard NameError:** `run_legal_pipeline` referenced undefined
   `adapters`. It now reads `app.state.adapters.mode`. Test executes only the guard
   expression for mock/mongodb/real/hybrid; no Engine 2 stage is run. Legacy routes
   remain tombstoned; this does not reactivate them.

9. **Persistence regression suite escaped its intended test boundary.** Its migration
   test copied real local JSON/uploads into a test DB, probed S3 and rewrote the
   tracked S3 manifest. The first audit run exposed this. Source JSON was unchanged,
   temporary DB teardown completed, and only the test-overwritten manifest was
   restored to HEAD content. The test now uses synthetic temporary JSON and a mocked
   S3 probe. Test database names now use a UUID instead of shared `caseseva_test`.

### Medium — remaining, documented rather than broadened

10. **Unseen domain orchestration gap:** Domain accepts new identifiers and corpus
    search abstains safely, but `LegalTeamAgents.team` selects only CATALOG members
    and requires primary-domain representation; `issues` requires selected-specialist
    provenance. No general unknown-domain team is provided. Adding a new domain
    may require pack registration/configuration and specialist implementation;
    merely accepting its label does not prove end-to-end support.

11. **Language/AWS media coupling:** common input transcription directly uses S3
    and Transcribe with `LanguageOptions=['ta-IN','en-IN','en-US']`. Hindi/Telugu and
    other languages are not demonstrated by this path. OCR language defaults are
    configuration-driven; Unicode script hints are not reliable language detection.
    Translation's English working representation is an explicit internal design,
    not proof of multilingual fidelity. Extract media capability/provider boundaries
    separately. GridFS migration does not remove Transcribe's S3 dependency.

12. **Storage semantics differ:** GridFS upload deletes prior bytes before putting
    new bytes, risking data loss on failure; ObjectStore says immutable URI although
    keys are overwritten. GridFS ObjectStore ignores caller metadata while S3 stores
    it. S3 listing is not paginated. These need a versioned-object/error-handling
    design, not a cosmetic rename. GridFS metadata retrieval also eagerly reads
    bytes to compute a fallback hash even when a hash already exists.

13. **Mongo compatibility edge cases:** adapter mutation falls back to `id` lookup
    but replaces by a synthesized `_id` and exact `_revision`; externally imported
    records with a different `_id` or absent revision can never satisfy the CAS.
    Review/admin insertions can omit `_revision`. Requires an explicit migration
    contract and compatibility tests; no database repair attempted.

14. **Jurisdiction model is coarse:** exact-match plus configured `IN-`→`IN`
    inheritance prevents the old unconditional Central-law fallback across foreign
    jurisdictions. It does not model court hierarchy, territorial applicability or
    forum competence by itself. Ingestion adapters still label extracted material
    `language='en'`/`jurisdiction='IN'`; those must be evidence-derived. No non-Indian
    coverage is claimed.

### Low / limitations

15. `reload_config` replaces CONFIG while several modules hold imported references;
    runtime reload is not reliable. Restart/config-version semantics need definition.
16. Legacy document templates are explicitly Consumer/Labour scoped; absent templates
    fail rather than silently generating Consumer output. They are not arbitrary-law
    professional drafting. Legacy corpus normalizers require registered aliases.
17. The previous audit's NDCG and full genericity claims were too broad. The isolated
    evaluation code implements recall@k, precision@k, reciprocal rank, citation recovery
    and abstention/filter checks, not NDCG. Passing synthetic tests proves contracts,
    not legal truth or completeness.

## Auditable occurrence inventory

`current-genericity-occurrences.csv` contains **467 matching lines in 65 files**
from a **254 tracked-file** backend/prework/scripts inventory. Each match has a
path, line, text, classification and reason. The search covers Consumer/CPA/RTI,
language names, jurisdiction/domain/source conditionals, verified flags and storage
providers. This is a reproducible textual inventory, not a claim that absence of
these strings proves genericity. CONTEXTUAL REVIEW rows intentionally distinguish
metadata references from actual defects; severity findings above interpret behavior.

Classification summary:

- TEST: test modules and explicit mock providers; cannot establish corpus readiness.
- CORPUS DATA: provision JSON; not a common-engine special case.
- DOMAIN CONFIG: registries, specialist catalog and named document templates.
- DOCUMENTATION: examples/claims, with outdated claims superseded here.
- ADMIN TOOLING: CLI, migration and validation scripts; not final reviewer UX.
- COMMON ENGINE BUG / ADAPTER LIMITATION: ingestion fabricated provenance and
  input-language/provider assumptions described above.
- PROVIDER IMPLEMENTATION: legitimate Mongo/GridFS/AWS implementation boundaries;
  not automatically a hardcoding defect merely because a provider name appears.

`cpa2019_s2_7` is not an active product-engine dependency. However, the separate
`cpa_2019` special case in ingestion prework means the broader statement that *all*
code is free from CPA-specific behavior would be false.

## Domain, retrieval and review boundaries

The same isolated BM25/query/rank-fusion/citation/evaluation code accepts per-issue
domain and source metadata. Dense embeddings and legal reranking are still provider
interfaces. There is no production hybrid pipeline. Multi-domain backend tests cover
Consumer, Contract, Cyber, RTI and new-domain abstention using synthetic sources.
Production VerifiedCorpus retains reviewed-receipt, source-text and temporal gates.
Domain packs do not approve authorities; RTI auxiliary restrictions are configuration,
not automatic law or fallback. Authority types are configured and model-validated.

**Does a new domain require common retrieval edits?** No for metadata-driven search
and isolated retrieval; yes/additional work may be necessary to achieve complete
specialist orchestration and real coverage. Do not conflate those answers.

**Does a new Act/Rule/section require common retrieval edits?** No for existing
authority schemas, provenance and reviewed gates. A new portal/parser or unsupported
authority semantic model may require adapter work; ingestion is not complete.

The CLI remains local/admin tooling. A future secured reviewer page should use the
same `/api/admin/authorities` endpoints and AuthorityReview service: authenticate,
list pending records, inspect excerpt/PDF/hash/lineage/version/temporal warnings,
submit expected-version + decision + rationale, and display immutable receipts.
Identity/time/lineage remain server-derived; no client or UI may override review
guards or self-review restrictions. No reviewer UI was built in this task.

## Validation and safety

- 121 tests passed: new bounded-fix tests, existing genericity/multi-domain,
  isolated retrieval and ingestion harness, authority review/revision, security,
  legal/core permissions, Blackboard and orchestration regressions.
- Initial Mongo suite: 12 passed, but exposed the test isolation leak above.
- After isolation fix: 15 tests passed (12 Mongo/GridFS persistence + 3 new fixes)
  against a unique temporary local database; migration used synthetic data and
  no S3 probe. No external provider/model live validation is claimed.
- Python compilation and `git diff --check` passed. Frontend unchanged.
- `current-genericity-state.json` records equal before/after JSON hashes:
  authority `b96220116ac40a01b4f96e6b620edc7eebfa35d39d11dfb33b677b9bf67716c3`;
  identity `bd055fe4bd996aba38a243fbb3572f68646be7cd469e0382a3b57920a9a15b17`.
  These hashes cover the original review JSON files, not a comprehensive concurrent
  snapshot of every live Mongo collection. Only unique temporary test DBs were
  targeted by this audit's writes. No production migration or manual history repair.

Changes: three small runtime fixes, persistence test isolation, three new regressions,
this report, occurrence CSV and before/after hash artifact. No prework implementation,
authority data, identity data, frontend or live legal gate was modified.

No legal authority was approved or modified by this audit.
Engine 2 was NOT started.
Phase 5 was NOT started.

Commit locally only; do not push.
