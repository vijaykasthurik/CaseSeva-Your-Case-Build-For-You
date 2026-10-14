"""Generic base source-adapter interface for official legal portals.

All portal-specific selectors, handle decoders, and HTML parsers reside strictly inside
individual adapters. The common engine never contains portal-specific branch logic.
"""
from abc import ABC, abstractmethod
from typing import Any
from .models import (
    OfficialSourceMetadata,
    RawDocumentRecord,
    ExtractedDocument,
    ProvisionRecord,
    VersionRelationship,
)


class BaseSourceAdapter(ABC):
    """Abstract protocol for official Indian legal source acquisition and extraction."""

    def __init__(self, metadata: OfficialSourceMetadata):
        self.metadata = metadata

    @property
    def source_id(self) -> str:
        return self.metadata.source_id

    @property
    def source_name(self) -> str:
        return self.metadata.name

    @abstractmethod
    def discover_documents(self, query: str = "", limit: int = 10, **filters) -> list[dict[str, Any]]:
        """Discovers official document candidates matching query and filters."""
        raise NotImplementedError

    @abstractmethod
    def fetch_document(self, document_id: str, official_url: str) -> RawDocumentRecord:
        """Retrieves official document bytes, computing raw SHA-256 hash and provenance."""
        raise NotImplementedError

    @abstractmethod
    def extract_metadata(self, raw_doc: RawDocumentRecord) -> dict[str, Any]:
        """Extracts title, enactment/gazette publication date, ministry, and act number."""
        raise NotImplementedError

    @abstractmethod
    def extract_text(self, raw_doc: RawDocumentRecord) -> ExtractedDocument:
        """Extracts clean full text with SHA-256 digest and linguistic attributes."""
        raise NotImplementedError

    @abstractmethod
    def enumerate_sections(self, extracted: ExtractedDocument) -> list[ProvisionRecord]:
        """Hierarchically parses document into section and subsection provision records."""
        raise NotImplementedError

    @abstractmethod
    def detect_version_metadata(self, extracted: ExtractedDocument) -> dict[str, Any]:
        """Detects commencement, consolidation, and amendment notes embedded in official text."""
        raise NotImplementedError

    @abstractmethod
    def discover_related_amendments(self, document_id: str) -> list[VersionRelationship]:
        """Discovers official amendments, corrigenda, and commencement notifications linked to enactment."""
        raise NotImplementedError

    def build_provenance(self, raw_doc: RawDocumentRecord, extracted: ExtractedDocument) -> dict[str, Any]:
        """Constructs an immutable provenance receipt for ingestion audit."""
        return {
            "source_id": self.source_id,
            "document_id": raw_doc.document_id,
            "official_domain": self.metadata.official_domain,
            "official_url": raw_doc.official_url,
            "final_url": raw_doc.final_url,
            "raw_content_hash": raw_doc.raw_content_hash,
            "extracted_text_hash": extracted.text_hash,
            "retrieved_at": raw_doc.retrieved_at,
            "file_size_bytes": raw_doc.file_size_bytes,
            "acquisition_method": self.metadata.recommended_acquisition_method.value,
            "verification_status": "DISCOVERED_PENDING_INDEPENDENT_REVIEW",
        }
