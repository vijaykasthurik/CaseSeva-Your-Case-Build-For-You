"""Honest interface for portals without a validated acquisition strategy.

Registry capability labels describe portals, not implemented retrieval support.
No network operations or CAPTCHA bypass occur in this module.
"""
from ..base_adapter import BaseSourceAdapter
from ..models import AcquisitionMethod
from ..sectionizer import StatutorySectionizer


class AcquisitionUnavailable(RuntimeError):
    def __init__(self, status, source_id):
        self.status = status
        super().__init__(f"{status}: {source_id}")


class UnsupportedSourceAdapter(BaseSourceAdapter):
    def _unavailable(self):
        manual = (self.metadata.captcha_required
                  or self.metadata.implementation_status == "MANUAL_BROWSER_ONLY"
                  or self.metadata.recommended_acquisition_method == AcquisitionMethod.MANUAL_OR_BROWSER_REVIEW_REQUIRED)
        raise AcquisitionUnavailable(
            "MANUAL_OR_BROWSER_REVIEW_REQUIRED" if manual else "NOT_FETCHED",
            self.source_id,
        )

    def discover_documents(self, query="", limit=10, **filters):
        self._unavailable()

    def fetch_document(self, document_id, official_url):
        self._unavailable()

    def extract_metadata(self, raw_doc):
        self._unavailable()

    def extract_text(self, raw_doc):
        self._unavailable()

    def build_provenance(self, raw_doc, extracted):
        self._unavailable()

    def enumerate_sections(self, extracted, domain="GENERAL"):
        # Parsing is generic and conveys no retrieval or review authority.
        records = StatutorySectionizer().extract_provisions(
            document_id=extracted.document_id, title=extracted.title,
            text=extracted.text_content, official_url=extracted.official_url,
            source_owner=extracted.source_owner or self.metadata.owner, raw_document_hash=extracted.raw_hash,
            authority_type=extracted.authority_type, domain=domain,
            jurisdiction=extracted.jurisdiction, language=extracted.language,
        )
        return [r.model_copy(update={"source_mode": extracted.source_mode}) for r in records]

    def detect_version_metadata(self, extracted):
        self._unavailable()

    def discover_related_amendments(self, document_id):
        self._unavailable()
