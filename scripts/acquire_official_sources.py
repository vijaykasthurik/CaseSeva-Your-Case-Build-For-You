"""Controlled live official-source acquisition script for CaseSeva Phase 4.

Executes real discovery, byte retrieval, GridFS raw persistence, PyMuPDF extraction,
generic sectionization, and REVIEW_PENDING authority version creation against official
Government of India legal portals without CAPTCHA bypass or anti-bot circumvention.

Usage:
    .venv/Scripts/python.exe scripts/acquire_official_sources.py --live
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database.mongo_client import get_mongo_db
from backend.services.verified_corpus import VerifiedCorpus
from backend.adapters.mongo.database import MongoDatabaseAdapter
from engineering_prework.legal_source_ingestion.models import AuthorityType
from engineering_prework.legal_source_ingestion.real_acquisition import (
    AcquisitionSecurityError,
    OfficialAcquisitionPipeline,
    OfficialDocumentRetriever,
    OfficialRegistrySecurity,
    inspect_candidate_for_review,
)

TARGET_ACQUISITIONS = [
    {
        "registry_id": "india_code_central",
        "document_id": "dspe_act_1946",
        "title": "The Delhi Special Police Establishment Act, 1946",
        "domain": "CRIMINAL_POLICE",
        "authority_type": AuthorityType.ACT,
        "citation": "Act No. 25 of 1946",
        "official_url": "https://indiacode.gov.in/server/api/core/bitstreams/d21dc595-7daa-4e65-b739-0dd39973afc1/content",
        "discovery_url": "https://indiacode.gov.in/handle/123456789/496174",
    },
    {
        "registry_id": "india_code_central",
        "document_id": "it_act_2000",
        "title": "The Information Technology Act, 2000",
        "domain": "CYBER",
        "authority_type": AuthorityType.ACT,
        "citation": "Act No. 21 of 2000",
        "official_url": "https://indiacode.gov.in/server/api/core/bitstreams/770a7d02-48f2-4274-bab9-10d0f48ee264/content",
        "discovery_url": "https://indiacode.gov.in/handle/123456789/1999",
    },
]

PROTECTED_COLLECTIONS = [
    "legal_authority_heads",
    "legal_authority_versions",
    "legal_authority_reviews",
    "legal_review_submissions",
    "legal_ingestion_requests",
    "fs.files",
    "fs.chunks",
]


def record_counts(db) -> dict[str, int]:
    return {c: db[c].count_documents({}) for c in PROTECTED_COLLECTIONS}


def run_live_acquisition(db, rate_delay_seconds: float = 2.0) -> dict:
    print("=" * 70)
    print("CASESEVA PHASE 4: CONTROLLED REAL OFFICIAL-SOURCE ACQUISITION")
    print("=" * 70)

    counts_before = record_counts(db)
    print("\n[1] Initial Real MongoDB Collection Counts:")
    for col, count in counts_before.items():
        print(f"    {col:28s}: {count}")

    pipeline = OfficialAcquisitionPipeline()
    results = []

    # Test negative control first: egazette_india (manual/browser required, fails closed)
    print("\n[2] Testing manual/browser-required source (negative control: egazette_india)...")
    security = OfficialRegistrySecurity()
    permitted, reason = security.is_automation_permitted("egazette_india")
    print(f"    Automation permitted: {permitted}")
    print(f"    Policy decision:      {reason}")
    if not permitted:
        print("    [PASS] egazette_india correctly failed closed without CAPTCHA bypass.")

    # Controlled live acquisition
    print("\n[3] Executing controlled live acquisition for genuine official documents...")
    for idx, target in enumerate(TARGET_ACQUISITIONS, 1):
        reg_id = target["registry_id"]
        doc_id = target["document_id"]
        title = target["title"]
        domain = target["domain"]
        url = target["official_url"]
        citation = target["citation"]

        print(f"\n--- Target {idx}/{len(TARGET_ACQUISITIONS)}: {title} ({domain}) ---")
        print(f"    Registry:     {reg_id}")
        print(f"    Official URL: {url}")

        t0 = time.time()
        try:
            res = pipeline.acquire_document(
                db=db,
                registry_id=reg_id,
                document_id=doc_id,
                title=title,
                official_url=url,
                domain=domain,
                authority_type=target["authority_type"],
                citation=citation,
            )
            elapsed = time.time() - t0
            res["status"] = "SUCCESS"
            res["elapsed_seconds"] = round(elapsed, 2)
            results.append(res)

            print(f"    Status:               SUCCESS ({elapsed:.2f}s)")
            print(f"    Raw bytes downloaded: {res['byte_size']} bytes")
            print(f"    Raw SHA-256:          {res['raw_hash']}")
            print(f"    GridFS File ID:       {res['gridfs_file_id']}")
            print(f"    GridFS Key:           {res['gridfs_key']}")
            print(f"    Already in GridFS:    {res['already_in_gridfs']}")
            print(f"    Extracted Text SHA:   {res['text_hash']}")
            print(f"    Provisions parsed:    {res['provisions_count']}")
            print(f"    Ingestion Request ID: {res['ingestion_id']}")
            print(f"    Candidate Version ID: {res['candidate_versions']}")
            print(f"    Review Status:        {res['review_status']}")
            print(f"    Review Eligible:      {res['review_eligible']}")

        except Exception as exc:
            elapsed = time.time() - t0
            err_res = {
                "document_id": doc_id,
                "title": title,
                "domain": domain,
                "status": "FAILURE",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "elapsed_seconds": round(elapsed, 2),
            }
            results.append(err_res)
            print(f"    Status: FAILED ({type(exc).__name__}: {exc})")

        # Polite rate limiting
        if idx < len(TARGET_ACQUISITIONS):
            print(f"    [Polite rate limit backoff: sleeping {rate_delay_seconds}s...]")
            time.sleep(rate_delay_seconds)

    # Post-acquisition counts
    counts_after = record_counts(db)
    print("\n[4] Post-Acquisition Real MongoDB Collection Counts:")
    for col in PROTECTED_COLLECTIONS:
        before = counts_before[col]
        after = counts_after[col]
        diff = after - before
        diff_str = f"(+{diff})" if diff > 0 else "(=)"
        print(f"    {col:28s}: {after:4d} {diff_str}")

    # Integrity verification
    print("\n[5] Verifying Retrieval Eligibility Gate (VerifiedCorpus Quarantine)...")
    adapter = MongoDatabaseAdapter()
    corpus = VerifiedCorpus(adapter)

    for r in results:
        if r.get("status") == "SUCCESS":
            domain = r["domain"]
            doc_id = r["document_id"]
            title = r["title"]
            # Search corpus
            hits = corpus.search(domain=domain, jurisdiction="IN", query=title)
            print(f"    Searching VerifiedCorpus for '{title}' in domain '{domain}':")
            print(f"    Hits returned: {len(hits)}")
            assert len(hits) == 0, f"SECURITY VIOLATION: Candidate {title} was returned by VerifiedCorpus.search()!"

            # Inspect candidate data package
            for vid in r.get("candidate_versions", []):
                inspection = inspect_candidate_for_review(db, vid)
                assert inspection is not None, f"Failed to inspect candidate {vid}"
                assert inspection["review_state"] == "REVIEW_PENDING", f"Review state must be REVIEW_PENDING, got {inspection['review_state']}"
                assert not inspection["source_reviewed"], "source_reviewed must be False!"
                print(f"    Candidate {vid} verified in REVIEW_PENDING; inspection package ready for human admin.")

    print("    [PASS] All newly acquired candidates remain strictly quarantined in REVIEW_PENDING.")
    print("    [PASS] No candidate is retrieval-eligible.")

    # Historical heads untouched check
    assert counts_before["legal_authority_heads"] == counts_after["legal_authority_heads"], (
        f"VIOLATION: legal_authority_heads modified! Before: {counts_before['legal_authority_heads']}, "
        f"After: {counts_after['legal_authority_heads']}"
    )
    assert counts_before["legal_authority_reviews"] == counts_after["legal_authority_reviews"], (
        f"VIOLATION: legal_authority_reviews modified! Before: {counts_before['legal_authority_reviews']}, "
        f"After: {counts_after['legal_authority_reviews']}"
    )
    print("    [PASS] Historical legal_authority_heads and legal_authority_reviews strictly preserved.")

    manifest = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "counts_before": counts_before,
        "counts_after": counts_after,
        "results": results,
    }
    return manifest


def main():
    parser = argparse.ArgumentParser(description="CaseSeva Phase 4 Controlled Official-Source Acquisition")
    parser.add_argument("--live", action="store_true", help="Execute real live official source acquisition")
    parser.add_argument("--rate-delay", type=float, default=2.0, help="Delay between requests in seconds")
    args = parser.parse_args()

    if not args.live:
        print("ERROR: --live flag required to execute real live official-source acquisition.")
        sys.exit(1)

    db = get_mongo_db()
    manifest = run_live_acquisition(db, rate_delay_seconds=args.rate_delay)

    manifest_path = ROOT / "docs" / "audits" / "phase4_acquisition_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nManifest saved to: {manifest_path}")


if __name__ == "__main__":
    main()
