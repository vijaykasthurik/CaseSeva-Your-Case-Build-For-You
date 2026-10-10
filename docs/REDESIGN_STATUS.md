# Repository analysis and phased migration

See [expanded specification phase status](REDESIGN_PHASE_2.md) for changes after this historical baseline.

Analysis was returned in the conversation before redesign edits. This records the discovered design and implementation status as of 2026-10-09. Tests use isolated adapters and do not establish live legal accuracy.

## 1. Architecture discovered

The repository uses React/Vite and FastAPI, with adapters for authentication, database, storage, LLM, workflow, and legal retrieval. Local adapters persist JSON/files; AWS adapters connect to DynamoDB, S3 and Bedrock. SAM packages the API and async processing into Lambda. The original flow was stage-based intake, factual analysis, Preview 1 approval, combined legal/adversarial analysis, Preview 2 approval, advocate review and document generation. Client record access and document permissions were broader than the new specification permits.

The Consumer/Labour corpora held summaries and URLs without reviewed official text, exact quotations, hashes and freshness records. Routing was limited to those domains. Template document generation and most browser tests targeted the old workflow.

## 2. Reusable functionality

Authentication, signup/profile forms, case ownership, autosave, uploads, evidence identifiers, directory, advocate request/accept/decline, document version storage, adapter interfaces, AWS integrations, Lambda entry point and styling remain. Historical records and service modules are retained where practical. Old source summaries cannot become verified law merely because they contain an official URL.

## 3. Gaps against the specification

The original implementation lacked bilingual/media common input, a separate argument-only Engine 2, verified multi-domain readiness, scoped expiring client consent, versioned advocate corrections/reruns, advocate-only professional outputs and reliable live-vs-mock behavior. The new code addresses these boundaries; remaining requirements are explicitly listed below.

## 4. Migration plan

Add versioned Raw Case Package and Case File alongside existing records. Automatically run Engine 1 for new submissions. Make Engine 2 optional and dependent on a fixed Case File version. Use explicit client projections. Require advocate acceptance plus scoped consent. Audit corrections, invalidate dependent outputs and allow targeted reruns. Gate Engine 3 on approval of the current version. Preserve historical documents privately and label stale versions. Upgrade old cases explicitly after saving migration snapshots.

## 5. Files changed

- Backend: main/Lambda entry points, analysis models, requirements; cases/analysis/legal_analysis/advocates/auth/documents routes; factory/database/source adapters and local/real implementations; legacy legal grounding guard.
- Frontend: App routes, API client, header, signup, home, dashboards, directory and profile. Old page source remains but is unmounted from active routes.
- Runtime: package scripts, backend launcher, auth regression tests, env example, README and SAM CORS.

## 6. Files added

- `backend/models/engines.py`.
- Services: `input_layer`, `legal_knowledge`, `engine1`, `engine2`, `engine3`, `jobs`, `overview`, `sharing`, `exports`.
- Routes: `engines`, `sharing`, `review`.
- Registries: sources, domains and filing_rules JSON; stage prompts under `services/prompts/v2/`.
- Pages: CommonInputPage, EngineCasePage, AdvocateWorkspacePage, CaseOutputsPage, VerificationAdminPage.
- Backend tests, redesign browser tests/config, backend test launcher, Chromium PDF renderer and this record.

## 7. Features affected

Preview approvals are retired. Older cases need explicit migration for new processing. Unverified law cannot appear under Applicable Law. Acceptance alone grants no case access. Clients cannot generate/read professional outputs. Mock mode cannot finish professional drafting. New advocate verification needs supporting evidence and an admin reason. Legal failures remain visible instead of becoming plausible mock/template output. Historical preview tests are retained separately.

## 8. Implementation order and status

| Phase | Implemented | Validation and limitation |
|---|---|---|
| Common Input | Single screen, autosave, optional fields, story/files/microphone, actual extraction, original+English package, pending statuses | Text/DOCX/digital PDF tests; Tamil OCR and AWS media still need live validation |
| Engine 1 and fixes | 14 stages, Case File versions, ID checks, source gate, corrections preserved, explicit pending/error states | Unit tests; no approved production corpus |
| Engine 2 and fixes | Six argument-only stages, validated references, issue readiness, foundation flags, pause/resume, stale detection | Tests enforce no extraction/retrieval or mutation of Engine 1 output |
| Case Overview | Client projection, verified law only, missing items, explicit skipped Engine 2 note | Backend and browser tests |
| Discovery and sharing | Verified directory, accept/request, scopes/evidence/expiry/revoke, hashed access tokens | Tests cover no consent, scope denial, expiry, revocation and verification downgrade |
| Review and reruns | Scoped workspace, auditable correction/approval/removal/manual verification, final approval, targeted Engine 1/2 reruns | Backend review tests; full advocate browser journey pending |
| Engine 3 and checks | Restricted structured real drafting, approved-content projection, versioned A/B outputs, baseline consistency checks, unknown filing requirements labelled | Test-double generation/versioning; mock generation blocked; live/legal acceptance pending |
| Integration | Current browser flows and auth/profile/health regressions; frontend production build | 12 browser tests passed; deployed/live end-to-end validation pending |

## Pending requirements — do not report complete

| Requirement | Blocker or unfinished work |
|---|---|
| Verified multi-domain corpus | All domains deliberately disabled. Review actual official text, terms/permissions, exact sections/quotes, hashes, dates, refresh policies and coverage before enabling each domain. Existing summaries cannot substitute. |
| Source refresh/retrieval | Automatic official-source ingestion/refresh, court/regulator connectors, verified case-law and robust semantic retrieval are unfinished. Current search is conservative over reviewed local candidates. |
| Forum/limitation/criminal transitions | Automatic legal computation needs verified current rules and case dates; currently pending advocate verification. IPC/CrPC/Evidence Act versus BNS/BNSS/BSA transition automation is unfinished. |
| Tamil and media | Original text retained. Live Bedrock translation/Transcribe need account validation; Tamil Tesseract trained data is missing locally. Full interface localization is unfinished. |
| Professional documents | Court-specific verified templates, comprehensive semantic checks for invented facts and live advocate acceptance remain unfinished. No claim of court-ready output. |
| E-filing | No verified current filing records. Unknown fees/forms/procedures use: "Current filing requirement requires advocate confirmation." Filing integrations remain pending. |
| Dashboard completeness | Notifications, deadlines calendar, complete recent-activity feed, help/settings, profile fees/availability and accessibility/localization review remain unfinished. |
| Deployment | Production identity/session hardening, KMS/secrets, consent race audit, durable job recovery, media IAM, Lambda PDF/OCR packaging, monitoring and deployed tests remain pending. Local threads are development orchestration. |
| Input reliability | Legacy DOC/richer spreadsheets, long-document chunking, interrupted-upload/job recovery and production malware scanning are unfinished. |

## Latest validation

- 40 backend tests passed, including engine boundaries, source proof, ownership, consent scopes/revocation/expiry, advocate review, document permissions/versioning and parallel evidence-number reservation.
- 12 Chromium browser tests passed for the current workflow plus authentication, profiles and backend health.
- Frontend production build, backend compilation and Git whitespace checks passed.
- Actual Chromium PDF export produced a readable one-page PDF with the expected text.
- Read-only live resource checks returned `NoCredentialsError` for DynamoDB and S3. Live processing cannot be validated with this environment's current credentials.
- Local frontend and backend were restarted on ports 5173/8000 in explicitly enabled development mock mode; health returned `ok` and `adapter_mode: mock`. No production deployment was performed.

Live mode does not fall back to mock output. Pending source/service requirements must remain visible until independently resolved.
