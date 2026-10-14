# CaseSeva Developer Guide: MongoDB Compass & Local Persistence

**Document Version:** 1.0.0  
**Target Environment:** Local Developer Machine  
**Database Server:** MongoDB Community Server 8.0+  
**Developer GUI:** MongoDB Compass 1.50+  

---

## 1. Architectural Distinction: Compass vs Runtime

> [!IMPORTANT]
> **MongoDB Compass is NOT runtime architecture.**  
> It is strictly an administrative and visualization GUI for developers.
> The runtime application connects directly to MongoDB Community Server via PyMongo drivers at `mongodb://127.0.0.1:27017`.
> 
> **Manual Compass edits must NEVER be used to bypass legal review gates, reviewer separation of duties, or Case File approval rules.**

---

## 2. Connecting with MongoDB Compass

1. Open **MongoDB Compass**.
2. In the **New Connection** dialog, paste the connection string:
   ```text
   mongodb://127.0.0.1:27017
   ```
3. Click **Connect**.
4. In the left navigation bar, select the database:
   ```text
   caseseva
   ```

---

## 3. Collections Reference

When opening the `caseseva` database in MongoDB Compass, developers will see the following collections:

| Collection Name | Description | Key Fields to Inspect |
|---|---|---|
| `users` | Authenticated citizen and advocate accounts | `email`, `role`, `verification_status`, `password_hash` (PBKDF2 salted hash, never plaintext) |
| `sessions` | Active user session tokens | `id` (session token), `user_id`, `created_at` |
| `cases` | Case entities, client stories, dynamic domains | `case_id`, `owner_user_id`, `status`, `legal_issues`, `evidence` |
| `case_board_heads` | Active pointer to the Case Blackboard head | `id` (case_id), `version`, `snapshot_id` |
| `case_board_snapshots` | Immutable, auditable historical Blackboard versions | `id` (snapshot_id), `case_id`, `version`, `previous`, `data`, `event` |
| `advocate_requests` | Formal requests from citizens to advocates | `case_id`, `advocate_id`, `status`, `created_at` |
| `documents` | Metadata for generated/exported case documents | `id`, `case_id`, `type`, `version`, `gridfs_file_id`, `sha256` |
| `workflow_runs` | Engine execution runs and states | `id`, `case_id`, `engine`, `status` |
| `notifications` | User alerts and document readiness notifications | `id`, `user_id`, `message`, `read` |
| `audit_events` | Append-only audit trail of actions taken on cases | `id`, `case_id`, `event_type`, `actor`, `created_at`, `detail` |
| `legal_authorities` | Active legal authority heads mirrored for querying | `source_id`, `version_id`, `head`, `current_source` |
| `legal_authority_heads` | Authoritative pointer to current revision for each source | `id` (source_id), `version` |
| `legal_authority_versions` | Immutable revisions of statutory sections/judgments | `id` (version digest), `source`, `reason` |
| `legal_authority_reviews` | Cryptographically bound human review receipts | `id` (review_id), `source_id`, `source_digest`, `reviewer_id`, `decision` |
| `legal_review_submissions` | Submissions of authorities for human review | `id`, `actor`, `source_id`, `submitted_at`, `events` |
| `legal_ingestion_requests` | Discovery & parsing pipeline records | `id`, `registry_id`, `official_url`, `state`, `raw_hash`, `content_hash` |
| `reviewer_identities` | Isolated authority-review administrator accounts | `id`, `email`, `role` (admin), `provisioning.method` |
| `review_admin_bootstrap` | Immutable one-time bootstrap audit record | `id` ('one-time'), `user_id`, `scope` ('PHASE4_REVIEW_ONLY') |
| `review_admin_provisioning`| Authenticated onboarding audit trail for reviewers | `id`, `user_id`, `authorized_by`, `scope` |

---

## 4. Binary Files in GridFS (`fs.files` & `fs.chunks`)

In MongoDB Compass, binary assets (PDFs, evidence uploads, scanned documents, audio recordings, exports) are stored in GridFS buckets:

- **`fs.files`**: Metadata documents for each stored file:
  - `_id`: ObjectId of the GridFS file (referenced by `gridfs_file_id`).
  - `filename`: Storage key (e.g. `cases/87dba4f6.../E001-invoice.txt` or `reports/v1/draft.html`).
  - `length`: File size in bytes.
  - `chunkSize`: Default 261,120 bytes (255 KB).
  - `uploadDate`: UTC timestamp of upload.
  - `metadata.sha256`: Verified SHA-256 digest of binary content.
  - `contentType`: MIME type (e.g. `application/pdf`, `text/html`, `image/png`).
- **`fs.chunks`**: Binary data broken into chunks:
  - `files_id`: Points to `_id` in `fs.files`.
  - `n`: Chunk sequence index (0, 1, 2, ...).
  - `data`: Binary BSON buffer.

> [!TIP]
> To view a file's metadata in Compass:
> 1. Click on `fs.files`.
> 2. Search by filename: `{"filename": /invoice/}`.
> 3. Verify `metadata.sha256` and `length`.

---

## 5. Local AWS-Independent Operation

When developing locally:
1. Ensure MongoDB Community Server is running:
   ```powershell
   mongod --version
   ```
2. Set environment variables (or let defaults apply):
   ```text
   MONGODB_URI=mongodb://127.0.0.1:27017
   MONGODB_DATABASE=caseseva
   DATABASE_PROVIDER=mongodb
   OBJECT_STORE_PROVIDER=mongodb
   ```
3. Run CaseSeva normally:
   ```powershell
   .venv\Scripts\python -m uvicorn backend.main:app --port 8000
   ```
No AWS credentials, DynamoDB tables, or S3 buckets are needed for full local operation.
