# CaseSeva.ai

CaseSeva.ai is a legal case intelligence platform prototype. Parts 1 through 3 provide the project foundation, offline AWS adapter layer, client authentication, profile management, case intake, story autosave, evidence storage, and browser-tested flows.

## Prerequisites

- Python 3.11+
- Node.js 18+
- npm

## Install

From the repository root:

```powershell
npm run install:all
```

This creates `.venv`, installs the backend and frontend dependencies, and installs Chromium for tests. Equivalent manual steps:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
npm install
npm install --prefix frontend
npx playwright install chromium
```

Start both servers from the repository root (no virtual environment activation required):

```powershell
npm run dev
```

Open `http://127.0.0.1:5173`. The startup command uses `.venv` and forces local mock adapters, so AWS credentials are not required. Stop both servers with Ctrl+C before running the tests.

## Run the backend

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Health endpoint:

```text
http://127.0.0.1:8000/api/health
```

## Run the frontend

In a second terminal:

```powershell
npm run dev --prefix frontend
```

Open `http://127.0.0.1:5173`.

## Authentication flow

- Visit `/signup` to create a client account.
- Successful signup creates an authenticated session and opens `/dashboard`.
- Visit `/profile` to edit the name, mobile, language, state, or district/city.
- Visit `/login` to sign in with an existing account.
- Sessions are stored in browser local storage and sent as bearer tokens.

## Case intake flow

- From the dashboard, choose **Start a new case**.
- Select one of the three plain-language case stages.
- Enter the client story; draft changes are saved to the backend as you type.
- Upload images, PDFs, documents, text files, spreadsheets, or common video files.
- Review and submit a complete case to move it from `DRAFT` to `READY_FOR_ANALYSIS`.
- Draft evidence receives stable IDs such as `E001`, `E002`; deleted IDs are not reused.

## Run the end-to-end test

The Playwright configuration starts both servers automatically:

```powershell
npx playwright test
```

The Playwright suite resets `.localdev/playwright-database.json` and `.localdev/playwright-uploads` before each run. It covers authentication, profile persistence, case stages, stage switching, story autosave, evidence upload/deletion, validation, submission status, ownership enforcement, and the Part 1 health smoke test.

Or, if GNU Make is available:

```text
make test
```

## Adapter mode

Set `USE_MOCK_AWS=true` to use the fully offline local adapters. Set it to `false` to load the AWS adapter stubs; real AWS operations intentionally raise `NotImplementedError` until later implementation parts.

No code outside `backend/adapters/real/` imports or references AWS SDK code.
