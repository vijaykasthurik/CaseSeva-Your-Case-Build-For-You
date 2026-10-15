from typing import Literal, Any, Optional
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


class OpposingArgument(BaseModel):
    argument_id: str
    perspective: str = "OPPOSING_PARTY"
    title: str
    summary: str
    issue_id: Optional[str] = None
    target_facts: list[str] = Field(default_factory=list)
    target_evidence: list[str] = Field(default_factory=list)
    counter_propositions: list[str] = Field(default_factory=list)
    provision_ids: list[str] = Field(default_factory=list)


class FactualWeakness(BaseModel):
    weakness_id: str
    description: str
    fact_ids: list[str] = Field(default_factory=list)
    severity: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    clarification_suggested: Optional[str] = None


class EvidenceGap(BaseModel):
    gap_id: str
    description: str
    related_issue_id: Optional[str] = None
    affected_facts: list[str] = Field(default_factory=list)
    suggested_evidence: list[str] = Field(default_factory=list)


class Contradiction(BaseModel):
    contradiction_id: str
    description: str
    conflicting_statements: list[str] = Field(default_factory=list)
    source_facts: list[str] = Field(default_factory=list)
    resolution_path: Optional[str] = None


class ProceduralRisk(BaseModel):
    risk_id: str
    category: str = "GENERAL"
    description: str
    statutory_basis: Optional[str] = None
    mitigation: Optional[str] = None


class AlternativeInterpretation(BaseModel):
    interpretation_id: str
    description: str
    competing_narrative: str
    vulnerable_claims: list[str] = Field(default_factory=list)


class IssueChallenge(BaseModel):
    issue_id: str
    question: str
    category: str = "FACTUAL_DISPUTE"
    readiness: Literal["Well supported", "Partially supported", "Thin", "Unresolved"] = "Partially supported"
    opposing_argument: str = ""
    supporting_facts: list[str] = Field(default_factory=list)
    weakening_facts: list[str] = Field(default_factory=list)
    evidence_supporting: list[str] = Field(default_factory=list)
    evidence_missing: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    preparation_needs: list[str] = Field(default_factory=list)


class CaseChallengeReport(BaseModel):
    engine2_run_id: str
    case_id: str
    engine1_case_file_version: int
    requested_by_actor_id: str
    requested_by_role: str = "citizen"
    created_at: str
    version: int = 1
    status: Literal["COMPLETED", "PARTIAL", "FAILED"] = "COMPLETED"
    challenge_perspectives: list[str] = Field(default_factory=list)
    opposing_arguments: list[OpposingArgument] = Field(default_factory=list)
    factual_weaknesses: list[FactualWeakness] = Field(default_factory=list)
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    procedural_risks: list[ProceduralRisk] = Field(default_factory=list)
    alternative_interpretations: list[AlternativeInterpretation] = Field(default_factory=list)
    unresolved_assumptions: list[str] = Field(default_factory=list)
    legal_authority_limitations: list[str] = Field(default_factory=list)
    questions_for_citizen_or_advocate: list[str] = Field(default_factory=list)
    preparation_actions: list[str] = Field(default_factory=list)
    issue_challenges: list[IssueChallenge] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    def to_legacy_dict(self) -> dict[str, Any]:
        """Projects challenge report into legacy engine2 structure for seamless overview compatibility."""
        readiness_items = [
            {
                "issue_id": ic.issue_id,
                "level": ic.readiness,
                "reasons": [ic.opposing_argument] if ic.opposing_argument else ["Factual review indicated."],
                "evidence_ids": ic.evidence_supporting,
                "provision_ids": [],
                "improvements": ic.preparation_needs or ["Provide supporting documents."],
            }
            for ic in self.issue_challenges
        ]
        unresolved_risks = [r.description for r in self.procedural_risks] + list(self.unresolved_assumptions)
        document_requests = [
            {
                "request_id": eg.gap_id,
                "description": eg.description,
                "affected_stages": ["EVIDENCE_CHALLENGER"],
                "resolved": False,
            }
            for eg in self.evidence_gaps
        ]
        objections = [
            {
                "objection_id": oa.argument_id,
                "text": oa.summary,
                "fact_ids": oa.target_facts,
                "evidence_ids": oa.target_evidence,
                "provision_ids": oa.provision_ids,
            }
            for oa in self.opposing_arguments
        ]
        points = [
            {
                "text": f"Issue: {ic.question}",
                "fact_ids": ic.supporting_facts,
                "evidence_ids": ic.evidence_supporting,
                "provision_ids": [],
            }
            for ic in self.issue_challenges
        ]
        return {
            "version": self.version,
            "engine2_run_id": self.engine2_run_id,
            "run_id": self.engine2_run_id,
            "case_file_version": self.engine1_case_file_version,
            "engine1_case_file_version": self.engine1_case_file_version,
            "overview_ready": True,
            "created_at": self.created_at,
            "status": self.status,
            "challenge_perspectives": self.challenge_perspectives,
            "opposing_arguments": [oa.model_dump() for oa in self.opposing_arguments],
            "factual_weaknesses": [fw.model_dump() for fw in self.factual_weaknesses],
            "evidence_gaps": [eg.model_dump() for eg in self.evidence_gaps],
            "contradictions": [c.model_dump() for c in self.contradictions],
            "procedural_risks": [pr.model_dump() for pr in self.procedural_risks],
            "alternative_interpretations": [ai.model_dump() for ai in self.alternative_interpretations],
            "unresolved_assumptions": self.unresolved_assumptions,
            "legal_authority_limitations": self.legal_authority_limitations,
            "questions_for_citizen_or_advocate": self.questions_for_citizen_or_advocate,
            "preparation_actions": self.preparation_actions,
            "issue_challenges": [ic.model_dump() for ic in self.issue_challenges],
            "provenance": self.provenance,
            # Legacy sub-dictionaries for overview compatibility:
            "neutral_evaluation": {
                "issue_readiness": readiness_items,
                "unresolved_risks": unresolved_risks,
                "advocate_review_points": self.questions_for_citizen_or_advocate,
                "foundation_flags": [{"flag": lim} for lim in self.legal_authority_limitations],
            },
            "evidence_challenger": {
                "attacks": [fw.description for fw in self.factual_weaknesses],
                "document_requests": document_requests,
            },
            "opponent_counsel": {
                "objections": objections,
            },
            "claimant_counsel": {
                "points": points,
            },
            "rebuttal": {
                "rebuttals": [],
            },
        }
