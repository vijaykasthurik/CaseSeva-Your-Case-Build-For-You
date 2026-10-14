# CaseSeva Phase 4: Authenticated Human-Review Session Checklist

This checklist provides the operational protocol for an authenticated, independent human administrator conducting statutory provision review in CaseSeva.

> **CRITICAL DIRECTIVE**: The AI system only presents inspection packages and verified technical provenance.
> The AI strictly abstains from recommending approval. The human reviewer holds exclusive decision authority.

---

## 1. Reviewer Requirements & Authentication Gate
Before inspecting any candidate provision, ensure:
1. **Authenticated Administrator Account**: Review decisions must be submitted via an active admin account. Citizen, advocate, or unauthenticated accounts are rejected with `PermissionError`.
2. **Separation of Duties (No Self-Review)**: The reviewer identity must be distinct from the ingestion actor. Self-approval attempts are blocked with `PermissionError`.
3. **Server-Bound Identity**: Reviewer ID and role are resolved exclusively from the authenticated session, preventing client-side override.
4. **Optimistic Version Lock**: Decisions require the expected immutable `version_id`. Outdated or changed candidate versions fail immediately with `ValueError`.

---

## 2. 10-Point Provision Inspection Protocol
For each candidate in `docs/audits/phase4_review_queue.json`, inspect the matching inspection package in `docs/audits/review_packets/{source_id}.json` using the following steps:

### Point 1: Official Document Identity
- Confirm the parent document matches an authentic enactment title and citation.
- Verify `official_url` and `final_url` link to the official gazette / government publication endpoint (e.g. `indiacode.gov.in`).

### Point 2: GridFS Raw Object & SHA-256 Hash Match
- Confirm `raw_gridfs_file_id` is present and resolves to stored bytes in MongoDB GridFS (`fs.files`).
- Verify the SHA-256 digest of stored bytes matches `raw_sha256` in the review packet.

### Point 3: Exact Provision Text
- Review `exact_official_excerpt` against the extracted text.
- Ensure the quote is verbatim statutory language without truncation, paraphrasing, or AI summarization.

### Point 4: Surrounding Statutory Context
- Inspect `surrounding_context` to understand preceding and following provisions, chapter titles, and headings.

### Point 5: Source Registry & Ownership
- Verify `registry_id` belongs to an authorized government repository (`india_code_central`).
- Confirm `official_owner` is an authentic government authority.

### Point 6: Extraction Accuracy
- Confirm `extraction_method` (e.g., `pymupdf`) cleanly extracted characters without OCR artifacts, missing lines, or encoding garble.

### Point 7: Section Boundary Accuracy
- Verify `section_start` and `section_end` character offsets accurately encompass the intended statutory provision without clipping trailing subsections.

### Point 8: Amendment, Commencement & Repeal Warnings
- Review `discovered_relationships` (marked `UNVERIFIED`).
- For the **Code on Wages, 2019**: Note that specific sections (e.g., Sections 1, 3, 5, 6) have distinct commencement notifications issued under Section 1(3). Confirm whether relevant commencement notifications have been officially published in the Gazette of India.

### Point 9: Temporal Coverage Disclaimer
- Verify the presence of the mandatory disclaimer:
  > *"Current-law coverage has not been established. Do not infer that an official consolidated PDF is current through today."*
- Reviewer must independently determine whether subsequent statutory amendments have modified the provision before setting `temporal_reviewed=True`.

### Point 10: Mandatory Written Rationale
- The reviewer must provide a substantive written explanation for their decision (`reason`). Blanket, empty, or boilerplate approvals are rejected by the review service.

---

## 3. Review Decision Options
An independent human administrator may select one of four valid states:

| Decision | State Transition | Consequence |
| :--- | :--- | :--- |
| `REVIEWED_PRIMARY` | `REVIEW_PENDING` -> `REVIEWED_PRIMARY` | Authority promoted to head; provision becomes retrieval-eligible in `VerifiedCorpus` |
| `REJECTED` | `REVIEW_PENDING` -> `REJECTED` | Candidate rejected; remains permanently quarantined from `VerifiedCorpus` |
| `NEEDS_NEW_REVISION` | `REVIEW_PENDING` -> `NEEDS_NEW_REVISION` | Flags requirement for fresh acquisition, re-sectionization, or cleaner PDF |
| `STALE` | `REVIEW_PENDING` -> `STALE` | Marks candidate as superseded by later enactment or notification |

---

## 4. Current Phase-4 Curated Queue Overview (12 Genuine Candidates)

| # | Source ID | Domain | Section | Parent Document | Version ID (First 12) |
| :-: | :--- | :--- | :-: | :--- | :--- |
| 1 | `dspe_act_1946_s1` | `CRIMINAL_POLICE` | 1 | The Delhi Special Police Establishment Act, 1946 | `4297fc1997cb...` |
| 2 | `dspe_act_1946_s2` | `CRIMINAL_POLICE` | 2 | The Delhi Special Police Establishment Act, 1946 | `89ce02ccd0d7...` |
| 3 | `dspe_act_1946_s3` | `CRIMINAL_POLICE` | 3 | The Delhi Special Police Establishment Act, 1946 | `38a342f2a3a4...` |
| 4 | `dspe_act_1946_s6` | `CRIMINAL_POLICE` | 6 | The Delhi Special Police Establishment Act, 1946 | `9e5cbab77e23...` |
| 5 | `it_act_2000_s1` | `CYBER` | 1 | The Information Technology Act, 2000 | `fc8d6d1c8b94...` |
| 6 | `it_act_2000_s3` | `CYBER` | 3 | The Information Technology Act, 2000 | `b3b5925b41dc...` |
| 7 | `it_act_2000_s43` | `CYBER` | 43 | The Information Technology Act, 2000 | `fb66bb523bb2...` |
| 8 | `it_act_2000_s66` | `CYBER` | 66 | The Information Technology Act, 2000 | `7996a9c4994c...` |
| 9 | `wages_code_2019_s1` | `LABOUR_EMPLOYMENT` | 1 | The Code on Wages, 2019 | `d1c00549bf81...` |
| 10 | `wages_code_2019_s3` | `LABOUR_EMPLOYMENT` | 3 | The Code on Wages, 2019 | `2a639da5c899...` |
| 11 | `wages_code_2019_s5` | `LABOUR_EMPLOYMENT` | 5 | The Code on Wages, 2019 | `96307452acb7...` |
| 12 | `wages_code_2019_s6` | `LABOUR_EMPLOYMENT` | 6 | The Code on Wages, 2019 | `b70c9b635e6a...` |
