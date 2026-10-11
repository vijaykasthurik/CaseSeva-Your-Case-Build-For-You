"""Versioned ingestion contracts, independent of legal intelligence."""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Declaration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    state: Literal["AVAILABLE_NOT_UPLOADED", "NOT_AVAILABLE", "UNKNOWN"]
    kind: Literal["EVIDENCE", "DETAIL"] = "EVIDENCE"
    source_id: str
    quote: str


class DeclarationSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    state: Literal["AVAILABLE_NOT_UPLOADED", "NOT_AVAILABLE", "UNKNOWN"]
    kind: Literal["EVIDENCE", "DETAIL"] = "EVIDENCE"
    source_id: str
    quote_index: int = Field(ge=0)


class DeclarationSelections(BaseModel):
    items: list[DeclarationSelection] = Field(default_factory=list)


class DeclarationOutput(BaseModel):
    items: list[Declaration] = Field(default_factory=list)


class SourceRecord(BaseModel):
    source_id: str
    actor_id: str | None = None
    case_id: str
    case_origin: str
    source_type: str
    original_filename: str | None = None
    mime_type: str
    uploaded_at: str | None = None
    extraction_method: str
    extraction_status: str
    language: str
    content_hash: str
    text_hash: str
    storage_reference: str | None = None
    derived_reference: str
    processing_mode: str
    error_state: str | None = None
    original_text: str
    evidence_id: str | None = None


class RawCasePackage(BaseModel):
    # Legacy keys remain available to the existing engines during migration.
    model_config = ConfigDict(extra="allow")
    schema_version: int = 1
    case_id: str
    origin: str
    case_type: str | None = None
    canonical_narrative: str
    original_language_content: str
    english_working_text: str
    preferred_language: str
    provenance: list[SourceRecord]
    declared_evidence: list[Declaration]
    unavailable_evidence: list[Declaration]
    unknown_evidence: list[Declaration]
    unknown_details: list[Declaration]
    evidence: list[dict]
    pending: list[dict]
