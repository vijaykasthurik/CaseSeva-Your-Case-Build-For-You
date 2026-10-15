"""Deterministic tests for hardened statutory sectionizer and review packet correction.

Proves:
- TOC entries lose to substantive provision occurrences
- Operative Section 1 is extracted correctly
- Next-section boundary is respected
- Repeated headers/footers/footnotes are excluded
- Multi-digit sections work (e.g. s43, s66, s108)
- Alphanumeric sections work (e.g. s1A, s43A, s66A)
- Arbitrary enactments work without domain hardcoding
- Old revisions remain immutable
- Corrected revisions form distinct new versions linked to predecessor
- Corrected revisions remain REVIEW_PENDING
- Review packets reference corrected versions with mandatory warnings
- Raw provenance lineage (GridFS, hashes) is preserved
- Review queue contains exactly 12 genuine candidates
- No VerifiedCorpus promotion occurs
"""
import hashlib
import json
from pathlib import Path
import unittest
from uuid import uuid4

from backend.adapters.mongo.database import MongoDatabaseAdapter
from backend.database.mongo_client import get_mongo_client
from backend.models.legal_foundation import LegalSource
from backend.services.case_blackboard import digest
from backend.services.verified_corpus import VerifiedCorpus
from engineering_prework.legal_source_ingestion.corpus_population import (
    ControlledCorpusPopulator,
    DocumentProvisionTarget,
    AuthorityType,
    TEMPORAL_WARNING_TEXT,
    TEMPORAL_SUBORDINATE_WARNING,
    TEMPORAL_LINEAGE_WARNING,
    generate_review_queue_report,
)
from engineering_prework.legal_source_ingestion.sectionizer import StatutorySectionizer


SYNTHETIC_STATUTE_WITH_TOC = """THE ARBITRARY COMMERCIAL DISPUTES ACT, 2024
ARRANGEMENT OF SECTIONS
SECTIONS
1. Short title, extent and commencement.
1A. Definitions and interpretation.
2. Establishment of tribunal.
43. Penalties for non-compliance.
43A. Compensation for commercial injury.
66. Digital submission requirements.
108. Appellate procedure.

THE ARBITRARY COMMERCIAL DISPUTES ACT, 2024
[ACT NO. 99 OF 2024]
[1st June, 2024]

An Act to establish commercial dispute settlement mechanisms and related procedures.
BE it enacted by Parliament in the Seventy-fifth Year of the Republic of India as follows:—

CHAPTER I
PRELIMINARY

1. Short title, extent and commencement.—(1) This Act may be called the Arbitrary Commercial Disputes Act, 2024.
(2) It extends to the whole of India.
(3) It shall come into force on such date as the Central Government may appoint.

1A. Definitions and interpretation.—In this Act, unless the context otherwise requires,—
(a) "Tribunal" means the Commercial Dispute Settlement Tribunal;
(b) "dispute" means any civil dispute arising out of commercial contracts.

CHAPTER II
TRIBUNAL ESTABLISHMENT

2. Establishment of tribunal.—(1) The Central Government shall, by notification, establish one or more Tribunals.
(2) Each Tribunal shall consist of a Chairperson and two Members.

1. Subs. by Act 50 of 2025, s. 2 (w.e.f. 1-1-2025).
2. Ins. by Act 50 of 2025, s. 3 (w.e.f. 1-1-2025).

CHAPTER V
OFFENCES AND PENALTIES

43. Penalties for non-compliance.—Whoever fails to comply with an order of the Tribunal shall be liable to a penalty not exceeding ten lakh rupees.

43A. Compensation for commercial injury.—(1) Where any person suffers commercial loss, the Tribunal may award compensation.

66. Digital submission requirements.—All pleadings and documentary evidence shall be submitted through the authenticated digital portal.

108. Appellate procedure.—Any person aggrieved by an order may prefer an appeal within thirty days.
"""


class SectionizerHardeningTests(unittest.TestCase):
    def setUp(self):
        self.sectionizer = StatutorySectionizer()
        self.populator = ControlledCorpusPopulator(self.sectionizer)
        self.client = get_mongo_client()
        self.test_db_name = f"caseseva_sec_test_{uuid4().hex[:12]}"
        self.db = self.client[self.test_db_name]
        self.adapter = MongoDatabaseAdapter(db_name=self.test_db_name)
        self.corpus = VerifiedCorpus(self.adapter)

    def tearDown(self):
        self.client.drop_database(self.test_db_name)

    def test_toc_entries_lose_to_substantive_operative_occurrences(self):
        """Proves TOC entries with zero body text lose to substantive operative provision."""
        valid_hash = hashlib.sha256(b"arbitrary_pdf_bytes").hexdigest()
        provisions = self.sectionizer.extract_provisions(
            document_id="arb_act_2024",
            title="The Arbitrary Commercial Disputes Act, 2024",
            text=SYNTHETIC_STATUTE_WITH_TOC,
            official_url="https://example.gov.in/act99",
            source_owner="Official Publisher",
            raw_document_hash=valid_hash,
        )
        sec1 = next(p for p in provisions if p.section == "1" and p.subsection is None)
        # Heading is substantive
        self.assertIn("Short title", sec1.heading)
        # Quote contains substantive operative subsections, not TOC line
        self.assertIn("This Act may be called the Arbitrary Commercial Disputes Act, 2024", sec1.quote)
        self.assertIn("(2) It extends to the whole of India", sec1.quote)
        # Exact substring guarantee
        self.assertEqual(SYNTHETIC_STATUTE_WITH_TOC[sec1.section_start:sec1.section_end], sec1.quote)

    def test_next_section_boundary_respected(self):
        """Proves provision boundaries terminate cleanly before next section."""
        valid_hash = hashlib.sha256(b"arbitrary_pdf_bytes").hexdigest()
        provisions = self.sectionizer.extract_provisions(
            document_id="arb_act_2024",
            title="The Arbitrary Commercial Disputes Act, 2024",
            text=SYNTHETIC_STATUTE_WITH_TOC,
            official_url="https://example.gov.in/act99",
            source_owner="Official Publisher",
            raw_document_hash=valid_hash,
        )
        sec1 = next(p for p in provisions if p.section == "1" and p.subsection is None)
        sec1A = next(p for p in provisions if p.section == "1A" and p.subsection is None)
        # Section 1 terminates at Section 1A start
        self.assertEqual(sec1.section_end, sec1A.section_start)
        self.assertNotIn("1A. Definitions", sec1.quote)

    def test_repeated_headers_footers_footnotes_excluded(self):
        """Proves footnote citations like '1. Subs. by' are not parsed as section 1."""
        valid_hash = hashlib.sha256(b"arbitrary_pdf_bytes").hexdigest()
        provisions = self.sectionizer.extract_provisions(
            document_id="arb_act_2024",
            title="The Arbitrary Commercial Disputes Act, 2024",
            text=SYNTHETIC_STATUTE_WITH_TOC,
            official_url="https://example.gov.in/act99",
            source_owner="Official Publisher",
            raw_document_hash=valid_hash,
        )
        # Exactly one top-level Section 1 should be returned, and not the footnote
        sec1_matches = [p for p in provisions if p.section == "1" and p.subsection is None]
        self.assertEqual(len(sec1_matches), 1)
        self.assertNotIn("Subs. by", sec1_matches[0].heading)

    def test_multidigit_and_alphanumeric_sections(self):
        """Proves multi-digit (43, 66, 108) and alphanumeric (1A, 43A) sections work generically."""
        valid_hash = hashlib.sha256(b"arbitrary_pdf_bytes").hexdigest()
        provisions = self.sectionizer.extract_provisions(
            document_id="arb_act_2024",
            title="The Arbitrary Commercial Disputes Act, 2024",
            text=SYNTHETIC_STATUTE_WITH_TOC,
            official_url="https://example.gov.in/act99",
            source_owner="Official Publisher",
            raw_document_hash=valid_hash,
        )
        sections = {p.section for p in provisions if p.subsection is None}
        self.assertIn("1A", sections)
        self.assertIn("43", sections)
        self.assertIn("43A", sections)
        self.assertIn("66", sections)
        self.assertIn("108", sections)

        sec43a = next(p for p in provisions if p.section == "43A" and p.subsection is None)
        self.assertIn("Compensation for commercial injury", sec43a.heading)
        self.assertIn("Where any person suffers commercial loss", sec43a.quote)

    def test_arbitrary_acts_work_without_hardcoding(self):
        """Proves sectionizer works on completely unseen statutes and arbitrary domains."""
        target = DocumentProvisionTarget(
            document_id="arb_act_2024",
            title="The Arbitrary Commercial Disputes Act, 2024",
            domain="ARBITRARY_NEW_DOMAIN",
            authority_type=AuthorityType.ACT,
            citation="Act 99 of 2024",
            target_sections=["1", "43", "43A", "66"],
            official_url="https://example.gov.in/act99",
        )
        valid_raw = hashlib.sha256(b"raw_bytes").hexdigest()
        matched = self.populator.select_provisions(
            target=target,
            text=SYNTHETIC_STATUTE_WITH_TOC,
            raw_hash=valid_raw,
            source_owner="Arbitrary Authority",
        )
        matched_sections = [p.section for p in matched]
        self.assertEqual(matched_sections, ["1", "43", "43A", "66"])
        for p in matched:
            self.assertGreater(len(p.quote), 50)

    def test_immutable_revision_lineage_and_packet_integrity(self):
        """Proves old revision is immutable, new revision is distinct, links parent, and packet updates."""
        valid_raw = hashlib.sha256(b"raw_pdf").hexdigest()
        valid_text_hash = hashlib.sha256(SYNTHETIC_STATUTE_WITH_TOC.encode("utf-8")).hexdigest()
        target = DocumentProvisionTarget(
            document_id="arb_act_2024",
            title="The Arbitrary Commercial Disputes Act, 2024",
            domain="COMMERCIAL",
            authority_type=AuthorityType.ACT,
            citation="Act 99 of 2024",
            target_sections=["1"],
            official_url="https://example.gov.in/act99",
        )
        matched = self.populator.select_provisions(
            target=target,
            text=SYNTHETIC_STATUTE_WITH_TOC,
            raw_hash=valid_raw,
            source_owner="Arbitrary Authority",
        )
        prov = matched[0]

        # Step A: Simulate old defective revision (e.g. quote was TOC line)
        old_src = self.populator.build_candidate_source(
            target=target,
            prov=prov,
            official_text=SYNTHETIC_STATUTE_WITH_TOC,
            text_hash=valid_text_hash,
            raw_hash=valid_raw,
            retrieved_at="2026-10-14T00:00:00Z",
            ingestion_id="ingest_001",
            final_url="https://example.gov.in/act99",
        )
        old_src["quote"] = "1. Short title, extent and commencement."
        old_vid, _ = self.populator.persist_candidate(
            db=self.db,
            candidate_source=old_src,
            gridfs_file_id="gridfs_file_001",
            gridfs_key="raw/file.pdf",
        )

        # Step B: Create corrected revision
        corrected_src = self.populator.build_candidate_source(
            target=target,
            prov=prov,
            official_text=SYNTHETIC_STATUTE_WITH_TOC,
            text_hash=valid_text_hash,
            raw_hash=valid_raw,
            retrieved_at="2026-10-14T00:00:00Z",
            ingestion_id="ingest_001",
            final_url="https://example.gov.in/act99",
        )
        corrected_src["parent_revision"] = old_vid
        corrected_src["revision_status"] = "NONE"
        corrected_src["revision_metadata"] = {
            "correction": "TECHNICAL_EXTRACTION_RESECTIONIZATION",
            "previous_version_id": old_vid,
            "reason": "Substantive operative provision re-sectionized",
        }
        corrected_vid, _ = self.populator.persist_candidate(
            db=self.db,
            candidate_source=corrected_src,
            gridfs_file_id="gridfs_file_001",
            gridfs_key="raw/file.pdf",
        )

        # Verify old revision is preserved and distinct
        self.assertNotEqual(old_vid, corrected_vid)
        old_record = self.db.legal_authority_versions.find_one({"id": old_vid})
        self.assertIsNotNone(old_record)
        self.assertEqual(old_record["source"]["quote"], "1. Short title, extent and commencement.")

        # Verify corrected revision
        new_record = self.db.legal_authority_versions.find_one({"id": corrected_vid})
        self.assertIsNotNone(new_record)
        self.assertEqual(new_record["source"]["parent_revision"], old_vid)
        self.assertEqual(new_record["source"]["review_state"], "REVIEW_PENDING")
        self.assertFalse(new_record["source"]["source_reviewed"])
        self.assertFalse(new_record["source"]["temporal_reviewed"])

        # Step C: Review packet verification
        packet = self.populator.build_reviewer_packet(
            version_id=corrected_vid,
            source=corrected_src,
            ingestion_doc={"document_id": "arb_act_2024", "events": []},
            gridfs_file_id="gridfs_file_001",
            gridfs_key="raw/file.pdf",
        )
        self.assertEqual(packet["version_id"], corrected_vid)
        self.assertEqual(packet["exact_official_excerpt"], corrected_src["quote"])
        self.assertEqual(packet["raw_sha256"], valid_raw)
        self.assertIn(TEMPORAL_WARNING_TEXT, packet["temporal_warnings"])
        self.assertIn(TEMPORAL_SUBORDINATE_WARNING, packet["temporal_warnings"])
        self.assertIn(TEMPORAL_LINEAGE_WARNING, packet["temporal_warnings"])

        # Step D: VerifiedCorpus Quarantine Verification
        all_verified = self.corpus.sources()
        self.assertFalse(any(a["source_id"] == "arb_act_2024_s1" for a in all_verified))


class GenuinePhase4QueueVerificationTests(unittest.TestCase):
    """Verifies that the genuine Phase-4 review queue and review packets meet all requirements."""

    def test_queue_and_packet_integrity(self):
        queue_path = Path("docs/audits/phase4_review_queue.json")
        self.assertTrue(queue_path.exists())
        queue_data = json.loads(queue_path.read_text(encoding="utf-8"))

        self.assertEqual(queue_data["total_pending_candidates"], 12)
        candidates = queue_data["candidates"]
        self.assertEqual(len(candidates), 12)

        client = get_mongo_client()
        db = client["caseseva"]

        # Expected 12 source IDs
        expected_sources = {
            "dspe_act_1946_s1", "dspe_act_1946_s2", "dspe_act_1946_s3", "dspe_act_1946_s6",
            "it_act_2000_s1", "it_act_2000_s3", "it_act_2000_s43", "it_act_2000_s66",
            "wages_code_2019_s1", "wages_code_2019_s3", "wages_code_2019_s5", "wages_code_2019_s6",
        }
        found_sources = set()

        for c in candidates:
            sid = c["source_id"]
            found_sources.add(sid)
            vid = c["version_id"]

            # Must remain REVIEW_PENDING
            self.assertEqual(c["review_state"], "REVIEW_PENDING")
            self.assertFalse(c["temporal_reviewed"])

            # Must exist in MongoDB legal_authority_versions
            vdoc = db.legal_authority_versions.find_one({"id": vid})
            self.assertIsNotNone(vdoc, f"Missing Mongo version {vid} for {sid}")
            src = vdoc["source"]
            self.assertEqual(src["review_state"], "REVIEW_PENDING")
            self.assertFalse(src["source_reviewed"])
            self.assertFalse(src["temporal_reviewed"])
            self.assertFalse(src["rules_reviewed"])
            self.assertEqual(src["verification"], "PENDING")
            # Must have substantive quote
            self.assertGreater(len(src["quote"]), 50)
            self.assertIsNotNone(src.get("parent_revision"))

            # Packet check
            pkt_path = Path(c["review_packet_reference"])
            self.assertTrue(pkt_path.exists(), f"Missing packet file {pkt_path}")
            pkt = json.loads(pkt_path.read_text(encoding="utf-8"))
            self.assertEqual(pkt["version_id"], vid)
            self.assertEqual(pkt["exact_official_excerpt"], src["quote"])
            self.assertEqual(pkt["current_review_state"], "REVIEW_PENDING")
            self.assertFalse(pkt["review_eligible"])
            self.assertIn("Current-law coverage has not been established.", pkt["temporal_warnings"])
            self.assertIn("Do not infer that an official consolidated PDF is current through today.", pkt["temporal_warnings"])
            self.assertIn("Amendment, commencement, and repeal coverage remain unverified pending independent authenticated human review.", pkt["temporal_warnings"])

        self.assertEqual(found_sources, expected_sources)

        # VerifiedCorpus quarantine verification
        adapter = MongoDatabaseAdapter(db_name="caseseva")
        corpus = VerifiedCorpus(adapter)
        verified_ids = {a["source_id"] for a in corpus.sources()}
        for s in expected_sources:
            self.assertNotIn(s, verified_ids, f"Candidate {s} leaked into VerifiedCorpus!")


if __name__ == "__main__":
    unittest.main()
