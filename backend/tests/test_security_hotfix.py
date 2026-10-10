"""HTTP permission regressions; all persistence is isolated in a temporary directory."""
import copy
import unittest
from unittest.mock import patch
from backend.tests.helpers import test_app, client_account
from backend.routes import legal_analysis, advocates, sharing, documents, engines, review, journey
from backend.routes.dependencies import retired_workflow
from backend.services.sharing import grant_access, issue_token, shared_case


class SecurityHotfixTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app, self.client = test_app()
        for module in (legal_analysis, advocates, sharing, documents, engines, review, journey):
            self.app.include_router(module.router)
        self.user, self.headers = client_account(self.client, "security")
        self.db = self.app.state.adapters.database
        self.id = self.client.post("/api/cases", headers=self.headers).json()["case"]["case_id"]
        session = self.client.post("/api/auth/login", json={"email": "demo.advocate@caseseva.local", "password": "DemoPassword123"}).json()
        self.advocate = {"Authorization": "Bearer " + session["session_token"]}
        self.db.update("cases", self.id, {
            "status": "NEEDS_DOCUMENT", "assigned_advocate_id": "seed-verified-advocate",
            "engine2": {"claimant_counsel": {"text": "PRIVATE_ARGUMENT"}},
            "professional_notes": [{"text": "PRIVATE_NOTE", "visibility": "ADVOCATE_INTERNAL"}, {"text": "Visible message", "visibility": "SHARED_WITH_CLIENT"}],
            "arguments": {"text": "PRIVATE_ARGUMENT"}, "professional_data": "PRIVATE_OUTPUT_B",
            "case_file": {"version": 1, "facts": [], "input_pending": [{"reason": "INTERNAL_TESSERACT_CONFIG"}], "pending_advocate_verification": [{"reason": "INTERNAL_AWS_CONFIG"}]},
            "evidence": [{"evidence_id": "E001", "filename": "one.txt", "content_type": "text/plain", "storage_key": "one", "extraction": {"status": "PENDING", "reason": "INTERNAL_TESSERACT_CONFIG"}}, {"evidence_id": "E002", "filename": "two.txt", "extraction": {"status": "COMPLETED", "original_text": "WITHHELD_EVIDENCE"}}],
        })
        self.app.state.adapters.storage.upload("one", b"selected evidence")
        for kind in ("client_case_overview", "professional_legal_draft", "case_intelligence_report", "efiling_readiness_pack", "report", "draft"):
            self.db.create("documents", {"id": kind, "case_id": self.id, "type": kind, "version": 1, "html": "Visible overview" if kind == "client_case_overview" else "PRIVATE_OUTPUT_B", "created_at": "2026-01-01"})

    def tearDown(self):
        self.directory.cleanup()

    def access(self):
        case = self.db.get("cases", self.id)
        grant = grant_access(self.db, case, self.user, ["case_file", "engine2", "evidence"], ["E001"], 24)
        return grant, {**self.advocate, "X-Case-Access": issue_token(self.db, grant)}

    def assert_safe(self, response):
        for marker in ("PRIVATE_ARGUMENT", "PRIVATE_NOTE", "PRIVATE_OUTPUT_B", "INTERNAL_TESSERACT_CONFIG", "INTERNAL_AWS_CONFIG"):
            self.assertNotIn(marker, response.text)

    def test_citizen_reads_hide_internal_content_and_keep_shared_notes(self):
        for suffix in ("", "/status", "/client-case-overview", "/documents"):
            response = self.client.get(f"/api/cases/{self.id}{suffix}", headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assert_safe(response)
        self.assertIn("Visible message", self.client.get(f"/api/cases/{self.id}", headers=self.headers).text)

    def test_output_b_denied_for_every_document_read_and_export(self):
        for kind in ("professional_legal_draft", "case_intelligence_report", "efiling_readiness_pack", "report", "draft"):
            for suffix in ("", "/consistency", "/download?format=html", "/download?format=pdf", "/download?format=docx"):
                response = self.client.get(f"/api/cases/{self.id}/documents/{kind}{suffix}", headers=self.headers)
                self.assertEqual(response.status_code, 403)
                self.assert_safe(response)
        response = self.client.get(f"/api/cases/{self.id}/documents", headers=self.headers)
        self.assertEqual([d["type"] for d in response.json()["documents"]], ["client_case_overview"])

    def test_all_retired_operations_are_tombstones_for_both_workflow_versions(self):
        routes = [r for r in self.app.routes if hasattr(r, "dependant") and any(d.call is retired_workflow for d in r.dependant.dependencies)]
        expected = {
            ("POST", "/api/cases/{case_id}/analyze"),
            ("POST", "/api/cases/{case_id}/analyze/retry"),
            ("POST", "/api/cases/{case_id}/preview1/rerun"),
            ("GET", "/api/cases/{case_id}/preview1"),
            ("PATCH", "/api/cases/{case_id}/facts/{fact_id}"),
            ("POST", "/api/cases/{case_id}/facts"),
            ("PATCH", "/api/cases/{case_id}/timeline/{event_id}"),
            ("PATCH", "/api/cases/{case_id}/parties"),
            ("POST", "/api/cases/{case_id}/preview1/approve"),
            ("POST", "/api/cases/{case_id}/legal-analysis"),
            ("GET", "/api/cases/{case_id}/preview2"),
            ("POST", "/api/cases/{case_id}/evidence-request/{request_id}/resolve"),
            ("POST", "/api/cases/{case_id}/preview2/approve"),
            ("PATCH", "/api/cases/{case_id}/preview2/facts/{fact_id}"),
            ("POST", "/api/cases/{case_id}/advocate/finalize"),
            ("POST", "/api/cases/{case_id}/documents/{document_id}/override-consistency"),
        }
        prefix = "/api/advocate/cases/{case_id}"
        for kind, identifier in (("facts", "fact_id"), ("provisions", "provision_id"), ("arguments", "objection_id")):
            expected.add(("PATCH", prefix + "/" + kind + "/{" + identifier + "}"))
            expected.add(("POST", prefix + "/" + kind + "/{" + identifier + "}/approve"))
        for kind in ("forum", "limitation"):
            expected.add(("PATCH", prefix + "/" + kind))
            expected.add(("POST", prefix + "/" + kind + "/approve"))
        expected.add(("POST", prefix + "/provisions/{provision_id}/remove"))
        for action in ("approve", "remove"):
            expected.add(("POST", prefix + "/evidence/{evidence_id}/" + action))
        self.assertEqual({(method, route.path) for route in routes for method in route.methods}, expected)
        for version in (1, 2):
            self.db.update("cases", self.id, {"workflow_version": version})
            before = self.db.get("cases", self.id)
            for route in routes:
                path = route.path.replace("{case_id}", self.id)
                import re
                path = re.sub(r"\{[^}]+\}", "test", path)
                for headers in (self.headers, self.advocate):
                    for method in route.methods:
                        response = self.client.request(method, path, headers=headers, json={})
                        self.assertEqual(response.status_code, 410, (method, path, response.text))
                        self.assert_safe(response)
            self.assertEqual(self.db.get("cases", self.id), before)

    def test_raw_scope_uses_allowlist_and_selected_evidence_only(self):
        case = self.db.get("cases", self.id)
        case["raw_package"] = {"original_story": "WITHHELD_STORY", "original_text": "WITHHELD_COMBINED", "english_working_text": "WITHHELD_COMBINED", "language": {"language": "Tamil", "english_text": "WITHHELD_COMBINED", "uncertainties": ["WITHHELD_COMBINED"], "normalized": {"text": "WITHHELD_COMBINED"}}, "future_normalized": {"text": "WITHHELD_COMBINED"}, "optional_fields": {"text": "WITHHELD_STORY"}, "pending": [{"evidence_id": "E002", "reason": "WITHHELD_EVIDENCE"}], "evidence": case["evidence"]}
        before = copy.deepcopy(case)
        for scopes in (["raw_package"], ["raw_package", "evidence"], ["raw_package", "evidence", "story"]):
            projection = shared_case(case, {"scopes": scopes, "evidence_ids": ["E001"]})
            self.assertNotIn("WITHHELD_COMBINED", str(projection))
            self.assertNotIn("WITHHELD_EVIDENCE", str(projection))
            self.assertNotIn("INTERNAL_TESSERACT_CONFIG", str(projection))
            if "story" not in scopes:
                self.assertNotIn("WITHHELD_STORY", str(projection))
            else:
                self.assertEqual(projection["raw_package"]["original_story"], "WITHHELD_STORY")
            self.assertEqual(len(projection["raw_package"]["evidence"]), int("evidence" in scopes))
        self.assertEqual(case, before)

    def test_revocation_blocks_workspace_evidence_documents_and_token_exchange(self):
        grant, headers = self.access()
        paths = [f"/api/advocate/cases/{self.id}", f"/api/advocate/cases/{self.id}/evidence/E001", f"/api/cases/{self.id}/documents", f"/api/cases/{self.id}/documents/professional_legal_draft", f"/api/cases/{self.id}/documents/professional_legal_draft/download"]
        for path in paths:
            self.assertEqual(self.client.get(path, headers=headers).status_code, 200, path)
        self.assertEqual(self.client.delete(f"/api/cases/{self.id}/sharing/{grant['id']}", headers=self.headers).status_code, 200)
        for path in paths:
            self.assertEqual(self.client.get(path, headers=headers).status_code, 403, path)
        self.assertEqual(self.client.post(f"/api/advocate/cases/{self.id}/access-token", headers=self.advocate).status_code, 403)

    def test_all_error_shapes_are_safe_and_diagnostics_remain_stored(self):
        for field in ("processing_error", "analysis_error", "legal_analysis_error"):
            for error in ("INTERNAL_AWS_CONFIG", {"message": "INTERNAL_AWS_CONFIG"}, {"engine": 0, "reason": "INTERNAL_AWS_CONFIG"}, {"engine": 2, "traceback": "INTERNAL_AWS_CONFIG"}):
                updates = {"processing_error": None, "analysis_error": None, "legal_analysis_error": None, field: error}
                self.db.update("cases", self.id, updates)
                for suffix in ("", "/status", "/client-case-overview"):
                    response = self.client.get(f"/api/cases/{self.id}{suffix}", headers=self.headers)
                    self.assertEqual(response.status_code, 200)
                    self.assert_safe(response)
                self.assertEqual(self.db.get("cases", self.id)[field], error)

    def test_upload_response_sanitizes_extraction_diagnostics(self):
        with patch("backend.routes.cases.extract_content", return_value={"status": "PENDING", "original_text": "", "reason": "INTERNAL_TESSERACT_CONFIG"}):
            response = self.client.post(f"/api/cases/{self.id}/evidence", headers=self.headers, files={"file": ("scan.png", b"image", "image/png")})
        self.assertEqual(response.status_code, 200)
        self.assert_safe(response)
        self.assertIn("clearer copy", response.text)

    def test_export_runtime_error_is_safe(self):
        with patch("backend.services.exports.export", side_effect=RuntimeError("INTERNAL_AWS_CONFIG")):
            response = self.client.get(f"/api/cases/{self.id}/documents/client_case_overview/download", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assert_safe(response)

    def test_scoped_workspace_and_download_exclude_unselected_content(self):
        grant, headers = self.access()
        self.db.update("case_grants", grant["id"], {"scopes": ["case_file", "raw_package", "evidence"]})
        self.db.update("cases", self.id, {"raw_package": {"original_story": "WITHHELD_STORY", "language": {"english_text": "WITHHELD_TRANSLATION"}, "evidence": self.db.get("cases", self.id)["evidence"]}})
        response = self.client.get(f"/api/advocate/cases/{self.id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        for marker in ("WITHHELD_STORY", "WITHHELD_TRANSLATION", "WITHHELD_EVIDENCE", "PRIVATE_ARGUMENT"):
            self.assertNotIn(marker, response.text)
        self.assertEqual(self.client.get(f"/api/advocate/cases/{self.id}/evidence/E002", headers=headers).status_code, 403)
        self.assertEqual(self.client.get(f"/api/advocate/cases/{self.id}/evidence/E001", headers=headers).content, b"selected evidence")

    def test_status_diagnostic_objects_cannot_leak_through_progress_maps(self):
        self.db.update("cases", self.id, {"input_statuses": {"E001": {"status": "FAILED", "error": "INTERNAL_AWS_CONFIG"}}, "stage_statuses": {"FACT_EXTRACTION": "INTERNAL_TESSERACT_CONFIG", "INTAKE_CLEANING": "COMPLETED"}})
        for suffix in ("", "/status"):
            response = self.client.get(f"/api/cases/{self.id}{suffix}", headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assert_safe(response)
            self.assertIn("COMPLETED", response.text)
