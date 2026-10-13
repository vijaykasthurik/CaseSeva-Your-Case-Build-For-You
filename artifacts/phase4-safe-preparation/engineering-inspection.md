# Engineering inspection — preparation checkpoint

No production code changes. This bounded inspection does not certify every concurrency or production failure mode. No accounts, decisions or live revisions were created.

| Area | Inspected implementation and current check | Result / limitation |
|---|---|---|
| Immutable lineage | `VerifiedCorpus.publish`, `AuthorityReview.submit`; canonical hashes and parent-source identity for all 18 persisted versions | Pass for saved history. Inactive branch returns before submission attribution/head advancement. External drafts never call publish/submit. |
| Review integrity | `authority_digest`, existing receipt input revision binding | One real NEEDS_NEW_REVISION receipt matches its original input. No receipt edited/replayed. Receipt insertion and head CAS are separate operations; this inspection is not an atomic multi-operation crash/concurrency certification. |
| Read-time hiding | `authority_manifest`, `current_case_file`; pending-source negative probe | Returns empty projection even with a caller-supplied current flag. Dependency manifest checks source versions and reviewed temporal support. Genuine positive-to-stale validation remains blocked. |
| Source fingerprints | `VerifiedCorpus.sync_case` | Issue-scoped candidate/dependency versions and usability included. Full Phase 3/team dependency invalidation remains conservative; no scheduler redesign. No live case mutated for this inspection. |
| Public projections | `overview.py`, `sharing.py` | Reuse read-time authority checks and safe processing-error projection. Existing security regressions remain historical; no newly executed full permission suite claimed. |
| Capacity | `CaseBlackboard._save`, legal worker capacity handler | Size guard precedes snapshot write; typed capacity path clears current flag and reports safe review-needed message. No limit increase or truncation introduced. |
| Inactive isolation | All 13 proposed digests absent from persisted versions; schema/approval gate checks | Pass. Drafts are files only, have no submitter event or receipt and cannot enable authority. |
| Human independence | Existing account-ID self-review check and documented same-person second account | Account distinction is not proof of human independence. External human review remains blocked; no technical person-identity verification is claimed. |

No demonstrated failure in the bounded checks required an application change. Remaining limitations are disclosed rather than marked fixed. Full backend/browser/build regression is required after future production-code changes; it was not rerun for these documentation/data artifacts. Python compilation and six service imports passed; see validation.json. No DynamoDB, Transcribe, Bedrock or Engine 2/3 call.
