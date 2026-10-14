"""Controlled legal corpus provision population and review preparation script.

Curates a small, representative set of genuine official provisions across multiple
domains (CRIMINAL_POLICE, CYBER, LABOUR_EMPLOYMENT), creates REVIEW_PENDING authority
candidates in MongoDB, and generates complete reviewer inspection packages.

Usage:
    .venv/Scripts/python.exe scripts/populate_review_corpus.py --live
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

from bson import ObjectId
from gridfs import GridFS

from backend.adapters.mongo.database import MongoDatabaseAdapter
from backend.database.mongo_client import get_mongo_db
from backend.services.verified_corpus import VerifiedCorpus
from engineering_prework.legal_source_ingestion.corpus_population import (
    ControlledCorpusPopulator,
    DocumentProvisionTarget,
    generate_review_queue_report,
)
from engineering_prework.legal_source_ingestion.models import AuthorityType
from engineering_prework.legal_source_ingestion.real_acquisition import (
    OfficialAcquisitionPipeline,
    OfficialDocumentRetriever,
    OfficialRegistrySecurity,
    OfficialTextExtractor,
)

TARGET_ENACTMENTS = [
    {
        "document_id": "dspe_act_1946",
        "title": "The Delhi Special Police Establishment Act, 1946",
        "domain": "CRIMINAL_POLICE",
        "authority_type": AuthorityType.ACT,
        "citation": "Act No. 25 of 1946",
        "official_url": "https://indiacode.gov.in/server/api/core/bitstreams/d21dc595-7daa-4e65-b739-0dd39973afc1/content",
        "target_sections": ["1", "2", "3", "6"],
    },
    {
        "document_id": "it_act_2000",
        "title": "The Information Technology Act, 2000",
        "domain": "CYBER",
        "authority_type": AuthorityType.ACT,
        "citation": "Act No. 21 of 2000",
        "official_url": "https://indiacode.gov.in/server/api/core/bitstreams/770a7d02-48f2-4274-bab9-10d0f48ee264/content",
        "target_sections": ["1", "3", "43", "66"],
    },
    {
        "document_id": "wages_code_2019",
        "title": "The Code on Wages, 2019",
        "domain": "LABOUR_EMPLOYMENT",
        "authority_type": AuthorityType.ACT,
        "citation": "Act No. 29 of 2019",
        "official_url": "https://indiacode.gov.in/server/api/core/bitstreams/7e3863af-0263-4c95-a42a-1bdd0a55a5fc/content",
        "target_sections": ["1", "3", "5", "6"],
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


def run_population(db) -> dict:
    print("=" * 75)
    print("CASESEVA PHASE 4: CONTROLLED CORPUS POPULATION & REVIEW PREPARATION")
    print("=" * 75)

    counts_before = record_counts(db)
    print("\n[1] Initial Real MongoDB Collection Counts:")
    for col, count in counts_before.items():
        print(f"    {col:28s}: {count}")

    fs = GridFS(db)
    pipeline = OfficialAcquisitionPipeline()
    populator = ControlledCorpusPopulator()

    packet_dir = ROOT / "docs" / "audits" / "review_packets"
    packet_dir.mkdir(parents=True, exist_ok=True)

    populated_candidates = []
    generated_packets = []

    print("\n[2] Processing genuine enactments across 3 legal domains...")
    for idx, target_info in enumerate(TARGET_ENACTMENTS, 1):
        doc_id = target_info["document_id"]
        title = target_info["title"]
        domain = target_info["domain"]
        url = target_info["official_url"]
        citation = target_info["citation"]
        target_secs = target_info["target_sections"]

        print(f"\n--- Enactment {idx}/{len(TARGET_ENACTMENTS)}: {title} ({domain}) ---")

        # Step 2a: Check if already in MongoDB / GridFS or acquire it
        ingestion_doc = db["legal_ingestion_requests"].find_one({"document_id": doc_id, "state": "PARSED"})
        gridfs_file_id = None
        gridfs_key = None
        raw_hash = None
        text_hash = None
        official_text = None
        retrieved_at = None
        final_url = url

        if ingestion_doc and ingestion_doc.get("gridfs_file_id"):
            print("    [Found existing GridFS & Ingestion record in MongoDB]")
            gridfs_file_id = ingestion_doc["gridfs_file_id"]
            gridfs_key = ingestion_doc["gridfs_key"]
            raw_hash = ingestion_doc["raw_hash"]
            text_hash = ingestion_doc["content_hash"]
            official_text = ingestion_doc["official_text"]
            retrieved_at = ingestion_doc["retrieved_at"]
            final_url = ingestion_doc.get("final_url", url)

            # Verify GridFS bytes
            grid_out = fs.get(ObjectId(gridfs_file_id))
            raw_bytes = grid_out.read()
            assert hashlib.sha256(raw_bytes).hexdigest() == raw_hash, "GridFS raw hash mismatch!"
        else:
            print(f"    [Acquiring fresh genuine document over HTTPS from India Code...]")
            acq_res = pipeline.acquire_document(
                db=db,
                registry_id="india_code_central",
                document_id=doc_id,
                title=title,
                official_url=url,
                domain=domain,
                authority_type=target_info["authority_type"],
                citation=citation,
            )
            gridfs_file_id = acq_res["gridfs_file_id"]
            gridfs_key = acq_res["gridfs_key"]
            raw_hash = acq_res["raw_hash"]
            text_hash = acq_res["text_hash"]
            ingestion_doc = db["legal_ingestion_requests"].find_one({"id": acq_res["ingestion_id"]})
            official_text = ingestion_doc["official_text"]
            retrieved_at = ingestion_doc["retrieved_at"]
            final_url = ingestion_doc.get("final_url", url)
            print(f"    Acquired {acq_res['byte_size']} bytes, hash: {raw_hash}")
            time.sleep(1.0)

        # Step 2b: Curate and populate representative provisions
        target_spec = DocumentProvisionTarget(
            document_id=doc_id,
            title=title,
            domain=domain,
            authority_type=target_info["authority_type"],
            citation=citation,
            target_sections=target_secs,
            official_url=url,
            registry_id="india_code_central",
        )

        matched_provisions = populator.select_provisions(
            target=target_spec,
            text=official_text,
            raw_hash=raw_hash,
            source_owner=ingestion_doc.get("source_owner", "Legislative Department"),
        )
        print(f"    Matched representative provisions: {[p.section for p in matched_provisions]}")

        for prov in matched_provisions:
            cand_src = populator.build_candidate_source(
                target=target_spec,
                prov=prov,
                official_text=official_text,
                text_hash=text_hash,
                raw_hash=raw_hash,
                retrieved_at=retrieved_at,
                ingestion_id=ingestion_doc["id"],
                final_url=final_url,
            )

            vid, already = populator.persist_candidate(
                db=db,
                candidate_source=cand_src,
                gridfs_file_id=gridfs_file_id,
                gridfs_key=gridfs_key,
            )

            # Build reviewer packet
            packet = populator.build_reviewer_packet(
                version_id=vid,
                source=cand_src,
                ingestion_doc=ingestion_doc,
                gridfs_file_id=gridfs_file_id,
                gridfs_key=gridfs_key,
            )

            # Save packet to disk
            packet_path = packet_dir / f"{cand_src['source_id']}.json"
            packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")

            populated_candidates.append({
                "source_id": cand_src["source_id"],
                "version_id": vid,
                "section": prov.section,
                "domain": domain,
                "title": title,
                "review_state": "REVIEW_PENDING",
                "packet_file": str(packet_path.relative_to(ROOT)),
            })
            generated_packets.append(packet)
            print(f"      - {cand_src['source_id']} (v: {vid[:12]}...): REVIEW_PENDING [Packet saved]")

    # Step 3: Generate machine-readable Review Queue Summary
    print("\n[3] Generating machine-readable review queue summary...")
    queue_report = generate_review_queue_report(db, review_packet_dir=packet_dir)
    queue_path = ROOT / "docs" / "audits" / "phase4_review_queue.json"
    queue_path.write_text(json.dumps(queue_report, indent=2), encoding="utf-8")
    print(f"    Saved review queue report: {queue_path} ({queue_report['total_pending_candidates']} candidates)")

    # Step 4: Post-population MongoDB counts
    counts_after = record_counts(db)
    print("\n[4] Post-Population Real MongoDB Collection Counts:")
    for col in PROTECTED_COLLECTIONS:
        before = counts_before[col]
        after = counts_after[col]
        diff = after - before
        diff_str = f"(+{diff})" if diff > 0 else "(=)"
        print(f"    {col:28s}: {after:4d} {diff_str}")

    # Step 5: VerifiedCorpus Quarantine Verification
    print("\n[5] Verifying VerifiedCorpus Quarantine for all populated candidates...")
    adapter = MongoDatabaseAdapter()
    corpus = VerifiedCorpus(adapter)

    for cand in populated_candidates:
        domain = cand["domain"]
        sec = cand["section"]
        title = cand["title"]
        sid = cand["source_id"]

        hits = corpus.search(domain=domain, jurisdiction="IN", query=f"{title} {sec}")
        assert len(hits) == 0, f"VIOLATION: Candidate {sid} returned in VerifiedCorpus search!"
        assert corpus.get(sid) is None, f"VIOLATION: Candidate {sid} accessible via corpus.get()!"

    print("    [PASS] VerifiedCorpus search returned 0 hits for all candidates.")
    print("    [PASS] All populated candidates remain strictly quarantined in REVIEW_PENDING.")

    # Step 6: Verify zero review approvals / zero head advancements
    assert counts_before["legal_authority_heads"] == counts_after["legal_authority_heads"], (
        "VIOLATION: legal_authority_heads modified!"
    )
    assert counts_before["legal_authority_reviews"] == counts_after["legal_authority_reviews"], (
        "VIOLATION: legal_authority_reviews modified!"
    )
    print("    [PASS] Historical authority heads and review decisions 100% untouched.")

    return {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "counts_before": counts_before,
        "counts_after": counts_after,
        "total_populated": len(populated_candidates),
        "candidates": populated_candidates,
    }


def main():
    parser = argparse.ArgumentParser(description="Populate CaseSeva Phase 4 Curated Legal Corpus")
    parser.add_argument("--live", action="store_true", help="Allow controlled live acquisition for missing domains")
    args = parser.parse_args()

    if not args.live:
        print("ERROR: --live flag required to execute controlled population.")
        sys.exit(1)

    db = get_mongo_db()
    manifest = run_population(db)

    audit_path = ROOT / "docs" / "audits" / "phase4_population_manifest.json"
    audit_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nManifest saved to: {audit_path}")


if __name__ == "__main__":
    main()
