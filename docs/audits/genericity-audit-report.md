# Genericity and Hardcoding Audit Report

## 1. Executive Summary

This audit systematically identifies, classifies, isolates, and remediates hardcoded legal domains, authority types, language/script assumptions, Act-specific branches, and jurisdiction rules across CaseSeva. All Phase 3 and Phase 4 invariants, tests, and database state hashes are preserved.

---

## 2. Baseline State Verification

The state baseline tracking file (`docs/audits/genericity-state-baseline.json`) verifies that local development databases and identity files were not mutated during the audit:

| Path | Expected Hash | Verified | Status |
|---|---|---|---|
| `.localdev/phase4-authority-review/database.json` | `b96220116ac40a01b4f96e6b620edc7eebfa35d39d11dfb33b677b9bf67716c3` | `b96220116ac40a01b4f96e6b620edc7eebfa35d39d11dfb33b677b9bf67716c3` | MATCH |
| `.localdev/phase4-authority-review/identity.json` | `bd055fe4bd996aba38a243fbb3572f68646be7cd469e0382a3b57920a9a15b17` | `bd055fe4bd996aba38a243fbb3572f68646be7cd469e0382a3b57920a9a15b17` | MATCH |

---

## 3. Repository-Wide Occurrence Classification

Every occurrence of audited terms across the codebase has been classified according to the audit taxonomy:

- **A. TEST / FIXTURE**:
  - `cpa2019_s2_7` in `backend/tests/test_review_continuation.py` and `backend/tests/test_review_client_diagnostics.py`.
  - `[NON_CONSUMER]`, `[HALLUCINATED_STATUTE]`, `[LEGAL_MALFORMED]` test fixture dispatch flags in `backend/services/legal_analysis.py` (guarded strictly under `if adapters.mode == 'mock':`).
  - Mock lawyer profile languages (`["English", "Tamil"]`) and state (`"Tamil Nadu"`) in `backend/adapters/mock/auth.py`.
  - Test user signup data in `backend/tests/helpers.py`, `backend/tests/test_review_admin_bootstrap.py`, and `backend/tests/test_additional_review_admin.py`.
  - Fictional Tamil text fixture `fixtures/tamil_refrigerator.txt` in `backend/tests/test_common_input.py`.
  - Synthetic Act `fixture_act` in `backend/tests/legal_test_support.py`.
- **B. LEGAL CORPUS DATA**:
  - `"Section 2(7) - Consumer"` in `backend/legal_corpus/consumer/provisions.json`.
  - Statutory texts and provisions in `backend/legal_corpus/`.
- **C. DOMAIN CONFIGURATION / DOMAIN PACK**:
  - Domain hints, authority types, and `auxiliary_secondary_domains` in `backend/registries/intelligence.json`.
  - Corpus aliases in `backend/registries/corpus_aliases.json`.
  - Supported domains in `backend/registries/domains.json`.
  - Specialist capability descriptors in `backend/services/specialist_packs.py` (`PACKS`, `CATALOG`).
  - Document templates registry in `backend/services/documents.py` (`TEMPLATE_REGISTRY`).
- **D. DOCUMENTATION / EXAMPLE**:
  - Prompt instructions in `backend/services/prompts/` (e.g. `domain_router.txt`, `v2/engine1_domain_router.txt`).
  - Schema docstrings in `backend/models/understanding.py`.
- **E. ADMIN / REVIEW TOOLING**:
  - Review CLI commands and diagnostic routines in `scripts/review_cli.py`.
  - Authority review service endpoints in `backend/routes/authorities.py`.
- **F. COMMON ENGINE HARDCODING (REMEDIATED)**:
  - Hardcoded `RTI_ADMINISTRATIVE` conditional branches in `backend/services/legal_team.py:team()` -> Extracted to data-driven `auxiliary_secondary_domains` registry in `intelligence.json`.
  - Hardcoded `"Consumer"` fallback in `backend/services/documents.py:build_documents()` -> Refactored to `normalize_domain_to_corpus()` and strict `TEMPLATE_REGISTRY` check that raises `ValueError` for unconfigured domains.
  - Hardcoded `"This MVP currently supports Consumer matters..."` in `backend/services/legal_analysis.py` -> Refactored to dynamic message stating actual detected domain.
  - Default `domain="Consumer"` in `backend/adapters/legal_retrieval.py` -> Changed to neutral `domain=""`.
  - Static `Domain` literal in `backend/models/understanding.py` -> Refactored to dynamic `Annotated[str, Field(...), AfterValidator(check_domain)]` checking `CONFIG['domain_hints']`.
  - Static language/script detection in `backend/services/input_canonical.py` -> Generalized to Unicode script category extraction (`script:<SCRIPTS>`).
  - Hardcoded Central-only `{issue['jurisdiction'], 'IN'}` checks in `backend/services/legal_checks.py` and `backend/services/verified_corpus.py` -> Replaced with generic `jurisdiction_matches()` supporting prefix-parent inheritance (e.g., `IN-TN` matching Central `IN`).

---

## 4. Audited Components & Remediations

### 4.1 Registry-Driven Configuration (`backend/registries/`)
- **`backend/registries/intelligence.json`**: Data-only capability registry defining:
  - `domain_hints`: `["CONSUMER", "LABOUR_EMPLOYMENT", "PROPERTY_TENANCY", "CRIMINAL_POLICE", "CIVIL_CONTRACT", "RTI_ADMINISTRATIVE", "CYBER", "OTHER_OR_UNCERTAIN"]`
  - `authority_types`: `["STATUTE", "RULE", "NOTIFICATION", "JUDGMENT"]`
  - `jurisdiction_prefix_parents`: `{"IN-": "IN"}`
  - `ocr_languages`: `["tam", "eng"]`
  - `auxiliary_secondary_domains`: Defines metadata rules for secondary domain attachments requiring grounded, unavailable evidence (e.g. RTI, public records).
- **`backend/registries/corpus_aliases.json`**: Data-driven JSON alias mapping for domain normalization.
- **`backend/services/intelligence_config.py`**: Central capability loader and `jurisdiction_matches(source, target)` helper.

### 4.2 Dynamic Domain Typing & Extensibility
- **`backend/models/understanding.py`**: Uses `Domain = Annotated[str, Field(pattern=r'^[A-Z][A-Z0-9_]{0,79}$'), AfterValidator(check_domain)]`. Every domain string is validated dynamically against `CONFIG['domain_hints']`. Adding a domain to configuration permits schema validation without code edits. Unconfigured domains fail closed safely.
- **`backend/services/legal_team.py`**: Generalized `team()` to iterate over `CONFIG.get('auxiliary_secondary_domains', {})`. Any domain configured with `requires_unavailable_evidence: true` enforces grounded, unuploaded evidence gating without Act/domain-specific Python branches.

### 4.3 Safe Fail-Closed Behavior (No Silent Fallback)
- **`backend/adapters/legal_retrieval.py`**: `normalize_domain_to_corpus()` returns `None` for unmapped or empty domains.
- **`backend/services/documents.py`**: `build_documents()` raises `ValueError` if `norm_domain not in TEMPLATE_REGISTRY`. Extracted facts and Intelligence Report remain accessible; no silent Consumer template generation occurs.
- **`backend/services/legal_analysis.py`**: When domain is out of scope or unknown, emits a clear non-coverage status referencing the actual domain.

### 4.4 Script-Based Language Generality
- **`backend/services/input_canonical.py`**: Unicode script classification (`unicodedata.name`) maps text to script tags (`script:LATIN`, `script:TAMIL`, `script:DEVANAGARI`, `script:LATIN+TAMIL`, etc.).
- Legal reasoning, authority gates, and verification components are completely decoupled from language/script metadata.

### 4.5 Law and Section Generality
- The common engine (`LegalChecks`, `VerifiedCorpus`, `LegalTeamAgents`, `AuthorityReview`) operates purely on abstract fields: `source_id`, `title`, `section`, `citation`, `quote`, `domain`, `jurisdiction`, `official_text`, `section_start`, `section_end`, `content_hash`, `effective_from`, `effective_until`.
- Introducing a synthetic new Act (e.g. `space_activities_act_2026_s42`) or section requires zero changes to common retrieval or verification logic.
- `cpa2019_s2_7` is purely corpus and review fixture data; no common engine component depends on it.

---

## 5. Engineering Prework Verification

- **Tests Executed**: `engineering_prework/test_retrieval.py` (12 tests, 100% passed).
- **BM25**: Fully generic text passage indexing.
- **Dense Embedder Interface**: Provider-swappable protocol.
- **Reranker Interface**: Provider-swappable protocol.
- **Authority Filters**: Generic domain, jurisdiction, authority type, date range filters.
- **Exact Passage Verification**: Generic substring and SHA-256 offset verification.
- **Evaluation Metrics**: Domain-independent MRR, Recall@k, NDCG.
- **Production Status**: Completely isolated; NOT connected to production.

---

## 6. Review and Admin Architecture

The architecture separating the developer CLI, the backend authority review service, and the future authenticated reviewer web interface is formally documented in [docs/audits/phase4-review-admin-architecture.md](file:///c:/Projects%20Vijay/AWSHACK/docs/audits/phase4-review-admin-architecture.md).

All review decisions (`REVIEWED_PRIMARY`, `NEEDS_NEW_REVISION`, `REJECTED`, `STALE`), separation of duties (submitter cannot approve), optimistic locking, reviewer rationale, and immutable audit receipts in `legal_authority_reviews` are preserved identically across all interfaces.

---

## 7. Test Suite Summary

| Test Suite | Tests | Result | Notes |
|---|---|---|---|
| `backend/tests/test_genericity_audit.py` | 16 | PASSED | Extensibility, no silent default, RTI generic, cross-domain offline, multi-domain, language, section generality |
| `engineering_prework/test_retrieval.py` | 12 | PASSED | Retrieval protocols, ranking, BM25, exact verification |
| `backend/tests/test_common_input.py` | 16 | PASSED | Script detection, packaging, canonicalization |
| `backend/tests/test_understanding_agents.py` | 32 | PASSED | Domain classification, core agents, schemas |
| `backend/tests/test_legal_team.py` | 7 | PASSED | Dynamic team selection, prompt generation |
| `backend/tests/test_legal_checks.py` | 13 | PASSED | Authority gates, temporal intervals, citation checks |
| `backend/tests/test_legal_artifacts.py` | 5 | PASSED | Artifact serialization, persistence |
| `backend/tests/test_legal_foundation.py` | 5 | PASSED | Full legal foundation workflow across specialist packs |
| `backend/tests/test_authority_review.py` | 9 | PASSED | Authority review service invariants and receipts |
| `backend/tests/test_authority_revision.py` | 10 | PASSED | Authority revision lineage and continuation |
| `scripts/verify_case_4db6.py` | 1 | PASSED | Real retrieval verification |
| `scripts/check-phase3-validation.py` | 1 | PASSED | Strict schemas and multi-language routing |
| `scripts/validate-phase4-authority-candidates.py` | 1 | PASSED | Pending authority candidate validation |
