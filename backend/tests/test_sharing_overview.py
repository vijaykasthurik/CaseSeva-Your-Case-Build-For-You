from datetime import datetime, timedelta, timezone
import unittest
from backend.tests.helpers import test_app, client_account
from backend.services.engine1 import run_engine1
from backend.services.overview import client_case, client_overview
from backend.routes.advocates import router as advocates
from backend.routes.sharing import router as sharing


class SharingTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app, self.client = test_app()
        self.app.include_router(advocates)
        self.app.include_router(sharing)
        self.user, self.headers = client_account(self.client)
        self.id = self.client.post("/api/cases", headers=self.headers).json()["case"]["case_id"]
        self.client.patch(f"/api/cases/{self.id}", headers=self.headers, json={"stage": "NEW_CONSULTATION", "client_story": "Private client story"})
        run_engine1(self.app, self.id)
        session = self.client.post("/api/auth/login", json={"email": "demo.advocate@caseseva.local", "password": "DemoPassword123"}).json()
        self.advocate = {"Authorization": "Bearer " + session["session_token"]}

    def tearDown(self):
        self.directory.cleanup()

    def accepted(self):
        self.assertEqual(self.client.post(f"/api/cases/{self.id}/request-advocate", headers=self.headers, json={"advocate_id": "seed-verified-advocate"}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/advocate/requests/{self.id}/accept", headers=self.advocate).status_code, 200)

    def grant(self):
        response = self.client.post(f"/api/cases/{self.id}/sharing", headers=self.headers, json={"scopes": ["case_file"], "evidence_ids": [], "expires_in_hours": 24})
        self.assertEqual(response.status_code, 200)
        token = self.client.post(f"/api/advocate/cases/{self.id}/access-token", headers=self.advocate).json()["access_token"]
        self.access = {**self.advocate, "X-Case-Access": token}
        return response.json()["grant"]

    def test_acceptance_does_not_grant_access_and_scope_is_enforced(self):
        self.accepted()
        self.assertEqual(self.client.get(f"/api/advocate/cases/{self.id}", headers=self.advocate).status_code, 403)
        self.assertEqual(self.client.post(f"/api/advocate/cases/{self.id}/access-token", headers=self.advocate).status_code, 403)
        self.grant()
        response = self.client.get(f"/api/advocate/cases/{self.id}", headers=self.access)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("client_story", response.json()["case"])
        self.assertNotIn("evidence", response.json()["case"])

    def test_revocation_invalidates_existing_token_immediately(self):
        self.accepted()
        grant = self.grant()
        self.client.delete(f"/api/cases/{self.id}/sharing/{grant['id']}", headers=self.headers)
        self.assertEqual(self.client.get(f"/api/advocate/cases/{self.id}", headers=self.access).status_code, 403)

    def test_expiry_and_verification_downgrade_invalidate_tokens(self):
        self.accepted()
        grant = self.grant()
        db = self.app.state.adapters.database
        db.update("case_grants", grant["id"], {"expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()})
        self.assertEqual(self.client.get(f"/api/advocate/cases/{self.id}", headers=self.access).status_code, 403)
        db.update("users", "seed-verified-advocate", {"verification_status": "VERIFICATION_PENDING"})
        self.assertEqual(self.client.post(f"/api/advocate/cases/{self.id}/access-token", headers=self.advocate).status_code, 403)

    def test_client_projection_never_exposes_counsel_arguments(self):
        case = self.app.state.adapters.database.get("cases", self.id)
        case.update({"engine2": {"claimant_counsel": {"points": ["PRIVATE STRATEGY"]}}, "arguments": {"secret": "PRIVATE STRATEGY"}})
        projection = client_case(case)
        self.assertNotIn("engine2", projection)
        self.assertNotIn("arguments", projection)
        self.assertNotIn("PRIVATE STRATEGY", str(projection))
        self.assertIn("was not run", projection["overview"]["argument_analysis_note"])
        self.assertEqual(projection["overview"]["issue_readiness"], [])

    def test_mutation_responses_do_not_leak_internal_arguments(self):
        self.app.state.adapters.database.update("cases", self.id, {"engine2": {"secret": "PRIVATE STRATEGY"}})
        response = self.client.post(f"/api/cases/{self.id}/evidence", headers=self.headers, files={"file": ("new.txt", b"Actual new evidence", "text/plain")})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("PRIVATE STRATEGY", response.text)
        response = self.client.post(f"/api/cases/{self.id}/request-advocate", headers=self.headers, json={"advocate_id": "seed-verified-advocate"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("PRIVATE STRATEGY", response.text)
        response = self.client.post(f"/api/advocate/requests/{self.id}/decline", headers=self.advocate)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("PRIVATE STRATEGY", response.text)
