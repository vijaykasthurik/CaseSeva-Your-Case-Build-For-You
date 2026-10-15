"""Persisted core contracts, also checked after human conflict resolution."""
import re
from typing import Literal
from pydantic import Field, TypeAdapter
from .understanding import Strict, Dated, LanguageAssessment, DomainCandidates


class SourceRef(Strict):
    source_id: str
    passage: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    wording: str = Field(min_length=1)
    evidence_id: str | None
    source_hash: str | None


class StoredDate(Dated):
    normalization_review_required: bool = False


class Identity(Strict):
    semantic_key: str
    identity_anchor: str
    source_refs: list[SourceRef] = Field(min_length=1)
    execution_id: str
    superseded: bool
    identity_review_required: bool


class Fact(Identity):
    fact_id: str
    proposition: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str]
    category: str
    date: StoredDate
    exact_values: list[str]
    certainty: Literal['STATED', 'UNKNOWN', 'CONFLICTED']
    support_state: Literal['UNKNOWN', 'CONFLICTED', 'DOCUMENT_STATED', 'USER_STATED']
    review_state: Literal['REVIEW_REQUIRED']
    verification: Literal['UNVERIFIED']
    created_by: Literal['FACT_TIMELINE']
    board_version: int
    stale: bool


class Incident(Identity):
    incident_id: str
    description: str
    fact_ids: list[str] = Field(min_length=1)
    date: StoredDate
    unknown_fields: list[str]
    party_ids: list[str]
    review_state: Literal['REVIEW_REQUIRED']


class Timeline(Incident):
    timeline_id: str


class Party(Identity):
    party_id: str
    name: str | None
    normalized_name: str | None
    role: str
    fact_ids: list[str] = Field(min_length=1)
    unknown_attributes: list[str]
    review_required: bool
    verification: Literal['UNVERIFIED']


class Relationship(Strict):
    relationship_id: str
    left: str
    right: str
    relationship: str
    fact_ids: list[str] = Field(min_length=1)
    review_required: Literal[True]


class Stage(Strict):
    language: LanguageAssessment
    stage: Literal['NEW_CONSULTATION', 'COMPLAINT_OR_FIR_STAGE', 'EXISTING_CASE', 'ONGOING_OR_OLD_CASE', 'UNKNOWN']
    review_required: bool
    unknowns: list[str]
    source_refs: list[SourceRef]
    execution_id: str


class EvidenceLink(Strict):
    evidence_id: str
    fact_id: str
    relation: Literal['SUPPORTS', 'CONTRADICTS', 'REVIEW_REQUIRED']
    source_refs: list[SourceRef] = Field(min_length=1)
    verified: Literal[False]


class Support(Strict):
    evidence_ids: list[str]
    state: Literal['CONTRADICTED', 'SUPPORTED_BY_UPLOADED_EVIDENCE', 'UNKNOWN', 'USER_STATEMENT_ONLY']


class EvidenceMapping(Strict):
    links: list[EvidenceLink]
    fact_support: dict[str, Support]
    uploaded_evidence_ids: list[str]
    declared_evidence: list[dict]
    unavailable_evidence: list[dict]
    unknown_evidence: list[dict]
    unknown_details: list[dict]
    unresolved: list[str]


class Clarification(Strict):
    status: Literal['SUFFICIENT_WITH_UNKNOWNS']
    suggestions: list[dict]
    answered_topics: list[str]
    suppressed_requests: list[dict]


class Reconciliation(Strict):
    status: Literal['RECONCILED_WITH_UNKNOWNS']
    unresolved: list[str]
    fact_ids: list[str]
    human_resolutions: list[str]


class Domain(DomainCandidates):
    legal_foundation: Literal['PENDING']
    legal_corpus_ready: Literal[False]
    execution_id: str


def record_map(model, prefix, field):
    adapter = TypeAdapter(dict[str, model])
    def validate(value):
        records = adapter.validate_python(value)
        for key, record in records.items():
            if not re.fullmatch(prefix + r'\d{3,}', key) or getattr(record, field) != key:
                raise ValueError('Persistent record identity does not match its key')
        return value
    return validate


VALIDATORS = {
    'case_understanding.stage': Stage.model_validate,
    'facts': record_map(Fact, 'F', 'fact_id'),
    'incidents': record_map(Incident, 'I', 'incident_id'),
    'timeline': record_map(Timeline, 'T', 'timeline_id'),
    'parties': record_map(Party, 'P', 'party_id'),
    'relationships': TypeAdapter(dict[str, Relationship]).validate_python,
    'evidence_mapping': EvidenceMapping.model_validate,
    'clarification': Clarification.model_validate,
    'reconciliation': Reconciliation.model_validate,
    'domain_classification': Domain.model_validate,
}


from .understanding import CaseQuestion
VALIDATORS['case_issues'] = TypeAdapter(dict[str, CaseQuestion]).validate_python
