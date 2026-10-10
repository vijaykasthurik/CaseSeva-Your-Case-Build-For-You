import hashlib
import unittest
from unittest.mock import patch
from backend.services.engine1 import run_engine1
from backend.services.legal_knowledge import LegalKnowledge, source_record
from backend.models.case import utc_now
from backend.tests.helpers import test_app, client_account


class Engine1Tests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app, self.client = test_app()
        self.user, self.headers = client_account(self.client)
        self.case = self.client.post("/api/cases", headers=self.headers).json()["case"]
        self.id = self.case["case_id"]
        self.client.patch(f"/api/cases/{self.id}", headers=self.headers, json={"stage": "NEW_CONSULTATION", "client_story": "My actual case story"})

    def tearDown(self):
        self.directory.cleanup()

    def test_submission_automatically_dispatches_engine1(self):
        with patch("backend.services.jobs.dispatch") as dispatch:
            response = self.client.post(f"/api/cases/{self.id}/submit", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["case"]["status"], "SUBMITTED")
        dispatch.assert_called_once_with(self.app, 1, self.id)

    def test_engine1_has_no_argumentation_or_preview_gate(self):
        run_engine1(self.app, self.id)
        case = self.app.state.adapters.database.get("cases", self.id)
        self.assertEqual(case["status"], "REVIEW_REQUIRED")
        self.assertEqual(case["case_file"]["applicable_law"], [])
        self.assertEqual(case["case_file"]["version"], 1)
        self.assertNotIn("CLAIMANT_COUNSEL", case["stage_statuses"])
        self.assertNotIn("arguments", case["case_file"])
        self.assertEqual(case["raw_package"]["original_story"], "My actual case story")

    def test_old_corpus_is_not_ready(self):
        knowledge = LegalKnowledge()
        for domain in ("consumer", "labour", "criminal", "family", "property"):
            self.assertFalse(knowledge.ready(domain))
        self.assertEqual(knowledge.search(["consumer"], "refund"), [])

    def test_detected_unready_domain_is_not_an_enabled_route(self):
        original = self.app.state.adapters.llm.generate
        def classify(prompt, schema):
            if schema.get("stage") == "engine1_domain_router":
                return {"domains": ["consumer"], "reasoning": "Test classification", "requires_review": False}
            return original(prompt, schema)
        self.app.state.adapters.llm.generate = classify
        run_engine1(self.app, self.id)
        case = self.app.state.adapters.database.get("cases", self.id)
        self.assertEqual(case["status"], "LEGAL_CORPUS_NOT_READY")
        self.assertEqual(case["case_file"]["routing"]["domains"], [])
        self.assertEqual(case["case_file"]["routing"]["unavailable_domains"], ["consumer"])

    def test_provenance_and_exact_text_required(self):
        self.assertFalse(source_record({"source_url": "https://www.indiacode.nic.in/x"}, {})[0])
        text = "Exact official provision text"
        item = {"source_id": "official", "source_url": "https://www.indiacode.nic.in/x", "official_text": text, "quote": "official provision", "content_hash": hashlib.sha256(text.encode()).hexdigest(), "source_reviewed": True, "reviewed_by": "test-ingestion-reviewer", "retrieved_at": utc_now()}
        sources = {"official": {"enabled": True, "tier": "PRIMARY", "hosts": ["www.indiacode.nic.in"]}}
        self.assertTrue(source_record(item, sources)[0])
        item["quote"] = "invented law"
        self.assertFalse(source_record(item, sources)[0])

    def test_cross_user_and_anonymous_cannot_access_case_or_progress(self):
        _, other = client_account(self.client, "other")
        for route in (f"/api/cases/{self.id}", f"/api/cases/{self.id}/status"):
            self.assertEqual(self.client.get(route, headers=other).status_code, 403)
            self.assertEqual(self.client.get(route).status_code, 401)

    def test_deleted_highest_evidence_id_is_never_reused(self):
        first = self.client.post(f"/api/cases/{self.id}/evidence", headers=self.headers, files={"file": ("a.txt", b"text", "text/plain")}).json()["evidence"]
        self.client.delete(f"/api/cases/{self.id}/evidence/{first['evidence_id']}", headers=self.headers)
        second = self.client.post(f"/api/cases/{self.id}/evidence", headers=self.headers, files={"file": ("b.txt", b"text", "text/plain")}).json()["evidence"]
        self.assertEqual(second["evidence_id"], "E002")

    def test_model_failure_is_visible_not_replaced_with_fixtures(self):
        self.app.state.adapters.llm.generate = lambda *args: (_ for _ in ()).throw(RuntimeError("service unavailable"))
        run_engine1(self.app, self.id)
        case = self.app.state.adapters.database.get("cases", self.id)
        self.assertEqual(case["status"], "REVIEW_REQUIRED")
        self.assertIn("service unavailable", case["processing_error"]["message"])
        self.assertNotIn("case_file", case)
