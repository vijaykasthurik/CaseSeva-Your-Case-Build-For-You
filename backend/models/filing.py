"""Canonical FilingPackage contract and schemas for Phase 10 Filing Preparation & Submission Safety.

Follows strict versioning, immutability, provenance, and advocate control.
Phase 10 strictly prepares filing materials and does NOT perform automated external court filing.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class FilingReadinessStatus(str, Enum):
    PREPARATION_ONLY = "PREPARATION_ONLY"
    MISSING_REQUIREMENTS = "MISSING_REQUIREMENTS"
    ADVOCATE_REVIEW_REQUIRED = "ADVOCATE_REVIEW_REQUIRED"
    READY_FOR_HUMAN_FILING = "READY_FOR_HUMAN_FILING"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    # Note: FILED is strictly omitted. Phase 10 must not create FILED state.


class AnnexureItem(BaseModel):
    evidence_id: str
    source_hash: str
    filename: str
    evidence_type: str = "DOCUMENT"
    relevance_note: str = ""
    annexure_label: str  # e.g. "Annexure A-1"
    ordering: int = 1
    source_case_file_version: int = 1
    storage_key: Optional[str] = None
    size_bytes: Optional[int] = None


class DocumentManifestItem(BaseModel):
    item_type: str  # APPROVED_DRAFT, APPROVED_PDF, ANNEXURE, EVIDENCE_INDEX, CHECKLIST, PROVENANCE, FILING_SUMMARY
    filename: str
    version: int | str
    sha256: str
    size_bytes: int
    mandatory_for_filing: bool = True
    description: str = ""


class PreSubmissionChecklistItem(BaseModel):
    item_id: str
    category: str  # PARTIES, FACTS, DRAFT, LAW, ANNEXURES, SIGNATURE, PROCEDURE, CONSENT
    label: str
    status: str  # PASSED, WARNING, ACTION_REQUIRED
    details: str
    requires_advocate_action: bool = False


class FilingPackage(BaseModel):
    filing_package_id: str
    case_id: str
    advocate_id: str
    engine1_case_file_version: int
    engine3_draft_id: str
    engine3_draft_version: int
    draft_integrity_hash: str
    engine2_run_id: Optional[str] = None
    status: str = FilingReadinessStatus.PREPARATION_ONLY.value
    created_at: str
    version: int = 1

    document_type: str = "complaint_petition"
    intended_forum: dict[str, Any] = Field(default_factory=dict)
    jurisdiction: dict[str, Any] = Field(default_factory=dict)
    filing_mode: str = "MANUAL_HUMAN_ADVOCATE_FILING"
    filing_readiness: str = FilingReadinessStatus.PREPARATION_ONLY.value

    approved_draft_reference: dict[str, Any] = Field(default_factory=dict)
    approved_pdf_reference: dict[str, Any] = Field(default_factory=dict)
    annexures: list[AnnexureItem] = Field(default_factory=list)
    evidence_index: list[dict[str, Any]] = Field(default_factory=list)
    document_manifest: list[DocumentManifestItem] = Field(default_factory=list)
    party_details: dict[str, Any] = Field(default_factory=dict)
    chronology_reference: list[dict[str, Any]] = Field(default_factory=list)
    verified_legal_basis: list[dict[str, Any]] = Field(default_factory=list)
    required_missing_items: list[str] = Field(default_factory=list)
    pre_submission_checklist: list[PreSubmissionChecklistItem] = Field(default_factory=list)
    disclosures: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    package_digest: str = ""
    storage_key: Optional[str] = None
    export_bundle_sha256: Optional[str] = None
