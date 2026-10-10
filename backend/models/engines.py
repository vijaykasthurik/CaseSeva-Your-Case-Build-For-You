from typing import Literal, Any
from pydantic import BaseModel, Field
from .analysis import Fact, TimelineEvent, Parties


class Intake(BaseModel):
    narrative: str
    uncertainties: list[str] = Field(default_factory=list)


class EvidenceIndex(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class MissingInformation(BaseModel):
    questions: list[str] = Field(default_factory=list)


class ClarificationQuestion(BaseModel):
    question_id: str
    incident_id: str
    question: str
    control: Literal["short_text", "date", "month", "single_choice", "upload"] = "short_text"
    choices: list[str] = Field(default_factory=list)
    legal_reason: str


class ClarificationOutput(BaseModel):
    questions: list[ClarificationQuestion] = Field(default_factory=list, max_length=12)


class ReconciliationOutput(BaseModel):
    facts: list[Fact]
    timeline: list[TimelineEvent]
    parties: Parties
    changes: list[str]


class Routing(BaseModel):
    domains: list[str] = Field(default_factory=list)
    reasoning: str
    requires_review: bool = False


class ReadinessItem(BaseModel):
    issue_id: str
    level: Literal["Well supported", "Partially supported", "Thin", "Unresolved"]
    reasons: list[str]
    evidence_ids: list[str] = Field(default_factory=list)
    provision_ids: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


class Evaluation(BaseModel):
    issue_readiness: list[ReadinessItem]
    unresolved_risks: list[str]
    advocate_review_points: list[str]
    foundation_flags: list[dict[str, Any]] = Field(default_factory=list)


class DraftSection(BaseModel):
    heading: str
    paragraphs: list[str]
    fact_ids: list[str] = Field(default_factory=list)
    provision_ids: list[str] = Field(default_factory=list)


class DraftOutput(BaseModel):
    title: str
    sections: list[DraftSection]
    cited_provision_ids: list[str]
    annexure_references: list[str]


class ArgumentPoint(BaseModel):
    text: str
    fact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    provision_ids: list[str] = Field(default_factory=list)


class Counsel(BaseModel):
    points: list[ArgumentPoint]


class ObjectionPoint(ArgumentPoint):
    objection_id: str


class Opponent(BaseModel):
    objections: list[ObjectionPoint]


class Reply(ArgumentPoint):
    objection_id: str
    resolution: str


class Replies(BaseModel):
    rebuttals: list[Reply]


ENGINE1_STAGES = ["INTAKE_CLEANING", "EVIDENCE_INDEXING", "FACT_EXTRACTION", "TIMELINE_CONSTRUCTION", "PARTY_IDENTIFICATION", "MISSING_INFORMATION", "RECONCILIATION", "DOMAIN_ROUTER", "LEGAL_ISSUE_IDENTIFICATION", "STATUTE_RETRIEVAL", "CITATION_VERIFICATION", "TEMPORAL_LAW_CHECK", "JURISDICTION_FORUM", "LIMITATION_CHECK", "EVIDENCE_ISSUE_MAPPING", "CASE_FILE_ASSEMBLY"]
ENGINE2_STAGES = ["CLAIMANT_COUNSEL", "OPPONENT_COUNSEL", "EVIDENCE_CHALLENGER", "REBUTTAL", "NEUTRAL_EVALUATION", "OVERVIEW_BUILDER"]
