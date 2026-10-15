"""Safe human review session harness for Phase-4 legal authority review.

Automates technical retrieval, candidate presentation, version binding, staleness
protection, receipt creation, and queue progression while ensuring ONLY an
authenticated, verified advocate with LEGAL_AUTHORITY_REVIEW can submit decisions.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .authority_review import AuthorityReview, is_authorized_authority_reviewer
from .verified_corpus import VerifiedCorpus

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_QUEUE_PATH = ROOT / "docs" / "audits" / "phase4_review_queue.json"
DEFAULT_MANIFEST_PATH = ROOT / "docs" / "audits" / "phase4_review_session_manifest.json"
DEFAULT_PACKET_DIR = ROOT / "docs" / "audits" / "review_packets"


class ReviewSessionHarness:
    """Manages sequential human review session state, inspection, and decision submission."""

    def __init__(
        self,
        db: Any,
        accounts_db: Any = None,
        queue_path: Path | None = None,
        manifest_path: Path | None = None,
        packet_dir: Path | None = None,
        corpus: Any = None,
        authority_review: Any = None,
    ):
        self.db = db
        self.accounts_db = accounts_db or db
        self.queue_path = queue_path or DEFAULT_QUEUE_PATH
        self.manifest_path = manifest_path or DEFAULT_MANIFEST_PATH
        self.packet_dir = packet_dir or DEFAULT_PACKET_DIR
        self.corpus = corpus or VerifiedCorpus(self.db)
        self.authority_review = authority_review or AuthorityReview(self.corpus, accounts_db=self.accounts_db)

    def verify_reviewer_eligibility(self, reviewer: dict[str, Any]) -> dict[str, Any]:
        """Validates that reviewer is a verified advocate with explicit LEGAL_AUTHORITY_REVIEW capability."""
        if not reviewer or not isinstance(reviewer, dict):
            raise PermissionError("Reviewer identity required")
        reviewer_id = reviewer.get("id") or ""
        account = self.accounts_db.get("users", reviewer_id)
        if not account:
            raise PermissionError("Reviewer account not found in persisted identity database")

        if account.get("role") == "admin" or reviewer.get("role") == "admin":
            raise PermissionError(
                "Platform administrators are not legal reviewers; a verified advocate with LEGAL_AUTHORITY_REVIEW capability is required."
            )
        if account.get("role") != "advocate" or reviewer.get("role") != "advocate":
            raise PermissionError("A verified advocate with LEGAL_AUTHORITY_REVIEW capability is required.")
        if account.get("verification_status") != "VERIFIED" or reviewer.get("verification_status") != "VERIFIED":
            raise PermissionError("Advocate verification is required for legal authority review.")
        if not is_authorized_authority_reviewer(account) or not is_authorized_authority_reviewer(reviewer):
            raise PermissionError("Explicit LEGAL_AUTHORITY_REVIEW capability required.")

        return account

    def get_manifest(self) -> dict[str, Any]:
        """Loads the deterministic session manifest."""
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest file not found: {self.manifest_path}")
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def get_queue(self) -> dict[str, Any]:
        """Loads the active review queue."""
        if not self.queue_path.exists():
            raise FileNotFoundError(f"Queue file not found: {self.queue_path}")
        return json.loads(self.queue_path.read_text(encoding="utf-8"))

    def get_candidate_packet(self, source_id: str) -> dict[str, Any]:
        """Loads the inspection package for a candidate."""
        packet_file = self.packet_dir / f"{source_id}.json"
        if not packet_file.exists():
            raise FileNotFoundError(f"Review packet not found for {source_id}: {packet_file}")
        return json.loads(packet_file.read_text(encoding="utf-8"))

    def submit_decision(
        self,
        source_id: str,
        expected_version: str,
        reviewer: dict[str, Any],
        decision: str,
        note: str,
    ) -> dict[str, Any]:
        """Submits an authenticated human legal review decision.

        Enforces:
        - Reviewer capability verification (verified advocate + LEGAL_AUTHORITY_REVIEW)
        - Nonblank human reason requirement
        - Stale-version detection (stops on version mismatch, no auto-resubmit)
        - Submitter-reviewer independence
        - Immutable receipt creation
        """
        # 1. Authenticate and verify reviewer capability
        verified_account = self.verify_reviewer_eligibility(reviewer)

        # 2. Check note
        if not note or not note.strip():
            raise ValueError("Explicit human review rationale/note required")

        # 3. Check decision
        valid_decisions = {"REVIEWED_PRIMARY", "REJECTED", "STALE", "NEEDS_NEW_REVISION"}
        if decision not in valid_decisions:
            raise ValueError(f"Invalid review decision: {decision}. Must be one of {valid_decisions}")

        # 4. Check active queue version match
        queue = self.get_queue()
        active_cand = next((c for c in queue.get("candidates", []) if c.get("source_id") == source_id), None)
        if active_cand and active_cand.get("version_id") != expected_version:
            raise ValueError(
                f"Authority revision changed between display and submission (expected {expected_version}, active is {active_cand.get('version_id')}). Stop review of this candidate."
            )

        # 5. Delegate to AuthorityReview service (enforces immutability, receipt, independence)
        published = self.authority_review.decide(
            source_id=source_id,
            expected_version=expected_version,
            reviewer=verified_account,
            decision=decision,
            note=note,
        )

        # 6. Retrieve the created receipt
        receipts = [r for r in self.db.list("legal_authority_reviews") if r.get("source_id") == source_id and r.get("input_version") == expected_version]
        receipt = receipts[-1] if receipts else None

        return {
            "source_id": source_id,
            "version_id": expected_version,
            "decision": decision,
            "published": published,
            "receipt": receipt,
            "review_receipt_id": receipt.get("id") if receipt else None,
            "status": "DECISION_RECORDED",
        }

    def skip_candidate(self, source_id: str) -> dict[str, Any]:
        """Skips candidate, strictly preserving REVIEW_PENDING state."""
        return {
            "source_id": source_id,
            "action": "SKIPPED",
            "state": "REVIEW_PENDING",
            "message": "Candidate skipped; remains REVIEW_PENDING without approval or receipt",
        }
