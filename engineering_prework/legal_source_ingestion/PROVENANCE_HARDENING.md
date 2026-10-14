# Isolated ingestion provenance hardening — 2026-10-14

Baseline HEAD: `7bf6ed305eb30d18fa5de58197ef72e4d22b9220`.
Initial status contained only pre-existing untracked `output/`. The current audit
was read before changes. All changes in this task stay inside this directory.

## Acquisition and provenance contract

Audited IndiaCodeAdapter, MinistryPortalAdapter and JudgmentSourceAdapter. Removed
fixed Act/Rule/judgment discovery lists, constructed ministry paths, invented text,
HTTP headers, current-time retrieval claims, assumed judgment disposition/hierarchy,
and the Act-specific automatically verified commencement relationship.

All three real adapters now share an explicit unsupported acquisition interface.
Discovery, fetching, extraction, metadata extraction, version detection, amendment
discovery and provenance construction fail closed with AcquisitionUnavailable.
The status is NOT_FETCHED, or MANUAL_OR_BROWSER_REVIEW_REQUIRED for CAPTCHA,
manual acquisition or manual-only sources. Registry capability labels do not enable
an implementation. Unknown source IDs also fail closed. No network request occurs.
No CAPTCHA bypass, bulk ingestion, authority publication or production integration
was performed. The live probe and its historical report were not run or changed.

There is deliberately no supported real retrieval path in this checkpoint, including
no verified-byte import path. Caller strings and extraction overrides are rejected.
An adapter cannot mint an official receipt from a caller-created RawDocumentRecord.
A future source-specific strategy must validate actual retrieval or independently
verified supplied bytes BEFORE enabling any real return path. Its required contract:

- source_id bound to registry identity and official owner;
- requested URL (official_url) and validated final URL, including redirect ownership;
- actual retrieval timestamp, method, content type and HTTP status/headers where available;
- raw bytes with computed SHA-256 and exact byte size;
- extraction bound to those same bytes, not arbitrary text overrides;
- independent authenticated review, separate from retrieval or discovery.

The current RawDocumentRecord carries the requested/final URLs, timestamp field,
raw hash, size and content type, plus newly required source_owner and retrieval_method
and optional http_status. No model currently permits officially_retrieved=True or
review_eligible=True. Synthetic retrieval timestamps are explicitly NOT_FETCHED.
This is an intentionally unavailable acquisition capability, not successful live-source
validation. A later implementation must extend the contract with evidence validation;
changing a flag or filling metadata fields is insufficient.

## Fixtures and generic parsing

Explicit FixtureIndiaCodeAdapter, FixtureMinistryAdapter and FixtureJudgmentAdapter
live only in tests/fixtures/adapters.py and are not exported by adapters/__init__.py.
They share a generic test provider. Synthetic records and receipts explicitly carry
source_mode=TEST_FIXTURE, officially_retrieved=false, review_eligible=false.
They use fixtures.invalid URLs, a fixture-prefixed source ID, TEST FIXTURE ownership,
computed payload hashes/sizes, empty HTTP headers and no invented HTTP status.
Fixture extraction rejects mismatched bytes. Flags are frozen and validated; reviewed
status is rejected. Provision output preserves the fixture marker and ownership.
The existing harness now explicitly uses fixtures, not live adapters.

The statutory sectionizer implementation was unchanged. Tests retain section,
subsection, clause, offsets and hashes, and exercise arbitrary Act, Rule, Notification,
Ordinance, Regulation and Judgment input through the same generic offline path.
Judgment fixtures represent synthetic text, not a validated judicial paragraph parser.

No executable CPA/Consumer-specific behavior remains in non-test ingestion Python.
Descriptive CPA/Consumer references remain in official_sources.json registry data
(the ministry and tribunal notes). These do not select or generate documents.
The live probe also names the Consumer Affairs source, not a specific-law branch.
No fixed case names, numbers, citations, dates or bench metadata remain in real adapters.

## Relationship guard and temporal limitations

VersionRelationship defaults to verified=False and rejects verified=True at creation
and assignment. There is no authenticated relationship-review contract in this
prework, so verification is intentionally unavailable even for caller assertions.
The graph never derives commencement/repeal trust from discovered edges, including
unchecked Pydantic copies carrying an injected true flag. Tests cover both paths.

The temporal model is NOT redesigned. Explicit node-level interval dates still drive
simulation results, including IN_FORCE; this is not reviewed legal validity. Supported-
through coverage, unresolved gaps, provision-level commencement exceptions, reliable
date semantics and independent review integration remain unresolved. Never use this
prework graph as a production temporal or legal review gate.

## Validation

104 distinct tests passed: 18 ingestion (12 existing plus 6 new test methods with
multiple subcases), 74 backend genericity/multi-domain/review/revision/security and
permission regressions, and 12 isolated Mongo persistence tests. No skips reported.
After the final fixture-owner and unchecked-edge refinements, all 18 ingestion tests
were rerun and passed. Python compileall and git diff --check also passed.
Pytest is not installed in the local venv; the repository's unittest tests were run
with unittest instead. No dependency installation was needed.

Commands (from repository root, using .venv/Scripts/python.exe):

```text
-m unittest engineering_prework.legal_source_ingestion.test_ingestion_harness engineering_prework.legal_source_ingestion.tests.test_provenance backend.tests.test_genericity_audit backend.tests.test_current_genericity_audit backend.tests.test_case_driven_multi_domain backend.tests.test_authority_review backend.tests.test_authority_revision backend.tests.test_security_hotfix backend.tests.test_core_permissions backend.tests.test_legal_permissions backend.tests.test_review_admin_bootstrap backend.tests.test_additional_review_admin -q
-m unittest backend.tests.test_mongo_persistence -q
-m unittest engineering_prework.legal_source_ingestion.test_ingestion_harness engineering_prework.legal_source_ingestion.tests.test_provenance -q
-m compileall -q engineering_prework/legal_source_ingestion
```

Mongo used only unique temporary database
caseseva_test_d401298b5a6842f6b070ace6c56a59ec with synthetic temporary migration JSON
and the existing mocked S3 probe (OFFLINE_TEST_NO_S3). Teardown completed. No actual
uploads were copied, no S3 probe ran, and the tracked migration manifest is unchanged.
Review regressions exercised synthetic temporary records only; real review history
and authority/identity databases were not written.

## Protected SHA-256 values

Authority database (.localdev/phase4-authority-review/database.json):

- Before: b96220116ac40a01b4f96e6b620edc7eebfa35d39d11dfb33b677b9bf67716c3
- After:  b96220116ac40a01b4f96e6b620edc7eebfa35d39d11dfb33b677b9bf67716c3

Identity database (.localdev/phase4-authority-review/identity.json):

- Before: bd055fe4bd996aba38a243fbb3572f68646be7cd469e0382a3b57920a9a15b17
- After:  bd055fe4bd996aba38a243fbb3572f68646be7cd469e0382a3b57920a9a15b17

## Files changed

- adapters/indiacode_adapter.py
- adapters/ministry_adapter.py
- adapters/judgment_adapter.py
- adapters/unsupported_adapter.py (new)
- base_adapter.py
- models.py
- version_graph.py
- test_ingestion_harness.py
- tests/__init__.py (new)
- tests/fixtures/__init__.py (new)
- tests/fixtures/adapters.py (new)
- tests/test_provenance.py (new)
- PROVENANCE_HARDENING.md (this report)

Final local commit identity is returned in the final task response; this report is
included in that commit. No push is authorized or performed.

## Required answers

Can a real source adapter still manufacture official-looking legal text without
fetching/providing source bytes? No. Real acquisition/extraction paths fail closed.

Can discovery alone mark an amendment or commencement relationship verified? No.
Verification is unavailable in this isolated prework.

Are CPA/Consumer-specific examples now confined to test fixtures/data? Yes for
executable examples. Descriptive source-registry references remain as noted above.

Was any legal authority or review state changed? No real authority or review state.
Only synthetic temporary regression records were exercised.

No synthetic legal fixture is eligible as reviewed law.

No legal authority was approved or modified by this task.

Engine 2 was NOT started.

Phase 5 was NOT started.
