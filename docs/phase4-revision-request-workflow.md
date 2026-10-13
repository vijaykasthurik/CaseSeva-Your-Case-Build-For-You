# Phase 4: revision requests and authenticated review

Prepared 13 October 2026. Phase 4 only. No Engine 2 work or formal review decision performed.

## Current status

The `NEEDS_NEW_REVISION` workflow is implemented. An authenticated request creates an immutable receipt with that exact decision, sets `revision_status=REVISION_REQUESTED`, and keeps `review_state=REVIEW_PENDING`, `source_reviewed=false`, `verification=PENDING`. The server reads the reviewer from the persisted authenticated account and assigns the timestamp. Payload identity, timestamps and revision lineage are rejected. The old revision and receipt are preserved.

A corrected submission creates a new immutable revision linked to the current revision and request receipt. It clears approval fields and requires a fresh independent review. The actual submitter cannot approve it. An inactive draft has no authenticated submission event, does not advance the source head and cannot be reviewed. Activating a draft cannot reuse another actor's submission attribution. History is available only to authenticated admins at `GET /api/admin/authorities/{source_id}/history`; there is no history edit/delete API.

Your chat instruction for record 1 is preserved as an instruction, **not** an authenticated receipt. There are **zero users and zero formal review receipts** in the isolated authority database. All 14 current authorities remain pending. Record 1's corrected draft is inactive and unusable. Records 2–14 have no new decisions recorded.

## Connect an existing administrator without importing credentials

The supported bridge uses an **existing local application account database** for normal login and session validation, while keeping authority records in the isolated review database. It does not copy accounts, import password hashes, create users or change roles. Both files must already exist. Startup refuses an identity database without an existing password-authenticated admin. No demo users are seeded.

This bridge supports the application's current local authentication adapter. It is not a Cognito/SSO import, does not connect to DynamoDB and is not a production authentication upgrade. It writes ordinary login/logout sessions to the selected identity database; authenticated review writes go to the authority database. Role demotion is checked on subsequent requests. Review-only routing exposes login/logout/me and authority administration, with no signup or profile/role mutation routes. It binds to loopback only.

In PowerShell, from `C:\Projects Vijay\AWSHACK`, replace the account-database placeholder with the path to an application database that already contains your legitimate administrator:

```powershell
.\.venv\Scripts\python.exe -B scripts/serve-authority-review.py --identity-database "<existing application database path>" --authority-database ".localdev/phase4-authority-review/database.json" --port 8012
```

In a second terminal, replace only the email placeholder:

```powershell
.\.venv\Scripts\python.exe -B scripts/record-authority-review.py --port 8012 --email "<existing administrator email>" --source-id cpa2019_s2_7 --revision d9804b732b3d855c06cf5c0143b721a5e9d0ad775092810c2f236150a51a024e --decision NEEDS_NEW_REVISION --reason-file ".localdev/phase4-authority-review/record-1/reason.txt"
```

The client prompts for your application password locally with hidden input. It logs in normally, keeps the session token in memory, submits only `expected_version`, `decision`, and `note`, prints non-secret receipt fields, then logs out. Do not put credentials in command arguments or chat. If the server is configured with the existing optional `ADMIN_TOKEN` control, add `--additional-admin-credential`; this prompts locally for that extra credential without displaying it. The server command does not automatically load a `.env` file.

**If no legitimate administrator exists anywhere:** the current application's normal signup supports only clients and advocates; profile editing cannot grant admin. There is no supported admin creation command to give you. The bridge deliberately refuses to bootstrap or promote one. An explicitly authorized admin-provisioning workflow is still needed before authentication can occur. No raw database role edits, fabricated account or invented signup command are supplied.

## After real authentication

1. Run the revision-request command yourself while signed in with the genuine existing admin credentials at its local prompt. Until it succeeds, there is no formal receipt.
2. Check the returned identity, server timestamp, exact decision and new request-state revision. Replay against the old head is refused.
3. Submit the corrected source through the authenticated `POST /api/admin/authorities` workflow. The prepared payload is `.localdev/phase4-authority-review/record-1/corrected-source-submission.json`. It is a candidate for review, not approved law. The server sets its parent to the newly requested revision and attaches the actual receipt; consequently the submitted revision ID will differ from the inactive draft ID below.
4. Resolve the listed legal metadata questions and compare the exact new revision. The person who submits the corrected revision cannot approve that same revision. A different genuine authenticated admin is required for approval; no second identity is created by this work.
5. Review each remaining record individually. Unresolved amendment, temporal, jurisdiction or rule questions continue to warrant `NEEDS_NEW_REVISION`, never automatic approval.

The positive genuine-law citation, temporal applicability, remedy/jurisdiction, supported limitation, Consumer/RTI acceptance, real-source invalidation and conditional Case File publication checks remain gated on actual review and sufficient case facts. Phase 4 is not legally complete.

## Record 1: exact correction

The full machine-readable comparison is in `artifacts/phase4_record1_revision_draft.json`. The excerpt is unchanged from the existing downloaded official text; no new law or effective date is asserted.

| Field | Old current revision | New inactive draft | Reason |
| --- | --- | --- | --- |
| Revision | `d9804b732b3d855c06cf5c0143b721a5e9d0ad775092810c2f236150a51a024e` | `a36240fa45fbaa6d553f77f5f7824de82d6961c2b38df27c0235df74f946239e` | Preserve current source while preparing a distinct immutable candidate. |
| Corpus version | `phase4-review-candidate-1` | `phase4-review-candidate-3-inactive` | Distinguish preparation from authenticated submission. |
| Amendment/version | Unreviewed note, no structured review metadata | Original 2019 enactment; `current_law_verified=false`, `reviewed_through=null`; provision-specific amendment coverage required | Do not imply that original text establishes current law. |
| Effective date | Candidate `2020-07-20`; `temporal_reviewed=false` | Same candidate, explicitly `date_is_reviewed=false`, `event_date_inferred=false` | No reviewed commencement or missing case date is fabricated. |
| Commencement dependency | `cpa_commencement_2351` | Same dependency, explicitly bound in draft metadata to revision `7e2dcb4a26af77e48790839bd6df946687b7668d2a3f58125f2c7a9ce02aa370` and original content hash | Reviewer must check provision-specific coverage and exclusions, applicable version and interval. Dependency remains pending. |
| Temporal support | Source ID list only | Pending source ID, exact revision, hash, official PDF and required check | Make unresolved support auditable rather than marking it reviewed. |
| Structured rules | `{}`, `rules_reviewed=false` | Unchanged; proposed definition-reference scope only, no entitlement, forum, remedy or deadline rule | Definition applicability requires complete exclusions/Explanation and case-fact review. |
| Review identity/time/receipt | Null | Null | No authenticated administrator or formal request exists yet. |
| Parent/request lineage | No parent metadata | Parent is old current revision; request receipt null | Preserve preparation provenance without inventing formal review. |
| Source, excerpt, offsets, hashes, jurisdiction | Existing Consumer Act PDF; section 2(7), jurisdiction `IN` | Unchanged | Preserve source binding; no jurisdiction fact or legal coverage is invented. |
| Preparation | Original candidate | Explicit `INACTIVE_DRAFT`, authenticated submission false, fresh submission required | Draft cannot count as a reviewed or submitted authority. |

An earlier inactive preparation (`142b747106a7662b13de8cfd433a2deb02cd09240005001562d30d39c2382084`) is retained in local history. That preliminary implementation recorded a preparer submission event. It was never activated or reviewed. The final workflow does not record submission events for inactive drafts and refuses activation under another actor's existing attribution. The replacement draft above has no submission event. No historical record was deleted or rewritten.

Official source: [Consumer Protection Act 2019 PDF](https://consumeraffairs.gov.in/public/upload/files/CP%20Act%202019_1732700731.pdf). Pending commencement support: [notification PDF](https://consumeraffairs.gov.in/public/upload/files/Act%20into%20force_1732702865.pdf). These links identify stored source provenance; this continuation has not independently verified amendments or commencement.

### Exact stored excerpt, unchanged

```text
(7) "consumer" means any person who—
(i) buys any goods for a consideration which has been paid or promised
or partly paid and partly promised, or under any system of deferred payment
and includes any user of such goods other than the person who buys such
goods for consideration paid or promised or partly paid or partly promised, or
under any system of deferred payment, when such use is made with the approval
of such person, but does not include a person who obtains such goods for
resale or for any commercial purpose; or
(ii) hires or avails of any service for a consideration which has been paid
or promised or partly paid and partly promised, or under any system of deferred
payment and includes any beneficiary of such service other than the person
who hires or avails of the services for consideration paid or promised, or partly
paid and partly promised, or under any system of deferred payment, when such
services are availed of with the approval of the first mentioned person, but does
not include a person who avails of such service for any commercial purpose.
Explanation.—For the purposes of this clause,—
(a) the expression "commercial purpose" does not include use by a
person of goods bought and used by him exclusively for the purpose of
earning his livelihood, by means of self-employment;
(b) the expressions "buys any goods" and "hires or avails any
services" includes offline or online transactions through electronic means
or by teleshopping or direct selling or multi-level marketing;
```
