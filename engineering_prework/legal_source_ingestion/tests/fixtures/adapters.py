"""TEST ONLY: deterministic synthetic input, never official retrieval or law."""
import hashlib
from ...adapters.unsupported_adapter import UnsupportedSourceAdapter
from ...models import RawDocumentRecord, ExtractedDocument, AuthorityType, VersionRelationship

FLAGS = dict(source_mode="TEST_FIXTURE", officially_retrieved=False, review_eligible=False)


class FixtureSourceAdapter(UnsupportedSourceAdapter):
    default_type = AuthorityType.ACT
    fixture_id = "arbitrary_act"
    fixture_title = "Synthetic Orbital Habitat Act"

    def discover_documents(self, query="", limit=10, **filters):
        candidates = [dict(document_id=self.fixture_id, title=self.fixture_title,
                           authority_type=self.default_type,
                           official_url="https://fixtures.invalid/" + self.fixture_id, **FLAGS)]
        return [c for c in candidates if not query or query.lower() in c["title"].lower()][:limit]

    def fetch_document(self, document_id, official_url, text_payload, *, authority_type=None):
        data = text_payload.encode("utf-8")
        return RawDocumentRecord(
            document_id=document_id, source_id="fixture:" + self.source_id, title=document_id,
            authority_type=authority_type or self.default_type,
            official_url="https://fixtures.invalid/" + document_id,
            final_url="https://fixtures.invalid/" + document_id,
            retrieved_at="NOT_FETCHED", raw_content_hash=hashlib.sha256(data).hexdigest(),
            content_type="text/plain; charset=utf-8", file_extension=".txt",
            file_size_bytes=len(data), source_owner="TEST FIXTURE",
            retrieval_method="TEST_FIXTURE", provenance_notes="Synthetic test input; no retrieval occurred",
            **FLAGS,
        )

    def extract_text(self, raw_doc, text_override):
        digest = hashlib.sha256(text_override.encode("utf-8")).hexdigest()
        if raw_doc.source_mode != "TEST_FIXTURE" or digest != raw_doc.raw_content_hash:
            raise ValueError("Fixture bytes must match the raw record")
        return ExtractedDocument(
            document_id=raw_doc.document_id, source_id=raw_doc.source_id,
            title=raw_doc.title, authority_type=raw_doc.authority_type,
            official_url=raw_doc.official_url, raw_hash=digest,
            text_content=text_override, text_hash=digest, source_owner="TEST FIXTURE", **FLAGS,
        )

    def extract_metadata(self, raw_doc):
        return raw_doc.model_dump()

    def build_provenance(self, raw_doc, extracted):
        if raw_doc.source_mode != "TEST_FIXTURE" or extracted.source_mode != "TEST_FIXTURE":
            raise ValueError("Test-only records required")
        if hashlib.sha256(extracted.text_content.encode("utf-8")).hexdigest() != raw_doc.raw_content_hash:
            raise ValueError("Fixture bytes mismatch")
        return dict(raw_doc.model_dump(), extracted_text_hash=extracted.text_hash,
                    verification_status="TEST_ONLY_NOT_REVIEW_ELIGIBLE")

    def discover_related_amendments(self, document_id):
        return [VersionRelationship(source_id="synthetic_notification", target_id=document_id,
                relationship="COMMENCED_BY", evidence_url="https://fixtures.invalid/notification",
                evidence_text="Synthetic possible commencement", commencement_date="2026-01-01", **FLAGS)]


class FixtureIndiaCodeAdapter(FixtureSourceAdapter):
    fixture_id = "cpa_2019"
    fixture_title = "Consumer Protection Act, 2019"


class FixtureMinistryAdapter(FixtureSourceAdapter):
    default_type = AuthorityType.RULE
    fixture_id = "arbitrary_rule"
    fixture_title = "Synthetic Orbital Habitat Rules"


class FixtureJudgmentAdapter(FixtureSourceAdapter):
    default_type = AuthorityType.JUDGMENT

    def discover_documents(self, query="", limit=10, **filters):
        return [dict(document_id="synthetic_judgment", title="Fictional Party A v Fictional Party B",
                     authority_type=self.default_type, official_url="https://fixtures.invalid/judgment",
                     **FLAGS)][:limit]
