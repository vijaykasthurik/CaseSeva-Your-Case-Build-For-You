"""Autonomous technical re-sectionization and review packet correction for Phase 4 candidates.

Generically re-extracts substantive operative provisions, creates new immutable
pending revisions in legal_authority_versions linking to predecessors, regenerates
review packets with substantive excerpts, and updates the review queue.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymongo

from backend.services.case_blackboard import digest
from engineering_prework.legal_source_ingestion.corpus_population import (
    ControlledCorpusPopulator,
    DocumentProvisionTarget,
    AuthorityType,
    generate_review_queue_report,
)

ROOT = Path(__file__).resolve().parent.parent
PACKET_DIR = ROOT / "docs" / "audits" / "review_packets"
QUEUE_PATH = ROOT / "docs" / "audits" / "phase4_review_queue.json"

TARGETS = [
    {
        "document_id": "dspe_act_1946",
        "title": "The Delhi Special Police Establishment Act, 1946",
        "domain": "CRIMINAL_POLICE",
        "authority_type": AuthorityType.ACT,
        "citation": "Act No. 25 of 1946",
        "target_sections": ["1", "2", "3", "6"],
        "url": "https://indiacode.gov.in/server/api/core/bitstreams/d21dc595-7daa-4e65-b739-0dd39973afc1/content",
    },
    {
        "document_id": "it_act_2000",
        "title": "The Information Technology Act, 2000",
        "domain": "CYBER",
        "authority_type": AuthorityType.ACT,
        "citation": "Act No. 21 of 2000",
        "target_sections": ["1", "3", "43", "66"],
        "url": "https://indiacode.gov.in/server/api/core/bitstreams/770a7d02-48f2-4274-bab9-10d0f48ee264/content",
    },
    {
        "document_id": "wages_code_2019",
        "title": "The Code on Wages, 2019",
        "domain": "LABOUR_EMPLOYMENT",
        "authority_type": AuthorityType.ACT,
        "citation": "Act No. 29 of 2019",
        "target_sections": ["1", "3", "5", "6"],
        "url": "https://indiacode.gov.in/server/api/core/bitstreams/7e3863af-0263-4c95-a42a-1bdd0a55a5fc/content",
    },
]


def execute_resectionization():
    client = pymongo.MongoClient("mongodb://127.0.0.1:27017")
    db = client["caseseva"]

    # Load current queue to map old version IDs
    current_queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    old_version_map = {c["source_id"]: c["version_id"] for c in current_queue["candidates"]}

    populator = ControlledCorpusPopulator()
    correction_records = []

    for t in TARGETS:
        ingestion_doc = db.legal_ingestion_requests.find_one({"document_id": t["document_id"]})
        if not ingestion_doc:
            raise RuntimeError(f"Missing ingestion doc for {t['document_id']}")

        official_text = ingestion_doc["official_text"]
        raw_hash = ingestion_doc["raw_hash"]
        text_hash = ingestion_doc["content_hash"]
        gridfs_file_id = str(ingestion_doc["gridfs_file_id"])
        gridfs_key = ingestion_doc["gridfs_key"]
        retrieved_at = ingestion_doc["retrieved_at"]
        final_url = ingestion_doc.get("final_url", t["url"])

        target_spec = DocumentProvisionTarget(
            document_id=t["document_id"],
            title=t["title"],
            domain=t["domain"],
            authority_type=t["authority_type"],
            citation=t["citation"],
            target_sections=t["target_sections"],
            official_url=t["url"],
            registry_id="india_code_central",
        )

        matched_provisions = populator.select_provisions(
            target=target_spec,
            text=official_text,
            raw_hash=raw_hash,
            source_owner=ingestion_doc.get("source_owner", "Legislative Department"),
        )

        for prov in matched_provisions:
            source_id = f"{t['document_id']}_s{prov.section.lower()}"
            old_vid = old_version_map[source_id]

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

            # Preserve predecessor lineage
            cand_src["parent_revision"] = old_vid
            cand_src["revision_status"] = "NONE"
            cand_src["revision_metadata"] = {
                "correction": "TECHNICAL_EXTRACTION_RESECTIONIZATION",
                "previous_version_id": old_vid,
                "reason": "Arrangement of sections replacement with substantive operative provision",
            }
            cand_src["version_note"] = "Corrected substantive operative provision - pending independent human review"

            new_vid, already_existed = populator.persist_candidate(
                db=db,
                candidate_source=cand_src,
                gridfs_file_id=gridfs_file_id,
                gridfs_key=gridfs_key,
                reason="Technical extraction correction: substantive operative provision re-sectionized from official source",
            )

            # Build regenerated reviewer packet
            packet = populator.build_reviewer_packet(
                version_id=new_vid,
                source=cand_src,
                ingestion_doc=ingestion_doc,
                gridfs_file_id=gridfs_file_id,
                gridfs_key=gridfs_key,
            )

            packet_path = PACKET_DIR / f"{source_id}.json"
            packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")

            correction_records.append({
                "source_id": source_id,
                "section": prov.section,
                "old_version_id": old_vid,
                "new_version_id": new_vid,
                "already_existed": already_existed,
                "quote_len": len(cand_src["quote"]),
                "section_start": cand_src["section_start"],
                "section_end": cand_src["section_end"],
            })

    # Regenerate review queue report
    queue_report = generate_review_queue_report(db, review_packet_dir=PACKET_DIR)
    QUEUE_PATH.write_text(json.dumps(queue_report, indent=2), encoding="utf-8")

    print(f"Re-sectionization complete! Corrected {len(correction_records)} candidates.")
    print(f"Review queue updated at {QUEUE_PATH} with {queue_report['total_pending_candidates']} candidates.")
    return correction_records, queue_report


if __name__ == "__main__":
    execute_resectionization()
