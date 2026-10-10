# Expanded specification: analysis and implementation status

2026-10-10. The existing implementation was inspected and the analysis returned before this phase changed code. Commit 1519827 preserves the earlier implementation. This phase is incremental and does not establish production readiness or legal accuracy.

## Architecture and reuse

React/Vite calls FastAPI. Adapter interfaces support local development and AWS database/storage/LLM services. Existing authentication, ownership, autosave, extraction, evidence IDs, verified directory, requests, scoped grants, document exports and separated engine services are retained. Legacy preview screens remain unmounted; APIs return 410.

Three origins share ingestion and a versioned case record: CITIZEN_SELF_SERVICE, CITIZEN_DIRECT_ADVOCATE and ADVOCATE_WALK_IN. Direct legal help does not require analysis. Walk-in creation requires a verified advocate and recorded consent; ingestion then runs Engine 1. Engine 2 remains optional. Engine 3 requires verified advocate access and approval of the current foundation. Professional output is never in the citizen projection.

## Gaps discovered and migration plan

The previous implementation lacked direct/walk-in origins, guest claiming, dynamic clarification, independent engine metadata, persisted professional overrides, admin roles, client-safe messages, filing tracking and retention requests. Add these around the existing services instead of replacing them. Preserve private outputs through explicit projections, invalidate dependent analysis on new information, and leave missing verified law or unavailable live services visibly pending.

## Stage migration

| Existing stage | New engine/stage |
|---|---|
| Intake/extraction | Shared ingestion, available independently of analysis |
| Intake cleaning / evidence indexing | Engine 1: 1–2 |
| Facts / timeline / parties | Engine 1: 3–5 |
| Missing information | Engine 1: 6, clarification gate |
| New answer reconciliation | Engine 1: 7 |
| Routing / issues / retrieval / citation verification | Engine 1: 8–11 |
| New temporal-law review | Engine 1: 12 |
| Forum / limitation / evidence mapping / assembly | Engine 1: 13–16 |
| Claimant / opponent / evidence challenge / rebuttal / evaluation / overview | Engine 2: 1–6 |
| Approved-content filtering | Engine 3: 1 |
| New current-law refresh | Engine 3: 2 |
| Internal report / legal draft / annexures / filing pack / checks / client overview | Engine 3: 3–8 |

## Blackboard

The case stores a public CS-year-reference separately from access credentials, origin, preferred language, input version, board version, journey stage and independent engine statuses. Board events record actor, time, action and changed fields. Professional corrections retain previous/new values, reason and author and are reapplied during reruns. Output versions and approval gates prevent stale foundation reuse. Not every legacy mutation yet uses the board event helper; full audit coverage is pending.

Professional notes default to ADVOCATE_INTERNAL. Only an explicit SHARED_WITH_CLIENT message appears in the citizen projection. Internal arguments and Output B stay private regardless of sharing settings. Shared evidence and raw-package excerpts respect selected evidence IDs. Walk-in access derives from recorded consent and verified creator/assigned permission; claiming the same case replaces this with citizen-controlled grants.

## Changed and added files

Changed: backend entry points, adapter factory, analysis/engine models, cases/advocates/review/documents/sharing/engine routes, ingestion and engine services, projections, frontend routing/API, intake, dashboards, overview, workspace, admin review and browser tests.

Added: blackboard, ingestion, clarification, overrides, law refresh and notifications services; clarification, guest claims, journey and retention routes; operator admin provisioning; clarification, communication and activity components; citizen language mappings; focused backend tests and stage instructions.

The exact scope is available through the Git diff/commit. Original functionality is preserved where compatible; supporting documents alone no longer satisfy the story requirement, acceptance alone grants no access, and ordinary approval cannot verify legal authority.

## Phase validation

| Phase | Checks |
|---|---|
| Common input/origins | Backend direct-path, consent, ownership and same-case guest claim checks; frontend build |
| Engine 1 | Clarification gates, unknown answers, maximum batches, reconciliation and ownership; frontend build |
| Engines 2/3 | Correction persistence, advocate challenge after skip, explicit absent-analysis note, current-source pending behavior and existing generation/permission regressions; frontend build |
| Admin | Role enforcement even with shared secret; mandatory official-record proof and audited reviewer identity; frontend build |
| Communication/filing/retention | Private note isolation, account-specific notifications, input staleness, filing gates/source labels, deletion revocation and retention holds |
| Integration | Chromium flows including direct legal help and walk-in workspace; full backend suite and production frontend build |

Final validation: 60 backend tests, 14 Chromium browser tests, frontend production build, Python compilation and Git whitespace checks passed. Credential-pattern scanning passed; the local `.env` remains ignored. Local frontend/backend health checks returned HTTP 200 and `adapter_mode: mock` after startup.

Tests use explicit development adapters and test doubles. They do not prove live AI accuracy or court acceptance.

## Pending — do not report complete

- Reviewed official corpus ingestion and scheduled refresh, reliable semantic retrieval, case-law connectors and current forum filing rules. Every legal domain remains disabled until its sources and coverage are reviewed. No fixture is established law.
- Temporal-law mapping and automated limitation/jurisdiction computation. These explicitly require advocate verification. Current-law refresh checks approved allowlisted downloads and exact quotes; procedure freshness, enforced source rate limits and durable cache refresh remain unfinished.
- Full stage-specific legal workflows, specialized incident branches and comprehensive semantic detection of invented facts. Current engine schemas and checks are structural, not proof of legal correctness.
- Full Tamil UI localization and validated live translation/transcription. Tamil OCR trained data is missing locally. Media processing requires configured AWS access; local credentials previously returned NoCredentialsError for S3/DynamoDB.
- Secure advocate upload of new evidence on citizen-owned matters, richer document-request attachment replies and independent wording-only professional document editing. Existing client upload and correction/rerun paths remain available.
- Deadlines calendar, read/dismiss notification controls, full dashboard search/filter/settings/availability and accessibility review.
- Verified official court status integration. Only advocate updates are supported; no CAPTCHA bypass or official-status claim is made. Forum-specific filing fields and receipt upload UI need completion.
- Automatic retention workers, restricted archive expiry, full history redaction policy and deletion across all historical version collections. Current requests delete eligible active content, revoke access immediately and report retained audit/version data.
- Durable jobs, crash recovery, consent/concurrent mutation audit, production identity/session hardening, monitoring, deployment and live end-to-end acceptance. Local daemon threads are development orchestration.
- Court-specific verified templates and advocate acceptance of real professional documents. Unknown filing requirements explicitly require advocate confirmation; failed current-law checks block readiness.

## Implementation order from here

Complete remaining input/clarification robustness and scoped advocate uploads, then durable staleness/audit/job recovery, remaining dashboard and document editing features, reviewed source ingestion and legal computation, procedure freshness and court formats, retention workers, production deployment and live end-to-end acceptance. Keep each phase tested. External access and reviewed sources must be supplied before blocked live capabilities can be validated.
