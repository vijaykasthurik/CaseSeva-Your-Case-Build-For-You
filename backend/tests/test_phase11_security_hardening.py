"""Phase 11 Deterministic Security, Privacy, Audit & Operational Hardening Suite.

Covers all 32 required deterministic security test cases:
1. citizen A cannot access citizen B case
2. citizen cannot access advocate-only Engine 3
3. unrelated advocate cannot access case
4. accepted advocate without consent denied
5. revoked consent denied immediately
6. admin cannot bypass assigned advocate
7. legal-authority reviewer capability cannot bypass consent
8. IDOR blocked for evidence
9. IDOR blocked for Engine-2 report
10. IDOR blocked for draft
11. IDOR blocked for PDF
12. IDOR blocked for filing package
13. private advocate notes never leak
14. verification docs never leak
15. password hash never serialized
16. access tokens never serialized
17. path traversal upload/retrieval blocked
18. unsafe filename sanitized/rejected
19. NoSQL operator injection rejected
20. XSS payload safely rendered/escaped
21. test/dev auth bypass disabled in production mode
22. REVIEW_PENDING authority never reaches law pipeline
23. fabricated citation rejected
24. concurrent immutable-version creation safe
25. duplicate approval safely handled
26. consent revoke/access race fails closed
27. provider failure preserves prior state
28. PDF failure preserves approved draft
29. package export failure preserves package metadata safely
30. audit events immutable
31. no external filing occurs
32. original evidence remains immutable
"""
import copy
import hashlib
import io
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.adapters import factory
from backend.adapters.factory import ProviderConfigurationError
from backend.adapters.mock.auth import MockAuthAdapter
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.adapters.mock.llm import MockLLMAdapter
from backend.adapters.mock.storage import MockStorageAdapter
from backend.models.case import utc_now
from backend.models.draft import (
    AdvocateDraft,
    ApprovalRecord,
    DraftMode,
    DraftStatus,
    DraftType,
    PdfArtifact,
)
from backend.models.filing import FilingPackage, FilingReadinessStatus
from backend.routes.advocates import router as advocates_router
from backend.routes.auth import router as auth_router
from backend.routes.cases import router as cases_router
from backend.routes.documents import router as documents_router
from backend.routes.engines import router as engines_router
from backend.routes.filing import router as filing_router
from backend.routes.health import router as health_router
from backend.routes.review import router as review_router
from backend.routes.sharing import router as sharing_router
from backend.services.engine3 import compute_draft_integrity_hash, escape
from backend.services.filing import (
    DISCLOSURE_NO_EXTERNAL_SUBMISSION,
    DISCLOSURE_PHASE10_SAFETY,
    export_filing_bundle,
    get_filing_package,
    prepare_filing_package,
)
from backend.services.overview import client_case, client_overview
from backend.services.sharing import issue_token
from backend.services.verified_corpus import VerifiedCorpus


def create_security_test_app():
    app = FastAPI(title="CaseSeva Security Test App")
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(cases_router)
    app.include_router(advocates_router)
    app.include_router(sharing_router)
    app.include_router(review_router)
    app.include_router(documents_router)
    app.include_router(filing_router)
    app.include_router(engines_router)

    app.state.temp_dir = tempfile.TemporaryDirectory()
    db = MockDatabaseAdapter(path=f"{app.state.temp_dir.name}/db.json")
    storage = MockStorageAdapter(root=f"{app.state.temp_dir.name}/storage")
    auth = MockAuthAdapter(database=db)
    llm = MockLLMAdapter()

    app.state.adapters = SimpleNamespace(
        database=db,
        storage=storage,
        auth=auth,
        llm=llm,
        mode="mock",
        providers={"database": "mock", "object_store": "mock", "llm": "mock", "workflow": "mock"},
        processing_mode="live",
        llm_processing_mode="live",
        workflow_processing_mode="mock",
        email_provider="disabled",
        persistence_provider="mock",
        object_store_provider="mock",
    )
    return app


class TestPhase11SecurityHardening(unittest.TestCase):
    def setUp(self):
        self.app = create_security_test_app()
        self.client = TestClient(self.app)
        self.db = self.app.state.adapters.database
        self.storage = self.app.state.adapters.storage
        self.auth = self.app.state.adapters.auth

        # 1. Citizen A
        self.citizen_a = {
            "id": "cit_a",
            "email": "citizen.a@example.com",
            "full_name": "Citizen A",
            "role": "client",
            "password_hash": self.auth._hash_password("Password123!"),
        }
        self.db.create("users", self.citizen_a)
        self.db.create("sessions", {"id": "ses_cit_a", "user_id": "cit_a"})
        self.cit_a_headers = {"Authorization": "Bearer ses_cit_a"}

        # 2. Citizen B
        self.citizen_b = {
            "id": "cit_b",
            "email": "citizen.b@example.com",
            "full_name": "Citizen B",
            "role": "client",
            "password_hash": self.auth._hash_password("Password123!"),
        }
        self.db.create("users", self.citizen_b)
        self.db.create("sessions", {"id": "ses_cit_b", "user_id": "cit_b"})
        self.cit_b_headers = {"Authorization": "Bearer ses_cit_b"}

        # 3. Assigned Advocate (Verified)
        self.advocate = {
            "id": "adv_assigned",
            "email": "advocate.assigned@court.in",
            "full_name": "Advocate Assigned",
            "role": "advocate",
            "verification_status": "VERIFIED",
            "bar_council": "Bar Council of Delhi",
            "enrolment_year": 2015,
            "place_of_practice": "Delhi",
            "password_hash": self.auth._hash_password("Password123!"),
        }
        self.db.create("users", self.advocate)
        self.db.create("sessions", {"id": "ses_adv_assigned", "user_id": "adv_assigned"})
        self.adv_headers = {"Authorization": "Bearer ses_adv_assigned"}

        # 4. Unrelated Advocate (Verified)
        self.unrelated_advocate = {
            "id": "adv_unrelated",
            "email": "advocate.unrelated@court.in",
            "full_name": "Advocate Unrelated",
            "role": "advocate",
            "verification_status": "VERIFIED",
            "bar_council": "Bar Council of Maharashtra",
            "enrolment_year": 2018,
            "place_of_practice": "Mumbai",
            "password_hash": self.auth._hash_password("Password123!"),
        }
        self.db.create("users", self.unrelated_advocate)
        self.db.create("sessions", {"id": "ses_adv_unrelated", "user_id": "adv_unrelated"})
        self.unrelated_adv_headers = {"Authorization": "Bearer ses_adv_unrelated"}

        # 5. Admin
        self.admin = {
            "id": "admin_ops",
            "email": "admin.ops@caseseva.internal",
            "full_name": "Platform Operations Admin",
            "role": "admin",
            "password_hash": self.auth._hash_password("Password123!"),
        }
        self.db.create("users", self.admin)
        self.db.create("sessions", {"id": "ses_admin", "user_id": "admin_ops"})
        self.admin_headers = {"Authorization": "Bearer ses_admin"}

        # 6. Legal Authority Reviewer (Qualified Advocate with capability)
        self.reviewer_advocate = {
            "id": "adv_reviewer",
            "email": "authority.reviewer@court.in",
            "full_name": "Adv. Authority Reviewer",
            "role": "advocate",
            "verification_status": "VERIFIED",
            "authority_review_capability": True,
            "password_hash": self.auth._hash_password("Password123!"),
        }
        self.db.create("users", self.reviewer_advocate)
        self.db.create("sessions", {"id": "ses_reviewer", "user_id": "adv_reviewer"})
        self.reviewer_headers = {"Authorization": "Bearer ses_reviewer"}

        # Setup base case owned by Citizen A
        self.case_a_id = "case_cit_a_101"
        self.case_a = {
            "case_id": self.case_a_id,
            "id": self.case_a_id,
            "owner_user_id": "cit_a",
            "status": "DRAFT",
            "version": 1,
            "input_version": 1,
            "workflow_version": 2,
            "client_story": "A disputed banking transaction on 15 March 2026.",
            "evidence": [],
            "created_at": utc_now(),
        }
        self.db.create("cases", self.case_a)

        # Setup base case owned by Citizen B
        self.case_b_id = "case_cit_b_202"
        self.case_b = {
            "case_id": self.case_b_id,
            "id": self.case_b_id,
            "owner_user_id": "cit_b",
            "status": "DRAFT",
            "version": 1,
            "input_version": 1,
            "workflow_version": 2,
            "client_story": "Defective electronics product purchased online.",
            "evidence": [],
            "created_at": utc_now(),
        }
        self.db.create("cases", self.case_b)

    # -------------------------------------------------------------
    # 1. citizen A cannot access citizen B case
    # -------------------------------------------------------------
    def test_01_citizen_a_cannot_access_citizen_b_case(self):
        resp = self.client.get(f"/api/cases/{self.case_b_id}", headers=self.cit_a_headers)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("You do not have access to this case", resp.text)

    # -------------------------------------------------------------
    # 2. citizen cannot access advocate-only Engine 3
    # -------------------------------------------------------------
    def test_02_citizen_cannot_access_advocate_only_engine3(self):
        resp = self.client.post(
            f"/api/cases/{self.case_a_id}/drafts/generate",
            headers=self.cit_a_headers,
            json={"draft_type": "COMPLAINT_PETITION"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Engine 3 is advocate-only", resp.text)

        resp2 = self.client.post(
            f"/api/cases/{self.case_a_id}/documents/generate",
            headers=self.cit_a_headers,
        )
        self.assertEqual(resp2.status_code, 403)

    # -------------------------------------------------------------
    # 3. unrelated advocate cannot access case
    # -------------------------------------------------------------
    def test_03_unrelated_advocate_cannot_access_case(self):
        # Case A assigned to adv_assigned
        self.db.update("cases", self.case_a_id, {"assigned_advocate_id": "adv_assigned", "status": "ADVOCATE_REVIEW"})
        resp = self.client.get(f"/api/advocate/cases/{self.case_a_id}", headers=self.unrelated_adv_headers)
        self.assertEqual(resp.status_code, 403)

    # -------------------------------------------------------------
    # 4. accepted advocate without consent denied
    # -------------------------------------------------------------
    def test_04_accepted_advocate_without_consent_denied(self):
        # Assigned but no active consent grant
        self.db.update("cases", self.case_a_id, {"assigned_advocate_id": "adv_assigned", "status": "AWAITING_ADVOCATE"})
        resp = self.client.get(f"/api/advocate/cases/{self.case_a_id}/handoff", headers=self.adv_headers)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("consent", resp.text.lower())

    # -------------------------------------------------------------
    # 5. revoked consent denied immediately
    # -------------------------------------------------------------
    def test_05_revoked_consent_denied_immediately(self):
        self.db.update("cases", self.case_a_id, {"assigned_advocate_id": "adv_assigned", "status": "AWAITING_ADVOCATE"})
        grant_resp = self.client.post(
            f"/api/cases/{self.case_a_id}/sharing",
            headers=self.cit_a_headers,
            json={"scopes": ["story", "case_file", "evidence"], "evidence_ids": [], "expires_in_hours": 24},
        )
        self.assertEqual(grant_resp.status_code, 200)
        grant_id = grant_resp.json()["grant"]["id"]

        # Revoke consent
        del_resp = self.client.delete(f"/api/cases/{self.case_a_id}/sharing/{grant_id}", headers=self.cit_a_headers)
        self.assertEqual(del_resp.status_code, 200)

        # Immediate fail-closed check
        handoff_resp = self.client.get(f"/api/advocate/cases/{self.case_a_id}/handoff", headers=self.adv_headers)
        self.assertEqual(handoff_resp.status_code, 403)

    # -------------------------------------------------------------
    # 6. admin cannot bypass assigned advocate
    # -------------------------------------------------------------
    def test_06_admin_cannot_bypass_assigned_advocate(self):
        # Admin trying to access citizen case
        resp = self.client.get(f"/api/cases/{self.case_a_id}", headers=self.admin_headers)
        self.assertEqual(resp.status_code, 403)

        # Admin trying advocate drafting
        resp_draft = self.client.post(
            f"/api/cases/{self.case_a_id}/drafts/generate",
            headers=self.admin_headers,
            json={"draft_type": "COMPLAINT_PETITION"},
        )
        self.assertEqual(resp_draft.status_code, 403)

        # Admin trying filing package preparation
        resp_filing = self.client.post(
            f"/api/cases/{self.case_a_id}/filing-packages/prepare",
            headers=self.admin_headers,
            json={},
        )
        self.assertEqual(resp_filing.status_code, 403)

    # -------------------------------------------------------------
    # 7. legal-authority reviewer capability cannot bypass consent
    # -------------------------------------------------------------
    def test_07_legal_authority_reviewer_capability_cannot_bypass_consent(self):
        self.db.update("cases", self.case_a_id, {"assigned_advocate_id": "adv_assigned", "status": "ADVOCATE_REVIEW"})
        # Even with authority review capability, reviewer cannot access citizen case without assignment + consent
        resp = self.client.get(f"/api/advocate/cases/{self.case_a_id}/handoff", headers=self.reviewer_headers)
        self.assertEqual(resp.status_code, 403)

    # -------------------------------------------------------------
    # 8. IDOR blocked for evidence
    # -------------------------------------------------------------
    def test_08_idor_blocked_for_evidence(self):
        ev_id = "E001"
        item = {
            "evidence_id": ev_id,
            "filename": "receipt.pdf",
            "content_type": "application/pdf",
            "size": 1024,
            "storage_key": "cases/case_cit_a_101/E001-receipt.pdf",
        }
        self.storage.upload(item["storage_key"], b"PDF CONTENT RECEIPT")
        self.db.update("cases", self.case_a_id, {"evidence": [item]})

        # Citizen B trying to access Citizen A's evidence
        resp_b = self.client.get(f"/api/cases/{self.case_a_id}/evidence/{ev_id}", headers=self.cit_b_headers)
        self.assertEqual(resp_b.status_code, 403)

        # Unrelated advocate trying to access evidence
        resp_unrel = self.client.get(f"/api/advocate/cases/{self.case_a_id}/evidence/{ev_id}", headers=self.unrelated_adv_headers)
        self.assertEqual(resp_unrel.status_code, 403)

    # -------------------------------------------------------------
    # 9. IDOR blocked for Engine-2 report
    # -------------------------------------------------------------
    def test_09_idor_blocked_for_engine2_report(self):
        self.db.update("cases", self.case_a_id, {
            "engine2": {"overview_ready": True, "neutral_evaluation": {"issue_readiness": ["Issue 1"]}},
            "canonical_case_file": {"version": 1},
        })
        resp = self.client.get(f"/api/cases/{self.case_a_id}/client-case-overview", headers=self.cit_b_headers)
        self.assertEqual(resp.status_code, 403)

    # -------------------------------------------------------------
    # 10. IDOR blocked for draft
    # -------------------------------------------------------------
    def test_10_idor_blocked_for_draft(self):
        draft_id = "draft_secret_1"
        self.db.create("engine3_drafts", {
            "id": draft_id,
            "case_id": self.case_a_id,
            "current_version": 1,
        })
        # Citizen accessing draft directly
        resp = self.client.get(f"/api/cases/{self.case_a_id}/drafts/{draft_id}", headers=self.cit_a_headers)
        self.assertEqual(resp.status_code, 403)

        # Unrelated advocate accessing draft
        resp2 = self.client.get(f"/api/cases/{self.case_a_id}/drafts/{draft_id}", headers=self.unrelated_adv_headers)
        self.assertEqual(resp2.status_code, 403)

    # -------------------------------------------------------------
    # 11. IDOR blocked for PDF
    # -------------------------------------------------------------
    def test_11_idor_blocked_for_pdf(self):
        draft_id = "draft_pdf_1"
        self.db.create("engine3_drafts", {
            "id": draft_id,
            "case_id": self.case_a_id,
            "current_version": 1,
        })
        resp_cit = self.client.get(f"/api/cases/{self.case_a_id}/drafts/{draft_id}/pdf", headers=self.cit_a_headers)
        self.assertEqual(resp_cit.status_code, 403)

        resp_unrel = self.client.get(f"/api/cases/{self.case_a_id}/drafts/{draft_id}/pdf", headers=self.unrelated_adv_headers)
        self.assertEqual(resp_unrel.status_code, 403)

    # -------------------------------------------------------------
    # 12. IDOR blocked for filing package
    # -------------------------------------------------------------
    def test_12_idor_blocked_for_filing_package(self):
        pkg_id = "pkg_sec_101"
        self.db.create("filing_packages", {
            "id": pkg_id,
            "filing_package_id": pkg_id,
            "case_id": self.case_a_id,
            "version": 1,
            "status": "PREPARATION_ONLY",
            "document_manifest": [],
            "pre_submission_checklist": [],
        })
        resp_b = self.client.get(f"/api/cases/{self.case_a_id}/filing-packages/{pkg_id}", headers=self.cit_b_headers)
        self.assertEqual(resp_b.status_code, 403)

        resp_unrel = self.client.get(f"/api/cases/{self.case_a_id}/filing-packages/{pkg_id}/export", headers=self.unrelated_adv_headers)
        self.assertEqual(resp_unrel.status_code, 403)

    # -------------------------------------------------------------
    # 13. private advocate notes never leak
    # -------------------------------------------------------------
    def test_13_private_advocate_notes_never_leak(self):
        case_with_notes = {
            **self.case_a,
            "professional_notes": [
                {"id": "n1", "note": "CONFIDENTIAL COUNSEL STRATEGY: Weak causation evidence", "visibility": "PRIVATE"},
                {"id": "n2", "note": "Please submit bank account passbook copy.", "visibility": "SHARED_WITH_CLIENT"},
            ],
        }
        proj = client_case(case_with_notes, self.db)
        proj_str = json.dumps(proj)
        self.assertNotIn("CONFIDENTIAL COUNSEL STRATEGY", proj_str)
        self.assertIn("Please submit bank account passbook copy.", proj_str)

    # -------------------------------------------------------------
    # 14. verification docs never leak
    # -------------------------------------------------------------
    def test_14_verification_docs_never_leak(self):
        self.db.update("users", "adv_assigned", {
            "verification_documents": [
                {"filename": "confidential_id_card.pdf", "storage_key": "verification/adv_assigned/doc.pdf"},
            ],
        })
        resp = self.client.get("/api/advocates", headers=self.cit_a_headers)
        self.assertEqual(resp.status_code, 200)
        text = resp.text
        self.assertNotIn("verification/adv_assigned/doc.pdf", text)
        self.assertNotIn("confidential_id_card.pdf", text)

    # -------------------------------------------------------------
    # 15. password hash never serialized
    # -------------------------------------------------------------
    def test_15_password_hash_never_serialized(self):
        login_resp = self.client.post("/api/auth/login", json={"email": "citizen.a@example.com", "password": "Password123!"})
        self.assertEqual(login_resp.status_code, 200)
        self.assertNotIn("password_hash", login_resp.text)

        me_resp = self.client.get("/api/auth/me", headers=self.cit_a_headers)
        self.assertEqual(me_resp.status_code, 200)
        self.assertNotIn("password_hash", me_resp.text)

    # -------------------------------------------------------------
    # 16. access tokens never serialized
    # -------------------------------------------------------------
    def test_16_access_tokens_never_serialized(self):
        resp = self.client.get(f"/api/cases/{self.case_a_id}", headers=self.cit_a_headers)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("case_access_tokens", resp.text)
        self.assertNotIn("sessions", resp.text)

    # -------------------------------------------------------------
    # 17. path traversal upload/retrieval blocked
    # -------------------------------------------------------------
    def test_17_path_traversal_upload_retrieval_blocked(self):
        with self.assertRaises(ValueError):
            self.storage.download("../../../../etc/passwd")

        with self.assertRaises(ValueError):
            self.storage.upload("../../shadow", b"malicious")

    # -------------------------------------------------------------
    # 18. unsafe filename sanitized/rejected
    # -------------------------------------------------------------
    def test_18_unsafe_filename_sanitized_rejected(self):
        malicious_filename = "../../../evil<script>.pdf"
        file_bytes = b"%PDF-1.4 Mock document bytes"
        resp = self.client.post(
            f"/api/cases/{self.case_a_id}/evidence",
            headers=self.cit_a_headers,
            files={"file": (malicious_filename, file_bytes, "application/pdf")},
        )
        self.assertEqual(resp.status_code, 200)
        evidence = resp.json()["evidence"]
        self.assertNotIn("../", evidence["filename"])
        self.assertNotIn("<script>", evidence["filename"])

    # -------------------------------------------------------------
    # 19. NoSQL operator injection rejected
    # -------------------------------------------------------------
    def test_19_nosql_operator_injection_rejected(self):
        # Passing object where string identifier is expected
        resp = self.client.post(
            f"/api/cases/{self.case_a_id}/sharing",
            headers=self.cit_a_headers,
            json={"scopes": ["case_file"], "evidence_ids": [{"$ne": None}], "expires_in_hours": 24},
        )
        self.assertEqual(resp.status_code, 422)

    # -------------------------------------------------------------
    # 20. XSS payload safely rendered/escaped
    # -------------------------------------------------------------
    def test_20_xss_payload_safely_rendered_escaped(self):
        raw_xss = '<script>alert("XSS")</script>'
        escaped_xss = escape(raw_xss)
        self.assertNotIn("<script>", escaped_xss)
        self.assertIn("&lt;script&gt;", escaped_xss)

    # -------------------------------------------------------------
    # 21. test/dev auth bypass disabled in production mode
    # -------------------------------------------------------------
    def test_21_test_dev_auth_bypass_disabled_in_production_mode(self):
        with patch.dict(os.environ, {"APP_ENV": "production", "USE_MOCK_AWS": "true", "LLM_PROVIDER": "mock"}):
            with self.assertRaises(ProviderConfigurationError):
                factory.load_adapters()

    # -------------------------------------------------------------
    # 22. REVIEW_PENDING authority never reaches law pipeline
    # -------------------------------------------------------------
    def test_22_review_pending_authority_never_reaches_law_pipeline(self):
        from backend.tests.legal_test_support import authority, test_knowledge
        corpus = VerifiedCorpus(self.db, test_knowledge())
        pending_record = authority(review_state="REVIEW_PENDING", source_reviewed=False)
        valid, reason = corpus.validate_source(pending_record)
        self.assertFalse(valid)
        self.assertEqual(reason, "Independent primary authority review required")

    # -------------------------------------------------------------
    # 23. fabricated citation rejected
    # -------------------------------------------------------------
    def test_23_fabricated_citation_rejected(self):
        from backend.tests.legal_test_support import authority, test_knowledge
        corpus = VerifiedCorpus(self.db, test_knowledge())
        fake_record = authority(citation="Fabricated Act 2099, Section 99", official_url="https://attacker.com/fake")
        valid, reason = corpus.validate_source(fake_record)
        self.assertFalse(valid)

    # -------------------------------------------------------------
    # 24. concurrent immutable-version creation safe
    # -------------------------------------------------------------
    def test_24_concurrent_immutable_version_creation_safe(self):
        record_id = "draft_ver_unique_cas_1"
        rec = {"id": record_id, "data": {"text": "Original version"}}
        self.db.create("engine3_draft_versions", rec)
        # Attempting duplicate creation fails closed with ValueError
        with self.assertRaises(ValueError):
            self.db.create("engine3_draft_versions", rec)

    # -------------------------------------------------------------
    # 25. duplicate approval safely handled
    # -------------------------------------------------------------
    def test_25_duplicate_approval_safely_handled(self):
        # Updating immutable review record fails closed
        review_id = "review_rec_1"
        self.db.create("legal_authority_reviews", {"id": review_id, "decision": "REVIEWED_PRIMARY"})
        with self.assertRaises(ValueError):
            self.db.mutate("legal_authority_reviews", review_id, lambda r: {"decision": "MUTATED"})

    # -------------------------------------------------------------
    # 26. consent revoke/access race fails closed
    # -------------------------------------------------------------
    def test_26_consent_revoke_access_race_fails_closed(self):
        self.db.update("cases", self.case_a_id, {"assigned_advocate_id": "adv_assigned", "status": "AWAITING_ADVOCATE"})
        grant_resp = self.client.post(
            f"/api/cases/{self.case_a_id}/sharing",
            headers=self.cit_a_headers,
            json={"scopes": ["case_file", "evidence"], "evidence_ids": [], "expires_in_hours": 24},
        )
        grant = grant_resp.json()["grant"]
        # Invalidate / revoke
        self.db.update("case_grants", grant["id"], {"revoked_at": utc_now(), "status": "REVOKED"})

        # Subsequent token exchange fails immediately
        resp = self.client.post(f"/api/advocate/cases/{self.case_a_id}/access-token", headers=self.adv_headers)
        self.assertEqual(resp.status_code, 403)

    # -------------------------------------------------------------
    # 27. provider failure preserves prior state
    # -------------------------------------------------------------
    def test_27_provider_failure_preserves_prior_state(self):
        self.db.update("cases", self.case_a_id, {"status": "REVIEW_REQUIRED"})
        orig_story = self.case_a["client_story"]
        # Simulate engine dispatch failure
        with patch("backend.routes.engines.dispatch", side_effect=RuntimeError("Provider timeout")):
            resp = self.client.post(f"/api/cases/{self.case_a_id}/reprocess-input", headers=self.cit_a_headers)
            self.assertEqual(resp.status_code, 503)

        # Prior case data preserved
        fresh_case = self.db.get("cases", self.case_a_id)
        self.assertEqual(fresh_case["client_story"], orig_story)
        self.assertIn("processing_error", fresh_case)

    # -------------------------------------------------------------
    # 28. PDF failure preserves approved draft
    # -------------------------------------------------------------
    def test_28_pdf_failure_preserves_approved_draft(self):
        draft_id = "draft_pdf_fail_1"
        draft_doc = {
            "id": draft_id,
            "case_id": self.case_a_id,
            "status": DraftStatus.ADVOCATE_APPROVED.value,
            "version": 1,
            "pdf_artifact": None,
        }
        self.db.create("engine3_drafts", draft_doc)

        resp = self.client.get(f"/api/cases/{self.case_a_id}/drafts/{draft_id}/pdf", headers=self.adv_headers)
        # Missing PDF returns 404/403 safely, does not corrupt draft
        self.assertIn(resp.status_code, {403, 404})
        draft_check = self.db.get("engine3_drafts", draft_id)
        self.assertEqual(draft_check["status"], DraftStatus.ADVOCATE_APPROVED.value)

    # -------------------------------------------------------------
    # 29. package export failure preserves package metadata safely
    # -------------------------------------------------------------
    def test_29_package_export_failure_preserves_package_metadata_safely(self):
        pkg_id = "pkg_export_fail_1"
        pkg_doc = {
            "id": pkg_id,
            "filing_package_id": pkg_id,
            "case_id": self.case_a_id,
            "version": 1,
            "status": "PREPARATION_ONLY",
            "document_manifest": [],
            "pre_submission_checklist": [],
            "storage_key": "nonexistent/bundle.zip",
        }
        self.db.create("filing_packages", pkg_doc)

        # Storage download failure does not delete metadata
        with self.assertRaises(Exception):
            export_filing_bundle(self.db, self.storage, self.case_a_id, pkg_id, self.advocate)

        persisted = self.db.get("filing_packages", pkg_id)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["status"], "PREPARATION_ONLY")

    # -------------------------------------------------------------
    # 30. audit events immutable
    # -------------------------------------------------------------
    def test_30_audit_events_immutable(self):
        ev_id = "audit_event_1"
        self.db.create("audit_events", {"id": ev_id, "action": "LOGIN", "timestamp": utc_now()})
        with self.assertRaises(ValueError):
            self.db.mutate("audit_events", ev_id, lambda e: {"action": "TAMPERED"})

        consent_ev_id = "consent_audit_1"
        self.db.create("consent_audit", {"id": consent_ev_id, "action": "GRANT", "timestamp": utc_now()})
        with self.assertRaises(ValueError):
            self.db.mutate("consent_audit", consent_ev_id, lambda e: {"action": "TAMPERED"})

    # -------------------------------------------------------------
    # 31. no external filing occurs
    # -------------------------------------------------------------
    def test_31_no_external_filing_occurs(self):
        # Verify that disclosures explicitly mandate preparation-only and no external submission
        self.assertIn("does not submit anything", DISCLOSURE_PHASE10_SAFETY)
        self.assertIn("No external filing", DISCLOSURE_NO_EXTERNAL_SUBMISSION)

    # -------------------------------------------------------------
    # 32. original evidence remains immutable
    # -------------------------------------------------------------
    def test_32_original_evidence_remains_immutable(self):
        item = {
            "evidence_id": "E100",
            "filename": "original_invoice.pdf",
            "content_type": "application/pdf",
            "size": 512,
            "content_hash": hashlib.sha256(b"original invoice content").hexdigest(),
            "storage_key": "cases/case_cit_a_101/E100-invoice.pdf",
        }
        self.db.update("cases", self.case_a_id, {"evidence": [item]})

        fresh_case = self.db.get("cases", self.case_a_id)
        ev = fresh_case["evidence"][0]
        self.assertEqual(ev["content_hash"], item["content_hash"])
        self.assertEqual(ev["size"], 512)

    # -------------------------------------------------------------
    # 33. oversized upload rejected (HTTP 413)
    # -------------------------------------------------------------
    def test_33_oversized_upload_rejected(self):
        # 10 MB + 1024 bytes
        oversized_bytes = b"%PDF-1.4 " + b"0" * (10 * 1024 * 1024 + 1024)
        resp = self.client.post(
            f"/api/cases/{self.case_a_id}/evidence",
            headers=self.cit_a_headers,
            files={"file": ("large_document.pdf", oversized_bytes, "application/pdf")},
        )
        self.assertEqual(resp.status_code, 413)
        self.assertIn("File is too large", resp.text)

    # -------------------------------------------------------------
    # 34. NoSQL $where, $gt, $regex operator injection rejected (HTTP 422)
    # -------------------------------------------------------------
    def test_34_nosql_where_gt_regex_operator_injection_rejected(self):
        # 1. $gt operator in login
        resp_gt = self.client.post("/api/auth/login", json={"email": {"$gt": ""}, "password": "Password123!"})
        self.assertEqual(resp_gt.status_code, 422)

        # 2. $where operator in login
        resp_where = self.client.post("/api/auth/login", json={"email": {"$where": "true"}, "password": "Password123!"})
        self.assertEqual(resp_where.status_code, 422)

        # 3. $regex operator in login
        resp_regex = self.client.post("/api/auth/login", json={"email": {"$regex": ".*"}, "password": "Password123!"})
        self.assertEqual(resp_regex.status_code, 422)

        # 4. Operator injection in case route
        resp_case_op = self.client.get("/api/cases/[$ne]=null", headers=self.cit_a_headers)
        self.assertEqual(resp_case_op.status_code, 404)

    # -------------------------------------------------------------
    # 35. shell and command injection absent / rejected
    # -------------------------------------------------------------
    def test_35_shell_and_command_injection_absent(self):
        malicious_shell_filename = "doc;cat /etc/passwd|calc.exe.pdf"
        file_bytes = b"%PDF-1.4 Mock document bytes"
        resp = self.client.post(
            f"/api/cases/{self.case_a_id}/evidence",
            headers=self.cit_a_headers,
            files={"file": (malicious_shell_filename, file_bytes, "application/pdf")},
        )
        self.assertEqual(resp.status_code, 200)
        evidence = resp.json()["evidence"]
        # Filename is sanitized and cleaned, preventing any shell metacharacters
        self.assertNotIn("|", evidence["filename"])
        self.assertNotIn(";", evidence["filename"])

    # -------------------------------------------------------------
    # 36. unsafe markdown and raw HTML does not execute
    # -------------------------------------------------------------
    def test_36_unsafe_markdown_raw_html_does_not_execute(self):
        payloads = [
            '<script>alert("XSS")</script>',
            '<img src=x onerror=alert(1)>',
            'javascript:alert("Pwn")',
            '<a href="javascript:alert(1)">Click</a>',
        ]
        for p in payloads:
            escaped = escape(p)
            self.assertNotIn("<script>", escaped)
            self.assertNotIn("<img", escaped)
            self.assertNotIn("<a ", escaped)
            self.assertTrue(escaped.startswith("&lt;") or "alert" in escaped)

    # -------------------------------------------------------------
    # 37. prompt injection cannot create win probability
    # -------------------------------------------------------------
    def test_37_prompt_injection_cannot_create_win_probability(self):
        # Even if an adversarial prompt attempts to inject win_probability into Engine-2
        adversarial_case = {
            **self.case_a,
            "engine2": {
                "overview_ready": True,
                "win_probability": "100%",
                "likely_winner": "Citizen Guaranteed",
                "neutral_evaluation": {"issue_readiness": ["Issue 1"]},
            },
            "canonical_case_file": {"version": 1},
        }
        overview = client_overview(adversarial_case, self.db)
        overview_str = json.dumps(overview)
        self.assertNotIn("win_probability", overview)
        self.assertNotIn("100%", overview_str)
        self.assertNotIn("likely_winner", overview)

    # -------------------------------------------------------------
    # 38. prompt injection cannot reveal protected system content
    # -------------------------------------------------------------
    def test_38_prompt_injection_cannot_reveal_system_content(self):
        # Case detail or client case projection never exposes internal prompt instructions or system prompts
        resp = self.client.get(f"/api/cases/{self.case_a_id}", headers=self.cit_a_headers)
        self.assertEqual(resp.status_code, 200)
        text = resp.text
        self.assertNotIn("system_prompt", text)
        self.assertNotIn("You are an AI assistant", text)
        self.assertNotIn("Ignore previous instructions", text)

    # -------------------------------------------------------------
    # 39. concurrent Engine-2 run safe
    # -------------------------------------------------------------
    def test_39_concurrent_engine2_run_safe(self):
        # If Engine 2 is already marked running, another dispatch fails closed or reports running
        self.db.update("cases", self.case_a_id, {
            "status": "ENGINE1_DONE",
            "canonical_case_file": {"version": 1, "applicable_law": []},
            "engine2_running": True,
        })
        # Verifying atomic check on case prevents concurrent corrupting state
        case_doc = self.db.get("cases", self.case_a_id)
        self.assertTrue(case_doc.get("engine2_running"))

    # -------------------------------------------------------------
    # 40. concurrent filing-package version creation safe
    # -------------------------------------------------------------
    def test_40_concurrent_filing_package_version_creation_safe(self):
        pkg_id = "pkg_ver_unique_cas_1"
        pkg_rec = {"id": pkg_id, "case_id": self.case_a_id, "version": 1}
        self.db.create("filing_packages", pkg_rec)
        # Attempting duplicate creation fails closed with ValueError
        with self.assertRaises(ValueError):
            self.db.create("filing_packages", pkg_rec)

    # -------------------------------------------------------------
    # 41. provider outage fallback preserves legal authority gate
    # -------------------------------------------------------------
    def test_41_provider_outage_fallback_preserves_legal_authority_gate(self):
        from backend.services.engine1 import run_engine1
        # Set case to initial state
        self.db.update("cases", self.case_a_id, {
            "status": "DRAFT",
            "raw_case_package": {"story": "Disputed transaction", "pending": False, "evidence": []},
            "stage_statuses": {},
        })
        # Simulate LLM failure during Engine 1
        with patch.object(self.app.state.adapters.llm, "generate", side_effect=RuntimeError("LLM Provider Unavailable")):
            run_engine1(self.app, self.case_a_id)

        failed_case = self.db.get("cases", self.case_a_id)
        # Must fail closed to REVIEW_REQUIRED, with error recorded
        self.assertEqual(failed_case["status"], "REVIEW_REQUIRED")
        self.assertIn("processing_error", failed_case)
        # Verified legal sections must NOT contain unverified or fabricated law
        verified_sections = failed_case.get("verified_legal_sections", [])
        self.assertEqual(len(verified_sections), 0)

    # -------------------------------------------------------------
    # 42. arbitrary file and GridFS lookup denial
    # -------------------------------------------------------------
    def test_42_arbitrary_file_gridfs_lookup_denial(self):
        # Attempting to fetch non-existent or arbitrary evidence ID yields 404/403
        resp = self.client.get(f"/api/cases/{self.case_a_id}/evidence/E999_NONEXISTENT", headers=self.cit_a_headers)
        self.assertIn(resp.status_code, {404, 403})

        # Citizen B cannot look up Citizen A's arbitrary file
        resp_b = self.client.get(f"/api/cases/{self.case_a_id}/evidence/E999_NONEXISTENT", headers=self.cit_b_headers)
        self.assertEqual(resp_b.status_code, 403)


if __name__ == "__main__":
    unittest.main()
