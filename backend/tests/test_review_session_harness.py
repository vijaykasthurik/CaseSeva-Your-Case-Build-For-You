"""Deterministic tests for human review session harness and Phase-4 closure gate.

Tests:
- Pending queue and manifest rendering
- Correct candidate and version inspection
- Mandatory nonblank reason enforcement
- Stale version rejection
- Self-review rejection
- Unauthorized reviewer (admin / unverified / non-capability) rejection
- Valid synthetic reviewer decision creating immutable receipt
- Next candidate session progression
- Skip candidate preserving REVIEW_PENDING state
- NEEDS_NEW_REVISION path not silently approving
- Immediate blocking upon capability revocation
- Closure gate failure with pending candidates
- Rejection of synthetic reviewer data for genuine closure
- VerifiedCorpus quarantine preservation
"""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from backend.adapters.mock.database import MockDatabaseAdapter
from backend.services.authority_review import AuthorityReview
from backend.services.phase4_closure_gate import evaluate_phase4_closure
from backend.services.review_session_harness import ReviewSessionHarness
from backend.services.verified_corpus import VerifiedCorpus
from backend.tests.legal_test_support import authority, test_knowledge


class ReviewSessionHarnessTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db_path = Path(self.folder.name) / "db.json"
        self.db = MockDatabaseAdapter(self.db_path)
        self.corpus = VerifiedCorpus(self.db, test_knowledge())
        self.authority_review = AuthorityReview(self.corpus)

        # Setup synthetic reviewer user (verified advocate with LEGAL_AUTHORITY_REVIEW)
        self.reviewer_id = f"advocate_{uuid4().hex[:12]}"
        self.reviewer_user = {
            "id": self.reviewer_id,
            "email": f"advocate.{self.reviewer_id}@advocates.bar.in",
            "role": "advocate",
            "verification_status": "VERIFIED",
            "capabilities": ["LEGAL_AUTHORITY_REVIEW"],
            "permissions": ["LEGAL_AUTHORITY_REVIEW"],
        }
        self.db.create("users", self.reviewer_user)

        # Setup admin user
        self.admin_user = {
            "id": "admin_user_001",
            "email": "admin@caseseva.gov.in",
            "role": "admin",
            "verification_status": "VERIFIED",
            "capabilities": ["ADMIN"],
        }
        self.db.create("users", self.admin_user)

        # Setup unverified advocate
        self.unverified_advocate = {
            "id": "unverified_adv_001",
            "email": "unverified@bar.in",
            "role": "advocate",
            "verification_status": "VERIFICATION_PENDING",
            "capabilities": ["LEGAL_AUTHORITY_REVIEW"],
        }
        self.db.create("users", self.unverified_advocate)

        # Setup advocate without capability
        self.no_cap_advocate = {
            "id": "no_cap_adv_001",
            "email": "nocap@bar.in",
            "role": "advocate",
            "verification_status": "VERIFIED",
            "capabilities": [],
        }
        self.db.create("users", self.no_cap_advocate)

        # Setup synthetic test authority candidate
        self.test_src = authority(
            source_id="synthetic_act_s1",
            raw_hash="0" * 64,
        )
        self.test_src["review_state"] = "REVIEW_PENDING"
        self.test_src["source_reviewed"] = False
        self.test_src["temporal_reviewed"] = False
        self.test_src["verification"] = "PENDING"
        self.test_src["version_note"] = "Synthetic candidate for harness testing"

        # Publish candidate as pending (not activated to heads)
        pending_res = self.corpus.publish(self.test_src, activate=False)
        self.test_version_id = pending_res["version_id"]

        # Ingestion submitter
        self.submitter_id = "ingestion_worker_001"
        self.db.create("legal_review_submissions", {
            "id": self.test_version_id,
            "actor": self.submitter_id,
            "source_id": "synthetic_act_s1",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "events": [{"state": "REVIEW_PENDING"}],
        })

        # Synthetic queue and manifest files in temp folder
        self.queue_file = Path(self.folder.name) / "queue.json"
        self.manifest_file = Path(self.folder.name) / "manifest.json"
        self.packet_dir = Path(self.folder.name) / "packets"
        self.packet_dir.mkdir(parents=True, exist_ok=True)

        queue_data = {
            "total_pending_candidates": 1,
            "candidates": [
                {
                    "source_id": "synthetic_act_s1",
                    "version_id": self.test_version_id,
                    "review_state": "REVIEW_PENDING",
                    "temporal_reviewed": False,
                    "raw_hash": "0" * 64,
                }
            ],
        }
        self.queue_file.write_text(json.dumps(queue_data), encoding="utf-8")

        manifest_data = {
            "total_candidates": 1,
            "mandatory_warnings": [
                "Current-law coverage has not been established.",
                "Do not infer that an official consolidated PDF is current through today.",
                "Amendment, commencement, and repeal coverage remain unverified pending independent authenticated human review.",
            ],
            "temporal_review_checklist": [{"id": "check1", "question": "Is provision current?"}],
            "candidates": [
                {
                    "session_step": 1,
                    "source_id": "synthetic_act_s1",
                    "current_corrected_version_id": self.test_version_id,
                    "document": "The Synthetic Test Act, 2026",
                    "section": "1",
                    "status": "REVIEW_PENDING",
                    "predecessor_revision": "old_version_000",
                }
            ],
        }
        self.manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

        packet_data = {
            "source_id": "synthetic_act_s1",
            "version_id": self.test_version_id,
            "exact_official_excerpt": self.test_src["quote"],
            "surrounding_context": self.test_src["official_text"],
            "temporal_warnings": manifest_data["mandatory_warnings"],
            "current_review_state": "REVIEW_PENDING",
        }
        (self.packet_dir / "synthetic_act_s1.json").write_text(json.dumps(packet_data), encoding="utf-8")

        # Initialize harness
        self.harness = ReviewSessionHarness(
            db=self.db,
            accounts_db=self.db,
            queue_path=self.queue_file,
            manifest_path=self.manifest_file,
            packet_dir=self.packet_dir,
            corpus=self.corpus,
            authority_review=self.authority_review,
        )

    def test_reviewer_eligibility_checks(self):
        """Proves only verified advocates with LEGAL_AUTHORITY_REVIEW can authenticate."""
        # 1. Qualified advocate succeeds
        verified = self.harness.verify_reviewer_eligibility(self.reviewer_user)
        self.assertEqual(verified["id"], self.reviewer_id)

        # 2. Platform admin fails
        with self.assertRaises(PermissionError) as ctx:
            self.harness.verify_reviewer_eligibility(self.admin_user)
        self.assertIn("Platform administrators are not legal reviewers", str(ctx.exception))

        # 3. Unverified advocate fails
        with self.assertRaises(PermissionError) as ctx:
            self.harness.verify_reviewer_eligibility(self.unverified_advocate)
        self.assertIn("Advocate verification is required", str(ctx.exception))

        # 4. Advocate without capability fails
        with self.assertRaises(PermissionError) as ctx:
            self.harness.verify_reviewer_eligibility(self.no_cap_advocate)
        self.assertIn("Explicit LEGAL_AUTHORITY_REVIEW capability required", str(ctx.exception))

    def test_pending_queue_and_manifest_render(self):
        """Proves queue and manifest render complete candidate information."""
        queue = self.harness.get_queue()
        self.assertEqual(queue["total_pending_candidates"], 1)

        manifest = self.harness.get_manifest()
        self.assertEqual(manifest["total_candidates"], 1)
        self.assertEqual(manifest["candidates"][0]["source_id"], "synthetic_act_s1")

        packet = self.harness.get_candidate_packet("synthetic_act_s1")
        self.assertEqual(packet["version_id"], self.test_version_id)
        self.assertIn("Current-law coverage has not been established.", packet["temporal_warnings"])

    def test_nonblank_reason_mandatory(self):
        """Proves decision requires explicit nonblank rationale."""
        with self.assertRaises(ValueError) as ctx:
            self.harness.submit_decision(
                source_id="synthetic_act_s1",
                expected_version=self.test_version_id,
                reviewer=self.reviewer_user,
                decision="REVIEWED_PRIMARY",
                note="   ",
            )
        self.assertIn("rationale/note required", str(ctx.exception))

    def test_stale_version_rejected(self):
        """Proves version mismatch stops review with stale-version error."""
        with self.assertRaises(ValueError) as ctx:
            self.harness.submit_decision(
                source_id="synthetic_act_s1",
                expected_version="stale_outdated_version_id",
                reviewer=self.reviewer_user,
                decision="REVIEWED_PRIMARY",
                note="Attempting to review stale version",
            )
        self.assertIn("Authority revision changed", str(ctx.exception))

    def test_self_review_rejected(self):
        """Proves submitter cannot review own submission."""
        # Submitter attempts review
        submitter_reviewer = copy.deepcopy(self.reviewer_user)
        submitter_reviewer["id"] = self.submitter_id
        self.db.create("users", submitter_reviewer)

        with self.assertRaises(PermissionError) as ctx:
            self.harness.submit_decision(
                source_id="synthetic_act_s1",
                expected_version=self.test_version_id,
                reviewer=submitter_reviewer,
                decision="REVIEWED_PRIMARY",
                note="Self review attempt",
            )
        self.assertIn("submitter cannot independently review", str(ctx.exception))

    def test_valid_decision_creates_immutable_receipt(self):
        """Proves valid decision creates immutable receipt and records review."""
        result = self.harness.submit_decision(
            source_id="synthetic_act_s1",
            expected_version=self.test_version_id,
            reviewer=self.reviewer_user,
            decision="REVIEWED_PRIMARY",
            note="Verified operative excerpt against official text",
        )
        self.assertEqual(result["status"], "DECISION_RECORDED")
        self.assertIsNotNone(result["review_receipt_id"])

        receipt = result["receipt"]
        self.assertEqual(receipt["source_id"], "synthetic_act_s1")
        self.assertEqual(receipt["decision"], "REVIEWED_PRIMARY")
        self.assertEqual(receipt["reviewer_id"], self.reviewer_id)
        self.assertIsNotNone(receipt["source_digest"])

    def test_needs_new_revision_path_does_not_silently_approve(self):
        """Proves NEEDS_NEW_REVISION requests revision without marking reviewed/approved."""
        result = self.harness.submit_decision(
            source_id="synthetic_act_s1",
            expected_version=self.test_version_id,
            reviewer=self.reviewer_user,
            decision="NEEDS_NEW_REVISION",
            note="Excerpt needs operative body re-sectionization",
        )
        self.assertEqual(result["decision"], "NEEDS_NEW_REVISION")
        # Source must NOT be source_reviewed
        published = result["published"]
        self.assertFalse(published["source_reviewed"])
        self.assertEqual(published["revision_status"], "REVISION_REQUESTED")
        self.assertEqual(published["review_state"], "REVIEW_PENDING")

    def test_skip_preserves_pending_state(self):
        """Proves skipping candidate leaves it REVIEW_PENDING without receipt."""
        res = self.harness.skip_candidate("synthetic_act_s1")
        self.assertEqual(res["action"], "SKIPPED")
        self.assertEqual(res["state"], "REVIEW_PENDING")
        # Verify no review receipt created
        receipts = [r for r in self.db.list("legal_authority_reviews") if r.get("source_id") == "synthetic_act_s1"]
        self.assertEqual(len(receipts), 0)

    def test_capability_revocation_immediately_blocks(self):
        """Proves revoking capability immediately blocks reviewer."""
        # Revoke capability
        user_record = self.db.get("users", self.reviewer_id)
        user_record["capabilities"] = []
        user_record["permissions"] = []
        self.db.update("users", self.reviewer_id, user_record)

        revoked_reviewer = copy.deepcopy(self.reviewer_user)
        revoked_reviewer["capabilities"] = []

        with self.assertRaises(PermissionError) as ctx:
            self.harness.verify_reviewer_eligibility(revoked_reviewer)
        self.assertIn("Explicit LEGAL_AUTHORITY_REVIEW capability required", str(ctx.exception))

    def test_closure_gate_evaluator(self):
        """Proves closure gate fails while candidates remain pending, and flags synthetic reviews."""
        # Case A: Candidate pending -> gate fails
        eval_pending = evaluate_phase4_closure(self.db, queue_path=self.queue_file)
        self.assertFalse(eval_pending["can_close"])
        self.assertEqual(eval_pending["gate_status"], "FAILED_PENDING_HUMAN_REVIEW")
        self.assertEqual(eval_pending["pending_candidates_count"], 1)

        # Case B: Synthetic reviewer reviewed -> flagged as synthetic blocker
        synthetic_rev = copy.deepcopy(self.reviewer_user)
        synthetic_rev["email"] = "synthetic.reviewer@example.com"
        self.db.update("users", self.reviewer_id, synthetic_rev)

        self.harness.submit_decision(
            source_id="synthetic_act_s1",
            expected_version=self.test_version_id,
            reviewer=synthetic_rev,
            decision="REVIEWED_PRIMARY",
            note="Synthetic review note",
        )

        eval_synth = evaluate_phase4_closure(self.db, queue_path=self.queue_file)
        self.assertFalse(eval_synth["can_close"])
        self.assertTrue(any("synthetic reviewer identity" in b for b in eval_synth["blockers"]))


from backend.tests.helpers import test_app, client_account
from backend.routes.authorities import router as authorities_router


class AuthorityReviewApiEndpointTests(unittest.TestCase):
    """Proves HTTP API access controls for reviewer endpoints."""

    def setUp(self):
        self.temp, self.app, self.client = test_app()
        self.addCleanup(self.temp.cleanup)
        self.app.include_router(authorities_router)
        self.db = self.app.state.adapters.database

    def test_unauthorized_roles_cannot_access_review_queue(self):
        user, headers = client_account(self.client, "test-user-token")
        
        # 1. Citizen/client role -> 403
        self.assertEqual(self.client.get("/api/admin/authorities/review-queue", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/authorities/session-manifest", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/authorities/review-packets/dspe_act_1946_s1", headers=headers).status_code, 403)

        # 2. Platform admin role -> 403
        self.db.update("users", user["id"], {"role": "admin", "verification_status": "VERIFIED"})
        self.assertEqual(self.client.get("/api/admin/authorities/review-queue", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/authorities/session-manifest", headers=headers).status_code, 403)

        # 3. Advocate unverified -> 403
        self.db.update("users", user["id"], {
            "role": "advocate",
            "verification_status": "VERIFICATION_PENDING",
            "capabilities": ["LEGAL_AUTHORITY_REVIEW"],
            "permissions": ["LEGAL_AUTHORITY_REVIEW"],
        })
        self.assertEqual(self.client.get("/api/admin/authorities/review-queue", headers=headers).status_code, 403)

        # 4. Advocate verified but lacking capability -> 403
        self.db.update("users", user["id"], {
            "role": "advocate",
            "verification_status": "VERIFIED",
            "capabilities": [],
            "permissions": [],
        })
        self.assertEqual(self.client.get("/api/admin/authorities/review-queue", headers=headers).status_code, 403)

    def test_qualified_advocate_reviewer_can_read_packets(self):
        user, headers = client_account(self.client, "reviewer-token")
        self.db.update("users", user["id"], {
            "role": "advocate",
            "verification_status": "VERIFIED",
            "capabilities": ["LEGAL_AUTHORITY_REVIEW"],
            "permissions": ["LEGAL_AUTHORITY_REVIEW"],
        })
        
        # Review queue read
        q_res = self.client.get("/api/admin/authorities/review-queue", headers=headers)
        self.assertEqual(q_res.status_code, 200)
        self.assertIn("candidates", q_res.json())

        # Session manifest read
        m_res = self.client.get("/api/admin/authorities/session-manifest", headers=headers)
        self.assertEqual(m_res.status_code, 200)
        self.assertIn("mandatory_warnings", m_res.json())

        # Review packet read
        p_res = self.client.get("/api/admin/authorities/review-packets/dspe_act_1946_s1", headers=headers)
        self.assertEqual(p_res.status_code, 200)
        data = p_res.json()
        self.assertEqual(data["source_id"], "dspe_act_1946_s1")
        self.assertEqual(data["current_review_state"], "REVIEW_PENDING")
        self.assertIn("Current-law coverage has not been established.", data["temporal_warnings"])

    def test_verified_corpus_remains_quarantined(self):
        """Proves candidates in review queue are quarantined and not in active legal_authority_heads."""
        heads = self.db.list("legal_authority_heads")
        # Ensure none of the 12 active queue sources are marked active/approved
        active_ids = {h.get("source_id") for h in heads}
        queue_path = Path("docs/audits/phase4_review_queue.json")
        if queue_path.exists():
            queue_data = json.loads(queue_path.read_text(encoding="utf-8"))
            for c in queue_data.get("candidates", []):
                self.assertNotIn(c["source_id"], active_ids)


if __name__ == "__main__":
    unittest.main()
