"""Source adapter for Judicial authorities (Supreme Court, High Courts, eCourts).

Ingests structured judgment records, bench constitution, citations, cited statutes,
disposition, and binding hierarchy metadata.
"""
import hashlib
import re
from typing import Any
from ..base_adapter import BaseSourceAdapter
from ..models import (
    OfficialSourceMetadata,
    RawDocumentRecord,
    ExtractedDocument,
    ProvisionRecord,
    VersionRelationship,
    JudgmentRecord,
    AuthorityType,
    ReviewStatus,
)


class JudgmentSourceAdapter(BaseSourceAdapter):
    """Adapter for official judicial portals and judgments repositories."""

    def __init__(self, metadata: OfficialSourceMetadata):
        super().__init__(metadata)

    def discover_documents(self, query: str = "", limit: int = 10, **filters) -> list[dict[str, Any]]:
        candidates = [
            {
                "judgment_id": "sc_2023_defective_service",
                "case_number": "Civil Appeal No. 4521 of 2021",
                "court": "Supreme Court of India",
                "decision_date": "2023-04-12",
                "parties": "National Insurance Co. Ltd. v. Consumer Welfare Association",
                "citations": ["2023 INSC 350", "(2023) 6 SCC 112"],
                "official_url": f"{self.metadata.base_url}judgments/2023_INSC_350.pdf",
            }
        ]
        if query:
            terms = set(re.findall(r"\w+", query.lower()))
            candidates = [c for c in candidates if terms & set(re.findall(r"\w+", (c["case_number"] + " " + c["parties"]).lower()))]
        return candidates[:limit]

    def fetch_document(self, document_id: str, official_url: str, text_payload: str | None = None) -> RawDocumentRecord:
        content = text_payload or f"Official Judgment Text for {document_id}"
        content_bytes = content.encode("utf-8")
        raw_hash = hashlib.sha256(content_bytes).hexdigest()
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()

        return RawDocumentRecord(
            document_id=document_id,
            source_id=self.source_id,
            title=document_id.replace("_", " ").title(),
            authority_type=AuthorityType.JUDGMENT,
            official_url=official_url,
            final_url=official_url,
            retrieved_at=now_str,
            raw_content_hash=raw_hash,
            content_type="application/pdf",
            file_extension=".pdf",
            file_size_bytes=len(content_bytes),
            http_headers={"X-Judicial-Body": self.metadata.owner},
            provenance_notes=f"Retrieved from {self.metadata.name}",
        )

    def extract_metadata(self, raw_doc: RawDocumentRecord) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "document_id": raw_doc.document_id,
            "court": self.metadata.owner,
            "official_url": raw_doc.official_url,
            "raw_content_hash": raw_doc.raw_content_hash,
        }

    def extract_text(self, raw_doc: RawDocumentRecord, text_override: str | None = None) -> ExtractedDocument:
        text = text_override or f"Official Judgment Text for {raw_doc.title}"
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return ExtractedDocument(
            document_id=raw_doc.document_id,
            source_id=self.source_id,
            title=raw_doc.title,
            authority_type=raw_doc.authority_type,
            official_url=raw_doc.official_url,
            raw_hash=raw_doc.raw_content_hash,
            text_content=text,
            text_hash=text_hash,
            language="en",
            jurisdiction="IN",
        )

    def enumerate_sections(self, extracted: ExtractedDocument) -> list[ProvisionRecord]:
        # Judgments do not have statutory sections; they yield ratio decidendi and paragraph records
        return []

    def parse_judgment_record(
        self,
        extracted: ExtractedDocument,
        case_number: str,
        decision_date: str,
        appellant: str,
        respondent: str,
        citations: list[str],
        disposition: str = "ALLOWED",
        bench: str | None = None,
        cited_statutes: list[str] | None = None,
        cited_cases: list[str] | None = None,
        hierarchy_rank: int = 1,
    ) -> JudgmentRecord:
        """Parses structured judgment metadata with immutable full-text hash."""
        return JudgmentRecord(
            judgment_id=extracted.document_id,
            court=self.metadata.owner,
            bench=bench,
            case_number=case_number,
            decision_date=decision_date,
            appellant=appellant,
            respondent=respondent,
            citation_identifiers=citations,
            official_url=extracted.official_url,
            document_hash=extracted.raw_hash,
            cited_statutes=cited_statutes or [],
            cited_cases=cited_cases or [],
            disposition=disposition,
            precedent_hierarchy_rank=hierarchy_rank,
            binding_jurisdiction="IN",
            full_text_hash=extracted.text_hash,
            review_status=ReviewStatus.DISCOVERED,
        )

    def detect_version_metadata(self, extracted: ExtractedDocument) -> dict[str, Any]:
        return {"document_id": extracted.document_id, "is_judgment": True}

    def discover_related_amendments(self, document_id: str) -> list[VersionRelationship]:
        return []
