import os
import unittest
from unittest.mock import patch
from backend.tests.helpers import test_app, client_account
from backend.routes.orchestration import router
from backend.services.case_blackboard import CaseBlackboard
from backend.services.agent_registry import production_registry
from backend.services.ingestion import run_ingestion


class OrchestrationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app, self.client = test_app()
        self.app.include_router(router)
        self.user, self.headers = client_account(self.client, "phase2")
        self.db = self.app.state.adapters.database
        self.case_id = self.client.post("/api/cases", headers=self.headers).json()["case"]["case_id"]
        self.path = f"/api/admin/cases/{self.case_id}/orchestration"

    def tearDown(self):
        self.directory.cleanup()

    def test_admin_only_diagnostics_and_production_registry_does_not_autorun(self):
        self.assertEqual(self.client.get(self.path).status_code, 401)
        self.assertEqual(self.client.get(self.path, headers=self.headers).status_code, 403)
        session = self.client.post("/api/auth/login", json={"email": "demo.advocate@caseseva.local", "password": "DemoPassword123"}).json()
        self.assertEqual(self.client.get(self.path, headers={"Authorization": "Bearer " + session["session_token"]}).status_code, 403)
        self.db.update("users", self.user["id"], {"role": "admin"})
        with patch.dict(os.environ, {"ADMIN_TOKEN": "test-admin-only"}):
            self.assertEqual(self.client.get(self.path, headers=self.headers).status_code, 403)
            response = self.client.get(self.path, headers={**self.headers, "X-Admin-Token": "test-admin-only"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["registry"]), 8)
        self.assertEqual(len(production_registry().describe()), 8)
        self.assertIn("DOMAIN_ROUTER", [a["agent_type"] for a in response.json()["registry"]])
        self.assertIsNone(response.json()["checkpoint"])

    def test_citizen_read_lazy_initialization_does_not_expose_control_state(self):
        store = CaseBlackboard(self.db)
        store.append_change(self.case_id, {"private.internal": "PRIVATE_ENGINE_DATA"}, actor="system", reason="test")
        store.record_conflict(self.case_id, "private.internal", ["PRIVATE_ENGINE_DATA", "PRIVATE_OUTPUT_B"], ["advocate", "agent"])
        response = self.client.get(f"/api/cases/{self.case_id}", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("PRIVATE_", response.text)
        self.assertNotIn("conflicts", response.json()["case"])
        self.assertTrue(self.db.get("case_board_heads", self.case_id))

    def test_existing_get_survives_sidecar_failure_without_technical_leak(self):
        with patch("backend.services.case_blackboard.CaseBlackboard.sync_input", side_effect=RuntimeError("INTERNAL_AWS_CONFIG")), self.assertLogs("backend.services.blackboard", level="ERROR"):
            response = self.client.get(f"/api/cases/{self.case_id}", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("INTERNAL_AWS_CONFIG", response.text)

    def test_phase1_ingestion_populates_references_for_all_origins_without_agents(self):
        for origin in ("CITIZEN_SELF_SERVICE", "CITIZEN_DIRECT_ADVOCATE", "ADVOCATE_WALK_IN"):
            self.db.update("cases", self.case_id, {"origin": origin, "client_story": "என் ரசீது உள்ளது. My receipt exists.", "input_version": 2})
            with patch("backend.services.engine1.run_engine1", side_effect=AssertionError("No automatic legal engine")):
                run_ingestion(self.app, self.case_id)
            board = CaseBlackboard(self.db).read_board(self.case_id)
            self.assertEqual(board["data"]["identity"]["origin"], origin)
            self.assertTrue(board["data"]["input"]["raw_fingerprint"])
            self.assertEqual(board["nodes"], {})
            self.assertNotIn("என்", str(board))
            self.assertNotIn("case_file", self.db.get("cases", self.case_id))

    def test_unauthorized_case_open_does_not_initialize_board(self):
        _, other = client_account(self.client, "otherphase2")
        self.assertEqual(self.client.get(f"/api/cases/{self.case_id}", headers=other).status_code, 403)
        self.assertIsNone(self.db.get("case_board_heads", self.case_id))
