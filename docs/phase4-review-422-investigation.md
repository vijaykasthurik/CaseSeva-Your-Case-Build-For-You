# Phase 4: HTTP 422 investigation

13 October 2026. No real review request was replayed, source submitted, account changed, bootstrap rerun or authority history repaired during this investigation.

## Persisted state inspected first

The real local identity database contains one provisioned administrator and one bootstrap marker. No password, session token or stored credential hash was printed or copied into a test database. The administrator identity was preserved.

For `cpa2019_s2_7` in `.localdev/phase4-authority-review/database.json`:

| Check | Observed |
| --- | --- |
| Current head | `d9804b732b3d855c06cf5c0143b721a5e9d0ad775092810c2f236150a51a024e` |
| Current status | `REVIEW_PENDING`; no `REVISION_REQUESTED` state |
| Formal review receipts | Zero |
| Source revisions | Three, all prepared before the failed attempt: original `d9804…`, earlier inactive preparation `142b…`, inactive corrected candidate `a362…` |
| Submission events | Two pre-existing events: original ingestion on 12 October and earlier preparer event on 13 October; none from the failed attempt |
| Corrected candidate | `a36240fa45fbaa6d553f77f5f7824de82d6961c2b38df27c0235df74f946239e`, inactive, no submission event, no receipt |
| Rationale | 251 characters; valid nonempty UTF-8, within the 1–4,000-character limit |
| Corrected JSON | Present and readable; no server-owned reviewer/time/lineage fields supplied |

The running loopback service identifies itself as the isolated authority-review app and its OpenAPI schema includes `NEEDS_NEW_REVISION`. Its process arguments point to the requested relative identity and authority database paths. The intended review body validates against the checkout's request model. The stored administrator email passes the login email format rule. The user confirmed using their actual email; the redacted invocation matches the documented flags.

## Exact cause: not yet established

The original client discarded the response detail and operation name. The saved state does **not** reveal which request returned 422. It would be incorrect to label this a revision-state failure, bad password, placeholder email or successful persisted request without further evidence.

| Candidate condition | Finding |
| --- | --- |
| Review request model | Intended body validates; running schema supports the decision. The historical received body/error was not retained. |
| Expected/current version mismatch | Head matches; this service reports such conflicts as 409, not 422. |
| Review-state precondition | No requested state exists; intended request succeeds in an isolated copy. Preconditions report 409. |
| Reviewer independence | Approval-only guard returns 403; this is a revision request, not approval. |
| Extra admin credential | Missing/invalid credential returns 403, not 422. Actual configured secret was not inspected or exposed. |
| Decision transition | Supported by running schema; no persisted transition from the failed attempt. |
| Reason/note | Current 251-character rationale validates. |
| Revision lineage/source submission | A corrected submission occurs after a review receipt; there is no receipt here. No evidence of a later corrected-source failure. |
| Login validation | Can return 422 for malformed email/input. Stored email is valid and user reports using it; not proven to be the cause. |

A guaranteed nonexistent diagnostic email was used once to check the running login endpoint, with no real credentials. It returned 401 as expected. Both real database files were verified byte-for-byte unchanged by that probe. No administrator authentication was attempted by the assistant.

## Client changes

Failures now identify the operation (`login`, `authenticated_identity`, `record_review_decision`, `verify_review_receipt`, `submit_corrected_source`, `verify_corrected_revision`, `logout`) and status. A strict allowlist exposes validation field locations/types and known-safe messages. It omits echoed input, arbitrary server messages, context, headers, cookies and credentials. A logout failure no longer masks the original failure. UTF-8 BOM files are accepted.

The new `--check-access-only` mode authenticates normally, reads identity and authority history, then logs out. It never posts a review or corrected source. It does create/delete the normal transient login session in the identity database; it does not alter users or authority data.

## Safe next diagnostic command — not a review retry

Run locally from the project root:

```powershell
.\.venv\Scripts\python.exe -B scripts/record-authority-review.py --port 8012 --email (Read-Host 'Administrator email') --source-id cpa2019_s2_7 --revision d9804b732b3d855c06cf5c0143b721a5e9d0ad775092810c2f236150a51a024e --decision NEEDS_NEW_REVISION --reason-file '.localdev/phase4-authority-review/record-1/reason.txt' --check-access-only
```

Enter the password only at its hidden local prompt. Return only the safe JSON result. Do not send credentials. This diagnostic is needed before recommending a state-changing retry. If access succeeds, it narrows the failure further; it does not prove that the earlier 422 cause has been recovered.

No continuation/submission command is appropriate yet: no formal receipt exists. Do not rerun the full decision merely to obtain better logging while the exact failure remains unresolved.

## Tests and limits

- Focused client/provisioning/review regression: **28 passed in 14.243 seconds**.
- Added regressions for secret redaction, real login validation detail, preservation of a review failure when logout also fails, and check-only behavior.
- A temporary copy of the exact original official authority/ingestion record, using a fictional test admin, accepted the intended request and produced a revision-request receipt. No real identity hashes were copied and the real authority file remained byte-for-byte unchanged. This test is skipped if the local official bundle is unavailable; existing synthetic review tests remain portable.
- The first focused run had one test-harness failure because redirecting stderr replaced the mocked interactive stream. The harness order was corrected; no application validation was weakened.
- All **156** backend/scripts Python files compiled in memory. `git diff --check` passed.
- No frontend, engine, corpus logic or authentication rule changed. The complete 224-test backend and final 17-test browser results in section 45 are prior-phase results, not reruns for this diagnostics-only change.

Implementation checkpoint: `ed5a3ff`. Files changed: `scripts/record-authority-review.py`, new `backend/tests/test_review_client_diagnostics.py`, this report and the Phase 4 report cross-reference. The original history, administrator and inactive candidate are preserved. Phase 4 remains review-gated; Engine 2 has not started.

## Follow-up: access confirmed and real HTTP reproduction

The user returned successful `check_access_only`: expected/current revisions match, zero review receipts, and no review/source posted. Authentication, identity access and authority-history access currently succeed.

The next reproduction used **real urllib HTTP requests to Uvicorn on a temporary loopback port**, not the prior in-process transport substitution. Only the original official source/version and its ingestion record were copied to a temporary authority database. A fictional test administrator was created in a separate temporary identity database; no real identity or password hash was copied. The exact saved rationale and corrected-source JSON were supplied to the normal client. Both review and corrected-source POSTs succeeded, the immutable request receipt was verified, and the new test revision remained unapproved/pending. The real authority and identity files were byte-for-byte unchanged throughout this test.

The running server's review request schema matches the checkout's schema (`properties`, `required`, and `additionalProperties`); its only review-POST parameter is the `source_id` path parameter. No unexpected query field or unsupported decision was found.

**Result:** there is no reproduced review-POST 422 to fix. The historical generic error cannot establish its operation or validation condition. Current access success does not prove where the earlier error occurred. No business rule, request schema, permission or actual review state was changed to force success. No real one-time replay is recommended under the user's explicit requirement that root cause be identified first. The missing evidence is the original structured failure detail or an equivalent failing reproduction; the earlier client did not retain it.

Added regression: `test_real_http_client_with_exact_official_candidate_and_corrected_payload`. It runs only when the local official bundle is available. A standalone execution passed in 1.085 seconds; the combined authority/client/provisioning regression result is recorded in the Phase 4 report. This is test-only workflow validation, not a real admin decision or legal completion.
