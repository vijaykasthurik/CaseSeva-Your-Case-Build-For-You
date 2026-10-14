# CaseSeva Persistence Migration Mapping
**Document Version:** 1.0.0  
**Baseline Commit:** `6e5716c201dcac2fe4bb23b318de18950a002ded`  
**Target Persistence:** Local MongoDB Community Server (`mongodb://127.0.0.1:27017`), Database: `caseseva`  
**Target Developer GUI:** MongoDB Compass (`mongodb://127.0.0.1:27017`, `caseseva`)

---

## 1. Inventory of Current Persistence Mechanisms

| Current System | File / Location | Primary Role | Contents & Record Counts |
|---|---|---|---|
| **Main Local JSON DB** | `.localdev/database.json` | Local dev database for core app | Users (188), Sessions (187), Cases (120), Workflow Runs (192), Advocate Requests (50), Documents (78), Notifications (2) |
| **Phase 4 Authority Review DB** | `.localdev/phase4-authority-review/database.json` | Legal authority review & versioning | Heads (14), Versions (21), Reviews (3), Review Submissions (17), Ingestion Requests (6), Specialist Artifacts (3), Cases (1) |
| **Phase 4 Review Identity DB** | `.localdev/phase4-authority-review/identity.json` | Isolated review administrator identity | Users (4), Review Admin Bootstrap (1), Provisioning (3), Sessions (0) |
| **Local Uploads Directory** | `.localdev/uploads/` | Encrypted binary file storage (Fernet AES) | 305 files (invoices, job sheets, images, exported HTML/text) |
| **Local Storage Key** | `.localdev/uploads/.storage-key` | Fernet symmetric key for local uploads | 1 binary key file |
| **DynamoDB Adapter** | `backend/adapters/real/database.py` | AWS DynamoDB single-table persistence | `caseseva-data-dev` with PK/SK partitioning and `_revision` CAS |
| **S3 Adapter** | `backend/adapters/real/storage.py` | AWS S3 binary object storage | `caseseva-storage-dev` bucket in `ap-southeast-2` |
| **Case Blackboard Heads** | `case_board_heads` (inside JSON DB) | Pointer to active Blackboard snapshot | Keyed by `case_id`, holds `version` and `snapshot_id` |
| **Case Blackboard Snapshots** | `case_board_snapshots` (inside JSON DB) | Immutable versioned Blackboard states | Full snapshot data, events, node statuses, conflict records |

---

## 2. MongoDB Target Schema & Collection Mapping

| Source Entity / Collection | MongoDB Collection | `_id` Strategy | Primary Indexes & Constraints | Storage Engine |
|---|---|---|---|---|
| `users` (Clients, Advocates, Admins) | `users` | `record['id']` (UUID string) | `email`: UNIQUE, `role`: 1, `verification_status`: 1 | WiredTiger BSON |
| `sessions` | `sessions` | `token` string | `user_id`: 1, `created_at`: 1 | WiredTiger BSON |
| `cases` | `cases` | `case_id` string | `case_id`: UNIQUE, `owner_user_id`: 1, `assigned_advocate_id`: 1, `status`: 1 | WiredTiger BSON |
| `case_board_heads` | `case_board_heads` | `case_id` string | `case_id`: UNIQUE, `snapshot_id`: 1 | WiredTiger BSON |
| `case_board_snapshots` | `case_board_snapshots` | `snapshot_id` string | `snapshot_id`: UNIQUE, `case_id`: 1, `version`: 1 | WiredTiger BSON |
| `advocate_requests` | `advocate_requests` | `request_id` string | `case_id`: 1, `advocate_id`: 1, `status`: 1 | WiredTiger BSON |
| `documents` (Metadata) | `documents` | `document_id` string | `case_id`: 1, `type`: 1, `gridfs_file_id`: 1, `sha256`: 1 | WiredTiger BSON |
| `workflow_runs` | `workflow_runs` | `run_id` string | `case_id`: 1, `status`: 1 | WiredTiger BSON |
| `notifications` | `notifications` | `notification_id` string | `user_id`: 1, `read`: 1 | WiredTiger BSON |
| `audit_events` | `audit_events` | `event_id` string | `case_id`: 1, `created_at`: -1, `actor`: 1 | WiredTiger BSON |
| `legal_authority_heads` | `legal_authority_heads` | `source_id` string | `source_id`: UNIQUE, `version`: 1 | WiredTiger BSON |
| `legal_authority_versions` | `legal_authority_versions` | `version_id` (digest) | `id`: UNIQUE, `source.source_id`: 1 | WiredTiger BSON |
| `legal_authority_reviews` | `legal_authority_reviews` | `review_id` string | `id`: UNIQUE, `source_id`: 1, `reviewer_id`: 1 | WiredTiger BSON |
| `legal_review_submissions` | `legal_review_submissions` | `submission_id` string | `id`: UNIQUE, `source_id`: 1, `actor`: 1 | WiredTiger BSON |
| `legal_ingestion_requests` | `legal_ingestion_requests` | `request_id` string | `id`: UNIQUE, `registry_id`: 1, `state`: 1 | WiredTiger BSON |
| `legal_specialist_artifacts` | `legal_specialist_artifacts` | `artifact_id` string | `id`: UNIQUE, `case_id`: 1 | WiredTiger BSON |
| `review_admin_bootstrap` | `review_admin_bootstrap` | `'one-time'` string | `id`: UNIQUE, `user_id`: 1 | WiredTiger BSON |
| `review_admin_provisioning` | `review_admin_provisioning` | `user_id` string | `id`: UNIQUE, `authorized_by`: 1 | WiredTiger BSON |
| Binary Files (PDF, Images, Audio, HTML) | `fs.files` & `fs.chunks` | GridFS ObjectId | `filename`: 1, `metadata.sha256`: 1, `metadata.case_id`: 1 | GridFS Buckets |

---

## 3. Storage Provider Migration Strategy

1. **Local GridFS as Primary**:
   - `OBJECT_STORE_PROVIDER=mongodb` (default for local development).
   - All uploaded evidence, documents, exports, and official downloads are written to MongoDB GridFS.
   - Files are chunked into 255 KB chunks natively by GridFS, avoiding 16 MB BSON document limits.
   - SHA-256 digests and MIME types are preserved in `metadata`.
2. **Local Uploads Ingestion**:
   - Files in `.localdev/uploads/` are decrypted (if Fernet-encrypted) or read directly.
   - Ingested into GridFS with verified SHA-256 and byte sizes.
   - File metadata in `documents` and `cases` updated with `gridfs_file_id`.
3. **AWS S3 Status & Preservation**:
   - Probe confirms AWS session is expired (`LoginRefreshRequired`).
   - S3 objects will NOT be mutated or deleted.
   - Manifest of unresolved S3 objects will be generated at `docs/audits/s3_migration_manifest.json`.
   - Local CaseSeva runs end-to-end locally without requiring AWS credentials or network access.

---

## 4. Safety & Immutability Rules

- **Zero Modification to Original JSON Files**: `.localdev/phase4-authority-review/database.json` and `identity.json` hashes are checked before and after migration. They remain read-only backup files.
- **No Automatic Approval**: All migrated legal authorities retain their exact review status (`PENDING`, `REVIEWED_PRIMARY`, etc.).
- **No Engine 2 / Phase 5 Start**: Migration changes only the persistence layer. Engine 2 remains unexecuted. Phase 5 remains unstarted.
- **Idempotency**: Running the migration multiple times produces identical state without duplicate records or new IDs.
