from unittest.mock import patch
import unittest
from backend.tests import test_sharing_overview as sharing_tests
from backend.routes.review import router
from backend.services.engine1 import run_engine1


class ReviewTests(unittest.TestCase):
    accepted = sharing_tests.SharingTests.accepted
    grant = sharing_tests.SharingTests.grant
    tearDown = sharing_tests.SharingTests.tearDown
    def setUp(self):
        sharing_tests.SharingTests.setUp(self)
        self.app.include_router(router)
        self.accepted()
        self.grant()

    def test_correction_is_audited_and_invalidates_documents(self):
        self.app.state.adapters.database.update("cases", self.id, {"document_version": 1})
        response = self.client.post(f"/api/advocate/cases/{self.id}/review", headers=self.access, json={"kind": "fact", "target_id": "F001", "action": "edit", "value": {"text": "Advocate corrected fact"}, "reason": "Checked client records"})
        self.assertEqual(response.status_code, 200)
        case = self.app.state.adapters.database.get("cases", self.id)
        self.assertTrue(case["documents_outdated"])
        self.assertEqual(case["recommended_engine1_start"], "FACT_EXTRACTION")
        self.assertEqual(case["advocate_audit"][-1]["previous"]["text"], "Private client story")
        self.assertEqual(case["advocate_audit"][-1]["new"]["text"], "Advocate corrected fact")

    def test_targeted_engine1_rerun_preserves_corrections_and_skips_earlier_stages(self):
        self.client.post(f"/api/advocate/cases/{self.id}/review", headers=self.access, json={"kind": "fact", "target_id": "F001", "action": "edit", "value": {"text": "Checked correction"}, "reason": "Checked record"})
        with patch("backend.services.engine1.build_raw_package", side_effect=AssertionError("No input extraction on targeted rerun")):
            run_engine1(self.app, self.id, start_stage="FACT_EXTRACTION")
        case = self.app.state.adapters.database.get("cases", self.id)
        self.assertEqual(case["status"], "ADVOCATE_REVIEW")
        self.assertEqual(case["case_file"]["facts"][0]["text"], "Checked correction")
        self.assertNotIn("INTAKE_CLEANING", case["stage_statuses"])

    def test_engine_boundary_and_input_consent_are_enforced_for_reruns(self):
        response = self.client.post(f"/api/advocate/cases/{self.id}/rerun", headers=self.access, json={"engine": 2, "start_stage": "FACT_EXTRACTION"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.post(f"/api/advocate/cases/{self.id}/rerun", headers=self.access, json={"engine": 1}).status_code, 403)

    def test_ordinary_approval_cannot_verify_forum(self):
        response = self.client.post(f"/api/advocate/cases/{self.id}/review", headers=self.access, json={"kind": "forum", "target_id": "forum", "action": "approve", "reason": "Looks right"})
        self.assertEqual(response.status_code, 409)

    def test_client_cannot_review_or_approve(self):
        self.assertEqual(self.client.post(f"/api/advocate/cases/{self.id}/approve", headers=self.headers).status_code, 403)

    def test_manual_authority_requires_exact_official_proof_then_separate_approval(self):
        from backend.models.case import utc_now
        proof = {"title": "Test authority - not real law", "official_text": "Synthetic test source text", "quote": "test source", "source_url": "https://www.indiacode.nic.in/test-only", "retrieved_at": utc_now()}
        body = {"kind": "pending", "target_id": "TEST-ONLY", "action": "verify", "value": proof, "reason": "Synthetic permission test"}
        endpoint = f"/api/advocate/cases/{self.id}/review"
        body["value"]["quote"] = "not present"
        self.assertEqual(self.client.post(endpoint, headers=self.access, json=body).status_code, 422)
        body["value"]["quote"] = "test source"
        self.assertEqual(self.client.post(endpoint, headers=self.access, json=body).status_code, 200)
        case = self.app.state.adapters.database.get("cases", self.id)
        self.assertEqual(case["case_file"]["applicable_law"][0]["verification_method"], "ADVOCATE_MANUAL_REVIEW")
        self.assertNotIn("provision:TEST-ONLY", case["advocate_approved_items"])
        self.assertEqual(case["advocate_audit"][-1]["advocate_id"], "seed-verified-advocate")

    def test_legacy_evidence_routes_cannot_bypass_versioned_scope_review(self):
        for action in ("approve", "remove"):
            response = self.client.post(f"/api/advocate/cases/{self.id}/evidence/E001/{action}", headers=self.access)
            self.assertEqual(response.status_code, 410)
