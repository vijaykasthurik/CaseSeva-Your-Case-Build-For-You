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

Common Input -> Engine 1 (automatic factual/legal Case File) -> optional Engine 2 (arguments only) -> Client Case Overview -> Find Advocate -> acceptance plus scoped client consent -> advocate review and optional targeted reruns -> Engine 3 (advocate only).

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

Admin advocate verification requires a server-configured `ADMIN_TOKEN`, supporting documents, and a recorded reason on `/admin/advocates`. There is no built-in admin credential. Development demo advocates do not represent real credential verification.
