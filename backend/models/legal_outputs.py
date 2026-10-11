"""Persisted legal contracts, including the human-resolution write boundary."""
from typing import Literal
from pydantic import Field, TypeAdapter
from .understanding import Strict, Domain
from .legal_foundation import IssueCandidate, Selection, LawApplication


class StoredIssue(IssueCandidate):
    legal_issue_id: str = Field(pattern=r'^L[0-9]{3,}$')
    status: Literal['PENDING_SOURCE']
    source_dependencies: list[str]
    temporal_dependency: str
    jurisdiction_dependency: str
    limitation_dependency: str | None
    review_state: Literal['ADVOCATE_REVIEW_REQUIRED']
    superseded: bool
    fingerprint: str
    version: int = Field(ge=1)


class StoredSelection(Selection):
    domain: Domain
    dependencies: list[str]
    status: Literal['SELECTED']


class Team(Strict):
    primary_domain: Domain
    selected: dict[str, StoredSelection]
    skipped: dict[str, str]
    optional: dict[Literal['LIMITATION', 'PRECEDENT_RETRIEVAL'], bool]
    optional_reason: str
    secondary_reason: str | None
    blocked: list[str]
    execution_id: str


class StoredApplication(LawApplication):
    source_version: str
    authority_state: Literal['SOURCE_VERIFIED']
    applicability_state: Literal['ADVOCATE_REVIEW_REQUIRED']


class Applications(Strict):
    issue_id: str
    status: Literal['SOURCE_VERIFIED', 'PENDING_SOURCE', 'REVIEW_REQUIRED']
    applications: list[StoredApplication]
    unknowns: list[str]


class CitationDecision(Strict):
    source_id: str
    version_id: str
    status: Literal['VERIFIED', 'PENDING', 'REJECTED', 'OUTDATED', 'NOT_APPLICABLE']
    reason: str


class Citations(Strict):
    issue_id: str
    decisions: list[CitationDecision]


def validate_issues(value):
    issues = TypeAdapter(dict[str, StoredIssue]).validate_python(value)
    for key, issue in issues.items():
        if key != issue.legal_issue_id:
            raise ValueError('Legal issue identity mismatch')
    return value


def validate_team(value):
    team = Team.model_validate(value)
    if not team.selected or any(k != v.agent for k, v in team.selected.items()):
        raise ValueError('Team identity mismatch')
    return value
