from pydantic import BaseModel, Field


class EvidenceQuote(BaseModel):
    evidence_id: str
    quote: str


class Fact(BaseModel):
    fact_id: str
    text: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = []
    evidence_quotes: list[EvidenceQuote] = []
    human_corrected: bool = False
    removed: bool = False
    incident_id: str | None = None


class Incident(BaseModel):
    incident_id: str
    description: str
    fact_ids: list[str] = []


class TimelineEvent(BaseModel):
    event_id: str
    date: str
    date_uncertain: bool = False
    description: str
    fact_ids: list[str] = []
    evidence_ids: list[str] = []
    human_corrected: bool = False


class Parties(BaseModel):
    client_role: str
    opposite_party: str
    relationship: str
    human_corrected: bool = False
    witnesses: list[dict[str, str]] = []
    authorities: list[dict[str, str]] = []


class IntakeOutput(BaseModel):
    normalized_story: str
    evidence_text: list[dict[str, str]]


class FactExtractionOutput(BaseModel):
    facts: list[Fact]
    incidents: list[Incident] = []


class TimelineOutput(BaseModel):
    timeline: list[TimelineEvent]
    gaps: list[str] = []


class PartyOutput(BaseModel):
    parties: Parties
