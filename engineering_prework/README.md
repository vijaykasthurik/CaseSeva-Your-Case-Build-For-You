# ENGINEERING PREWORK — NOT PRODUCTION LEGAL RETRIEVAL

This folder is an isolated, dependency-free offline experiment. No backend routes,
application imports, database adapters, AWS calls, real corpus records, credentials
or model downloads are used. Phase 5 and Engine 2 have NOT started. Phase 4 remains
subject to its existing independent-review requirements.

## Architecture

Blackboard issue snapshot (future authenticated adapter) → issue-preserving query
planner → domain/authority filters → lexical BM25 and optional dense provider →
reciprocal rank fusion → optional legal reranker → exact source-bound passages.

`Issue` is an offline DTO, not a connection to the live Blackboard. IDs such as
L001 and fact/evidence references are preserved. Domain packs provide query
templates; the shared engine contains no Consumer or Tamil-specific branching.
Language travels with each query. Unicode tokenization is a baseline, not a claim
of multilingual segmentation quality. Production tokenizers/embeddings require
language-specific evaluation behind provider interfaces.

`DenseRetriever`, `LegalReranker`, `Tokenizer` and `AuthorityGate` define swappable
contracts. Legal-BERT R&D is interface design only: no model is installed, trained,
benchmarked or in production. Future experiments must compare model licenses,
supported languages, legal-domain datasets, latency and held-out ranking quality.
Rerankers order candidate IDs; they cannot create legal authority or legal truth.

The implemented conservative policy requires official origin, exact jurisdiction,
matching domain, reviewed eligibility/receipt, verified revision, citation coverage,
reviewed temporal interval and coverage date, hierarchy verification and exact text
hash/offset binding. End dates are exclusive; coverage dates inclusive. A null end
date does not imply unlimited currency. Hierarchy/applicability are currently
abstract reviewed metadata, not an implemented court hierarchy reasoner. Future
official-source preference may rank eligible sources, but cannot authorize pending
sources. The offline engine fixes the conservative gate; it has no permissive gate
override. Provider IDs outside the eligible set are discarded.

## Provenance and limits

User Statement → Fact → Evidence → Legal Issue → Retrieved Law → Citation → Legal
Finding is represented by `CitationTrace`. It checks upstream relationship sets,
issue membership, source revision, passage and citation identity. This proves only
structural linkage; entailment and legal conclusions still require separate review.

All test sources and receipt identifiers are explicitly synthetic. Caller-provided
eligibility flags are NEVER suitable production proof. Future integration must
obtain authority status from immutable server-owned Phase 4 records, bind receipts
to exact revisions, check staleness/revocation at use time, and enforce permissions.
No real authority was loaded, altered or approved by these tests.

## Offline evaluation

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -B -m unittest engineering_prework.test_retrieval -v
```

The harness computes recall@k, precision@k (denominator k), truncated reciprocal
rank, exact citation recovery, expected abstention and forbidden-result filtering.
Empty relevance has recall 0; empty citation targets yield null recovery. Aggregate
MRR across a dataset is the mean of per-case `mrr_at_k`. Fixtures cover wrong
jurisdiction/date, pending sources, altered quotes, broken provenance, and hostile
provider IDs. Passing synthetic tests is not a measured production retrieval score.

## Integration lock

`OfflineRetrieval(enabled=False)` is disabled by default; explicitly enabling it
only enables this local object. There is no application feature flag, route or live
wiring. Normal tests use only stdlib unittest and do not require network access.

Before integration: Phase 4 acceptance for the relevant reviewed corpus; authenticated
Blackboard mapping; server-owned gate adapter with receipt and invalidation checks;
reviewed jurisdiction/hierarchy/temporal policies; licensed model selection and
multilingual evaluations; real corpus gold sets; latency/resource/security tests;
explicit authorization for live integration. Nothing here advances Phase 5.

The current Record 1 workflow and preserved review packages remain separate.

## Checkpoint results — 14 October 2026

- New offline suite: 12 tests passed (`python -B -m unittest engineering_prework.test_retrieval -v`).
- Existing authority review/revision suite: 14 tests passed
  (`python -B -m unittest backend.tests.test_authority_review backend.tests.test_authority_revision -q`).
- No frontend/build checks required: no frontend, dependency or application files changed.
- Authority and identity database SHA-256 hashes unchanged before/after prework.
- BM25, rank fusion, conservative filters, structural trace checks and metric harness
  are IMPLEMENTED / UNIT TESTED against synthetic fixtures only.
- Dense retrieval and Legal-BERT reranking remain ABSTRACT; tests inject fake providers.
- No LIVE CONNECTED, LIVE INPUT VALIDATED, production END-TO-END VALIDATED or LEGAL
  CORPUS READY claim is made. No live service was tested.
- Phase 4 source-evidence research remains separate and unresolved; this engineering
  checkpoint does not complete that task or prepare/submit an authority correction.
- Engine 2 was NOT started. Phase 5 was NOT started or marked complete.
