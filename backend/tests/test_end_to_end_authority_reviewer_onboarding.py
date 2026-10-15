"""Deterministic isolated end-to-end test of CaseSeva authority-reviewer onboarding.

SYNTHETIC TEST ENVIRONMENT ONLY.
No genuine advocate onboarding.
No genuine human legal review.
No genuine legal authority was approved or modified by this test.
All credentials, tokens, and documents are purely synthetic test fixtures.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.adapters.mock.auth import MockAuthAdapter
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.adapters.mock.storage import MockStorageAdapter
from backend.adapters.mongo.database import MongoDatabaseAdapter
from backend.models.case import utc_now
from backend.routes.advocates import router as advocates_router
from backend.routes.auth import router as auth_router
from backend.routes.authorities import router as authorities_router
from backend.services.admin_promotion import promote_existing_user_to_admin
from backend.services.authority_review import (
    AUTHORITY_REVIEW_CAPABILITY,
    AuthorityReview,
    is_authorized_authority_reviewer,
)
from backend.services.legal_knowledge import LegalKnowledge
from backend.services.verified_corpus import VerifiedCorpus


class _WorkflowHarness:
    """Shared workflow runner across mock and disposable Mongo adapters."""

    def init_runtime(self, db):
        self.db = db
        self.temp_dir = tempfile.TemporaryDirectory()

        self.storage = MockStorageAdapter(Path(self.temp_dir.name) / "uploads")
        self.auth = MockAuthAdapter(self.db, seed_demo=False)

        # Knowledge fixture allowing synthetic test registry host
        self.knowledge = LegalKnowledge()
        self.knowledge.sources["synthetic_registry"] = {
            "tier": "PRIMARY",
            "enabled": True,
            "hosts": ["verification.example.test"],
            "refresh_days": 30,
        }

        self.app = FastAPI()
        self.app.state.adapters = SimpleNamespace(
            database=self.db,
            storage=self.storage,
            auth=self.auth,
            email_provider="mock",
            mode="mock",
            processing_mode="mock",
            llm_processing_mode="mock",
        )
        self.app.include_router(auth_router)
        self.app.include_router(advocates_router)
        self.app.include_router(authorities_router)
        self.client = TestClient(self.app)

    def cleanup_runtime(self):
        self.temp_dir.cleanup()

    def run_complete_workflow(self, test_case: unittest.TestCase):
        """Prove the complete workflow through supported application interfaces:

        1. Synthetic normal user signup -> client
        2. Promote to platform admin via supported admin-promotion workflow
        3. Synthetic advocate signup -> role=advocate, VERIFICATION_PENDING, no docs yet
        4. Authenticate advocate
        5. Verify that admin verification without supporting documents fails (409)
        6. Upload synthetic verification document -> VERIFICATION_PENDING, doc stored
        7. Authenticate synthetic platform admin
        8. Admin verification via official source -> VERIFIED
        9. Admin grants LEGAL_AUTHORITY_REVIEW -> capabilities contains capability
        10. Advocate authority review authorization:
           - expected-version enforcement
           - self-review rejected
           - stale version rejected
           - authorized independent review succeeds
           - receipt immutability enforced
        11. Revoke LEGAL_AUTHORITY_REVIEW:
           - role remains advocate, status remains VERIFIED
           - capability removed
           - post-revoke review attempt denied (403)
           - idempotent revoke confirmed
        """
        # =====================================================================
        # 1. SYNTHETIC PLATFORM ADMIN SETUP
        # =====================================================================
        admin_password = secrets.token_urlsafe(16)
        admin_email = f"test-platform-admin-{uuid4().hex[:8]}@example.test"
        admin_signup_payload = {
            "full_name": "CaseSeva Test Platform Admin",
            "email": admin_email,
            "mobile_number": "9876543210",
            "password": admin_password,
            "preferred_language": "English",
            "state": "Tamil Nadu",
            "district_city": "Chennai",
            "role": "client",
        }

        signup_resp = self.client.post("/api/auth/signup", json=admin_signup_payload)
        test_case.assertEqual(signup_resp.status_code, 201, signup_resp.text)
        admin_user = signup_resp.json()["user"]
        admin_id = admin_user["id"]
        test_case.assertEqual(admin_user["role"], "client")

        # Promote via supported admin-promotion workflow
        promotion_result = promote_existing_user_to_admin(self.db, admin_email)
        test_case.assertEqual(promotion_result["status"], "promoted")
        test_case.assertEqual(promotion_result["user_id"], admin_id)

        # Confirm admin state in isolated DB
        admin_db_record = self.db.get("users", admin_id)
        test_case.assertEqual(admin_db_record["role"], "admin")
        test_case.assertIsNotNone(admin_db_record.get("admin_role_intent_id"))
        test_case.assertEqual(len(self.db.list("admin_role_audit")), 1)

        # Authenticate admin
        admin_login_resp = self.client.post("/api/auth/login", json={"email": admin_email, "password": admin_password})
        test_case.assertEqual(admin_login_resp.status_code, 200, admin_login_resp.text)
        admin_session_token = admin_login_resp.json()["session_token"]
        admin_headers = {"Authorization": f"Bearer {admin_session_token}"}

        # =====================================================================
        # 2. SYNTHETIC ADVOCATE SIGNUP
        # =====================================================================
        advocate_password = secrets.token_urlsafe(16)
        advocate_email = f"test-advocate-{uuid4().hex[:8]}@example.test"
        advocate_enrolment = f"SYNTHETIC/TN/TEST/2026/{uuid4().hex[:6].upper()}"
        advocate_signup_payload = {
            "full_name": "CaseSeva Test Advocate",
            "email": advocate_email,
            "mobile_number": "9876543211",
            "password": advocate_password,
            "preferred_language": "English",
            "state": "Tamil Nadu",
            "district_city": "Chennai",
            "role": "advocate",
            "bar_council": "TEST BAR COUNCIL - SYNTHETIC",
            "enrolment_number": advocate_enrolment,
            "enrolment_year": 2020,
            "place_of_practice": "Synthetic Test Court",
            "court_region": "TEST_REGION",
            "practice_domains": ["TEST_LEGAL_DOMAIN"],
            "languages": ["English"],
        }

        adv_signup_resp = self.client.post("/api/auth/signup", json=advocate_signup_payload)
        test_case.assertEqual(adv_signup_resp.status_code, 201, adv_signup_resp.text)
        advocate_user = adv_signup_resp.json()["user"]
        advocate_id = advocate_user["id"]
        test_case.assertEqual(advocate_user["role"], "advocate")
        test_case.assertEqual(advocate_user.get("verification_status"), "VERIFICATION_PENDING")
        test_case.assertFalse(advocate_user.get("verification_documents"))

        # Authenticate advocate
        adv_login_resp = self.client.post("/api/auth/login", json={"email": advocate_email, "password": advocate_password})
        test_case.assertEqual(adv_login_resp.status_code, 200, adv_login_resp.text)
        advocate_session_token = adv_login_resp.json()["session_token"]
        advocate_headers = {"Authorization": f"Bearer {advocate_session_token}"}

        # Verification attempt before uploading document must be rejected (409)
        verification_payload = {
            "status": "VERIFIED",
            "reason": "Synthetic test verification against test official source",
            "official_source_url": "https://verification.example.test/advocates/test-record",
            "official_record_reference": "TEST-ENROLMENT-RECORD-001",
            "reviewer_id": admin_id,
            "reviewed_at": utc_now(),
        }
        with patch.dict(os.environ, {"ADMIN_VERIFICATION_HOSTS": "verification.example.test", "ADMIN_TOKEN": ""}):
            premature_verify = self.client.post(
                f"/api/admin/advocates/{advocate_id}/verification",
                headers=admin_headers,
                json=verification_payload,
            )
            test_case.assertEqual(premature_verify.status_code, 409)
            test_case.assertIn("supporting enrolment documents", premature_verify.text)

        # =====================================================================
        # 3. SYNTHETIC VERIFICATION DOCUMENT UPLOAD
        # =====================================================================
        synthetic_pdf = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n"
            b"0000000101 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"
            b"% CASESEVA SYNTHETIC ADVOCATE VERIFICATION TEST DOCUMENT\n"
            b"% NOT A REAL BAR COUNCIL RECORD\n"
        )

        doc_upload_resp = self.client.post(
            "/api/auth/advocate-verification-documents",
            headers=advocate_headers,
            files={"file": ("synthetic_verification_doc.pdf", synthetic_pdf, "application/pdf")},
        )
        test_case.assertEqual(doc_upload_resp.status_code, 200, doc_upload_resp.text)
        test_case.assertEqual(doc_upload_resp.json().get("status"), "VERIFICATION_PENDING")

        # Confirm advocate status in isolated DB
        adv_db_record = self.db.get("users", advocate_id)
        test_case.assertEqual(adv_db_record["role"], "advocate")
        test_case.assertEqual(adv_db_record["verification_status"], "VERIFICATION_PENDING")
        test_case.assertEqual(len(adv_db_record.get("verification_documents", [])), 1)

        # =====================================================================
        # 4. PLATFORM-ADMIN OFFICIAL-SOURCE VERIFICATION
        # =====================================================================
        verification_payload["reviewed_at"] = utc_now()
        with patch.dict(os.environ, {"ADMIN_VERIFICATION_HOSTS": "verification.example.test", "ADMIN_TOKEN": ""}):
            # Non-admin cannot verify
            client_denied_resp = self.client.post(
                f"/api/admin/advocates/{advocate_id}/verification",
                headers=advocate_headers,
                json=verification_payload,
            )
            test_case.assertEqual(client_denied_resp.status_code, 403)

            # Admin verifies successfully
            admin_verify_resp = self.client.post(
                f"/api/admin/advocates/{advocate_id}/verification",
                headers=admin_headers,
                json=verification_payload,
            )
            test_case.assertEqual(admin_verify_resp.status_code, 200, admin_verify_resp.text)

        # Confirm advocate is VERIFIED
        adv_db_record = self.db.get("users", advocate_id)
        test_case.assertEqual(adv_db_record["role"], "advocate")
        test_case.assertEqual(adv_db_record["verification_status"], "VERIFIED")
        test_case.assertEqual(adv_db_record["verification_basis"]["official_record_reference"], "TEST-ENROLMENT-RECORD-001")
        test_case.assertFalse(is_authorized_authority_reviewer(adv_db_record))

        # =====================================================================
        # 5. GRANT LEGAL_AUTHORITY_REVIEW CAPABILITY
        # =====================================================================
        grant_url = f"/api/admin/advocates/{advocate_id}/capabilities/legal-authority-review"
        grant_payload = {
            "confirmation": "GRANT LEGAL AUTHORITY REVIEW",
            "reason": "Synthetic qualification checked for isolated automated testing",
        }

        with patch.dict(os.environ, {"ADMIN_TOKEN": ""}):
            # Non-admin cannot grant
            adv_grant_denied = self.client.post(grant_url, headers=advocate_headers, json=grant_payload)
            test_case.assertEqual(adv_grant_denied.status_code, 403)

            # Missing confirmation phrase rejected
            invalid_phrase_resp = self.client.post(
                grant_url,
                headers=admin_headers,
                json={"confirmation": "INVALID PHRASE", "reason": "test"},
            )
            test_case.assertEqual(invalid_phrase_resp.status_code, 422)

            # Platform admin grants capability
            grant_resp = self.client.post(grant_url, headers=admin_headers, json=grant_payload)
            test_case.assertEqual(grant_resp.status_code, 200, grant_resp.text)
            test_case.assertEqual(grant_resp.json().get("capability_granted"), "LEGAL_AUTHORITY_REVIEW")

        # Confirm advocate has capability and role is still advocate (NO role promotion)
        adv_db_record = self.db.get("users", advocate_id)
        test_case.assertEqual(adv_db_record["role"], "advocate")
        test_case.assertEqual(adv_db_record["verification_status"], "VERIFIED")
        test_case.assertIn(AUTHORITY_REVIEW_CAPABILITY, adv_db_record.get("capabilities", []))
        test_case.assertTrue(is_authorized_authority_reviewer(adv_db_record))

        # Confirm exactly 1 grant audit exists in authority_reviewer_grants
        grants = self.db.list("authority_reviewer_grants")
        test_case.assertEqual(len(grants), 1)
        test_case.assertEqual(grants[0]["action"], "GRANT")
        test_case.assertEqual(grants[0]["target_user_id"], advocate_id)
        test_case.assertEqual(grants[0]["granter_id"], admin_id)
        test_case.assertEqual(grants[0]["capability"], AUTHORITY_REVIEW_CAPABILITY)

        # =====================================================================
        # 6. SYNTHETIC AUTHORITY REVIEW AUTHORIZATION TEST
        # =====================================================================
        corpus = VerifiedCorpus(self.db, knowledge=self.knowledge)
        workflow = AuthorityReview(corpus)

        quote = "1. Synthetic test provision operative text for isolated test harness."
        text = "SYNTHETIC TEST ACT\n" + quote
        now = utc_now()
        raw_hash = hashlib.sha256(b"synthetic_raw_data").hexdigest()
        content_hash = hashlib.sha256(text.encode()).hexdigest()

        # Seed synthetic parsed ingestion record
        ingestion_id = "synthetic_ingestion_req_001"
        self.db.create(
            "legal_ingestion_requests",
            {
                "id": ingestion_id,
                "registry_id": "synthetic_registry",
                "official_url": "https://verification.example.test/acts/synthetic_test_act.pdf",
                "final_url": "https://verification.example.test/acts/synthetic_test_act.pdf",
                "retrieved_at": now,
                "raw_hash": raw_hash,
                "content_hash": content_hash,
                "official_text": text,
                "state": "PARSED",
                "created_at": now,
            },
        )

        # Candidate 1: Submitted by synthetic third party (valid for independent review)
        cand1 = {
            "source_id": "synthetic_test_authority_s1",
            "family": "synthetic_family",
            "source_type": "STATUTE",
            "domain": "TEST_LEGAL_DOMAIN",
            "jurisdiction": "IN",
            "title": "SYNTHETIC TEST ACT",
            "section": "1",
            "citation": "SYNTHETIC TEST ACT, section 1",
            "official_url": "https://verification.example.test/acts/synthetic_test_act.pdf",
            "final_url": "https://verification.example.test/acts/synthetic_test_act.pdf",
            "registry_id": "synthetic_registry",
            "source_language": "en",
            "official_text": text,
            "quote": quote,
            "section_start": text.index(quote),
            "section_end": len(text),
            "content_hash": content_hash,
            "raw_hash": raw_hash,
            "retrieved_at": now,
            "ingestion_id": ingestion_id,
            "effective_from": "2026-01-01",
            "temporal_source_ids": ["synthetic_test_authority_s1"],
            "temporal_reviewed": False,
            "rules_reviewed": False,
            "rules": {},
            "version_note": "SYNTHETIC TEST FIXTURE ONLY",
            "corpus_version": "synthetic-v1",
        }
        sub1 = workflow.submit(cand1, actor="synthetic-ingestor")
        v1 = sub1["version_id"]

        # Candidate 2: Submitted by the advocate (to test self-review rejection)
        cand2 = {**cand1, "source_id": "synthetic_test_authority_s2", "citation": "SYNTHETIC TEST ACT, section 2"}
        sub2 = workflow.submit(cand2, actor=advocate_id)
        v2 = sub2["version_id"]

        # Ensure genuine Phase-4 candidates remain untouched
        for prohibited in ("dspe_act_1946_s1", "it_act_2000_s1", "wages_code_2019_s1"):
            test_case.assertIsNone(self.db.get("legal_authority_heads", prohibited))

        with patch("backend.routes.authorities.VerifiedCorpus", return_value=corpus):
            # Test 6a: Self-review rejection
            self_review_resp = self.client.post(
                "/api/admin/authorities/synthetic_test_authority_s2/review",
                headers=advocate_headers,
                json={
                    "expected_version": v2,
                    "decision": "REVIEWED_PRIMARY",
                    "note": "Self-review attempt must fail",
                },
            )
            test_case.assertEqual(self_review_resp.status_code, 403, self_review_resp.text)
            test_case.assertIn("submitter cannot independently review", self_review_resp.text)

            # Test 6b: Stale version rejection
            stale_review_resp = self.client.post(
                "/api/admin/authorities/synthetic_test_authority_s1/review",
                headers=advocate_headers,
                json={
                    "expected_version": "stale_version_hash_00000000000000",
                    "decision": "REVIEWED_PRIMARY",
                    "note": "Stale version attempt must fail",
                },
            )
            test_case.assertEqual(stale_review_resp.status_code, 409, stale_review_resp.text)
            test_case.assertIn("Authority revision changed", stale_review_resp.text)

            # Test 6c: Platform admin CANNOT review
            admin_review_resp = self.client.post(
                "/api/admin/authorities/synthetic_test_authority_s1/review",
                headers=admin_headers,
                json={
                    "expected_version": v1,
                    "decision": "REVIEWED_PRIMARY",
                    "note": "Admin review must be rejected",
                },
            )
            test_case.assertEqual(admin_review_resp.status_code, 403, admin_review_resp.text)
            test_case.assertIn("Platform administrators are not legal reviewers", admin_review_resp.text)

            # Test 6d: Authorized independent advocate review SUCCEEDS
            valid_review_resp = self.client.post(
                "/api/admin/authorities/synthetic_test_authority_s1/review",
                headers=advocate_headers,
                json={
                    "expected_version": v1,
                    "decision": "REVIEWED_PRIMARY",
                    "note": "Synthetic independent advocate review approved for isolated E2E test",
                },
            )
            test_case.assertEqual(valid_review_resp.status_code, 200, valid_review_resp.text)

        # Confirm review receipt was created in DB
        head = self.db.get("legal_authority_heads", "synthetic_test_authority_s1")
        test_case.assertIsNotNone(head)
        reviewed_version = self.db.get("legal_authority_versions", head["version"])
        test_case.assertEqual(reviewed_version["source"]["review_state"], "REVIEWED_PRIMARY")
        test_case.assertEqual(reviewed_version["source"]["reviewed_by"], advocate_id)

        reviews = [r for r in self.db.list("legal_authority_reviews") if r["source_id"] == "synthetic_test_authority_s1"]
        test_case.assertEqual(len(reviews), 1)
        receipt = reviews[0]
        test_case.assertEqual(receipt["decision"], "REVIEWED_PRIMARY")
        test_case.assertEqual(receipt["reviewer_id"], advocate_id)

        # Receipt immutability: Cannot update or delete receipt
        with test_case.assertRaises(ValueError):
            self.db.update("legal_authority_reviews", receipt["id"], {"decision": "REJECTED"})
        with test_case.assertRaises(ValueError):
            self.db.delete("legal_authority_reviews", receipt["id"])

        # =====================================================================
        # 7. REVOKE LEGAL_AUTHORITY_REVIEW CAPABILITY
        # =====================================================================
        revoke_payload = {
            "confirmation": "REVOKE LEGAL AUTHORITY REVIEW",
            "reason": "Synthetic capability revocation for isolated automated test",
        }

        with patch.dict(os.environ, {"ADMIN_TOKEN": ""}):
            revoke_resp = self.client.request("DELETE", grant_url, headers=admin_headers, json=revoke_payload)
            test_case.assertEqual(revoke_resp.status_code, 200, revoke_resp.text)
            test_case.assertEqual(revoke_resp.json().get("capability_revoked"), "LEGAL_AUTHORITY_REVIEW")

        # Confirm advocate status and capability removal
        adv_db_record = self.db.get("users", advocate_id)
        test_case.assertEqual(adv_db_record["role"], "advocate")
        test_case.assertEqual(adv_db_record["verification_status"], "VERIFIED")
        test_case.assertNotIn(AUTHORITY_REVIEW_CAPABILITY, adv_db_record.get("capabilities", []))
        test_case.assertFalse(is_authorized_authority_reviewer(adv_db_record))

        # Confirm audit count: exactly 2 (GRANT, then REVOKE)
        grants_after = self.db.list("authority_reviewer_grants")
        test_case.assertEqual(len(grants_after), 2)
        test_case.assertEqual(grants_after[1]["action"], "REVOKE")
        test_case.assertEqual(grants_after[1]["target_user_id"], advocate_id)

        # Test 7a: Post-revoke denial
        cand3 = {**cand1, "source_id": "synthetic_test_authority_s3", "citation": "SYNTHETIC TEST ACT, section 3"}
        sub3 = workflow.submit(cand3, actor="synthetic-ingestor")
        v3 = sub3["version_id"]

        with patch("backend.routes.authorities.VerifiedCorpus", return_value=corpus):
            post_revoke_resp = self.client.post(
                "/api/admin/authorities/synthetic_test_authority_s3/review",
                headers=advocate_headers,
                json={
                    "expected_version": v3,
                    "decision": "REVIEWED_PRIMARY",
                    "note": "Post-revoke review attempt must fail",
                },
            )
            test_case.assertEqual(post_revoke_resp.status_code, 403, post_revoke_resp.text)
            test_case.assertIn("Administrator or authorized legal authority reviewer access required", post_revoke_resp.text)

        # Also confirm service-level enforcement raises PermissionError directly
        with test_case.assertRaises(PermissionError) as ctx:
            workflow.decide(
                "synthetic_test_authority_s3",
                v3,
                reviewer=self.db.get("users", advocate_id),
                decision="REVIEWED_PRIMARY",
                note="Service-level post-revoke attempt",
            )
        test_case.assertIn("Explicit LEGAL_AUTHORITY_REVIEW capability required", str(ctx.exception))

        # Test 7b: Idempotent revoke
        with patch.dict(os.environ, {"ADMIN_TOKEN": ""}):
            second_revoke_resp = self.client.request("DELETE", grant_url, headers=admin_headers, json=revoke_payload)
            test_case.assertEqual(second_revoke_resp.status_code, 200, second_revoke_resp.text)

        # Confirm no extra audit created on idempotent revoke
        test_case.assertEqual(len(self.db.list("authority_reviewer_grants")), 2)


class TestEndToEndAuthorityReviewerOnboardingMock(unittest.TestCase):
    """Run E2E test using MockDatabaseAdapter (offline isolated environment)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = MockDatabaseAdapter(Path(temp.name) / "test.json")
        self.harness = _WorkflowHarness()
        self.harness.init_runtime(db)
        self.addCleanup(self.harness.cleanup_runtime)

    def test_complete_reviewer_onboarding_lifecycle(self):
        self.harness.run_complete_workflow(self)


class TestEndToEndAuthorityReviewerOnboardingMongo(unittest.TestCase):
    """Run E2E test using MongoDatabaseAdapter against a disposable test DB."""

    def setUp(self):
        test_db_name = f"caseseva_test_e2e_{uuid4().hex}"
        try:
            db = MongoDatabaseAdapter(test_db_name, "mongodb://127.0.0.1:27017")
            db.db.client.server_info()
        except Exception as exc:
            self.skipTest(f"MongoDB offline or unavailable: {exc}")
        self.addCleanup(lambda: db.db.client.drop_database(test_db_name))
        self.harness = _WorkflowHarness()
        self.harness.init_runtime(db)
        self.addCleanup(self.harness.cleanup_runtime)

    def test_complete_reviewer_onboarding_lifecycle(self):
        # Real database safety verification: inspect real caseseva database
        client = self.harness.db.db.client
        real_db = client["caseseva"]
        protected_collections = [
            "legal_authority_heads",
            "legal_authority_versions",
            "legal_authority_reviews",
            "legal_review_submissions",
            "legal_revision_requests",
            "authority_reviewer_grants",
            "users",
            "admin_role_audit",
        ]
        counts_before = {col: real_db[col].count_documents({}) for col in protected_collections}
        admin_before = list(real_db.users.find({"role": "admin"}))

        # Execute full synthetic workflow
        self.harness.run_complete_workflow(self)

        # Confirm real caseseva collections are completely unchanged
        counts_after = {col: real_db[col].count_documents({}) for col in protected_collections}
        self.assertEqual(counts_before, counts_after)
        admin_after = list(real_db.users.find({"role": "admin"}))
        self.assertEqual(len(admin_before), len(admin_after))
        self.assertEqual([a.get("email") for a in admin_before], [a.get("email") for a in admin_after])


if __name__ == "__main__":
    unittest.main()
