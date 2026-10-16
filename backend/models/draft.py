"""Canonical AdvocateDraft contract and schemas for Engine-3 drafting.

Follows strict versioning, immutability, provenance, and advocate control.
"""
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class DraftType(str, Enum):
    COMPLAINT_PETITION = "complaint_petition"
    LEGAL_NOTICE = "legal_notice"
    WRITTEN_REPRESENTATION = "written_representation"
    REPLY_RESPONSE = "reply_response"
    AFFIDAVIT = "affidavit"
    CASE_BRIEF = "case_brief"
    ADVOCATE_CASE_NOTE = "advocate_case_note"
    CHRONOLOGY = "chronology"
    EVIDENCE_ANNEXURE = "evidence_annexure"
    OTHER = "other"


class DraftMode(str, Enum):
    AUTHORITATIVE = "AUTHORITATIVE"
    FACTUAL_WORKING_DRAFT = "FACTUAL_WORKING_DRAFT"


class DraftStatus(str, Enum):
    DRAFT = "DRAFT"
    ADVOCATE_EDITED = "ADVOCATE_EDITED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    ADVOCATE_APPROVED = "ADVOCATE_APPROVED"
    STALE_INPUT = "STALE_INPUT"
    SUPERSEDED = "SUPERSEDED"


class ConflictResolutionStrategy(str, Enum):
    KEEP_ADVOCATE = "KEEP_ADVOCATE"
    USE_REGENERATED = "USE_REGENERATED"
    MERGE = "MERGE"


class SectionConflict(BaseModel):
    has_conflict: bool = True
    proposed_paragraphs: list[str] = Field(default_factory=list)
    advocate_paragraphs: list[str] = Field(default_factory=list)
    detected_at: str
    resolution: Optional[str] = None
    resolved_at: Optional[str] = None


class SectionContent(BaseModel):
    section_id: str
    heading: str
    paragraphs: list[str] = Field(default_factory=list)
    order: int = 0
    fact_ids: list[str] = Field(default_factory=list)
    provision_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    edited_by_advocate: bool = False
    advocate_notes: list[str] = Field(default_factory=list)
    last_regenerated_at: Optional[str] = None
    conflict: Optional[SectionConflict] = None


class ApprovalRecord(BaseModel):
    approved_by_advocate_id: str
    draft_version: int
    source_engine1_version: int
    approved_at: str
    integrity_hash: str
    approval_state: str = "ADVOCATE_APPROVED"
    disclosures: list[str] = Field(default_factory=list)


class PdfArtifact(BaseModel):
    storage_key: str
    sha256: str
    created_at: str
    size_bytes: int
    filename: str


class AdvocateDraft(BaseModel):
    draft_id: str
    case_id: str
    advocate_id: str
    draft_type: str = DraftType.COMPLAINT_PETITION.value
    draft_mode: str = DraftMode.AUTHORITATIVE.value
    engine1_case_file_version: int
    engine2_run_id: Optional[str] = None
    engine2_status: str = "NOT_RUN"
    source_review_version: Optional[int] = None
    version: int = 1
    parent_version_id: Optional[str] = None
    status: str = DraftStatus.DRAFT.value
    created_at: str
    updated_at: str

    title: str
    jurisdiction_forum: dict[str, Any] = Field(default_factory=dict)
    parties: dict[str, Any] = Field(default_factory=dict)
    facts_section: list[dict[str, Any]] = Field(default_factory=list)
    chronology: list[dict[str, Any]] = Field(default_factory=list)
    issues_section: list[dict[str, Any]] = Field(default_factory=list)
    legal_basis: list[dict[str, Any]] = Field(default_factory=list)
    reliefs_or_requests: list[str] = Field(default_factory=list)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list)
    annexures: list[dict[str, Any]] = Field(default_factory=list)
    professional_notes: Optional[str] = None
    disclosures: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    sections: list[SectionContent] = Field(default_factory=list)
    consistency_findings: list[dict[str, Any]] = Field(default_factory=list)
    approval_record: Optional[ApprovalRecord] = None
    pdf_artifact: Optional[PdfArtifact] = None
    html_content: Optional[str] = None
