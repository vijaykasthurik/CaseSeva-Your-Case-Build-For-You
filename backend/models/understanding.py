"""Strict language-neutral candidate schemas. Persistent IDs belong to the server."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Domain = Literal["CONSUMER", "LABOUR_EMPLOYMENT", "PROPERTY_TENANCY", "CRIMINAL_POLICE", "CIVIL_CONTRACT", "RTI_ADMINISTRATIVE", "OTHER_OR_UNCERTAIN"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSpan(Strict):
    passage: int = Field(ge=0)
    excerpt: str = Field(min_length=1, max_length=2500)


class LanguageAssessment(Strict):
    detected_languages: list[str] = Field(min_length=1, max_length=12)
    supported: bool
    review_reason: str | None = None


class Dated(Strict):
    expression: str | None = None
    precision: Literal["EXACT_DATE", "MONTH_ONLY", "APPROXIMATE", "RANGE", "SEQUENCE_ONLY", "UNKNOWN"] = "UNKNOWN"
    normalized: str | None = None


class FactCandidate(Strict):
    key: str = Field(min_length=1, max_length=100)
    proposition: str = Field(min_length=1, max_length=1500)
    category: str = Field(min_length=1, max_length=80)
    sources: list[SourceSpan] = Field(min_length=1, max_length=8)
    certainty: Literal["STATED", "UNKNOWN", "CONFLICTED"] = "STATED"
    date: Dated = Field(default_factory=Dated)
    exact_values: list[str] = Field(default_factory=list, max_length=20)


class IncidentCandidate(Strict):
    key: str
    description: str = Field(max_length=1200)
    fact_keys: list[str] = Field(min_length=1, max_length=20)
    date: Dated = Field(default_factory=Dated)
    unknown_fields: list[str] = Field(default_factory=list, max_length=15)


class FactCandidates(Strict):
    language: LanguageAssessment
    facts: list[FactCandidate] = Field(max_length=60)
    incidents: list[IncidentCandidate] = Field(max_length=40)


class StageCandidates(Strict):
    language: LanguageAssessment
    stage: Literal["NEW_CONSULTATION", "COMPLAINT_OR_FIR_STAGE", "EXISTING_CASE", "ONGOING_OR_OLD_CASE", "UNKNOWN"]
    sources: list[SourceSpan] = Field(max_length=10)
    review_required: bool
    unknowns: list[str] = Field(default_factory=list, max_length=12)


class PartyCandidate(Strict):
    key: str
    name: str | None = None
    role: str = Field(max_length=100)
    fact_ids: list[str] = Field(min_length=1, max_length=20)
    sources: list[SourceSpan] = Field(min_length=1, max_length=8)
    unknown_attributes: list[str] = Field(default_factory=list, max_length=12)
    review_required: bool = True


class RelationshipCandidate(Strict):
    left_key: str
    right_key: str
    relationship: str = Field(max_length=100)
    fact_ids: list[str] = Field(min_length=1, max_length=20)


class PartyCandidates(Strict):
    language: LanguageAssessment
    parties: list[PartyCandidate] = Field(max_length=25)
    relationships: list[RelationshipCandidate] = Field(default_factory=list, max_length=40)
    ambiguity: list[str] = Field(default_factory=list, max_length=12)


class EvidenceLink(Strict):
    evidence_id: str
    fact_id: str
    relation: Literal["SUPPORTS", "CONTRADICTS", "REVIEW_REQUIRED"]
    sources: list[SourceSpan] = Field(min_length=1, max_length=6)


class EvidenceCandidates(Strict):
    language: LanguageAssessment
    links: list[EvidenceLink] = Field(default_factory=list, max_length=100)
    unresolved: list[str] = Field(default_factory=list, max_length=20)


class QuestionCandidate(Strict):
    topic: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=400)
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    essential: bool
    response_kind: Literal["DETAIL", "DOCUMENT"]
    fact_ids: list[str] = Field(default_factory=list, max_length=10)
    declaration_index: int | None = None
    affected: list[Literal["CASE_STAGE", "FACT_TIMELINE", "PARTY_RELATIONSHIP", "EVIDENCE_MAPPING", "RECONCILIATION", "DOMAIN_ROUTER"]] = Field(min_length=1, max_length=6)
    already_answered: bool = False
    material_reason: str = Field(max_length=500)


class ClarificationCandidates(Strict):
    language: LanguageAssessment
    questions: list[QuestionCandidate] = Field(default_factory=list, max_length=8)


class SourceConflict(Strict):
    fact_ids: list[str] = Field(min_length=2, max_length=8)
    field: str = Field(max_length=80)
    explanation: str = Field(max_length=500)


class ReconciliationCandidates(Strict):
    language: LanguageAssessment
    conflicts: list[SourceConflict] = Field(default_factory=list, max_length=20)
    unresolved: list[str] = Field(default_factory=list, max_length=20)


class DomainCandidates(Strict):
    language: LanguageAssessment
    primary_domain: Domain
    primary_subdomain: str = Field(max_length=100)
    secondary_domains: list[Domain] = Field(default_factory=list, max_length=3)
    fact_ids: list[str] = Field(max_length=30)
    relationship_ids: list[str] = Field(default_factory=list, max_length=30)
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    review_required: bool
    ambiguity: list[str] = Field(default_factory=list, max_length=12)
    reasons: list[str] = Field(max_length=10)
