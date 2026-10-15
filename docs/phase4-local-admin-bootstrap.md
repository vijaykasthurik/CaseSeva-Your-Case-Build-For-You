> Historical Phase-4 procedure: administrator identities and receipts remain preserved, but administrator role no longer authorizes new legal reviews. New decisions require a verified advocate with `LEGAL_AUTHORITY_REVIEW`. See [current role and permission contract](role-boundary-authority-review.md). Bootstrap/password recovery does not grant this capability.

# Phase 4: supported local administrator provisioning

13 October 2026. This is the explicitly authorized development/review provisioning path for this checkout. It is not a production IAM/Cognito design. Implementation and tests do not create your account.

## Run locally in PowerShell

```powershell
Set-Location -LiteralPath 'C:\Projects Vijay\AWSHACK'
.\.venv\Scripts\python.exe -B scripts/provision-review-admin.py --allow-admin-bootstrap
```

The command asks you to type `CREATE REVIEW ADMIN`, then prompts for administrator email, a hidden password and hidden password confirmation. The existing application rule requires at least eight characters. Enter your own credentials locally; do not paste them into chat. No password argument, password environment variable, automatic account, demo credential or public signup is supported.

The dedicated identity file is `.localdev/phase4-authority-review/identity.json`, inside the ignored local directory. It is separate from `.localdev/phase4-authority-review/database.json`, which contains the authority records. The command cannot select another database path or a network host.

The controlled authentication-adapter method validates the email and existing password rule, hashes the password with the application's existing salted PBKDF2 function, and inserts a new `admin` account with server `created_at` and provisioning audit metadata. It does not issue a session. The local OS operator name is an audit hint, not an authenticated application reviewer identity. Actual review identity and timestamp are obtained later from normal login and the review server.

## Safeguards

- Explicit bootstrap flag and typed interactive confirmation are required. Redirected/piped input and unavailable hidden-password entry are refused.
- Run from the project root using this project's `.venv` interpreter. The entry point rejects known SSH/remote-desktop invocation, linked paths, paths outside the project, UNC/network paths and non-fixed Windows drives. There is no network bootstrap endpoint or listener. These checks do not claim to protect against a malicious local process already able to alter application files.
- Account insertion and the one-time bootstrap marker are committed together under the existing local database file lock. Concurrent bootstrap attempts cannot create two admins. The marker remains after account deletion, so deleting a user does not reopen bootstrap.
- Duplicate email addresses, including existing client/advocate accounts, are rejected without mutation. Existing admins also prevent bootstrap. No promotion path is implemented.
- Passwords/tokens are never printed. Unknown command arguments are rejected without echoing their values. No password hash is copied from another account or database. No accounts are seeded.
- The public signup API still rejects admin roles. No HTTP provisioning route is added.
- The local file uses the existing adapter's filesystem/storage model and inherited local permissions. Keep this review identity database local and excluded from source control; this work does not implement production secret storage or replace authentication.

## After you create your real administrator

The assistant has not run the provisioning command against real data. Tell the assistant when your local command succeeds; no password or token is needed in chat. The isolated server can then be started with:

```powershell
.\.venv\Scripts\python.exe -B scripts/serve-authority-review.py --identity-database '.localdev/phase4-authority-review/identity.json' --authority-database '.localdev/phase4-authority-review/database.json' --port 8012
```

It binds only to `127.0.0.1`. In a second local PowerShell terminal, use the following command, replacing the email placeholder with the administrator email you just entered:

```powershell
.\.venv\Scripts\python.exe -B scripts/record-authority-review.py --port 8012 --email '<your administrator email>' --source-id cpa2019_s2_7 --revision d9804b732b3d855c06cf5c0143b721a5e9d0ad775092810c2f236150a51a024e --decision NEEDS_NEW_REVISION --reason-file '.localdev/phase4-authority-review/record-1/reason.txt' --corrected-source-file '.localdev/phase4-authority-review/record-1/corrected-source-submission.json'
```

This prompts locally for the hidden password, authenticates normally, records the exact `NEEDS_NEW_REVISION` decision, checks the receipt against the authenticated identity and server timestamp, submits a new corrected pending revision and confirms that the receipt is unchanged. The client never requests approval in this sequence. The server supplies parent/request lineage. The new revision requires fresh independent approval and its submitter cannot approve it.

If the server uses its existing optional `ADMIN_TOKEN` check, add `--additional-admin-credential`; that credential is also entered through a hidden prompt. The server does not automatically load `.env`. The client logs out after its authenticated operation and prints only non-secret result fields.

Recording the request and submitting the correction are separate persisted operations. If correction submission fails after the request succeeds, the immutable receipt remains valid; inspect history before retrying. Replaying the old revision is rejected. Do not delete history or repeat bootstrap to bypass a failure.

Until these real authenticated operations succeed, the original `cpa2019_s2_7` head remains `d9804b732b3d855c06cf5c0143b721a5e9d0ad775092810c2f236150a51a024e`, and corrected draft `a36240fa45fbaa6d553f77f5f7824de82d6961c2b38df27c0235df74f946239e` remains inactive. No authority is approved by provisioning an account.

## Validation and scope

Regression coverage uses fictional credentials and isolated temporary files only: successful creation, login, audit metadata, no bootstrap session, duplicate/email/role checks, one-time concurrency, password rules, secret-output checks, missing flag, unsafe invocation, explicit confirmation, admin/non-admin endpoint access, public signup rejection, and the authenticated receipt-to-corrected-revision sequence with self-review refusal.

Final results and every changed file are recorded in section 45 of [the Phase 4 report](phase4-legal-foundation-report.md). Phase 4 remains review-gated; Engine 2 has not started.
