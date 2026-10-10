# CaseSeva AI

Case understanding, optional argument analysis, advocate review, and advocate-only document generation. See [repository analysis and migration status](docs/REDESIGN_STATUS.md) for the architecture, changes, validation, and pending requirements. Implementation is in progress; this is not a production-ready legal service.

## Install and run

Requires Python 3.11+, Node.js 18+, and npm.

```powershell
npm run install:all
npm run dev:mock
```

Frontend: http://127.0.0.1:5173. Backend health: http://127.0.0.1:8000/api/health.

`dev:mock` explicitly enables development adapters. The UI labels this mode. It does not verify law or produce completed professional documents. Local evidence is encrypted with a development key in the ignored upload directory; preserve that key with the uploads. This is not production key management.

For live processing configure the ignored `.env` using `.env.example`, then run `npm run dev`. This command honors configuration; it does not force mock mode. `USE_MOCK_AWS=false` uses real Bedrock, DynamoDB, and S3 adapters without a mock fallback. Errors remain failed/pending. Live permissions, model access, media transcription, and verified legal corpus ingestion require validation. Legal domains are disabled until reviewed official-source records are available.

OCR needs Tesseract on PATH and both `eng` and `tam` language data. Audio/video needs FFmpeg on PATH, `ENABLE_AWS_MEDIA=true`, a private `MEDIA_S3_BUCKET`, and authorized Amazon Transcribe access. Missing extraction dependencies are reported as pending; filenames never replace extracted content. Digital PDF, DOCX, UTF-8 TXT and CSV text extraction is implemented. Files are limited to 10 MB each.

## Workflow

Common Input -> Understand My Case (Engine 1 with clarification) -> optional Check My Case Further (Engine 2) -> Case Overview -> Find Advocate -> acceptance plus scoped client consent -> advocate review and optional targeted reruns -> Engine 3 (advocate only).

Get Legal Help prepares the intake and goes directly to advocate discovery without running either analysis. Verified advocates can create a walk-in case with recorded client consent; ingestion then runs the case foundation. Guest clients can claim the existing case through email verification, after which citizen sharing controls apply. In explicit mock mode the verification code is visibly labelled development-only and no email delivery is claimed.

Clients receive Output A, Client Case Overview. Output B, Professional Legal Draft including the internal report and E-Filing Readiness Pack, is advocate-only. Unverified law remains pending.

Existing cases are retained. Owners can explicitly upgrade an old case after the backend saves a migration snapshot. Old preview page URLs lead to the overview; preview APIs return 410.

## Verification

```powershell
npm run test:backend
npm test
npm run build --prefix frontend
```

Browser tests start isolated servers on ports 8001/5174 with separate ignored storage and explicit mock mode. They validate workflow and permissions, not live legal correctness. `npm run test:legacy` retains historical preview-flow tests; these describe the retired workflow and are not the current acceptance suite.

PDF download needs the installed Node/Playwright Chromium renderer; HTML and DOCX exports also exist. PDF rendering in a Python-only Lambda deployment remains pending.

Admin verification requires a signed-in account with the `admin` role. Provision an existing operator account from the host using `.venv\Scripts\python.exe -m backend.admin_command --email operator@example.com`. Do not run this for an ordinary client or advocate. Set `ADMIN_VERIFICATION_HOSTS` to the official credential-record hosts reviewed by the operator. Verification requires supporting documents, an official record reference/URL, reviewer identity, current timestamp and notes. `ADMIN_TOKEN`, when configured, is an additional check; it never grants the admin role. Development demo advocates do not represent real credential verification.

Set `APP_ENV=production` to refuse mock or hybrid startup. Guest claiming in live mode requires `OTP_FROM_EMAIL` and authorized SES delivery. `CASE_RETENTION_DAYS` and `AUDIT_RETENTION_DAYS` configure deletion eligibility and restricted audit retention. Automatic scheduled deletion and audit expiry are pending; recorded requests can be retried once eligible. See [the latest phase status](docs/REDESIGN_PHASE_2.md) for validation and unfinished requirements.
