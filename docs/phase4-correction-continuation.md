# Record 1: submit an existing correction without replaying review

The local client now accepts `--submit-correction-only`. It authenticates normally with an interactive email and hidden password, reads authority history, checks the exact requested head and receipt, and makes only one authority source POST. It never calls the review-decision endpoint in this mode. Do not run another client/admin operation concurrently: the preflight is a read followed by the existing server submission endpoint, not a transaction spanning both requests. Server-side head compare-and-swap and post-write verification remain in effect.

Preflight rejects a changed head, absent/wrong receipt, non-requested state, newer decision, existing child revision, wrong source, altered statutory binding, or client-supplied reviewer/time/lineage fields. The server derives the new parent and request receipt. After submission the client reads history and checks the new head, preserved prior versions/receipts, exact parent/receipt, pending state, cleared reviewer fields and unchanged text/hash/offsets. No authority approval is requested.

From the project root, run once:

```powershell
.\.venv\Scripts\python.exe -B scripts/record-authority-review.py --port 8012 --source-id cpa2019_s2_7 --revision 53fd4f1a3956c751ea8f270d161c6611c414f0e92d19af78eaed99c24a089e9d --submit-correction-only --existing-receipt 1e4dffb85d2b4e3b9cb99bf680990061 --corrected-source-file '.localdev/phase4-authority-review/record-1/external-request-correction/corrected-source-submission.json'
```

The review server must already be running on loopback port 8012 with the existing authority and identity databases. The command prompts locally; no password/token belongs in argv or chat. Use the submitting administrator account; the submitter cannot subsequently approve the new revision. If this server requires its optional additional admin credential, use the existing hidden-prompt flag instead of supplying a credential value in argv.

Any failure stops the command without automatic retry. A failed response or post-write verification can mean a new revision already exists: preserve the safe diagnostic and inspect history before continuing. Do not rerun the decision or bootstrap. The command does not alter the accepted payload's documentary metadata; `PROPOSED_NOT_SUBMITTED` describes its preparation provenance, while the server submission event is authoritative for actual submission. The payload contains no fabricated authenticated submission receipt.

This handoff does not claim submission has happened, amendment coverage is complete, or Phase 4 is legally ready. The source remains pending until a fresh independent review. Engine 2 remains out of scope.
