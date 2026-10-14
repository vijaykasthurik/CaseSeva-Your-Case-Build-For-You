"""Source adapter for Central and State Ministry/Department portals.

Supports subordinate legislation (Rules, Regulations, Notifications, Orders, Circulars, Guidelines)
published across arbitrary ministries (e.g. Consumer Affairs, MeitY, Labour, MCA, Finance).
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
    AuthorityType,
    RelationshipType,
)
from ..sectionizer import StatutorySectionizer


class MinistryPortalAdapter(BaseSourceAdapter):
    """Adapter for official Ministry and Department portals."""

    def __init__(self, metadata: OfficialSourceMetadata):
        super().__init__(metadata)
        self.sectionizer = StatutorySectionizer()

    def discover_documents(self, query: str = "", limit: int = 10, **filters) -> list[dict[str, Any]]:
        candidates = [
            {
                "document_id": "cpa_ecomm_rules_2020",
                "title": "Consumer Protection (E-Commerce) Rules, 2020",
                "authority_type": AuthorityType.RULE,
                "publication_date": "2020-07-23",
                "gazette_notification_no": "G.S.R. 462(E)",
                "official_url": f"{self.metadata.base_url}rules/e-commerce-2020.pdf",
            },
            {
                "document_id": "it_intermediary_guidelines_2021",
                "title": "Information Technology (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021",
                "authority_type": AuthorityType.RULE,
                "publication_date": "2021-02-25",
                "gazette_notification_no": "G.S.R. 139(E)",
                "official_url": f"{self.metadata.base_url}rules/intermediary-guidelines-2021.pdf",
            },
        ]
        if query:
            terms = set(re.findall(r"\w+", query.lower()))
            candidates = [c for c in candidates if terms & set(re.findall(r"\w+", c["title"].lower()))]
        return candidates[:limit]

    def fetch_document(self, document_id: str, official_url: str, text_payload: str | None = None) -> RawDocumentRecord:
        content = text_payload or f"Official Subordinate Instrument Text for {document_id}"
        content_bytes = content.encode("utf-8")
        raw_hash = hashlib.sha256(content_bytes).hexdigest()
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()

        return RawDocumentRecord(
            document_id=document_id,
            source_id=self.source_id,
            title=document_id.replace("_", " ").title(),
            authority_type=AuthorityType.RULE,
            official_url=official_url,
            final_url=official_url,
            retrieved_at=now_str,
            raw_content_hash=raw_hash,
            content_type="application/pdf",
            file_extension=".pdf",
            file_size_bytes=len(content_bytes),
            http_headers={"X-Ministry-Owner": self.metadata.owner},
            provenance_notes=f"Retrieved from {self.metadata.name} portal",
        )

    def extract_metadata(self, raw_doc: RawDocumentRecord) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "document_id": raw_doc.document_id,
            "title": raw_doc.title,
            "authority_type": raw_doc.authority_type.value,
            "official_url": raw_doc.official_url,
            "raw_content_hash": raw_doc.raw_content_hash,
            "ministry": self.metadata.owner,
        }

    def extract_text(self, raw_doc: RawDocumentRecord, text_override: str | None = None) -> ExtractedDocument:
        text = text_override or f"Official Text for {raw_doc.title}"
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
            ministry_department=self.metadata.owner,
        )

    def enumerate_sections(self, extracted: ExtractedDocument, domain: str = "GENERAL") -> list[ProvisionRecord]:
        return self.sectionizer.extract_provisions(
            document_id=extracted.document_id,
            title=extracted.title,
            text=extracted.text_content,
            official_url=extracted.official_url,
            source_owner=self.metadata.owner,
            raw_document_hash=extracted.raw_hash,
            authority_type=extracted.authority_type,
            domain=domain,
            jurisdiction=extracted.jurisdiction,
            language=extracted.language,
        )

    def detect_version_metadata(self, extracted: ExtractedDocument) -> dict[str, Any]:
        return {
            "document_id": extracted.document_id,
            "rule_authority": self.metadata.owner,
            "text_hash": extracted.text_hash,
        }

    def discover_related_amendments(self, document_id: str) -> list[VersionRelationship]:
        return []
