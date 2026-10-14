"""Deterministic offline unit and regression test suite for real official-source acquisition.

Tests all security boundaries, SSRF prevention, GridFS persistence, PyMuPDF extraction,
generic sectionization, REVIEW_PENDING authority state, and VerifiedCorpus quarantine
without internet access.
"""
import hashlib
import io
import socket
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from uuid import uuid4

import pymupdf
import pymongo

from backend.database.mongo_client import get_mongo_client
from backend.services.verified_corpus import VerifiedCorpus
from backend.repositories.authority_repository import MongoAuthorityRepository
from ..models import AuthorityType, ReviewStatus, VersionRelationship
from ..real_acquisition import (
    AcquisitionSecurityError,
    ContentValidationError,
    GridFSPersistenceError,
    GridFSRawStorage,
    OfficialAcquisitionPipeline,
    OfficialDocumentRetriever,
    OfficialRegistrySecurity,
    OfficialTextExtractor,
    inspect_candidate_for_review,
)


def create_minimal_pdf(text: str) -> bytes:
    """Generates valid minimal in-memory PDF bytes containing given text."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class RealAcquisitionTests(unittest.TestCase):
    def setUp(self):
        # Unique temporary MongoDB test database
        self.client = get_mongo_client()
        self.test_db_name = f"caseseva_test_{uuid4().hex[:12]}"
        self.db = self.client[self.test_db_name]

        # Security policy and retriever
        self.security = OfficialRegistrySecurity()
        self.retriever = OfficialDocumentRetriever(security=self.security)
        self.pipeline = OfficialAcquisitionPipeline(retriever=self.retriever)

        # Ensure no live network calls happen during test suite (permit only local MongoDB)
        self.orig_connect = socket.socket.connect

        def safe_connect(sock, address):
            host = address[0] if isinstance(address, tuple) and len(address) > 0 else str(address)
            port = address[1] if isinstance(address, tuple) and len(address) > 1 else None
            if host in ("127.0.0.1", "localhost") and port == 27017:
                return self.orig_connect(sock, address)
            raise AssertionError(f"Live internet access is strictly forbidden: attempted connection to {address}")

        self.connect_patch = patch.object(socket.socket, "connect", safe_connect)
        self.connect_patch.start()
        self.addCleanup(self.connect_patch.stop)

    def tearDown(self):
        # Clean up temporary test database
        self.client.drop_database(self.test_db_name)

    # ---------------------------------------------------------
    # 1. Official Host Validation & SSRF Protection
    # ---------------------------------------------------------
    def test_official_host_validation_permits_registered_domains(self):
        valid_urls = [
            "https://indiacode.gov.in/handle/123456789/496174",
            "https://backend.indiacode.gov.in/server/api/core/bitstreams/uuid/content",
            "https://www.indiacode.nic.in/bitstream/123456789/1/test.pdf",
        ]
        for url in valid_urls:
            with self.subTest(url=url):
                # Should not raise
                self.security.validate_url("india_code_central", url)

    def test_official_host_validation_rejects_disallowed_hosts_and_schemes(self):
        invalid_cases = [
            ("http://indiacode.gov.in/doc", "Insecure scheme"),
            ("file:///etc/passwd", "Insecure scheme"),
            ("ftp://indiacode.gov.in/file", "Insecure scheme"),
            ("https://evil-portal.com/doc", "not permitted"),
            ("https://fakeindiacode.gov.in/doc", "not permitted"),
            ("https://user:pass@indiacode.gov.in/doc", "credentials forbidden"),
            ("https://indiacode.gov.in:8080/doc", "Disallowed non-standard port"),
        ]
        for url, expected_err in invalid_cases:
            with self.subTest(url=url):
                with self.assertRaises(AcquisitionSecurityError) as ctx:
                    self.security.validate_url("india_code_central", url)
                self.assertIn(expected_err, str(ctx.exception))

    def test_ssrf_blocks_private_and_loopback_ips(self):
        private_ips = [
            "127.0.0.1",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.1.1",
            "169.254.169.254",
            "::1",
        ]
        for ip in private_ips:
            with self.subTest(ip=ip):
                self.assertTrue(self.security.is_ip_blocked(ip))
                with self.assertRaises(AcquisitionSecurityError):
                    self.security.validate_url("india_code_central", f"https://{ip}/doc")

    # ---------------------------------------------------------
    # 2. Unsupported / Manual Source Fails Closed
    # ---------------------------------------------------------
    def test_unsupported_and_manual_sources_fail_closed(self):
        # egazette_india has captcha_required=true and MANUAL_BROWSER_ONLY
        permitted, reason = self.security.is_automation_permitted("egazette_india")
        self.assertFalse(permitted)
        self.assertIn("MANUAL_OR_BROWSER_REVIEW_REQUIRED", reason)

        # sci_judgments has captcha_required=true
        permitted, reason = self.security.is_automation_permitted("sci_judgments")
        self.assertFalse(permitted)
        self.assertIn("MANUAL_OR_BROWSER_REVIEW_REQUIRED", reason)

        # Unknown registry source
        permitted, reason = self.security.is_automation_permitted("unknown_source_xyz")
        self.assertFalse(permitted)
        self.assertIn("Unknown registry source", reason)

        # Attempting retrieval on manual source raises AcquisitionSecurityError
        with self.assertRaises(AcquisitionSecurityError) as ctx:
            self.retriever.fetch("egazette_india", "https://egazette.gov.in/default.aspx")
        self.assertIn("MANUAL_OR_BROWSER_REVIEW_REQUIRED", str(ctx.exception))

    # ---------------------------------------------------------
    # 3. Off-Domain Redirect Rejection
    # ---------------------------------------------------------
    def test_off_domain_redirect_is_rejected(self):
        from ..real_acquisition import SecureRedirectHandler
        handler = SecureRedirectHandler(self.security, "india_code_central")
        # Redirect to off-domain host
        with self.assertRaises(AcquisitionSecurityError) as ctx:
            handler.redirect_request(MagicMock(), MagicMock(), 302, "Found", {}, "https://attacker.org/exfiltrate")
        self.assertIn("not permitted", str(ctx.exception))

    # ---------------------------------------------------------
    # 4. Content Validation: Magic Bytes & Anti-Bot Rejection
    # ---------------------------------------------------------
    def test_unexpected_html_pretending_to_be_pdf_is_rejected(self):
        fake_html = b"<html><body><h1>404 Not Found - Server Error</h1></body></html>"
        with self.assertRaises(ContentValidationError) as ctx:
            OfficialTextExtractor.extract(fake_html, content_type="application/pdf")
        self.assertIn("lacks '%PDF' magic header", str(ctx.exception))

    def test_zero_byte_download_is_rejected(self):
        # Direct test on empty bytes
        empty_bytes = b""
        with self.assertRaises(ContentValidationError) as ctx:
            # We mock opener returning 0 bytes
            mock_resp = MagicMock()
            mock_resp.geturl.return_value = "https://indiacode.gov.in/doc.pdf"
            mock_resp.status = 200
            mock_resp.headers = {"Content-Type": "application/pdf"}
            mock_resp.read.return_value = empty_bytes
            with patch("engineering_prework.legal_source_ingestion.real_acquisition.build_opener") as mock_opener:
                mock_opener.return_value.open.return_value.__enter__.return_value = mock_resp
                self.retriever.fetch("india_code_central", "https://indiacode.gov.in/doc.pdf")
        self.assertIn("0-byte", str(ctx.exception))

    # ---------------------------------------------------------
    # 5. GridFS Raw Storage Round Trip & Idempotency
    # ---------------------------------------------------------
    def test_gridfs_raw_byte_round_trip_and_integrity_check(self):
        pdf_content = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"
        pdf_hash = hashlib.sha256(pdf_content).hexdigest()

        file_id, key, already_existed = GridFSRawStorage.store_raw_document(
            db=self.db,
            registry_id="india_code_central",
            document_id="doc_001",
            raw_bytes=pdf_content,
            raw_hash=pdf_hash,
            metadata={"content_type": "application/pdf", "title": "Test Enactment"},
        )
        self.assertFalse(already_existed)
        self.assertTrue(file_id)
        self.assertEqual(key, f"raw_legal_sources/india_code_central/{pdf_hash}.pdf")

        # Verify GridFS collections populated
        self.assertEqual(self.db["fs.files"].count_documents({}), 1)
        self.assertGreaterEqual(self.db["fs.chunks"].count_documents({}), 1)

        # Idempotent retrieval: re-storing identical bytes returns existing ID
        file_id2, key2, already_existed2 = GridFSRawStorage.store_raw_document(
            db=self.db,
            registry_id="india_code_central",
            document_id="doc_001",
            raw_bytes=pdf_content,
            raw_hash=pdf_hash,
            metadata={"content_type": "application/pdf", "title": "Test Enactment"},
        )
        self.assertTrue(already_existed2)
        self.assertEqual(file_id, file_id2)
        self.assertEqual(key, key2)
        self.assertEqual(self.db["fs.files"].count_documents({}), 1)

    def test_gridfs_detects_hash_tampering_or_collision_safely(self):
        pdf_content = b"%PDF-1.7 original bytes"
        pdf_hash = hashlib.sha256(pdf_content).hexdigest()

        GridFSRawStorage.store_raw_document(
            db=self.db,
            registry_id="india_code_central",
            document_id="doc_001",
            raw_bytes=pdf_content,
            raw_hash=pdf_hash,
            metadata={"content_type": "application/pdf"},
        )

        # Simulate attempting to store different bytes with the same key/hash assertion
        corrupted_bytes = b"%PDF-1.7 corrupted bytes"
        with self.assertRaises(GridFSPersistenceError) as ctx:
            GridFSRawStorage.store_raw_document(
                db=self.db,
                registry_id="india_code_central",
                document_id="doc_001",
                raw_bytes=corrupted_bytes,
                raw_hash=pdf_hash,  # Claiming the old hash for different bytes
                metadata={"content_type": "application/pdf"},
            )
        self.assertIn("mismatch", str(ctx.exception))

    # ---------------------------------------------------------
    # 6. Extraction Strictly Bound to Raw Bytes
    # ---------------------------------------------------------
    def test_extraction_strictly_bound_to_raw_bytes(self):
        test_text = "PART I\nCHAPTER I\n1. Short Title.\nThis enactment governs digital signatures and cyber records.\n"
        pdf_bytes = create_minimal_pdf(test_text)

        text, text_hash, extractor_ver, status, warnings = OfficialTextExtractor.extract(pdf_bytes, "application/pdf")
        self.assertEqual(status, "EXTRACTED")
        self.assertIn("Short Title", text)
        self.assertEqual(text_hash, hashlib.sha256(text.encode("utf-8")).hexdigest())
        self.assertTrue(extractor_ver.startswith("pymupdf_"))
        self.assertEqual(warnings, [])

    def test_scanned_zero_text_pdf_flags_ocr_requirement(self):
        # Empty page with no text
        doc = pymupdf.open()
        doc.new_page()
        empty_pdf = doc.tobytes()
        doc.close()

        text, text_hash, extractor_ver, status, warnings = OfficialTextExtractor.extract(empty_pdf, "application/pdf")
        self.assertEqual(status, "SCANNED_OCR_REQUIRED")
        self.assertEqual(text, "")
        self.assertTrue(any("OCR review required" in w for w in warnings))

    # ---------------------------------------------------------
    # 7. Multi-Domain Acquisition Pipeline & Candidate Creation
    # ---------------------------------------------------------
    def test_pipeline_acquires_genuine_candidates_across_multiple_domains(self):
        domains = [
            ("CRIMINAL_POLICE", "dspe_test_act", "The Police Establishment Act, 1946", "3. Powers of Investigation.—Special officers have authority.\n"),
            ("CYBER", "cyber_test_act", "The Information Systems Act, 2000", "43. Penalty for unauthorized computer access.—Any person accessing...\n"),
            ("LABOUR_EMPLOYMENT", "wages_test_act", "The Code on Wages, 2019", "5. Payment of Minimum Wages.—Every employer shall pay minimum rates.\n"),
        ]

        for domain, doc_id, doc_title, sec_text in domains:
            with self.subTest(domain=domain):
                statutory_body = (
                    f"{doc_title}\n"
                    f"ARRANGEMENT OF SECTIONS\n"
                    f"1. Short title and extent\n"
                    f"PART I\n"
                    f"CHAPTER I\n"
                    f"1. Short title and extent.—(1) This Act may be called {doc_title}.\n"
                    f"(2) It extends to the whole of India.\n"
                    f"{sec_text}"
                )
                raw_bytes = create_minimal_pdf(statutory_body)
                raw_hash = hashlib.sha256(raw_bytes).hexdigest()

                # Mock retriever fetch
                mock_retrieval = {
                    "registry_id": "india_code_central",
                    "requested_url": f"https://indiacode.gov.in/handle/123456789/{doc_id}",
                    "final_url": f"https://indiacode.gov.in/server/api/core/bitstreams/{doc_id}/content",
                    "redirect_chain": [],
                    "retrieved_at": "2026-10-14T20:00:00+00:00",
                    "http_status": 200,
                    "content_type": "application/pdf",
                    "byte_size": len(raw_bytes),
                    "raw_bytes": raw_bytes,
                    "raw_hash": raw_hash,
                    "source_owner": "Legislative Department, Ministry of Law and Justice",
                    "retrieval_method": "OFFICIAL_HTTPS_GET",
                    "http_headers": {"Content-Type": "application/pdf"},
                }

                with patch.object(self.retriever, "fetch", return_value=mock_retrieval):
                    res = self.pipeline.acquire_document(
                        db=self.db,
                        registry_id="india_code_central",
                        document_id=doc_id,
                        title=doc_title,
                        official_url=f"https://indiacode.gov.in/handle/123456789/{doc_id}",
                        domain=domain,
                        authority_type=AuthorityType.ACT,
                    )

                # Assert result structure
                self.assertEqual(res["review_status"], "REVIEW_PENDING")
                self.assertFalse(res["source_reviewed"])
                self.assertFalse(res["review_eligible"])
                self.assertEqual(res["domain"], domain)
                self.assertGreaterEqual(res["provisions_count"], 1)
                self.assertEqual(len(res["candidate_versions"]), 1)

                # Verify Ingestion Request record in MongoDB
                ingestion_req = self.db["legal_ingestion_requests"].find_one({"id": res["ingestion_id"]})
                self.assertIsNotNone(ingestion_req)
                self.assertEqual(ingestion_req["state"], "PARSED")
                self.assertEqual(ingestion_req["raw_hash"], raw_hash)
                self.assertEqual(ingestion_req["gridfs_file_id"], res["gridfs_file_id"])

                # Verify Version record in legal_authority_versions (NOT in heads)
                ver_id = res["candidate_versions"][0]
                version_record = self.db["legal_authority_versions"].find_one({"id": ver_id})
                self.assertIsNotNone(version_record)
                src = version_record["source"]
                self.assertEqual(src["review_state"], "REVIEW_PENDING")
                self.assertEqual(src["verification"], "PENDING")
                self.assertFalse(src["source_reviewed"])
                self.assertIsNone(src["review_id"])
                self.assertIsNone(src["reviewed_by"])
                self.assertEqual(src["domain"], domain)

                # CRITICAL: Verify NOT in legal_authority_heads
                heads = list(self.db["legal_authority_heads"].find({}))
                self.assertEqual(len(heads), 0, "Candidate must NOT be inserted into legal_authority_heads!")

    # ---------------------------------------------------------
    # 8. Retrieval Eligibility Gate (VerifiedCorpus Quarantine)
    # ---------------------------------------------------------
    def test_candidate_in_review_pending_is_not_retrieval_eligible(self):
        # 1. Acquire a genuine candidate into test DB
        statutory_body = "The Evidence Act\n1. Scope.—Applies to proceedings.\n3. Definitions.—Court includes all judges.\n"
        raw_bytes = create_minimal_pdf(statutory_body)
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()

        mock_retrieval = {
            "registry_id": "india_code_central",
            "requested_url": "https://indiacode.gov.in/doc",
            "final_url": "https://indiacode.gov.in/doc",
            "redirect_chain": [],
            "retrieved_at": "2026-10-14T20:00:00+00:00",
            "http_status": 200,
            "content_type": "application/pdf",
            "byte_size": len(raw_bytes),
            "raw_bytes": raw_bytes,
            "raw_hash": raw_hash,
            "source_owner": "Legislative Department",
            "retrieval_method": "OFFICIAL_HTTPS_GET",
            "http_headers": {},
        }

        with patch.object(self.retriever, "fetch", return_value=mock_retrieval):
            res = self.pipeline.acquire_document(
                db=self.db,
                registry_id="india_code_central",
                document_id="evidence_act_test",
                title="The Evidence Act",
                official_url="https://indiacode.gov.in/doc",
                domain="CIVIL_CONTRACT",
            )

        ver_id = res["candidate_versions"][0]
        ver_record = self.db["legal_authority_versions"].find_one({"id": ver_id})
        candidate_source = ver_record["source"]

        # Adapt DB for VerifiedCorpus
        from backend.adapters.mongo.database import MongoDatabaseAdapter
        adapter = MongoDatabaseAdapter(db_name=self.test_db_name)
        corpus = VerifiedCorpus(adapter)

        # A: Candidate is NOT returned by corpus search
        search_results = corpus.search(domain="CIVIL_CONTRACT", jurisdiction="IN", query="Evidence Court judges")
        self.assertEqual(search_results, [], "REVIEW_PENDING candidate must NEVER be returned by VerifiedCorpus.search()")

        # B: Candidate cannot be accessed via corpus.get()
        self.assertIsNone(corpus.get(candidate_source["source_id"]))

        # C: Candidate fails validate_source() because it has not undergone independent primary review
        valid, reason = corpus.validate_source(candidate_source)
        self.assertFalse(valid)
        self.assertEqual(reason, "Independent primary authority review required")

    # ---------------------------------------------------------
    # 9. Reviewer Inspection Data Package
    # ---------------------------------------------------------
    def test_reviewer_inspection_data_package(self):
        statutory_body = "The National Cyber Act\n1. Short title and extent - Applies to cyber forensics.\n"
        raw_bytes = create_minimal_pdf(statutory_body)
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()

        mock_retrieval = {
            "registry_id": "india_code_central",
            "requested_url": "https://indiacode.gov.in/cyber",
            "final_url": "https://indiacode.gov.in/cyber",
            "redirect_chain": [],
            "retrieved_at": "2026-10-14T20:00:00+00:00",
            "http_status": 200,
            "content_type": "application/pdf",
            "byte_size": len(raw_bytes),
            "raw_bytes": raw_bytes,
            "raw_hash": raw_hash,
            "source_owner": "Legislative Department",
            "retrieval_method": "OFFICIAL_HTTPS_GET",
            "http_headers": {},
        }

        with patch.object(self.retriever, "fetch", return_value=mock_retrieval):
            res = self.pipeline.acquire_document(
                db=self.db,
                registry_id="india_code_central",
                document_id="cyber_inspection_test",
                title="The National Cyber Act",
                official_url="https://indiacode.gov.in/cyber",
                domain="CYBER",
            )

        ver_id = res["candidate_versions"][0]
        inspection = inspect_candidate_for_review(self.db, ver_id)
        self.assertIsNotNone(inspection)

        # Reviewer can inspect all necessary provenance and text items
        self.assertEqual(inspection["version_id"], ver_id)
        self.assertEqual(inspection["official_source"], "india_code_central")
        self.assertEqual(inspection["requested_url"], "https://indiacode.gov.in/cyber")
        self.assertEqual(inspection["raw_hash"], raw_hash)
        self.assertEqual(inspection["domain"], "CYBER")
        self.assertEqual(inspection["review_state"], "REVIEW_PENDING")
        self.assertFalse(inspection["source_reviewed"])
        self.assertFalse(inspection["temporal_reviewed"])
        self.assertTrue(inspection["raw_gridfs_file_id"])
        self.assertTrue(inspection["raw_gridfs_key"])
        self.assertIn("TEMPORAL_STATUS_UNVERIFIED", inspection["temporal_warnings"])


if __name__ == "__main__":
    unittest.main()
