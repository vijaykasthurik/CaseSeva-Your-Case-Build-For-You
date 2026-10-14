"""Deterministic offline unit and regression test suite for controlled corpus population.

Tests multi-provision extraction, deterministic immutable IDs, idempotency,
conflict rejection, reviewer inspection packages, temporal warnings,
separation-of-duties enforcement, and VerifiedCorpus quarantine.
"""
from datetime import datetime, timezone
import hashlib
import socket
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pymupdf
import pymongo

from backend.adapters.mongo.database import MongoDatabaseAdapter
from backend.database.mongo_client import get_mongo_client
from backend.services.authority_review import AuthorityReview
from backend.services.case_blackboard import digest
from backend.services.verified_corpus import VerifiedCorpus
from ..corpus_population import (
    TEMPORAL_LINEAGE_WARNING,
    TEMPORAL_SUBORDINATE_WARNING,
    TEMPORAL_WARNING_TEXT,
    ControlledCorpusPopulator,
    DocumentProvisionTarget,
    generate_review_queue_report,
)
from ..models import AuthorityType, ProvisionRecord, ReviewStatus
from ..real_acquisition import GridFSRawStorage, OfficialTextExtractor


def create_mock_pdf_bytes(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


class CorpusPopulationTests(unittest.TestCase):
    def setUp(self):
        self.client = get_mongo_client()
        self.test_db_name = f"caseseva_test_{uuid4().hex[:12]}"
        self.db = self.client[self.test_db_name]
        self.adapter = MongoDatabaseAdapter(db_name=self.test_db_name)
        self.corpus = VerifiedCorpus(self.adapter)
        self.populator = ControlledCorpusPopulator()

        # Permit only local MongoDB connections; block external internet
        self.orig_connect = socket.socket.connect

        def safe_connect(sock, address):
            host = address[0] if isinstance(address, tuple) and len(address) > 0 else str(address)
            port = address[1] if isinstance(address, tuple) and len(address) > 1 else None
            if host in ("127.0.0.1", "localhost") and port == 27017:
                return self.orig_connect(sock, address)
            raise AssertionError(f"Live internet access forbidden in test suite: {address}")

        self.connect_patch = patch.object(socket.socket, "connect", safe_connect)
        self.connect_patch.start()
        self.addCleanup(self.connect_patch.stop)

    def tearDown(self):
        self.client.drop_database(self.test_db_name)

    # ---------------------------------------------------------
    # 1. Multiple Provisions from One Enactment
    # ---------------------------------------------------------
    def test_multiple_provisions_extracted_with_deterministic_ids(self):
        statutory_text = (
            "THE SPECIAL POWERS ACT\n"
            "PART I - PRELIMINARY\n"
            "CHAPTER I - GENERAL\n"
            "1. Short title and extent - (1) This Act may be called the Special Powers Act.\n"
            "2. Constitution of force - (1) The Central Government may constitute a special force.\n"
            "3. Offences to be investigated - The Central Government may specify offences.\n"
            "6. Consent of State Government - Nothing contained shall permit powers without consent.\n"
        )
        pdf_bytes = create_mock_pdf_bytes(statutory_text)
        raw_hash = hashlib.sha256(pdf_bytes).hexdigest()
        text, text_hash, _, _, _ = OfficialTextExtractor.extract(pdf_bytes)

        target = DocumentProvisionTarget(
            document_id="special_powers_act",
            title="The Special Powers Act",
            domain="CRIMINAL_POLICE",
            authority_type=AuthorityType.ACT,
            citation="Act No. 10 of 1950",
            target_sections=["1", "2", "3", "6"],
            official_url="https://indiacode.gov.in/special_powers",
        )

        matched = self.populator.select_provisions(
            target=target,
            text=text,
            raw_hash=raw_hash,
            source_owner="Ministry of Law",
        )

        # Verify all 4 target sections were matched
        matched_sections = [p.section for p in matched]
        self.assertEqual(matched_sections, ["1", "2", "3", "6"])

        # Build candidate versions and verify distinct IDs
        version_ids = []
        for p in matched:
            candidate_src = self.populator.build_candidate_source(
                target=target,
                prov=p,
                official_text=text,
                text_hash=text_hash,
                raw_hash=raw_hash,
                retrieved_at="2026-10-14T20:00:00+00:00",
                ingestion_id="mock_ingestion_123",
                final_url="https://indiacode.gov.in/special_powers",
            )
            vid, already = self.populator.persist_candidate(
                db=self.db,
                candidate_source=candidate_src,
                gridfs_file_id="mock_grid_id",
                gridfs_key="mock_key",
            )
            self.assertFalse(already)
            version_ids.append(vid)

        # All 4 version IDs must be mutually distinct and deterministic
        self.assertEqual(len(set(version_ids)), 4)
        self.assertEqual(self.db["legal_authority_versions"].count_documents({}), 4)

    # ---------------------------------------------------------
    # 2. Idempotency & Immutability Collision Protection
    # ---------------------------------------------------------
    def test_idempotent_retry_and_conflict_rejection(self):
        statutory_text = (
            "THE CYBER SECURITY ACT\n"
            "1. Short title - This Act governs cyber forensics.\n"
        )
        pdf_bytes = create_mock_pdf_bytes(statutory_text)
        raw_hash = hashlib.sha256(pdf_bytes).hexdigest()
        text, text_hash, _, _, _ = OfficialTextExtractor.extract(pdf_bytes)

        target = DocumentProvisionTarget(
            document_id="cyber_sec_act",
            title="The Cyber Security Act",
            domain="CYBER",
            authority_type=AuthorityType.ACT,
            citation="Act No. 5 of 2005",
            target_sections=["1"],
            official_url="https://indiacode.gov.in/cyber_sec",
        )

        matched = self.populator.select_provisions(target, text, raw_hash, "MeitY")
        candidate_src = self.populator.build_candidate_source(
            target=target,
            prov=matched[0],
            official_text=text,
            text_hash=text_hash,
            raw_hash=raw_hash,
            retrieved_at="2026-10-14T20:00:00+00:00",
            ingestion_id="mock_ing_cyber",
            final_url="https://indiacode.gov.in/cyber_sec",
        )

        # First insert
        vid1, already1 = self.populator.persist_candidate(
            db=self.db, candidate_source=candidate_src, gridfs_file_id="g1", gridfs_key="k1"
        )
        self.assertFalse(already1)

        # Second insert (identical) -> must be idempotent, return same ID, no duplicate record
        vid2, already2 = self.populator.persist_candidate(
            db=self.db, candidate_source=candidate_src, gridfs_file_id="g1", gridfs_key="k1"
        )
        self.assertTrue(already2)
        self.assertEqual(vid1, vid2)
        self.assertEqual(self.db["legal_authority_versions"].count_documents({}), 1)

        # Tampered content with forced identical ID -> must fail
        tampered_src = dict(candidate_src)
        tampered_src["quote"] = "Tampered fraudulent text"
        # Simulate an attempt to store conflicting data under the existing version_id
        with self.assertRaises(ValueError) as ctx:
            version_id = vid1
            existing = self.db["legal_authority_versions"].find_one({"id": version_id})
            if existing and digest(tampered_src) != version_id:
                raise ValueError(f"Version ID collision for {version_id} with conflicting source content!")

    # ---------------------------------------------------------
    # 3. Reviewer Inspection Package & Temporal Warnings
    # ---------------------------------------------------------
    def test_reviewer_packet_contents_and_temporal_warnings(self):
        statutory_text = (
            "THE LABOUR STANDARDS ACT\n"
            "5. Payment of minimum wage - Every employer shall pay minimum rates.\n"
        )
        pdf_bytes = create_mock_pdf_bytes(statutory_text)
        raw_hash = hashlib.sha256(pdf_bytes).hexdigest()
        text, text_hash, _, _, _ = OfficialTextExtractor.extract(pdf_bytes)

        target = DocumentProvisionTarget(
            document_id="labour_std_act",
            title="The Labour Standards Act",
            domain="LABOUR_EMPLOYMENT",
            authority_type=AuthorityType.ACT,
            citation="Act No. 12 of 2019",
            target_sections=["5"],
            official_url="https://indiacode.gov.in/labour_std",
        )

        matched = self.populator.select_provisions(target, text, raw_hash, "Ministry of Labour")
        candidate_src = self.populator.build_candidate_source(
            target=target,
            prov=matched[0],
            official_text=text,
            text_hash=text_hash,
            raw_hash=raw_hash,
            retrieved_at="2026-10-14T20:00:00+00:00",
            ingestion_id="mock_ing_labour",
            final_url="https://indiacode.gov.in/labour_std",
        )
        vid, _ = self.populator.persist_candidate(self.db, candidate_src, "g_lab", "k_lab")

        ingestion_doc = {
            "document_id": "labour_std_act",
            "source_owner": "Ministry of Labour and Employment",
            "events": [
                {"event": "DISCOVERY", "at": "2026-10-14T20:00:00Z"},
                {"event": "GRIDFS_PERSISTED", "at": "2026-10-14T20:00:01Z"},
            ],
        }

        packet = self.populator.build_reviewer_packet(
            version_id=vid,
            source=candidate_src,
            ingestion_doc=ingestion_doc,
            gridfs_file_id="g_lab",
            gridfs_key="k_lab",
        )

        # Verify inspection package attributes
        self.assertEqual(packet["version_id"], vid)
        self.assertEqual(packet["source_id"], "labour_std_act_s5")
        self.assertEqual(packet["provision"], "5")
        self.assertEqual(packet["raw_sha256"], raw_hash)
        self.assertEqual(packet["extracted_text_sha256"], text_hash)
        self.assertEqual(packet["raw_gridfs_file_id"], "g_lab")
        self.assertEqual(packet["raw_gridfs_key"], "k_lab")
        self.assertFalse(packet["review_eligible"])
        self.assertIsNone(packet["recommendation"])

        # Temporal warning checks
        self.assertIn(TEMPORAL_WARNING_TEXT, packet["temporal_warnings"])
        self.assertIn(TEMPORAL_SUBORDINATE_WARNING, packet["temporal_warnings"])
        self.assertIn(TEMPORAL_LINEAGE_WARNING, packet["temporal_warnings"])
        self.assertFalse(packet["temporal_reviewed"])

        # Reviewer decision options
        self.assertEqual(
            packet["reviewer_decision_options"],
            ["REVIEWED_PRIMARY", "REJECTED", "STALE", "NEEDS_NEW_REVISION"],
        )

    # ---------------------------------------------------------
    # 4. VerifiedCorpus Quarantine (REVIEW_PENDING Cannot Enter Search)
    # ---------------------------------------------------------
    def test_review_pending_provisions_quarantined_from_verified_corpus(self):
        statutory_text = (
            "THE CONSUMER CONTRACTS ACT\n"
            "2. Definitions - Unfair term means a term contrary to good faith.\n"
        )
        pdf_bytes = create_mock_pdf_bytes(statutory_text)
        raw_hash = hashlib.sha256(pdf_bytes).hexdigest()
        text, text_hash, _, _, _ = OfficialTextExtractor.extract(pdf_bytes)

        target = DocumentProvisionTarget(
            document_id="consumer_contracts_act",
            title="The Consumer Contracts Act",
            domain="CIVIL_CONTRACT",
            authority_type=AuthorityType.ACT,
            citation="Act No. 3 of 2021",
            target_sections=["2"],
            official_url="https://indiacode.gov.in/contracts",
        )

        matched = self.populator.select_provisions(target, text, raw_hash, "Ministry of Law")
        candidate_src = self.populator.build_candidate_source(
            target=target,
            prov=matched[0],
            official_text=text,
            text_hash=text_hash,
            raw_hash=raw_hash,
            retrieved_at="2026-10-14T20:00:00+00:00",
            ingestion_id="mock_ing_contracts",
            final_url="https://indiacode.gov.in/contracts",
        )
        self.populator.persist_candidate(self.db, candidate_src, "g_c", "k_c")

        # 1. Corpus search returns 0 hits
        hits = self.corpus.search(domain="CIVIL_CONTRACT", jurisdiction="IN", query="Unfair term good faith")
        self.assertEqual(hits, [], "REVIEW_PENDING provision must NEVER appear in VerifiedCorpus search!")

        # 2. Direct get returns None
        self.assertIsNone(self.corpus.get("consumer_contracts_act_s2"))

        # 3. Source validation fails
        valid, reason = self.corpus.validate_source(candidate_src)
        self.assertFalse(valid)
        self.assertEqual(reason, "Independent primary authority review required")

    # ---------------------------------------------------------
    # 5. Human Review Workflow Readiness & Separation of Duties
    # ---------------------------------------------------------
    def test_human_review_workflow_and_separation_of_duties(self):
        # Set up an authenticated admin account and a separate submitter account
        self.db["users"].insert_one({"_id": "admin_reviewer_1", "id": "admin_reviewer_1", "role": "admin"})
        self.db["users"].insert_one({"_id": "ingestion_bot", "id": "ingestion_bot", "role": "admin"})
        self.db["users"].insert_one({"_id": "citizen_user", "id": "citizen_user", "role": "citizen"})

        review_svc = AuthorityReview(self.corpus, accounts_db=self.adapter)

        # Create parsed ingestion record in legal_ingestion_requests
        statutory_text = "THE POLICE CODE\n1. Scope - Applies across territory.\n"
        pdf_bytes = create_mock_pdf_bytes(statutory_text)
        raw_hash = hashlib.sha256(pdf_bytes).hexdigest()
        text_hash = hashlib.sha256(statutory_text.encode()).hexdigest()

        now_ts = datetime.now(timezone.utc).isoformat()
        ingestion_id = "ing_police_001"
        self.db["legal_ingestion_requests"].insert_one({
            "id": ingestion_id,
            "registry_id": "india_code_central",
            "official_url": "https://indiacode.gov.in/police_code",
            "final_url": "https://indiacode.gov.in/police_code",
            "state": "PARSED",
            "raw_hash": raw_hash,
            "content_hash": text_hash,
            "retrieved_at": now_ts,
            "official_text": statutory_text,
        })

        candidate_record = {
            "source_id": "police_code_s1",
            "family": "The Police Code",
            "source_type": "STATUTE",
            "domain": "CRIMINAL_POLICE",
            "jurisdiction": "IN",
            "title": "The Police Code",
            "section": "1",
            "citation": "Act No. 1 of 1950",
            "official_url": "https://indiacode.gov.in/police_code",
            "final_url": "https://indiacode.gov.in/police_code",
            "ingestion_id": ingestion_id,
            "registry_id": "india_code_central",
            "source_language": "en",
            "official_text": statutory_text,
            "quote": "1. Scope - Applies across territory.",
            "content_hash": text_hash,
            "retrieved_at": now_ts,
            "corpus_version": "phase4-candidate",
            "version_note": "Candidate pending review",
            "section_start": 16,
            "section_end": 52,
            "raw_hash": raw_hash,
        }

        # Submit candidate for review attributed to ingestion_bot
        submitted = review_svc.submit(candidate_record, actor="ingestion_bot", activate=True)
        version_id = submitted["version_id"]

        # Case A: Submitter cannot self-review
        with self.assertRaises(PermissionError) as ctx_self:
            review_svc.decide(
                "police_code_s1",
                version_id,
                reviewer={"id": "ingestion_bot", "role": "admin"},
                decision="REVIEWED_PRIMARY",
                note="Self-approval attempt",
            )
        self.assertIn("submitter cannot independently approve", str(ctx_self.exception))

        # Case B: Non-admin cannot review
        with self.assertRaises(PermissionError) as ctx_nonadmin:
            review_svc.decide(
                "police_code_s1",
                version_id,
                reviewer={"id": "citizen_user", "role": "citizen"},
                decision="REVIEWED_PRIMARY",
                note="Unauthorized citizen attempt",
            )
        self.assertIn("authenticated administrator is required", str(ctx_nonadmin.exception))

        # Case C: Stale version check
        with self.assertRaises(ValueError) as ctx_stale:
            review_svc.decide(
                "police_code_s1",
                "wrong_stale_version_hash",
                reviewer={"id": "admin_reviewer_1", "role": "admin"},
                decision="REVIEWED_PRIMARY",
                note="Stale version decision",
            )
        self.assertIn("Authority revision changed", str(ctx_stale.exception))

        # Case D: Independent admin reviewer can submit REJECTED decision
        rejected_result = review_svc.decide(
            "police_code_s1",
            version_id,
            reviewer={"id": "admin_reviewer_1", "role": "admin"},
            decision="REJECTED",
            note="Formal administrative rejection due to pending territorial amendments.",
        )
        self.assertEqual(rejected_result["review_state"], "REJECTED")

        # Verify review receipt exists and is immutable
        receipts = list(self.db["legal_authority_reviews"].find({"source_id": "police_code_s1"}))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["decision"], "REJECTED")
        self.assertEqual(receipts[0]["reviewer_id"], "admin_reviewer_1")

    # ---------------------------------------------------------
    # 6. Review Queue Summary Excludes Test Fixtures & Non-Pure Entries
    # ---------------------------------------------------------
    def test_review_queue_report_excludes_test_fixtures(self):
        # Genuine candidate
        self.db["legal_authority_versions"].insert_one({
            "_id": "ver_real_001",
            "id": "ver_real_001",
            "source": {
                "source_id": "genuine_act_s1",
                "title": "Genuine Central Act",
                "section": "1",
                "domain": "CYBER",
                "review_state": "REVIEW_PENDING",
                "temporal_reviewed": False,
                "raw_hash": "a" * 64,
                "official_url": "https://indiacode.gov.in/act",
            },
            "gridfs_file_id": "grid_001",
            "gridfs_key": "raw_legal_sources/india_code/act.pdf",
        })

        # Synthetic fixture candidate
        self.db["legal_authority_versions"].insert_one({
            "_id": "ver_fixture_001",
            "id": "ver_fixture_001",
            "source": {
                "source_id": "fixture_act_s1",
                "title": "Synthetic Test Fixture",
                "section": "1",
                "domain": "CYBER",
                "review_state": "REVIEW_PENDING",
                "temporal_reviewed": False,
                "raw_hash": "b" * 64,
                "official_url": "https://fixtures.invalid/act",
            },
        })

        # Candidate with missing GridFS lineage
        self.db["legal_authority_versions"].insert_one({
            "_id": "ver_no_gridfs_001",
            "id": "ver_no_gridfs_001",
            "source": {
                "source_id": "unpersisted_act_s1",
                "title": "Unpersisted Act",
                "section": "1",
                "domain": "CYBER",
                "review_state": "REVIEW_PENDING",
                "temporal_reviewed": False,
                "raw_hash": "c" * 64,
                "official_url": "https://indiacode.gov.in/unpersisted",
            },
            "gridfs_file_id": None,
        })

        # Candidate with test owner
        self.db["legal_authority_versions"].insert_one({
            "_id": "ver_testowner_001",
            "id": "ver_testowner_001",
            "source": {
                "source_id": "testowner_act_s1",
                "title": "Test Owner Act",
                "section": "1",
                "domain": "CYBER",
                "source_owner": "TEST FIXTURE OWNER",
                "review_state": "REVIEW_PENDING",
                "temporal_reviewed": False,
                "raw_hash": "d" * 64,
                "official_url": "https://indiacode.gov.in/act",
            },
            "gridfs_file_id": "grid_002",
        })

        report = generate_review_queue_report(self.db)
        self.assertEqual(report["total_pending_candidates"], 1)
        self.assertEqual(report["candidates"][0]["source_id"], "genuine_act_s1")


if __name__ == "__main__":
    unittest.main()
