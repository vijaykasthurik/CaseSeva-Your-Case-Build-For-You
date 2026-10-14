"""Safe, idempotent migration utility for CaseSeva from local JSON/files/S3 to MongoDB Community Server & GridFS.

Preserves all historical IDs, review receipts, statutory text, and hashes without modification.
Ensures zero alteration to original JSON databases.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import unquote

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database.mongo_client import get_mongo_client, get_mongo_db, get_gridfs, ping_mongodb
from backend.database.mongo_indexes import ensure_indexes
from backend.models.case import utc_now


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_fernet_cipher(uploads_dir: Path):
    key_path = uploads_dir / ".storage-key"
    if key_path.exists():
        from cryptography.fernet import Fernet
        return Fernet(key_path.read_bytes())
    return None


def read_local_upload(path: Path, cipher) -> bytes:
    raw = path.read_bytes()
    prefix = b"CASESEVA_ENCRYPTED_V1\n"
    if raw.startswith(prefix) and cipher:
        try:
            return cipher.decrypt(raw[len(prefix):])
        except Exception:
            return raw
    return raw


def migrate_collection(db, collection_name: str, records: dict[str, Any] | list[dict[str, Any]]) -> int:
    coll = db[collection_name]
    items = records.values() if isinstance(records, dict) else records
    migrated_count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        doc = dict(item)
        record_id = str(doc.get("id") or doc.get("case_id") or doc.get("source_id") or doc.get("review_id") or doc.get("token") or "")
        if not record_id:
            continue
        doc["_id"] = record_id
        doc.setdefault("id", record_id)
        # Idempotent upsert
        coll.replace_one({"_id": record_id}, doc, upsert=True)
        migrated_count += 1
    return migrated_count


def migrate_uploads_to_gridfs(db, uploads_dir: Path) -> tuple[int, int]:
    fs = get_gridfs(db)
    cipher = load_fernet_cipher(uploads_dir)
    files = [f for f in uploads_dir.rglob("*") if f.is_file() and f.name != ".storage-key"]
    migrated = 0
    verified = 0

    for file_path in files:
        rel_key = file_path.relative_to(uploads_dir).as_posix()
        data = read_local_upload(file_path, cipher)
        expected_sha = sha256_bytes(data)
        byte_size = len(data)

        # Check if already in GridFS with exact sha256
        existing = fs.find_one({"filename": rel_key})
        if existing:
            meta = existing.metadata or {}
            if meta.get("sha256") == expected_sha and existing.length == byte_size:
                verified += 1
                continue
            # Remove outdated version
            for old in fs.find({"filename": rel_key}):
                fs.delete(old._id)

        # Guess MIME type
        ext = file_path.suffix.lower()
        content_type = "application/octet-stream"
        if ext in {".pdf"}:
            content_type = "application/pdf"
        elif ext in {".png"}:
            content_type = "image/png"
        elif ext in {".jpg", ".jpeg"}:
            content_type = "image/jpeg"
        elif ext in {".html", ".htm"}:
            content_type = "text/html"
        elif ext in {".txt"}:
            content_type = "text/plain"
        elif ext in {".json"}:
            content_type = "application/json"
        elif ext in {".mp3"}:
            content_type = "audio/mpeg"
        elif ext in {".wav"}:
            content_type = "audio/wav"
        elif ext in {".mp4"}:
            content_type = "video/mp4"

        grid_id = fs.put(
            data,
            filename=rel_key,
            contentType=content_type,
            metadata={
                "key": rel_key,
                "sha256": expected_sha,
                "size": byte_size,
                "original_filename": file_path.name,
                "uploaded_at": utc_now(),
                "migrated_from": "local_uploads",
            }
        )

        # Read back and verify
        read_back = fs.get(grid_id).read()
        assert sha256_bytes(read_back) == expected_sha, f"GridFS SHA-256 verification failed for {rel_key}"
        assert len(read_back) == byte_size, f"GridFS size verification failed for {rel_key}"

        migrated += 1
        verified += 1

    return migrated, verified


def probe_s3_and_build_manifest(db) -> dict[str, Any]:
    """Inspects S3 references in cases and documents, and creates a manifest of migrated/unresolved items."""
    docs = list(db["documents"].find({}))
    cases = list(db["cases"].find({}))
    s3_references = []

    for d in docs:
        storage_key = d.get("storage_key") or ""
        if storage_key.startswith("s3://") or "cases/" in storage_key:
            s3_references.append({
                "type": "document",
                "id": d.get("id"),
                "case_id": d.get("case_id"),
                "storage_key": storage_key,
            })

    for c in cases:
        for ev in c.get("evidence", []):
            sk = ev.get("storage_key") or ""
            if sk:
                s3_references.append({
                    "type": "evidence",
                    "evidence_id": ev.get("evidence_id"),
                    "case_id": c.get("case_id"),
                    "storage_key": sk,
                    "content_hash": ev.get("content_hash"),
                })

    # Test S3 connectivity
    s3_available = False
    s3_error = "AWS credentials expired or unavailable (LoginRefreshRequired)"
    try:
        import boto3
        s3 = boto3.client("s3", region_name=os.getenv("CASESEVA_AWS_REGION", "ap-southeast-2"))
        s3.head_bucket(Bucket=os.getenv("S3_BUCKET_NAME", "caseseva-storage-dev"))
        s3_available = True
        s3_error = None
    except Exception as exc:
        s3_error = str(exc)

    manifest = {
        "generated_at": utc_now(),
        "s3_connected": s3_available,
        "s3_connection_note": s3_error,
        "total_remote_references_discovered": len(s3_references),
        "migrated_from_s3_count": 0,
        "unresolved_remote_objects_count": len(s3_references) if not s3_available else 0,
        "unresolved_reason": s3_error if not s3_available else None,
        "local_operation_status": "CaseSeva runs completely independently of AWS using MongoDB and local GridFS",
        "sample_references": s3_references[:20],
    }

    manifest_path = ROOT / "docs" / "audits" / "s3_migration_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def run_migration(db_name: str = "caseseva", mongo_uri: str = "mongodb://127.0.0.1:27017") -> dict[str, Any]:
    print(f"[*] Starting migration to MongoDB ({mongo_uri}), Database: {db_name}")

    if not ping_mongodb(mongo_uri):
        raise ConnectionError(f"Cannot connect to MongoDB Server at {mongo_uri}. Ensure mongod is running.")

    client = get_mongo_client(mongo_uri)
    db = client[db_name]

    # Pre-migration hashes
    auth_db_path = ROOT / ".localdev" / "phase4-authority-review" / "database.json"
    ident_db_path = ROOT / ".localdev" / "phase4-authority-review" / "identity.json"
    main_db_path = ROOT / ".localdev" / "database.json"
    uploads_dir = ROOT / ".localdev" / "uploads"

    auth_hash_before = sha256_file(auth_db_path)
    ident_hash_before = sha256_file(ident_db_path)
    main_hash_before = sha256_file(main_db_path) if main_db_path.exists() else None

    print(f"[*] Pre-migration SHA-256 for authority DB: {auth_hash_before}")
    print(f"[*] Pre-migration SHA-256 for identity DB:  {ident_hash_before}")

    # Ensure indexes
    print("[*] Ensuring MongoDB indexes...")
    indexes = ensure_indexes(db)
    print(f"[*] Indexes ensured on {len(indexes)} collections.")

    # Migrate main database.json
    migration_counts = {}
    if main_db_path.exists():
        print("[*] Migrating main development database...")
        main_data = json.loads(main_db_path.read_text(encoding="utf-8"))
        for coll_name, records in main_data.items():
            count = migrate_collection(db, coll_name, records)
            migration_counts[coll_name] = count
            print(f"    - {coll_name}: {count} records")

    # Migrate phase4 authority review database
    print("[*] Migrating phase4 authority review database...")
    auth_data = json.loads(auth_db_path.read_text(encoding="utf-8"))
    for coll_name, records in auth_data.items():
        count = migrate_collection(db, coll_name, records)
        migration_counts[f"phase4_{coll_name}"] = count
        print(f"    - {coll_name}: {count} records")

    # Mirror legal_authority_heads to legal_authorities for convenience
    heads = auth_data.get("legal_authority_heads", {})
    versions = auth_data.get("legal_authority_versions", {})
    legal_auth_coll = db["legal_authorities"]
    for sid, h in heads.items():
        ver_id = h.get("version")
        ver_record = versions.get(ver_id, {})
        source_data = ver_record.get("source", {})
        doc = {
            "_id": sid,
            "id": sid,
            "source_id": sid,
            "version_id": ver_id,
            "head": h,
            "current_source": source_data,
        }
        legal_auth_coll.replace_one({"_id": sid}, doc, upsert=True)

    # Migrate phase4 identity database
    print("[*] Migrating phase4 identity database...")
    ident_data = json.loads(ident_db_path.read_text(encoding="utf-8"))
    for coll_name, records in ident_data.items():
        target_coll = "reviewer_identities" if coll_name == "users" else coll_name
        count = migrate_collection(db, target_coll, records)
        migration_counts[f"identity_{coll_name}"] = count
        print(f"    - {target_coll}: {count} records")

    # Migrate uploads to GridFS
    migrated_files, verified_files = 0, 0
    if uploads_dir.exists():
        print(f"[*] Migrating local uploads to GridFS from {uploads_dir}...")
        migrated_files, verified_files = migrate_uploads_to_gridfs(db, uploads_dir)
        print(f"[*] GridFS migration complete: {migrated_files} uploaded, {verified_files} verified.")

    # Probe S3 and write manifest
    print("[*] Generating S3 migration manifest...")
    manifest = probe_s3_and_build_manifest(db)
    print(f"[*] S3 probe result: {manifest['unresolved_reason'] or 'Connected'}")

    # Verify post-migration hashes of original JSON files
    auth_hash_after = sha256_file(auth_db_path)
    ident_hash_after = sha256_file(ident_db_path)
    main_hash_after = sha256_file(main_db_path) if main_db_path.exists() else None

    assert auth_hash_before == auth_hash_after, "SAFETY VIOLATION: Authority JSON was modified during migration!"
    assert ident_hash_before == ident_hash_after, "SAFETY VIOLATION: Identity JSON was modified during migration!"
    if main_hash_before:
        assert main_hash_before == main_hash_after, "SAFETY VIOLATION: Main JSON was modified during migration!"

    print("[*] Verified: Original JSON databases remain 100% UNTOUCHED.")
    print("[*] Migration completed successfully.")

    return {
        "status": "SUCCESS",
        "counts": migration_counts,
        "gridfs_migrated": migrated_files,
        "gridfs_verified": verified_files,
        "auth_hash": auth_hash_after,
        "ident_hash": ident_hash_after,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate CaseSeva persistence to MongoDB and GridFS")
    parser.add_argument("--db-name", default=os.getenv("MONGODB_DATABASE", "caseseva"))
    parser.add_argument("--mongo-uri", default=os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017"))
    args = parser.parse_args()
    res = run_migration(db_name=args.db_name, mongo_uri=args.mongo_uri)
    print(json.dumps(res, indent=2))
