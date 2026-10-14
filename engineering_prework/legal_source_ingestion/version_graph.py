"""Generic version and amendment relationship graph for Indian enactments and subordinate law.

Maintains immutable provenance links:
ACT <- amended_by -> AMENDMENT_ACT
    <- corrected_by -> CORRIGENDUM
    <- commenced_by -> NOTIFICATION
    <- supplemented_by -> RULE / REGULATION
    <- interpreted_by -> JUDGMENT
"""
from typing import Any
from .models import VersionRelationship, RelationshipType, AuthorityType


class VersionGraph:
    """Directed relationship graph tracking amendment, commencement, and interpretation lineages."""

    def __init__(self):
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[VersionRelationship] = []

    def add_node(
        self,
        document_id: str,
        title: str,
        authority_type: AuthorityType,
        official_url: str,
        enactment_date: str | None = None,
        effective_from: str | None = None,
        effective_until: str | None = None,
        raw_hash: str = "",
    ):
        self.nodes[document_id] = {
            "document_id": document_id,
            "title": title,
            "authority_type": authority_type,
            "official_url": official_url,
            "enactment_date": enactment_date,
            "effective_from": effective_from,
            "effective_until": effective_until,
            "raw_hash": raw_hash,
        }

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship: RelationshipType,
        evidence_url: str,
        evidence_text: str,
        commencement_date: str | None = None,
        repeal_date: str | None = None,
        supported_through_date: str | None = None,
        unresolved_coverage: list[str] | None = None,
        verified: bool = False,
    ) -> VersionRelationship:
        edge = VersionRelationship(
            source_id=source_id,
            target_id=target_id,
            relationship=relationship,
            evidence_url=evidence_url,
            evidence_text=evidence_text,
            commencement_date=commencement_date,
            repeal_date=repeal_date,
            supported_through_date=supported_through_date,
            unresolved_coverage=unresolved_coverage or [],
            verified=verified,
        )
        self.edges.append(edge)
        return edge

    def get_amendments(self, document_id: str) -> list[VersionRelationship]:
        return [e for e in self.edges if e.target_id == document_id and e.relationship == RelationshipType.AMENDED_BY]

    def get_commencements(self, document_id: str) -> list[VersionRelationship]:
        return [e for e in self.edges if e.target_id == document_id and e.relationship == RelationshipType.COMMENCED_BY]

    def get_rules(self, document_id: str) -> list[VersionRelationship]:
        return [e for e in self.edges if e.target_id == document_id and e.relationship == RelationshipType.SUPPLEMENTED_BY]

    def get_interpretations(self, document_id: str) -> list[VersionRelationship]:
        return [e for e in self.edges if e.target_id == document_id and e.relationship == RelationshipType.INTERPRETED_BY]

    def is_temporally_valid_on(self, document_id: str, event_date: str) -> tuple[bool, str]:
        """Evaluates whether an enactment is in force on event_date based on known commencement and repeal dates."""
        node = self.nodes.get(document_id)
        if not node:
            return False, "ENACTMENT_NOT_FOUND"

        effective_from = node.get("effective_from")
        # No authenticated relationship review contract exists in prework. Even an
        # unchecked model_copy/model_construct flag cannot confer temporal trust.
        # Explicit node intervals remain a simulation input, not reviewed law.
        if not effective_from:
            return False, "COMMENCEMENT_DATE_UNRESOLVED"

        if event_date < effective_from:
            return False, f"PRE_COMMENCEMENT (commenced {effective_from}, event {event_date})"

        effective_until = node.get("effective_until")
        if effective_until and event_date >= effective_until:
            return False, f"REPEALED (repealed {effective_until}, event {event_date})"

        return True, "IN_FORCE"
