"""Pydantic schema for canonical Engine-1 Case File contract."""
from typing import Any, Literal
from pydantic import Field
from .understanding import Strict


LegalFoundationStatus = Literal["VERIFIED_AUTHORITY", "PENDING_SOURCE", "ABSTAINED", "CONFLICTING_AUTHORITY", "NOT_REQUESTED"]


class CaseFact(Strict):
    fact_id: str = Field(pattern=r'^F\d{3,}$')
    text: str = Field(min_length=1)
    proposition: str = Field(min_length=1)
    category: str = "GENERAL"
    date: dict[str, Any] | None = None
    exact_values: list[str] = Field(default_factory=list)
    certainty: Literal["STATED", "UNKNOWN", "CONFLICTED"] = "STATED"
    source_status: str = "UNVERIFIED"
    verification_status: str = "UNVERIFIED"
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class CaseTimelineEvent(Strict):
    timeline_id: str
    event_id: str
    description: str = Field(min_length=1)
    date: dict[str, Any] | None = None
    fact_ids: list[str] = Field(default_factory=list)
    party_ids: list[str] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)


class CaseParty(Strict):
    party_id: str = Field(pattern=r'^P\d{3,}$')
    name: str | None = None
    role: str = "PARTICIPANT"
    fact_ids: list[str] = Field(default_factory=list)
    unknown_attributes: list[str] = Field(default_factory=list)
    verification: str = "UNVERIFIED"


class CaseRelationship(Strict):
    relationship_id: str = Field(pattern=r'^R[a-f0-9]+$')
    left: str
    right: str
    relationship: str
    fact_ids: list[str] = Field(default_factory=list)


class CaseEvidenceItem(Strict):
    evidence_id: str = Field(pattern=r'^E\d{3,}$')
    filename: str
    content_type: str
    size: int = Field(ge=0)
    description: str = ""
    readable: bool = False
    uploaded_at: str | None = None


class CaseEvidenceMapping(Strict):
    evidence_id: str
    fact_id: str
    relationship_type: str = "SUPPORTS"
    passage: int | None = None


class CaseClarificationQuestion(Strict):
    question_id: str
    topic: str
    question: str
    priority: str = "NORMAL"
    answered: bool = False
    answer_response: str | None = None
    answer_value: str | None = None


class CaseIssue(Strict):
    legal_issue_id: str = Field(pattern=r'^L\d{3,}$')
    key: str
    statement: str
    category: str
    domain: str
    domain_contexts: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    specialist_origins: list[str] = Field(default_factory=list)
    query: str
    jurisdiction: str | None = None
    limitation_relevant: bool = False
    precedent_useful: bool = False
    unknowns: list[str] = Field(default_factory=list)


class CaseSpecialistOutput(Strict):
    specialist: str
    agent: str
    domain: str
    observations: list[dict[str, Any]] = Field(default_factory=list)
    issue_families: list[str] = Field(default_factory=list)


class CaseLegalFinding(Strict):
    provision_id: str
    title: str
    section: str | None = None
    citation: str | None = None
    court: str | None = None
    source_url: str | None = None
    retrieved_at: str | None = None
    verification_status: Literal["VERIFIED", "PENDING_HUMAN_REVIEW", "PENDING", "REJECTED", "OUTDATED"] = "PENDING"
    authority_status: LegalFoundationStatus = "PENDING_SOURCE"
    source_version: str | None = None
    explanation: str


class CanonicalCaseFile(Strict):
    version: int = Field(ge=1)
    case_file_version: int = Field(ge=1)
    kind: str
    created_at: str
    case_id: str
    original_narrative: str
    normalized_narrative: str
    intake: dict[str, Any]
    facts: list[CaseFact]
    disputed_facts: list[CaseFact] = Field(default_factory=list)
    timeline: list[CaseTimelineEvent] = Field(default_factory=list)
    parties: list[CaseParty] = Field(default_factory=list)
    relationships: list[CaseRelationship] = Field(default_factory=list)
    evidence_inventory: list[CaseEvidenceItem] = Field(default_factory=list)
    evidence_mappings: list[CaseEvidenceMapping] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    clarification_questions: list[CaseClarificationQuestion] = Field(default_factory=list)
    issues: list[CaseIssue] = Field(default_factory=list)
    domains: dict[str, Any] = Field(default_factory=dict)
    specialist_outputs: list[CaseSpecialistOutput] = Field(default_factory=list)
    applicable_law: list[CaseLegalFinding] = Field(default_factory=list)
    legal_findings: list[CaseLegalFinding] = Field(default_factory=list)
    authority_provenance: dict[str, str] = Field(default_factory=dict)
    authority_versions: dict[str, str] = Field(default_factory=dict)
    legal_foundation_status: LegalFoundationStatus
    unresolved_legal_requirements: list[str] = Field(default_factory=list)
    reconciliation: dict[str, Any] = Field(default_factory=dict)
    citizen_safe_summary: str
    next_actions: list[str] = Field(default_factory=list)
    pipeline_status: str
    stage_provenance: dict[str, Any]
    dependency_versions: dict[str, int]
    input_version: int = 1
    board_version: int = 1
    foundation_complete: bool = False
    pending_advocate_verification: list[dict[str, Any]] = Field(default_factory=list)
    processing_mode: str = "mock"
