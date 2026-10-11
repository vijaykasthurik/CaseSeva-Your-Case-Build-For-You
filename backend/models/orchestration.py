"""Control-plane contracts. These schemas do not implement legal reasoning."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Status = Literal["WAITING", "READY", "RUNNING", "COMPLETED", "NEEDS_USER_INPUT",
                 "NEEDS_DOCUMENT", "CONFLICT_FOUND", "REVIEW_REQUIRED", "FAILED",
                 "STALE", "SKIPPED", "BLOCKED", "NOT_IMPLEMENTED"]
Verification = Literal["CANDIDATE", "PENDING", "VERIFIED", "REJECTED", "OUTDATED", "NOT_APPLICABLE"]


class Condition(BaseModel):
    path: str
    operator: Literal["exists", "equals"] = "exists"
    value: Any = None


class AgentContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    agent_type: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    engine: Literal[0, 1, 2, 3]
    purpose: str = Field(min_length=1)
    required_inputs: tuple[str, ...] = ()
    optional_inputs: tuple[str, ...] = ()
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    conditions: tuple[Condition, ...] = ()
    pack: str | None = None
    can_run_concurrently: bool = False
    timeout_seconds: float = Field(default=60, gt=0, le=900)
    retry_policy: Literal["transient_only", "never"] = "transient_only"
    max_retries: int = Field(default=2, ge=0, le=5)
    retry_delay_seconds: float = Field(default=1, ge=0, le=300)
    idempotency: Literal["case_agent_versions_action"] = "case_agent_versions_action"
    stale_on: tuple[str, ...] = ()
    requires_human_review: bool = False
    failure_behavior: Literal["block_dependents"] = "block_dependents"
    supported_languages: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    visibility: Literal["INTERNAL", "ADVOCATE_INTERNAL"] = "INTERNAL"

    @model_validator(mode="after")
    def validate_paths(self):
        import re
        paths = self.reads + self.writes + self.required_inputs + self.optional_inputs + self.stale_on
        paths += tuple(c.path for c in self.conditions)
        if any(not re.fullmatch(r"[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*", p) for p in paths):
            raise ValueError("Invalid Blackboard path")
        if len(set(self.writes)) != len(self.writes):
            raise ValueError("Duplicate output paths")
        if any(a != b and b.startswith(a + ".") for a in self.writes for b in self.writes):
            raise ValueError("Overlapping output paths")
        if any(p.split('.')[0] in {"identity", "input"} for p in self.writes):
            raise ValueError("Input and identity are owned by the input bridge")
        return self

    def watched_paths(self):
        return tuple(sorted(set(self.reads + self.required_inputs + self.optional_inputs + self.stale_on
                                + tuple(c.path for c in self.conditions))))


class AgentResult(BaseModel):
    status: Literal["COMPLETED", "NEEDS_USER_INPUT", "NEEDS_DOCUMENT", "REVIEW_REQUIRED", "CONFLICT_FOUND", "BLOCKED"]
    outputs: dict[str, Any] = Field(default_factory=dict)
    requests: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None


class SourcedRecord(BaseModel):
    """Shared provenance metadata for future typed legal agents; empty until produced."""
    source_refs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    actor: str | None = None
    extraction_agent: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    review_state: str = "PENDING"
    verification: Verification = "PENDING"
    advocate_approved: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    version: int = 1
    stale: bool = False


class FactRecord(SourcedRecord):
    fact_id: str
    statement: str
    normalized: dict[str, Any] = Field(default_factory=dict)
    original_wording: str | None = None


class IncidentRecord(SourcedRecord):
    incident_id: str
    event: str
    party_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    date_time: str | None = None
    date_certainty: str = "UNKNOWN"
    location: str | None = None
    conflicts: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class TimelineRecord(IncidentRecord):
    timeline_id: str
    date_end: str | None = None


class PartyRecord(SourcedRecord):
    party_id: str
    name: str | None = None
    role: str | None = None
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)


class IssueRecord(SourcedRecord):
    issue_id: str
    statement: str
    supporting_facts: list[str] = Field(default_factory=list)
    contradicting_facts: list[str] = Field(default_factory=list)
    legal_dependencies: list[str] = Field(default_factory=list)
    temporal_dependency: str | None = None
    jurisdiction_dependency: str | None = None
    limitation_dependency: str | None = None
    status: str = "PENDING"


class LegalSourceRecord(SourcedRecord):
    source_id: str
    source_type: str
    act: str | None = None
    section: str | None = None
    rule: str | None = None
    judgment: str | None = None
    court: str | None = None
    citation: str | None = None
    official_url: str | None = None
    retrieved_at: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None
    source_hash: str | None = None
    quotation: str | None = None


class CaseFileProvenance(BaseModel):
    case_file_version: int
    board_version: int
    input_version: int
    dependency_versions: dict[str, int]
    generated_at: str
    status: Literal["CURRENT", "STALE"] = "CURRENT"
