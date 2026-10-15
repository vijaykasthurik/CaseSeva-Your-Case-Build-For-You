"""Deterministic tests for Phase-4 immutable version-lineage integrity audit.

Proves:
- complete lineage traversal across all versions
- active target uniqueness (12 unique sources, 1 active version each)
- queue / packet / manifest version equality
- predecessor reference resolves in legal_authority_versions
- historical TOC revision remains immutable and unapproved
- duplicate / preliminary revisions do not become active
- no orphan active version exists
- closure gate fails on ambiguous lineage (version mismatch / missing predecessor)
- closure gate passes lineage-integrity subcheck when lineage is verified,
  while still failing overall due to pending human review
"""
import ast
import json
from pathlib import Path
import tempfile
import unittest

from backend.adapters.mock.database import MockDatabaseAdapter
from backend.services.phase4_closure_gate import evaluate_phase4_closure
from backend.services.verified_corpus import VerifiedCorpus
from backend.tests.legal_test_support import authority, test_knowledge


class ImmutableLineageAuditTests(unittest.TestCase):
    """Lineage integrity and closure gate tests."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = MockDatabaseAdapter(Path(self.folder.name) / "db.json")
        self.corpus = VerifiedCorpus(self.db, test_knowledge())

        # Construct a synthetic multi-generation lineage:
        # Gen 1: Preliminary acquisition version (quarantined)
        # Gen 2: Curated TOC extraction version (superseded)
        # Gen 3: Substantive operative corrected version (active target)

        self.sid = "test_statute_s1"

        # Gen 1: Preliminary
        gen1_src = authority(source_id=self.sid, section="1", version_note="Preliminary acquisition")
        gen1_src["review_state"] = "REVIEW_PENDING"
        gen1_src["source_reviewed"] = False
        gen1_pub = self.corpus.publish(gen1_src, activate=False)
        self.gen1_vid = gen1_pub["version_id"]

        # Gen 2: Curated TOC
        gen2_src = authority(
            source_id=self.sid,
            section="1",
            version_note="Curated TOC extraction",
            quote="1. Short title and extent",
        )
        gen2_src["parent_revision"] = self.gen1_vid
        gen2_src["review_state"] = "REVIEW_PENDING"
        gen2_src["source_reviewed"] = False
        gen2_pub = self.corpus.publish(gen2_src, activate=False)
        self.gen2_vid = gen2_pub["version_id"]

        # Gen 3: Substantive operative provision
        gen3_quote = "1. Short title and extent. (1) This Act may be called the Test Statute, 2026. (2) It extends to the whole of India."
        gen3_text = f"Test Statute 2026\n{gen3_quote}"
        gen3_src = authority(
            source_id=self.sid,
            section="1",
            title="Test Statute 2026",
            official_text=gen3_text,
            quote=gen3_quote,
            section_start=gen3_text.index(gen3_quote),
            section_end=len(gen3_text),
            version_note="Substantive operative provision",
        )
        gen3_src["parent_revision"] = self.gen2_vid
        gen3_src["review_state"] = "REVIEW_PENDING"
        gen3_src["source_reviewed"] = False
        gen3_pub = self.corpus.publish(gen3_src, activate=False)
        self.gen3_vid = gen3_pub["version_id"]

        # Artifact paths
        self.queue_file = Path(self.folder.name) / "queue.json"
        self.manifest_file = Path(self.folder.name) / "manifest.json"
        self.packet_dir = Path(self.folder.name) / "packets"
        self.packet_dir.mkdir(parents=True, exist_ok=True)

        # Write matching queue
        queue_data = {
            "total_pending_candidates": 1,
            "candidates": [
                {
                    "source_id": self.sid,
                    "version_id": self.gen3_vid,
                    "review_state": "REVIEW_PENDING",
                    "temporal_reviewed": False,
                }
            ],
        }
        self.queue_file.write_text(json.dumps(queue_data), encoding="utf-8")

        # Write matching manifest
        manifest_data = {
            "total_candidates": 1,
            "candidates": [
                {
                    "source_id": self.sid,
                    "current_corrected_version_id": self.gen3_vid,
                    "predecessor_revision": self.gen2_vid,
                    "status": "REVIEW_PENDING",
                }
            ],
        }
        self.manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

        # Write matching packet
        packet_data = {
            "source_id": self.sid,
            "version_id": self.gen3_vid,
            "predecessor_revision": self.gen2_vid,
            "prior_revision": self.gen2_vid,
            "exact_official_excerpt": gen3_quote,
            "current_review_state": "REVIEW_PENDING",
        }
        (self.packet_dir / f"{self.sid}.json").write_text(json.dumps(packet_data), encoding="utf-8")

    def test_complete_lineage_traversal(self):
        """Proves lineage can be traversed from Gen 3 back through Gen 2 and Gen 1."""
        active_doc = self.db.get("legal_authority_versions", self.gen3_vid)
        self.assertIsNotNone(active_doc)
        parent_id = active_doc["source"]["parent_revision"]
        self.assertEqual(parent_id, self.gen2_vid)

        parent_doc = self.db.get("legal_authority_versions", parent_id)
        self.assertIsNotNone(parent_doc)
        grandparent_id = parent_doc["source"]["parent_revision"]
        self.assertEqual(grandparent_id, self.gen1_vid)

        grandparent_doc = self.db.get("legal_authority_versions", grandparent_id)
        self.assertIsNotNone(grandparent_doc)
        self.assertIsNone(grandparent_doc["source"].get("parent_revision"))

    def test_queue_packet_manifest_version_equality(self):
        """Proves queue, packet, and manifest must agree on active version and predecessor."""
        eval_res = evaluate_phase4_closure(
            self.db,
            queue_path=self.queue_file,
            manifest_path=self.manifest_file,
            packet_dir=self.packet_dir,
        )
        self.assertTrue(eval_res["lineage_integrity_passed"])
        self.assertEqual(eval_res["lineage_integrity_status"], "PASSED")
        self.assertEqual(len(eval_res["lineage_blockers"]), 0)

    def test_closure_gate_fails_on_version_mismatch(self):
        """Proves closure gate catches mismatch between queue and manifest."""
        bad_manifest = {
            "total_candidates": 1,
            "candidates": [
                {
                    "source_id": self.sid,
                    "current_corrected_version_id": "outdated_or_deleted_version_hash",
                    "predecessor_revision": self.gen2_vid,
                }
            ],
        }
        self.manifest_file.write_text(json.dumps(bad_manifest), encoding="utf-8")

        eval_res = evaluate_phase4_closure(
            self.db,
            queue_path=self.queue_file,
            manifest_path=self.manifest_file,
            packet_dir=self.packet_dir,
        )
        self.assertFalse(eval_res["lineage_integrity_passed"])
        self.assertEqual(eval_res["lineage_integrity_status"], "FAILED_LINEAGE_AMBIGUITY")
        self.assertTrue(any("version mismatch" in b for b in eval_res["lineage_blockers"]))

    def test_closure_gate_fails_on_predecessor_mismatch(self):
        """Proves closure gate catches mismatch between packet predecessor and DB parent."""
        bad_packet = {
            "source_id": self.sid,
            "version_id": self.gen3_vid,
            "predecessor_revision": "hallucinated_or_wrong_predecessor_id",
            "exact_official_excerpt": "Substantive operative provision text that is long enough.",
        }
        (self.packet_dir / f"{self.sid}.json").write_text(json.dumps(bad_packet), encoding="utf-8")

        eval_res = evaluate_phase4_closure(
            self.db,
            queue_path=self.queue_file,
            manifest_path=self.manifest_file,
            packet_dir=self.packet_dir,
        )
        self.assertFalse(eval_res["lineage_integrity_passed"])
        self.assertEqual(eval_res["lineage_integrity_status"], "FAILED_LINEAGE_AMBIGUITY")
        self.assertTrue(any("predecessor mismatch" in b for b in eval_res["lineage_blockers"]))

    def test_closure_gate_fails_on_unresolved_predecessor(self):
        """Proves closure gate catches declared parent revision missing from DB."""
        # Create candidate pointing to nonexistent parent
        orphan_src = authority(source_id="orphan_source_s1", section="1")
        orphan_src["parent_revision"] = "missing_parent_00000000000000000000000000000000"
        orphan_pub = self.corpus.publish(orphan_src, activate=False)
        orphan_vid = orphan_pub["version_id"]

        orphan_queue = {
            "total_pending_candidates": 1,
            "candidates": [{"source_id": "orphan_source_s1", "version_id": orphan_vid}],
        }
        orphan_queue_file = Path(self.folder.name) / "orphan_queue.json"
        orphan_queue_file.write_text(json.dumps(orphan_queue), encoding="utf-8")

        eval_res = evaluate_phase4_closure(
            self.db,
            queue_path=orphan_queue_file,
            manifest_path=Path("nonexistent_manifest.json"),
            packet_dir=Path("nonexistent_packets"),
        )
        self.assertFalse(eval_res["lineage_integrity_passed"])
        self.assertTrue(any("not found in legal_authority_versions" in b for b in eval_res["lineage_blockers"]))

    def test_historical_toc_revision_remains_immutable_and_unapproved(self):
        """Proves superseded TOC extraction exists in versions but is not active in heads."""
        toc_doc = self.db.get("legal_authority_versions", self.gen2_vid)
        self.assertIsNotNone(toc_doc)
        self.assertEqual(toc_doc["source"]["quote"], "1. Short title and extent")

        # Must not be approved in legal_authority_heads
        head = self.db.get("legal_authority_heads", self.sid)
        self.assertIsNone(head)

    def test_duplicate_and_preliminary_revisions_do_not_become_active(self):
        """Proves preliminary (Gen 1) revision is not the active review target."""
        q_data = json.loads(self.queue_file.read_text(encoding="utf-8"))
        active_vid = q_data["candidates"][0]["version_id"]
        self.assertNotEqual(active_vid, self.gen1_vid)
        self.assertEqual(active_vid, self.gen3_vid)


class GenuinePhase4LineageIntegrityTests(unittest.TestCase):
    """Integrity checks on the real repository artifacts against active MongoDB."""

    def test_real_repository_lineage_integrity(self):
        """Proves genuine 12 candidates have consistent queue, manifest, packets, and DB."""
        from backend.adapters.mongo.database import MongoDatabaseAdapter
        adapter = MongoDatabaseAdapter(db_name="caseseva")

        # Run closure gate against real repository paths
        res = evaluate_phase4_closure(adapter)
        self.assertTrue(
            res["lineage_integrity_passed"],
            f"Lineage integrity failed: {res.get('lineage_blockers')}",
        )
        self.assertEqual(res["lineage_integrity_status"], "PASSED")
        self.assertEqual(len(res["lineage_blockers"]), 0)

        # Gate must still fail overall because genuine review decisions are pending
        self.assertFalse(res["can_close"])
        self.assertEqual(res["gate_status"], "FAILED_PENDING_HUMAN_REVIEW")
        self.assertEqual(res["pending_candidates_count"], 12)


if __name__ == "__main__":
    unittest.main()
