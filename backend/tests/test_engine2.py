import copy
import unittest
from unittest.mock import patch
from backend.tests.helpers import test_app, client_account
from backend.services.engine1 import run_engine1
from backend.services.engine2 import run_engine2, validate_references
from backend.routes.engines import router


class Engine2Tests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app, self.client = test_app()
        self.app.include_router(router)
        _, self.headers = client_account(self.client)
        self.id = self.client.post("/api/cases", headers=self.headers).json()["case"]["case_id"]
        self.client.patch(f"/api/cases/{self.id}", headers=self.headers, json={"stage": "NEW_CONSULTATION", "client_story": "An actual dispute"})
        run_engine1(self.app, self.id)

    def tearDown(self):
        self.directory.cleanup()

    def test_engine2_never_calls_engine1_or_retrieval(self):
        before = copy.deepcopy(self.app.state.adapters.database.get("cases", self.id)["case_file"])
        with patch("backend.services.engine1.run_engine1", side_effect=AssertionError("Engine 1 boundary")), patch("backend.services.legal_knowledge.LegalKnowledge.search", side_effect=AssertionError("Retrieval boundary")):
            run_engine2(self.app, self.id)
        case = self.app.state.adapters.database.get("cases", self.id)
        self.assertEqual(case["status"], "ENGINE2_DONE")
        self.assertEqual(case["case_file"], before)
        self.assertEqual(case["engine2"]["case_file_version"], before["version"])
        self.assertNotIn("STATUTE_RETRIEVAL", case["stage_statuses"])

    def test_declining_is_recorded_without_running_arguments(self):
        with patch("backend.routes.engines.dispatch") as dispatch:
            response = self.client.post(f"/api/cases/{self.id}/engine2", headers=self.headers, json={"run": False})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["engine2_choice"], "DECLINED")
        dispatch.assert_not_called()
        self.assertNotIn("engine2", self.app.state.adapters.database.get("cases", self.id))

    def test_unverified_authority_references_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_references({"points": [{"provision_ids": ["invented"]}]}, {"applicable_law": []})

    def test_unverified_facts_and_unreadable_evidence_cannot_be_argument_premises(self):
        foundation = {"facts": [{"fact_id": "F1", "verification_status": "UNVERIFIED"}], "evidence_index": [{"evidence_id": "E1", "verification_status": "PENDING_ADVOCATE_VERIFICATION"}]}
        for output in ({"fact_ids": ["F1"]}, {"evidence_ids": ["E1"]}):
            with self.assertRaises(ValueError):
                validate_references(output, foundation)
        foundation["facts"][0]["advocate_approved"] = True
        foundation["evidence_index"][0]["verification_status"] = "VERIFIED"
        validate_references({"fact_ids": ["F1"], "evidence_ids": ["E1"]}, foundation)

    def test_choice_requires_complete_foundation_and_owner(self):
        _, other = client_account(self.client, "another")
        self.assertEqual(self.client.post(f"/api/cases/{self.id}/engine2", headers=other, json={"run": True}).status_code, 403)
        self.app.state.adapters.database.update("cases", self.id, {"status": "ENGINE1_RUNNING"})
        self.assertEqual(self.client.post(f"/api/cases/{self.id}/engine2", headers=self.headers, json={"run": True}).status_code, 409)
