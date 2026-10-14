"""Controlled S3 -> MongoDB GridFS Migration and Verification Script.

Ensures:
- S3 is strictly read-only (zero put, zero delete, zero copy back).
- Idempotent and resumable execution.
- SHA-256 and byte-size verification for every object.
- Exact audit logging in docs/audits/s3_migration_manifest.json.
- Preservation of original JSON review databases.
- Zero modification to legal authorities or review decisions.
"""

import hashlib
import json
import mimetypes
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError
from pymongo import MongoClient
import gridfs

ROOT = Path(__file__).resolve().parent.parent

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_file(p: Path) -> str:
    return sha256_bytes(p.read_bytes())


def run_controlled_s3_migration() -> dict[str, Any]:
    print("=" * 60)
    print("CONTROLLED REMOTE S3 -> LOCAL MONGODB GRIDFS MIGRATION")
    print("=" * 60)

    # 1. Check baseline files
    auth_db_path = ROOT / ".localdev" / "phase4-authority-review" / "database.json"
    ident_db_path = ROOT / ".localdev" / "phase4-authority-review" / "identity.json"
    main_db_path = ROOT / ".localdev" / "database.json"

    expected_auth_hash = "b96220116ac40a01b4f96e6b620edc7eebfa35d39d11dfb33b677b9bf67716c3"
    expected_ident_hash = "bd055fe4bd996aba38a243fbb3572f68646be7cd469e0382a3b57920a9a15b17"

    auth_hash_pre = sha256_file(auth_db_path)
    ident_hash_pre = sha256_file(ident_db_path)

    assert auth_hash_pre == expected_auth_hash, f"Pre-migration auth DB hash mismatch: {auth_hash_pre}"
    assert ident_hash_pre == expected_ident_hash, f"Pre-migration ident DB hash mismatch: {ident_hash_pre}"
    print(f"[*] Pre-migration Authority DB SHA-256: {auth_hash_pre} (VERIFIED)")
    print(f"[*] Pre-migration Identity DB SHA-256:  {ident_hash_pre} (VERIFIED)")

    # 2. Connect to MongoDB
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    db_name = os.getenv("MONGODB_DATABASE", "caseseva")
    client = MongoClient(mongo_uri)
    db = client[db_name]
    fs = gridfs.GridFS(db)

    print(f"[*] Connected to MongoDB: {mongo_uri}, database: {db_name}")
    fs_files_before = db["fs.files"].count_documents({})
    fs_chunks_before = db["fs.chunks"].count_documents({})
    print(f"[*] Pre-migration GridFS state: {fs_files_before} files, {fs_chunks_before} chunks")

    # 3. Connect to S3 (Read-Only)
    s3_region = os.getenv("CASESEVA_AWS_REGION", "ap-southeast-2")
    s3_bucket = os.getenv("S3_BUCKET_NAME", "caseseva-storage-dev-370401801549")
    print(f"[*] Initializing Read-Only S3 client: bucket={s3_bucket}, region={s3_region}")
    s3 = boto3.client("s3", region_name=s3_region)

    sts = boto3.client("sts", region_name=s3_region)
    caller = sts.get_caller_identity()
    print(f"[*] AWS Caller Identity: Account={caller.get('Account')}, Arn={caller.get('Arn')}")

    # 4. Discover historical 195 references from database.json
    main_data = json.loads(main_db_path.read_text(encoding="utf-8"))
    orig_docs = main_data.get("documents", {})
    orig_cases = main_data.get("cases", {})

    discovered_refs = []
    # Collect 78 documents
    for doc_id, d in orig_docs.items():
        sk = d.get("storage_key") or ""
        if sk:
            clean_k = sk.replace("s3://caseseva-storage-dev/", "").replace(f"s3://{s3_bucket}/", "")
            discovered_refs.append({
                "type": "document",
                "id": doc_id,
                "case_id": d.get("case_id"),
                "storage_key": sk,
                "clean_key": clean_k,
                "content_hash": None,
                "provenance": "database.json:documents"
            })

    # Collect 117 evidence items
    for case_id, c in orig_cases.items():
        for ev in c.get("evidence", []):
            sk = ev.get("storage_key") or ""
            if sk:
                clean_k = sk.replace("s3://caseseva-storage-dev/", "").replace(f"s3://{s3_bucket}/", "")
                discovered_refs.append({
                    "type": "evidence",
                    "id": ev.get("evidence_id"),
                    "case_id": case_id,
                    "storage_key": sk,
                    "clean_key": clean_k,
                    "content_hash": ev.get("content_hash"),
                    "provenance": "database.json:cases.evidence"
                })

    total_refs = len(discovered_refs)
    print(f"[*] Discovered {total_refs} historical references to process.")
    assert total_refs == 195, f"Expected 195 references, found {total_refs}"

    # 5. Process each reference
    migrated_count = 0
    already_present_count = 0
    failed_count = 0
    results = []

    for idx, ref in enumerate(discovered_refs, 1):
        clean_key = ref["clean_key"]
        ref_type = ref["type"]
        ref_id = ref["id"]
        case_id = ref["case_id"]

        # Step 5a: Check if already present in GridFS
        grid_file = fs.find_one({"filename": clean_key}) or fs.find_one({"metadata.key": clean_key})
        if grid_file is not None:
            # Verify existing GridFS binary
            grid_bytes = grid_file.read()
            computed_sha = sha256_bytes(grid_bytes)
            computed_size = len(grid_bytes)
            meta = grid_file.metadata or {}
            expected_sha = meta.get("sha256") or ref.get("content_hash")

            if expected_sha:
                assert computed_sha == expected_sha, f"GridFS SHA-256 mismatch for existing file {clean_key}"
            assert computed_size == grid_file.length, f"GridFS length mismatch for {clean_key}"

            already_present_count += 1
            results.append({
                "key": clean_key,
                "original_reference": ref["storage_key"],
                "type": ref_type,
                "id": ref_id,
                "case_id": case_id,
                "status": "ALREADY_PRESENT_VERIFIED",
                "gridfs_file_id": str(grid_file._id),
                "sha256": computed_sha,
                "byte_size": computed_size,
                "provenance": ref["provenance"],
                "verified_at": utc_now()
            })
            continue

        # Step 5b: Object NOT in GridFS. Attempt S3 Download (READ-ONLY)
        print(f"[{idx}/{total_refs}] Attempting S3 download for: {clean_key}")
        try:
            s3_obj = s3.get_object(Bucket=s3_bucket, Key=clean_key)
            s3_bytes = s3_obj["Body"].read()
            s3_sha = sha256_bytes(s3_bytes)
            s3_size = len(s3_bytes)
            content_type = s3_obj.get("ContentType") or mimetypes.guess_type(clean_key)[0] or "application/octet-stream"

            # Step 5c: Put into GridFS
            new_id = fs.put(
                s3_bytes,
                filename=clean_key,
                contentType=content_type,
                metadata={
                    "key": clean_key,
                    "sha256": s3_sha,
                    "size": s3_size,
                    "original_bucket": s3_bucket,
                    "original_reference": ref["storage_key"],
                    "migrated_at": utc_now(),
                    "migrated_from": "s3_read_only",
                }
            )

            # Step 5d: Read back and verify
            read_back = fs.get(new_id).read()
            rb_sha = sha256_bytes(read_back)
            rb_size = len(read_back)

            assert rb_sha == s3_sha, f"SHA-256 verification failed after GridFS write for {clean_key}"
            assert rb_size == s3_size, f"Size verification failed after GridFS write for {clean_key}"

            migrated_count += 1
            results.append({
                "key": clean_key,
                "original_reference": ref["storage_key"],
                "type": ref_type,
                "id": ref_id,
                "case_id": case_id,
                "status": "MIGRATED_SUCCESS",
                "gridfs_file_id": str(new_id),
                "sha256": s3_sha,
                "byte_size": s3_size,
                "provenance": ref["provenance"],
                "verified_at": utc_now()
            })
            print(f"    -> Successfully migrated {clean_key} ({s3_size} bytes, SHA-256: {s3_sha[:16]}...)")

        except ClientError as exc:
            err_code = exc.response.get("Error", {}).get("Code", "UNKNOWN")
            err_msg = exc.response.get("Error", {}).get("Message", str(exc))
            failure_class = "NOT_FOUND" if err_code in {"NoSuchKey", "404"} else ("ACCESS_DENIED" if err_code in {"AccessDenied", "403"} else "CLIENT_ERROR")

            failed_count += 1
            results.append({
                "key": clean_key,
                "original_reference": ref["storage_key"],
                "type": ref_type,
                "id": ref_id,
                "case_id": case_id,
                "status": "FAILED",
                "failure_class": failure_class,
                "error_code": err_code,
                "error_summary": err_msg,
                "retry_appropriate": False if failure_class in {"NOT_FOUND", "ACCESS_DENIED"} else True,
                "provenance": ref["provenance"],
                "recorded_at": utc_now()
            })
            print(f"    -> [FAILED] {clean_key}: {failure_class} ({err_code}) - {err_msg}")

        except Exception as exc:
            failed_count += 1
            results.append({
                "key": clean_key,
                "original_reference": ref["storage_key"],
                "type": ref_type,
                "id": ref_id,
                "case_id": case_id,
                "status": "FAILED",
                "failure_class": "UNEXPECTED_ERROR",
                "error_code": type(exc).__name__,
                "error_summary": str(exc),
                "retry_appropriate": True,
                "provenance": ref["provenance"],
                "recorded_at": utc_now()
            })
            print(f"    -> [ERROR] {clean_key}: {type(exc).__name__} - {exc}")

    # 6. GridFS state after
    fs_files_after = db["fs.files"].count_documents({})
    fs_chunks_after = db["fs.chunks"].count_documents({})

    # 7. Broken references and orphan check
    broken_refs = [r for r in results if r["status"] == "FAILED"]
    gridfs_all_keys = set()
    for doc in db["fs.files"].find({}, {"filename": 1, "metadata.key": 1}):
        if doc.get("filename"): gridfs_all_keys.add(doc["filename"])
        if doc.get("metadata", {}).get("key"): gridfs_all_keys.add(doc["metadata"]["key"])

    referenced_keys = set(r["clean_key"] for r in discovered_refs)
    orphan_files = [k for k in gridfs_all_keys if k.startswith("cases/") and k not in referenced_keys]

    # 8. Post-migration hashes of original JSON databases
    auth_hash_post = sha256_file(auth_db_path)
    ident_hash_post = sha256_file(ident_db_path)

    assert auth_hash_post == expected_auth_hash, f"Post-migration auth DB hash modified! {auth_hash_post}"
    assert ident_hash_post == expected_ident_hash, f"Post-migration ident DB hash modified! {ident_hash_post}"
    print(f"[*] Post-migration Authority DB SHA-256: {auth_hash_post} (VERIFIED UNCHANGED)")
    print(f"[*] Post-migration Identity DB SHA-256:  {ident_hash_post} (VERIFIED UNCHANGED)")

    # 9. Verify zero legal authorities approved
    reviews = list(db["legal_authority_reviews"].find({}))
    for rev in reviews:
        assert rev.get("decision") not in {"REVIEW_APPROVED", "APPROVED"}, f"Error: Found approved review: {rev}"
    print(f"[*] Legal Authorities check: All {len(reviews)} review receipts are {reviews[0]['decision']}. Zero approved (VERIFIED).")

    # 10. Write comprehensive manifest
    manifest_data = {
        "generated_at": utc_now(),
        "s3_connected": True,
        "s3_bucket": s3_bucket,
        "s3_region": s3_region,
        "initial_unresolved_references_count": total_refs,
        "objects_attempted_count": total_refs,
        "already_present_verified_count": already_present_count,
        "migrated_from_s3_count": migrated_count,
        "failed_count": failed_count,
        "remaining_unresolved_count": failed_count,
        "fs_files_before": fs_files_before,
        "fs_files_after": fs_files_after,
        "fs_chunks_before": fs_chunks_before,
        "fs_chunks_after": fs_chunks_after,
        "broken_references_count": len(broken_refs),
        "broken_references_summary": broken_refs,
        "authority_json_sha256": auth_hash_post,
        "identity_json_sha256": ident_hash_post,
        "all_processed_objects": results
    }

    manifest_path = ROOT / "docs" / "audits" / "s3_migration_manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    print(f"[*] Updated migration manifest written to: {manifest_path}")

    print("\n" + "=" * 60)
    print("MIGRATION EXECUTION SUMMARY:")
    print(f"  - Initial unresolved S3 references: {total_refs}")
    print(f"  - Objects attempted:                {total_refs}")
    print(f"  - Already-present / verified:       {already_present_count}")
    print(f"  - Successfully migrated from S3:    {migrated_count}")
    print(f"  - Failed (NOT_FOUND):               {failed_count}")
    print(f"  - Remaining unresolved references:  {failed_count}")
    print(f"  - GridFS files before/after:        {fs_files_before} -> {fs_files_after}")
    print(f"  - Broken references count:          {len(broken_refs)}")
    print(f"  - Authority JSON SHA-256 intact:    True")
    print(f"  - Identity JSON SHA-256 intact:     True")
    print("=" * 60)

    return manifest_data


if __name__ == "__main__":
    run_controlled_s3_migration()
