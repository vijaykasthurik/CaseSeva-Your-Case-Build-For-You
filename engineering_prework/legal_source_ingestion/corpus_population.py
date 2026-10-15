"""Controlled legal corpus provision population and reviewer preparation engine.

Transforms genuinely acquired official legal texts into a curated, multi-domain
REVIEW_PENDING corpus with comprehensive reviewer inspection packages.

Enforces:
- Deterministic immutable version identities
- Complete provenance linkage (GridFS raw bytes, raw SHA-256, text SHA-256)
- Reviewer package generation with explicit temporal warnings
- Complete quarantine from VerifiedCorpus until independent human review
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymongo
from gridfs import GridFS

from backend.models.legal_foundation import LegalSource
from backend.services.case_blackboard import digest
from .models import AuthorityType, ProvisionRecord, ReviewStatus
from .sectionizer import StatutorySectionizer

TEMPORAL_WARNING_TEXT = "Current-law coverage has not been established."
TEMPORAL_SUBORDINATE_WARNING = "Do not infer that an official consolidated PDF is current through today."
TEMPORAL_LINEAGE_WARNING = (
    "Amendment, commencement, and repeal coverage remain unverified pending independent authenticated human review."
)


class DocumentProvisionTarget:
    """Configurable data specification for selecting representative provisions from an enactment."""

    def __init__(
        self,
        document_id: str,
        title: str,
        domain: str,
        authority_type: AuthorityType,
        citation: str,
        target_sections: list[str],
        official_url: str,
        registry_id: str = "india_code_central",
    ):
        self.document_id = document_id
        self.title = title
        self.domain = domain
        self.authority_type = authority_type
        self.citation = citation
        self.target_sections = [s.strip().upper() for s in target_sections]
        self.official_url = official_url
        self.registry_id = registry_id


class ControlledCorpusPopulator:
    """Selects, formats, and persists curated provision candidates into legal_authority_versions."""

    def __init__(self, sectionizer: StatutorySectionizer | None = None):
        self.sectionizer = sectionizer or StatutorySectionizer()

    def select_provisions(
        self,
        target: DocumentProvisionTarget,
        text: str,
        raw_hash: str,
        source_owner: str,
    ) -> list[ProvisionRecord]:
        """Extracts and filters provisions to the specified target sections."""
        all_provisions = self.sectionizer.extract_provisions(
            document_id=target.document_id,
            title=target.title,
            text=text,
            official_url=target.official_url,
            source_owner=source_owner,
            raw_document_hash=raw_hash,
            authority_type=target.authority_type,
            domain=target.domain,
            jurisdiction="IN",
            language="en",
        )

        matched: list[ProvisionRecord] = []
        seen_sections: set[str] = set()

        for prov in all_provisions:
            sec_norm = prov.section.strip().upper()
            if sec_norm in target.target_sections and sec_norm not in seen_sections and prov.subsection is None:
                # Top-level section preferred
                matched.append(prov)
                seen_sections.add(sec_norm)

        return matched

    def build_candidate_source(
        self,
        target: DocumentProvisionTarget,
        prov: ProvisionRecord,
        official_text: str,
        text_hash: str,
        raw_hash: str,
        retrieved_at: str,
        ingestion_id: str,
        final_url: str,
    ) -> dict[str, Any]:
        """Constructs a strictly validated LegalSource candidate dictionary."""
        source_id = f"{target.document_id}_s{prov.section.lower()}"
        quote_text = prov.quote
        if len(quote_text) > 5900:
            quote_text = quote_text[:5900]

        bounded_text = official_text[:245000]

        source_dict = {
            "source_id": source_id,
            "family": target.title,
            "source_type": "STATUTE",
            "domain": target.domain,
            "jurisdiction": "IN",
            "title": target.title,
            "section": prov.section,
            "court": None,
            "citation": target.citation or f"{target.title} (Official Gazette)",
            "official_url": target.official_url,
            "final_url": final_url,
            "ingestion_id": ingestion_id,
            "review_state": "REVIEW_PENDING",
            "review_id": None,
            "revision_status": "NONE",
            "parent_revision": None,
            "revision_request_id": None,
            "revision_metadata": {},
            "reviewed_at": None,
            "registry_id": target.registry_id,
            "source_language": "en",
            "official_text": bounded_text,
            "quote": quote_text,
            "content_hash": text_hash,
            "retrieved_at": retrieved_at,
            "effective_from": None,
            "effective_until": None,
            "temporal_source_ids": [],
            "temporal_reviewed": False,
            "version_note": "Official source acquisition candidate - pending independent human review",
            "corpus_version": "phase4-candidate",
            "source_reviewed": False,
            "reviewed_by": None,
            "section_start": prov.section_start,
            "section_end": prov.section_start + len(quote_text),
            "verification": "PENDING",
            "rules": {},
            "rules_reviewed": False,
            "raw_hash": raw_hash,
            "working_translation": None,
        }

        # Validate against strict Phase 4 LegalSource schema
        LegalSource.model_validate(source_dict)
        return source_dict

    def persist_candidate(
        self,
        db: pymongo.database.Database,
        candidate_source: dict[str, Any],
        gridfs_file_id: str,
        gridfs_key: str,
        reason: str = "Curated official provision candidate - pending independent human review",
    ) -> tuple[str, bool]:
        """Saves version candidate to legal_authority_versions with immutability and idempotency checks.

        Returns (version_id, already_existed).
        """
        version_id = digest(candidate_source)
        collection = db["legal_authority_versions"]

        existing = collection.find_one({"$or": [{"_id": version_id}, {"id": version_id}]})
        if existing:
            # Idempotency check: verify identical content
            existing_src = existing.get("source", {})
            if digest(existing_src) == version_id:
                return version_id, True
            raise ValueError(f"Version ID collision for {version_id} with conflicting source content!")

        version_doc = {
            "_id": version_id,
            "id": version_id,
            "source": candidate_source,
            "reason": reason,
            "gridfs_file_id": gridfs_file_id,
            "gridfs_key": gridfs_key,
            "populated_at": datetime.now(timezone.utc).isoformat(),
        }
        collection.insert_one(version_doc)
        return version_id, False

    def build_reviewer_packet(
        self,
        version_id: str,
        source: dict[str, Any],
        ingestion_doc: dict[str, Any],
        gridfs_file_id: str,
        gridfs_key: str,
    ) -> dict[str, Any]:
        """Creates the comprehensive inspection package for an independent human reviewer."""
        # Extract surrounding context (up to 300 characters before and after excerpt)
        full_text = source.get("official_text", "")
        start = source.get("section_start", 0)
        end = source.get("section_end", len(source.get("quote", "")))

        ctx_start = max(0, start - 300)
        ctx_end = min(len(full_text), end + 300)
        surrounding_context = full_text[ctx_start:ctx_end]

        packet = {
            "packet_id": f"revpkt_{version_id[:16]}",
            "source_id": source.get("source_id"),
            "version_id": version_id,
            "parent_document_id": ingestion_doc.get("document_id", source.get("source_id")),
            "official_title": source.get("title"),
            "authority_type": source.get("source_type"),
            "provision": source.get("section"),
            "heading": source.get("title"),
            "exact_official_excerpt": source.get("quote"),
            "section_start": start,
            "section_end": end,
            "surrounding_context": surrounding_context,
            "official_url": source.get("official_url"),
            "final_url": source.get("final_url"),
            "official_owner": ingestion_doc.get("source_owner", "Official Government Publisher"),
            "registry_id": source.get("registry_id"),
            "raw_sha256": source.get("raw_hash"),
            "extracted_text_sha256": source.get("content_hash"),
            "raw_gridfs_file_id": gridfs_file_id,
            "raw_gridfs_key": gridfs_key,
            "retrieval_timestamp": source.get("retrieved_at"),
            "extraction_method": "pymupdf",
            "provenance_chain": ingestion_doc.get("events", []),
            "temporal_warnings": [
                TEMPORAL_WARNING_TEXT,
                TEMPORAL_SUBORDINATE_WARNING,
                TEMPORAL_LINEAGE_WARNING,
            ],
            "discovered_relationships": [
                {
                    "type": "STATUTORY_AMENDMENT_LINEAGE",
                    "status": "UNVERIFIED",
                    "note": "Commencement and amendment notifications require independent human verification",
                }
            ],
            "prior_revision": source.get("parent_revision"),
            "predecessor_revision": source.get("parent_revision"),
            "review_eligible": False,
            "current_review_state": source.get("review_state", "REVIEW_PENDING"),
            "temporal_reviewed": source.get("temporal_reviewed", False),
            "reviewer_decision_options": [
                "REVIEWED_PRIMARY",
                "REJECTED",
                "STALE",
                "NEEDS_NEW_REVISION",
            ],
            "recommendation": None,  # System strictly abstains from recommending approval
            "inspection_ready": True,
        }
        return packet


def generate_review_queue_report(
    db: pymongo.database.Database,
    review_packet_dir: Path | None = None,
) -> dict[str, Any]:
    """Generates machine-readable review queue report listing all genuine pending candidates."""
    versions = list(db["legal_authority_versions"].find({}))
    queue_items = []

    for v in versions:
        src = v.get("source", {})
        if src.get("review_state") != "REVIEW_PENDING":
            continue

        sid = src.get("source_id", "")
        url = src.get("official_url", "")
        owner = src.get("source_owner", "")
        reg_id = src.get("registry_id", "")
        gridfs_id = v.get("gridfs_file_id") or src.get("gridfs_file_id")

        # 1. Purity: Reject fixture identity or synthetic provenance
        if "fixture" in sid.lower() or "synthetic" in sid.lower():
            continue
        # 2. Purity: Reject fixture URLs
        if "fixtures.invalid" in url.lower():
            continue
        # 3. Purity: Reject test owners and test registries
        if "test fixture" in owner.lower() or "test" in reg_id.lower():
            continue
        # 4. Purity: Reject missing genuine GridFS lineage
        if not gridfs_id:
            continue

        vid = v.get("id") or str(v.get("_id"))
        packet_ref = None
        if review_packet_dir:
            pkt_file = review_packet_dir / f"{sid}.json"
            if pkt_file.exists():
                try:
                    pkt_data = json.loads(pkt_file.read_text(encoding="utf-8"))
                    if pkt_data.get("version_id") != vid:
                        # Version superseded or unpacketed preliminary entry
                        continue
                except Exception:
                    continue
                packet_ref = str(pkt_file).replace("\\", "/")
            else:
                continue
        if not packet_ref:
            packet_ref = f"docs/audits/review_packets/{sid}.json"

        item = {
            "source_id": sid,
            "version_id": vid,
            "document": src.get("title"),
            "section_provision": src.get("section"),
            "domain": src.get("domain"),
            "review_state": src.get("review_state"),
            "temporal_reviewed": src.get("temporal_reviewed", False),
            "raw_hash": src.get("raw_hash"),
            "review_packet_reference": packet_ref,
            "gridfs_file_id": gridfs_id,
            "gridfs_key": v.get("gridfs_key") or src.get("gridfs_key"),
            "retrieved_at": src.get("retrieved_at"),
            "official_url": src.get("official_url"),
        }
        queue_items.append(item)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_pending_candidates": len(queue_items),
        "candidates": queue_items,
    }
