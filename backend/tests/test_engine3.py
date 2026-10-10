import unittest
from unittest.mock import patch
from backend.tests import test_sharing_overview as shared
from backend.routes.documents import router
from backend.services.engine3 import filing_pack, FILING_CONFIRMATION, consistency, MANDATORY_SECTIONS
from backend.services.engine3 import run_engine3


class Engine3Tests(unittest.TestCase):
    tearDown = shared.SharingTests.tearDown
    accepted = shared.SharingTests.accepted
    grant = shared.SharingTests.grant

    def setUp(self):
        shared.SharingTests.setUp(self)
        self.app.include_router(router)
        self.accepted()
        grant = self.grant()
        db = self.app.state.adapters.database
        db.update("case_grants", grant["id"], {"scopes": ["case_file", "evidence", "engine2"]})
        case = db.get("cases", self.id)
        db.update("cases", self.id, {"status": "ADVOCATE_APPROVED", "advocate_approved_case_file_version": case["case_file"]["version"]})
        for kind in ("client_case_overview", "professional_legal_draft", "report", "draft"):
            db.create("documents", {"id": kind, "case_id": self.id, "type": kind, "version": 1, "html": "<h1>" + kind + "</h1>", "created_at": "2026-01-01"})

    def test_client_cannot_execute_engine3(self):
        for action in ("generate", "regenerate"):
            self.assertEqual(self.client.post(f"/api/cases/{self.id}/documents/{action}", headers=self.headers).status_code, 403)

    def test_output_b_is_blocked_at_list_view_download_and_consistency(self):
        response = self.client.get(f"/api/cases/{self.id}/documents", headers=self.headers)
        self.assertEqual([item["type"] for item in response.json()["documents"]], ["client_case_overview"])
        for kind in ("professional_legal_draft", "report", "draft"):
            for suffix in ("", "/download", "/consistency"):
                self.assertEqual(self.client.get(f"/api/cases/{self.id}/documents/{kind}{suffix}", headers=self.headers).status_code, 403)
        self.assertEqual(self.client.get(f"/api/cases/{self.id}/documents/client_case_overview/download", headers=self.headers).status_code, 200)

    def test_only_valid_current_advocate_approval_can_dispatch(self):
        with patch("backend.services.jobs.dispatch") as dispatch:
            response = self.client.post(f"/api/cases/{self.id}/documents/generate", headers=self.access)
        self.assertEqual(response.status_code, 200)
        dispatch.assert_called_once_with(self.app, 3, self.id)

    def test_filing_unknowns_use_exact_required_text_even_for_supreme_court(self):
        result = filing_pack({"forum_id": "supreme_court"})
        self.assertEqual(len(result), 4)
        self.assertTrue(all(item["note"] == FILING_CONFIRMATION for item in result))
        self.assertTrue(all(not item["items"] for item in result))

    def test_invented_sections_and_annexures_block_documents(self):
        draft = {"cited_provision_ids": ["FAKE"], "annexure_references": ["Annexure Z"], "sections": [{"heading": heading, "paragraphs": ["Section 999 applies"], "fact_ids": [], "provision_ids": []} for heading in MANDATORY_SECTIONS]}
        checks = consistency(draft, {"applicable_law": [], "facts": [], "annexures": [], "forum": {}})
        failed = {item["check"] for item in checks if item["result"] == "FAIL"}
        self.assertTrue({"section_references", "approved_verified_law_only", "annexure_references", "forum_verified"}.issubset(failed))

    def test_docx_download_uses_same_permissions(self):
        response = self.client.get(f"/api/cases/{self.id}/documents/client_case_overview/download?format=docx", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"PK"))
        self.assertEqual(self.client.get(f"/api/cases/{self.id}/documents/professional_legal_draft/download?format=docx", headers=self.headers).status_code, 403)

    def test_mock_mode_never_generates_a_completed_professional_document(self):
        db = self.app.state.adapters.database
        grant = db.list("case_grants")[0]
        db.update("cases", self.id, {"engine3_advocate_id": "seed-verified-advocate", "engine3_grant_id": grant["id"]})
        run_engine3(self.app, self.id)
        case = db.get("cases", self.id)
        self.assertEqual(case["status"], "DOCUMENTS_BLOCKED")
        self.assertIn("mock mode", case["processing_error"]["message"])
        self.assertIsNone(case.get("document_version"))

    def test_structured_drafting_and_versioning_with_a_test_adapter(self):
        db = self.app.state.adapters.database
        case = db.get("cases", self.id)
        file = case["case_file"]
        file["forum"] = {"verification_status": "VERIFIED", "commission_level": "TEST FORUM", "forum_id": "test-forum"}
        file["applicable_law"] = [{"provision_id": "TEST-1", "title": "Section 1 - Test authority", "verification_status": "VERIFIED"}]
        grant = db.list("case_grants")[0]
        db.update("cases", self.id, {"case_file": file, "advocate_approved_items": ["fact:F001", "provision:TEST-1"], "engine3_advocate_id": "seed-verified-advocate", "engine3_grant_id": grant["id"]})
        self.app.state.adapters.mode = "real"
        self.app.state.adapters.llm.generate = lambda *args: {"title": "Test pleading", "sections": [{"heading": heading, "paragraphs": ["TEST FORUM" if heading == "Forum" else "[TO BE COMPLETED: checked details]"], "fact_ids": [], "provision_ids": []} for heading in MANDATORY_SECTIONS], "cited_provision_ids": ["TEST-1"], "annexure_references": []}
        run_engine3(self.app, self.id)
        self.assertEqual(db.get("cases", self.id)["status"], "DOCUMENTS_READY")
        run_engine3(self.app, self.id)
        self.assertEqual(db.get("cases", self.id)["document_version"], 2)
        versioned = [item for item in db.list("documents") if item.get("case_file_version")]
        self.assertEqual(len(versioned), 4)
        client_docs = [item for item in versioned if item["type"] == "client_case_overview"]
        self.assertTrue(all("Professional Legal Draft" not in item["html"] for item in client_docs))
