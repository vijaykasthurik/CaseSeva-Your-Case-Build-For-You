# Additional local authority reviewer

This is a development/review-only path for the existing isolated identity database. It is not production IAM/Cognito provisioning. It never reopens bootstrap, promotes an existing account, or reviews an authority. No additional account is created by installation or tests.

Run in a local interactive PowerShell console:

```powershell
Set-Location -LiteralPath 'C:\Projects Vijay\AWSHACK'
.\.venv\Scripts\python.exe -B scripts/add-review-administrator.py --allow-reviewer-onboarding
```

Enter the existing administrator email and password at the prompts. Password input is hidden. Type `ADD REVIEW ADMIN` to confirm. Enter the different reviewer's email, then have that reviewer enter and confirm their own new password locally (at least eight characters, matching the existing application rule). Do not share credentials in chat or pass them as arguments. The authorizing administrator's temporary login session is logged out on exit.

The command requires this checkout's virtual environment, project working directory, interactive local console and fixed local storage. Remote sessions, redirected input, linked review paths and arbitrary host/password arguments are refused. It uses only `.localdev/phase4-authority-review/identity.json`; no authority database is opened. An existing bootstrap marker is required and preserved. Duplicate emails across every role are rejected without promotion. Authorization is checked again inside the database write lock, alongside duplicate checks.

The new account and audit entry are written together. Audit metadata records the existing authenticated administrator ID, server/local UTC creation time, OS operator and review-only scope. Password hashing uses the existing application adapter with a fresh salt. No credential is copied, printed or placed in the audit entry. No new-reviewer session is issued by provisioning.

A distinct account ID does **not** establish independent human review. A genuinely different person must authenticate normally and examine the source. The original submitter remains unable to approve their own revision. Creating this account does not approve any authority.

After successful provisioning, report completion without credentials. We will then prepare a read-only review package for revision `fdd9c175c4fb253f74e3a5b8a4e846398e9efd871e770278fe79db0aec8fe14c`, including the original official PDF, exact excerpt, old/new revision comparison, amendment/version and commencement/temporal metadata, structured rules, unresolved issues, recommendation and exact decision commands. Do not replay the existing revision request or resubmit this revision. No decision command is executed automatically. Unresolved legal metadata continues to require a new revision rather than approval.
