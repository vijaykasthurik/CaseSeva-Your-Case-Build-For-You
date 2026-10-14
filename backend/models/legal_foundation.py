"""Phase 4 candidate contracts. Authority and persistent identity are server-owned."""
from typing import Literal
from ..services.intelligence_config import CONFIG
from pydantic import Field
from .understanding import Strict, Domain


class Selection(Strict):
    agent: str
    fact_ids: list[str] = Field(min_length=1, max_length=30)
    reason: str = Field(min_length=1, max_length=500)


Capability = Literal['ISSUE_ANALYSIS', 'EVIDENCE_GAPS', 'PROCEDURAL_CONTEXT', 'REQUESTED_RELIEF', 'SOURCE_QUERY_PLANNING']


class AnalyticalNeed(Strict):
    issue_key: str = Field(pattern=r'^[a-z][a-z0-9_]{0,79}$')
    domain: Domain
    capability: Capability = 'ISSUE_ANALYSIS'
    fact_ids: list[str] = Field(min_length=1, max_length=30)
    reason: str = Field(min_length=1, max_length=500)


class TeamProposal(Strict):
    selected: list[Selection] = Field(default_factory=list, max_length=12)
    needs: list[AnalyticalNeed] = Field(default_factory=list, max_length=20)
    secondary_reason: str | None = None
    public_record_fact_ids: list[str] = Field(default_factory=list)
    unavailable_record_refs: list[int] = Field(default_factory=list)
    limitation_relevant: bool
    precedent_useful: bool
    optional_reason: str = Field(max_length=1500)


class IssueCandidate(Strict):
    key: str = Field(pattern=r'^[a-z][a-z0-9_]{0,79}$')
    statement: str = Field(min_length=1, max_length=1000)
    category: str = Field(min_length=1, max_length=100)
    domain: Domain
    domain_contexts: list[Domain] = Field(default_factory=list, max_length=8)
    fact_ids: list[str] = Field(min_length=1, max_length=30)
    contradicting_fact_ids: list[str] = Field(default_factory=list)
    party_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    date_fact_ids: list[str] = Field(default_factory=list)
    specialist_origins: list[str] = Field(default_factory=list)
    query: str = Field(min_length=1, max_length=500)
    jurisdiction: str | None = None
    jurisdiction_fact_ids: list[str] = Field(default_factory=list)
    limitation_relevant: bool
    precedent_useful: bool
    unknowns: list[str] = Field(default_factory=list, max_length=15)


class IssuesProposal(Strict):
    issues: list[IssueCandidate] = Field(min_length=1, max_length=4)
    further_issues_require_review: bool = False


class SpecialistObservation(Strict):
    observation: str = Field(min_length=1, max_length=1000)
    fact_ids: list[str] = Field(min_length=1, max_length=25)
    evidence_ids: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list, max_length=15)


class SpecialistProposal(Strict):
    observations: list[SpecialistObservation] = Field(max_length=16)
    issue_families: list[str] = Field(max_length=12)
    review_requirements: list[str] = Field(default_factory=list, max_length=15)


class LegalSource(Strict):
    source_id: str = Field(pattern=r'^[A-Za-z0-9_]+$')
    family: str
    source_type: Literal[tuple(CONFIG['authority_types'])]
    domain: Domain
    jurisdiction: str
    title: str
    section: str | None = None
    court: str | None = None
    citation: str
    official_url: str
    final_url: str | None = None
    ingestion_id: str | None = None
    review_state: Literal['DISCOVERED', 'DOWNLOADED', 'PARSED', 'IDENTITY_CHECKED', 'REVIEW_PENDING', 'REVIEWED_PRIMARY', 'REJECTED', 'STALE'] = 'REVIEW_PENDING'
    review_id: str | None = None
    revision_status: Literal['NONE', 'REVISION_REQUESTED'] = 'NONE'
    parent_revision: str | None = None
    revision_request_id: str | None = None
    revision_metadata: dict = Field(default_factory=dict)
    reviewed_at: str | None = None
    registry_id: str
    source_language: str
    official_text: str = Field(min_length=1, max_length=250000)
    quote: str = Field(min_length=1, max_length=6000)
    content_hash: str
    retrieved_at: str
    effective_from: str | None = None
    effective_until: str | None = None
    temporal_source_ids: list[str] = Field(default_factory=list)
    temporal_reviewed: bool = False
    version_note: str
    corpus_version: str
    source_reviewed: bool = False
    reviewed_by: str | None = None
    section_start: int = Field(ge=0)
    section_end: int = Field(gt=0)
    verification: Literal['PENDING', 'VERIFIED', 'REJECTED', 'OUTDATED'] = 'PENDING'
    # Structured, independently reviewed rule metadata, never populated by an LLM.
    rules: dict = Field(default_factory=dict)
    rules_reviewed: bool = False
    raw_hash: str | None = None
    working_translation: str | None = None


class ElementSupport(Strict):
    element: str = Field(min_length=1, max_length=1500)
    fact_ids: list[str] = Field(default_factory=list, max_length=30)
    contradicting_fact_ids: list[str] = Field(default_factory=list, max_length=30)
    unknowns: list[str] = Field(default_factory=list, max_length=10)


class LawApplication(Strict):
    source_id: str
    citation: str
    title: str
    section: str | None = None
    quote: str = Field(min_length=1, max_length=4000)
    fact_ids: list[str] = Field(min_length=1, max_length=30)
    explanation: str = Field(max_length=1500)
    required_elements: list[str] = Field(default_factory=list, max_length=20)
    element_mapping: list[ElementSupport] = Field(default_factory=list, max_length=20)


class ApplicationProposal(Strict):
    applications: list[LawApplication] = Field(max_length=12)
    unknowns: list[str] = Field(default_factory=list, max_length=15)
