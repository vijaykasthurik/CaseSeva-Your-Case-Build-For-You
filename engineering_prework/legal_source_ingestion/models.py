"""Data models for official Indian legal source discovery, sectionization, versioning, and ingestion.

Isolated engineering prework: under no circumstances may these records populate the production
reviewed corpus without independent authenticated human administrative review.
"""
from enum import Enum
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AuthorityType(str, Enum):
    CONSTITUTION_PROVISION = "CONSTITUTION_PROVISION"
    ACT = "ACT"
    AMENDMENT_ACT = "AMENDMENT_ACT"
    RULE = "RULE"
    REGULATION = "REGULATION"
    NOTIFICATION = "NOTIFICATION"
    ORDER = "ORDER"
    ORDINANCE = "ORDINANCE"
    CIRCULAR = "CIRCULAR"
    GUIDELINE = "GUIDELINE"
    JUDGMENT = "JUDGMENT"
    PRECEDENT_METADATA = "PRECEDENT_METADATA"


class ReviewStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    DOWNLOADED = "DOWNLOADED"
    EXTRACTED = "EXTRACTED"
    REVIEW_PENDING = "REVIEW_PENDING"
    REVIEWED_PRIMARY = "REVIEWED_PRIMARY"
    REJECTED = "REJECTED"
    STALE = "STALE"


class RelationshipType(str, Enum):
    AMENDED_BY = "AMENDED_BY"
    CORRECTED_BY = "CORRECTED_BY"
    COMMENCED_BY = "COMMENCED_BY"
    SUPPLEMENTED_BY = "SUPPLEMENTED_BY"
    INTERPRETED_BY = "INTERPRETED_BY"


class AcquisitionMethod(str, Enum):
    DIRECT_API = "DIRECT_API"
    STABLE_HTTP_INDEX = "STABLE_HTTP_INDEX"
    DETERMINISTIC_HTML = "DETERMINISTIC_HTML"
    MANUAL_OR_BROWSER_REVIEW_REQUIRED = "MANUAL_OR_BROWSER_REVIEW_REQUIRED"


class OfficialSourceMetadata(StrictModel):
    source_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    official_domain: str = Field(min_length=1, max_length=150)
    owner: str = Field(min_length=1, max_length=200)
    authority_category: Literal[
        "CENTRAL_LEGISLATION", "MINISTRY_DEPARTMENT", "JUDICIARY", "STATE_LEGISLATION", "TRIBUNAL_REGULATOR"
    ]
    base_url: str = Field(min_length=1, max_length=300)
    available_document_types: list[AuthorityType]
    search_capability: bool
    download_formats: list[str]
    stable_document_ids: bool
    pagination: bool
    access_restrictions: str
    captcha_required: bool
    rate_limit_guidelines: str
    recommended_acquisition_method: AcquisitionMethod
    priority: Literal["P0_CRITICAL", "P1_HIGH", "P2_MEDIUM", "P3_LOW"]
    implementation_status: Literal["AUTOMATABLE_VALIDATED", "PARTIALLY_FEASIBLE", "MANUAL_BROWSER_ONLY"]
    notes: str = ""


class IngestionRecord(StrictModel):
    # Prework has no authenticated review integration. No record is reviewed law.
    source_mode: Literal["UNVERIFIED", "TEST_FIXTURE", "OFFICIAL_ACQUISITION"] = Field(default="UNVERIFIED", frozen=True)
    officially_retrieved: bool = Field(default=False, frozen=True)
    review_eligible: Literal[False] = Field(default=False, frozen=True)

    @field_validator("review_status", check_fields=False)
    @classmethod
    def no_reviewed_law(cls, value):
        if value == ReviewStatus.REVIEWED_PRIMARY:
            raise ValueError("Isolated ingestion records cannot be reviewed law")
        return value


class RawDocumentRecord(IngestionRecord):
    document_id: str = Field(min_length=1, max_length=120)
    source_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    authority_type: AuthorityType
    official_url: str
    final_url: str
    retrieved_at: str
    raw_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: str
    file_extension: str
    file_size_bytes: int = Field(ge=1)
    http_headers: dict[str, str] = Field(default_factory=dict)
    provenance_notes: str = ""
    source_owner: str = Field(min_length=1)
    retrieval_method: Literal["NOT_FETCHED", "TEST_FIXTURE", "OFFICIAL_HTTPS_GET", "DIRECT_API"]
    http_status: int | None = Field(default=None, ge=100, le=599)
    gridfs_file_id: str | None = None
    gridfs_key: str | None = None
    redirect_chain: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_official_retrieval(self):
        if self.officially_retrieved:
            if self.source_mode != "OFFICIAL_ACQUISITION" or self.retrieval_method not in ("OFFICIAL_HTTPS_GET", "DIRECT_API") or self.http_status != 200:
                raise ValueError("officially_retrieved requires OFFICIAL_ACQUISITION, HTTP 200, and verified official retrieval method")
        return self


class ExtractedDocument(IngestionRecord):
    document_id: str
    source_id: str
    title: str
    authority_type: AuthorityType
    official_url: str
    raw_hash: str
    source_owner: str = ""
    text_content: str
    text_hash: str
    language: str = "en"
    jurisdiction: str = "IN"
    enactment_date: str | None = None
    publication_date: str | None = None
    act_number: str | None = None
    ministry_department: str | None = None
    extractor_version: str | None = None
    extraction_status: str = "EXTRACTED"
    extraction_warnings: list[str] = Field(default_factory=list)
    gridfs_file_id: str | None = None


class ProvisionRecord(IngestionRecord):
    provision_id: str = Field(pattern=r"^[a-z0-9_]{1,120}$")
    parent_document_id: str
    parent_document_title: str
    authority_type: AuthorityType
    domain: str
    jurisdiction: str = "IN"
    language: str = "en"
    part: str | None = None
    chapter: str | None = None
    section: str = Field(min_length=1, max_length=20)
    subsection: str | None = None
    clause: str | None = None
    subclause: str | None = None
    proviso_index: int | None = None
    explanation_index: int | None = None
    heading: str | None = None
    quote: str = Field(min_length=1)
    section_start: int = Field(ge=0)
    section_end: int = Field(gt=0)
    official_url: str
    source_owner: str
    raw_document_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    extracted_text_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    enactment_date: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None
    amendment_references: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.DISCOVERED


class VersionRelationship(IngestionRecord):
    source_id: str
    target_id: str
    relationship: RelationshipType
    evidence_url: str
    evidence_text: str = Field(min_length=1, max_length=2000)
    commencement_date: str | None = None
    repeal_date: str | None = None
    supported_through_date: str | None = None
    unresolved_coverage: list[str] = Field(default_factory=list)
    # Disabled until independently authenticated evidence/review is integrated.
    verified: Literal[False] = Field(default=False, frozen=True)


class JudgmentRecord(IngestionRecord):
    judgment_id: str = Field(pattern=r"^[a-z0-9_]{1,120}$")
    court: str = Field(min_length=1, max_length=200)
    bench: str | None = None
    case_number: str = Field(min_length=1, max_length=120)
    decision_date: str
    appellant: str = Field(min_length=1, max_length=300)
    respondent: str = Field(min_length=1, max_length=300)
    citation_identifiers: list[str] = Field(default_factory=list)
    official_url: str
    document_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    cited_statutes: list[str] = Field(default_factory=list)
    cited_cases: list[str] = Field(default_factory=list)
    disposition: Literal["ALLOWED", "DISMISSED", "PARTLY_ALLOWED", "REMANDED", "SET_ASIDE", "DISPOSED", "UNKNOWN"]
    precedent_hierarchy_rank: int = 100
    binding_jurisdiction: str = "IN"
    ratio_decidendi_summary: str | None = None
    full_text_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_status: ReviewStatus = ReviewStatus.DISCOVERED
