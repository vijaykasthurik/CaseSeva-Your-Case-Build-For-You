"""Phase 7 Deterministic Tests for Citizen Experience and Journey Integration.

Validates the full citizen product journey end-to-end:
1. citizen creates a case
2. citizen sees Engine-1 Case Overview
3. PENDING_SOURCE renders safely
4. verified authority renders distinctly
5. citizen clarification submission
6. mixed-language intake
7. evidence upload projection
8. citizen can run Strengthen My Case
9. citizen can skip Engine 2
10. stale Engine-2 analysis prompts rerun
11. no win probability visible
12. citizen can open Get Legal Help
13. only eligible verified advocate appears
14. citizen sends connection request
15. advocate acceptance alone does not share case
16. explicit citizen consent enables handoff eligibility
17. revoked/cancelled consent prevents access where applicable
18. another citizen cannot access the case
19. unauthorized advocate cannot access the case
20. no private advocate verification document leaks
21. handoff binds exact Case File version
22. Engine-2 version/disclosure included correctly
23. original evidence remains immutable
24. no automatic Engine-3 invocation
"""

import copy
import hashlib
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.adapters.mock.auth import MockAuthAdapter
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.adapters.mock.llm import MockLLMAdapter
from backend.adapters.mock.storage import MockStorageAdapter
from backend.routes.advocates import router as advocates_router
from backend.routes.analysis import router as analysis_router
from backend.routes.auth import router as auth_router
from backend.routes.cases import router as cases_router
from backend.routes.clarification import router as clarification_router
from backend.routes.engines import router as engines_router
from backend.routes.sharing import router as sharing_router
from backend.services.engine1 import run_engine1
from backend.services.engine2 import run_engine2
from backend.services.overview import client_overview
from backend.services.review_contracts import ENGINE2_NOT_RUN_DISCLOSURE


def create_phase7_app():
    directory = tempfile.TemporaryDirectory()
    db = MockDatabaseAdapter(directory.name + "/database.json")
    storage = MockStorageAdapter(directory.name + "/uploads")
    adapters = SimpleNamespace(
        database=db,
        storage=storage,
        llm=MockLLMAdapter(),
        auth=MockAuthAdapter(db),
        email_provider="mock",
        mode="mock",
        processing_mode="mock",
        llm_processing_mode="mock",
    )
    app = FastAPI()
    app.state.adapters = adapters
    for r in (cases_router, auth_router, analysis_router, engines_router, advocates_router, sharing_router, clarification_router):
        app.include_router(r)
    return directory, app, TestClient(app)


def create_user(client, name="Test Citizen", role="client", email=None):
    email = email or f"{uuid4().hex}@example.com"
    payload = {
        "full_name": name,
        "email": email,
        "password": "Password123!",
        "mobile_number": "9876543210",
        "preferred_language": "English",
        "state": "Tamil Nadu",
        "district_city": "Chennai",
        "role": role,
    }
    if role == "advocate":
        payload.update({
            "bar_council": "Bar Council of Tamil Nadu and Puducherry",
            "enrolment_number": "MS/1234/2018",
            "enrolment_year": 2018,
            "place_of_practice": "Chennai",
            "practice_domains": ["CONSUMER", "CONTRACT"],
            "languages": ["English", "Tamil"],
            "court_region": "Chennai High Court",
        })
    res = client.post("/api/auth/signup", json=payload)
    data = res.json()
    token = data["session_token"]
    return data["user"], {"Authorization": f"Bearer {token}"}


class Phase7CitizenJourneyTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app, self.client = create_phase7_app()
        self.citizen, self.citizen_headers = create_user(self.client, name="Ananya Citizen", role="client")
        self.other_citizen, self.other_headers = create_user(self.client, name="Other Citizen", role="client")

        # Create a verified advocate and an unverified advocate
        self.advocate, self.advocate_headers = create_user(self.client, name="Advocate Ramanathan", role="advocate")
        self.unverified_advocate, self.unverified_advocate_headers = create_user(self.client, name="Unverified Adv", role="advocate")

        # Mark advocate as verified in database with mock verification document
        db = self.app.state.adapters.database
        db.update("users", self.advocate["id"], {
            "verification_status": "VERIFIED",
            "verification_documents": [{"filename": "bar_enrolment_cert.pdf", "storage_key": "private/doc1.pdf"}],
        })
        db.update("users", self.unverified_advocate["id"], {
            "verification_status": "VERIFICATION_PENDING",
            "verification_documents": [{"filename": "pending_cert.pdf", "storage_key": "private/doc2.pdf"}],
        })

    def tearDown(self):
        try:
            self.directory.cleanup()
        except Exception:
            pass

    def _create_and_run_case(self, story="I bought a defective laptop on 1 September 2026."):
        res = self.client.post("/api/cases", headers=self.citizen_headers)
        case_id = res.json()["case"]["case_id"]
        self.client.patch(
            f"/api/cases/{case_id}",
            headers=self.citizen_headers,
            json={"stage": "NEW_CONSULTATION", "client_story": story},
        )
        run_engine1(self.app, case_id)
        return case_id

    # 1. citizen creates a case
    def test_01_citizen_creates_a_case(self):
        res = self.client.post("/api/cases", headers=self.citizen_headers)
        self.assertEqual(res.status_code, 200)
        case = res.json()["case"]
        self.assertIn("case_id", case)
        self.assertEqual(case["status"], "DRAFT")
        self.assertEqual(case["owner_user_id"], self.citizen["id"])

        # Check in list_cases
        list_res = self.client.get("/api/cases", headers=self.citizen_headers)
        self.assertEqual(list_res.status_code, 200)
        cases = list_res.json()["cases"]
        self.assertTrue(any(c["case_id"] == case["case_id"] for c in cases))

    # 2. citizen sees Engine-1 Case Overview
    def test_02_citizen_sees_engine1_case_overview(self):
        cid = self._create_and_run_case("Purchased a mobile phone with broken display on 10 August 2026.")
        res = self.client.get(f"/api/cases/{cid}", headers=self.citizen_headers)
        self.assertEqual(res.status_code, 200)
        c = res.json()["case"]
        overview = c.get("overview")
        self.assertIsNotNone(overview)
        self.assertIn("summary", overview)
        self.assertIn("key_facts", overview)
        self.assertIn("timeline", overview)
        self.assertIn("parties", overview)
        self.assertIn("issues", overview)
        self.assertEqual(overview["case_file_version"], 1)

    # 3. PENDING_SOURCE renders safely
    def test_03_pending_source_renders_safely(self):
        cid = self._create_and_run_case()
        db = self.app.state.adapters.database
        case = db.get("cases", cid)
        case["case_file"]["legal_foundation_status"] = "PENDING_SOURCE"
        case["case_file"]["applicable_law"] = []
        db.update("cases", cid, {"case_file": case["case_file"]})

        res = self.client.get(f"/api/cases/{cid}", headers=self.citizen_headers)
        overview = res.json()["case"]["overview"]
        self.assertEqual(overview["legal_foundation_status"], "PENDING_SOURCE")
        self.assertEqual(overview["applicable_law"], [])
        self.assertIn("pending independent legal review", overview["next_step"])

    # 4. verified authority renders distinctly
    def test_04_verified_authority_renders_distinctly(self):
        cid = self._create_and_run_case()
        db = self.app.state.adapters.database
        case = db.get("cases", cid)
        case["case_file"]["legal_foundation_status"] = "VERIFIED_AUTHORITY"
        case["case_file"]["applicable_law"] = [{
            "provision_id": "cpa2019_s2_10",
            "title": "Section 2(10) Defect",
            "explanation": "Defect means any shortcoming in quality.",
            "source_url": "https://example.gov.in/cpa",
            "retrieved_at": "2026-10-15T00:00:00Z",
            "verification_status": "VERIFIED",
        }]
        db.update("cases", cid, {"case_file": case["case_file"]})

        res = self.client.get(f"/api/cases/{cid}", headers=self.citizen_headers)
        overview = res.json()["case"]["overview"]
        self.assertEqual(overview["legal_foundation_status"], "VERIFIED_AUTHORITY")
        self.assertEqual(len(overview["applicable_law"]), 1)
        self.assertEqual(overview["applicable_law"][0]["title"], "Section 2(10) Defect")

    # 5. citizen clarification submission
    @patch("backend.routes.clarification.dispatch")
    def test_05_citizen_clarification_submission(self, mock_dispatch):
        res = self.client.post("/api/cases", headers=self.citizen_headers)
        cid = res.json()["case"]["case_id"]
        db = self.app.state.adapters.database
        db.update("cases", cid, {
            "status": "AWAITING_CLIENT_INFO",
            "clarification_rounds": [{
                "id": "round_1",
                "status": "WAITING",
                "answering_user_id": self.citizen["id"],
                "questions": [{
                    "question_id": "q1",
                    "text": "When was the laptop delivered?",
                    "control": "text",
                    "choices": [],
                }]
            }]
        })

        ans_res = self.client.post(
            f"/api/cases/{cid}/clarifications",
            headers=self.citizen_headers,
            json={"answers": [{"question_id": "q1", "response": "ANSWER", "value": "Delivered on 5 September 2026"}]}
        )
        self.assertEqual(ans_res.status_code, 200)
        c = db.get("cases", cid)
        round_entry = c["clarification_rounds"][-1]
        self.assertEqual(round_entry["status"], "ANSWERED")
        self.assertEqual(round_entry["answers"][0]["value"], "Delivered on 5 September 2026")
        mock_dispatch.assert_called_once()

    # 6. mixed-language intake
    def test_06_mixed_language_intake(self):
        res = self.client.post("/api/cases", headers=self.citizen_headers)
        cid = res.json()["case"]["case_id"]
        mixed_story = "நான் ஒரு புதிய laptop வாங்கினேன் on 1 September 2026 for Rs. 45,000. It arrived with broken screen and defect."
        patch_res = self.client.patch(
            f"/api/cases/{cid}",
            headers=self.citizen_headers,
            json={"stage": "NEW_CONSULTATION", "client_story": mixed_story}
        )
        self.assertEqual(patch_res.status_code, 200)
        case = patch_res.json()["case"]
        self.assertEqual(case["client_story"], mixed_story)

    # 7. evidence upload projection
    def test_07_evidence_upload_projection(self):
        res = self.client.post("/api/cases", headers=self.citizen_headers)
        cid = res.json()["case"]["case_id"]
        content = b"SYNTHETIC BILL: Paid Rs. 50,000 for electronic device."
        up_res = self.client.post(
            f"/api/cases/{cid}/evidence",
            headers=self.citizen_headers,
            files={"file": ("receipt.txt", content, "text/plain")}
        )
        self.assertEqual(up_res.status_code, 200)
        ev = up_res.json()["evidence"]
        self.assertEqual(ev["filename"], "receipt.txt")
        self.assertIn("evidence_id", ev)
        self.assertNotIn("storage_key", ev)  # Storage key is private

    # 8. citizen can run Strengthen My Case
    def test_08_citizen_can_run_strengthen_my_case(self):
        cid = self._create_and_run_case()
        run_engine2(self.app, cid)
        res = self.client.get(f"/api/cases/{cid}", headers=self.citizen_headers)
        overview = res.json()["case"]["overview"]
        self.assertTrue(overview["argument_analysis_run"])
        self.assertEqual(overview["argument_analysis_note"], "Argument analysis was run on the current Case File.")
        self.assertTrue(len(overview["key_challenges"]) > 0 or len(overview["issue_readiness"]) > 0)

    # 9. citizen can skip Engine 2
    def test_09_citizen_can_skip_engine2(self):
        cid = self._create_and_run_case()
        skip_res = self.client.post(f"/api/cases/{cid}/engine2", headers=self.citizen_headers, json={"run": False})
        self.assertEqual(skip_res.status_code, 200)
        self.assertEqual(skip_res.json()["engine2_choice"], "DECLINED")

        res = self.client.get(f"/api/cases/{cid}", headers=self.citizen_headers)
        overview = res.json()["case"]["overview"]
        self.assertFalse(overview["argument_analysis_run"])
        self.assertEqual(ENGINE2_NOT_RUN_DISCLOSURE, "Case Challenge / Argument Analysis was not run.")

    # 10. stale Engine-2 analysis prompts rerun
    def test_10_stale_engine2_analysis_prompts_rerun(self):
        cid = self._create_and_run_case()
        run_engine2(self.app, cid)

        # Simulate Engine 1 updating case file to v2
        db = self.app.state.adapters.database
        c = db.get("cases", cid)
        cf = copy.deepcopy(c["case_file"])
        cf["version"] = 2
        db.update("cases", cid, {"case_file": cf, "canonical_case_file": cf})

        res = self.client.get(f"/api/cases/{cid}", headers=self.citizen_headers)
        overview = res.json()["case"]["overview"]
        self.assertTrue(overview["engine2_stale"])
        self.assertIn("Rerun Strengthen My Case to update", overview["argument_analysis_note"])

    # 11. no win probability visible
    def test_11_no_win_probability_visible(self):
        cid = self._create_and_run_case()
        run_engine2(self.app, cid)
        res = self.client.get(f"/api/cases/{cid}", headers=self.citizen_headers)
        overview_str = json.dumps(res.json()["case"]["overview"]).lower()
        forbidden = ["win probability", "success percentage", "victory chance", "win_percentage", "win_rate", "case_score", "likely winner"]
        for phrase in forbidden:
            self.assertNotIn(phrase, overview_str)

    # 12. citizen can open Get Legal Help
    def test_12_citizen_can_open_get_legal_help(self):
        res = self.client.get("/api/advocates", headers=self.citizen_headers)
        self.assertEqual(res.status_code, 200)
        advocates = res.json()["advocates"]
        self.assertIsInstance(advocates, list)

    # 13. only eligible verified advocate appears
    def test_13_only_eligible_verified_advocate_appears(self):
        res = self.client.get("/api/advocates", headers=self.citizen_headers)
        advocates = res.json()["advocates"]
        ids = [a["id"] for a in advocates]
        self.assertIn(self.advocate["id"], ids)
        self.assertNotIn(self.unverified_advocate["id"], ids)

    # 14. citizen sends connection request
    def test_14_citizen_sends_connection_request(self):
        cid = self._create_and_run_case()
        req_res = self.client.post(
            f"/api/cases/{cid}/request-advocate",
            headers=self.citizen_headers,
            json={"advocate_id": self.advocate["id"]}
        )
        self.assertEqual(req_res.status_code, 200)
        case = req_res.json()["case"]
        self.assertEqual(case["status"], "AWAITING_ADVOCATE")
        self.assertEqual(case["requested_advocate_id"], self.advocate["id"])

        # Check in advocate's incoming requests
        adv_res = self.client.get("/api/advocate/requests", headers=self.advocate_headers)
        self.assertEqual(adv_res.status_code, 200)
        reqs = adv_res.json()["requests"]
        self.assertTrue(any(r["case_id"] == cid for r in reqs))

    # 15. advocate acceptance alone does not share case
    def test_15_advocate_acceptance_alone_does_not_share_case(self):
        cid = self._create_and_run_case()
        self.client.post(f"/api/cases/{cid}/request-advocate", headers=self.citizen_headers, json={"advocate_id": self.advocate["id"]})

        # Advocate accepts
        acc_res = self.client.post(f"/api/advocate/requests/{cid}/accept", headers=self.advocate_headers)
        self.assertEqual(acc_res.status_code, 200)

        # Advocate tries to access case details without citizen consent -> must fail with 403
        adv_case_res = self.client.get(f"/api/advocate/cases/{cid}", headers=self.advocate_headers)
        self.assertEqual(adv_case_res.status_code, 403)

        # Advocate tries to exchange access token -> must fail with 403
        token_res = self.client.post(f"/api/advocate/cases/{cid}/access-token", headers=self.advocate_headers)
        self.assertEqual(token_res.status_code, 403)

    # 16. explicit citizen consent enables handoff eligibility
    def test_16_explicit_citizen_consent_enables_handoff_eligibility(self):
        cid = self._create_and_run_case()
        self.client.post(f"/api/cases/{cid}/request-advocate", headers=self.citizen_headers, json={"advocate_id": self.advocate["id"]})
        self.client.post(f"/api/advocate/requests/{cid}/accept", headers=self.advocate_headers)

        # Citizen grants consent
        grant_res = self.client.post(
            f"/api/cases/{cid}/sharing",
            headers=self.citizen_headers,
            json={"scopes": ["story", "case_file"], "evidence_ids": [], "expires_in_hours": 168}
        )
        self.assertEqual(grant_res.status_code, 200)
        grant = grant_res.json()["grant"]
        self.assertEqual(grant["owner_user_id"], self.citizen["id"])
        self.assertEqual(grant["advocate_id"], self.advocate["id"])

        # Advocate can now exchange access token and view case
        tok_res = self.client.post(f"/api/advocate/cases/{cid}/access-token", headers=self.advocate_headers)
        self.assertEqual(tok_res.status_code, 200)
        token = tok_res.json()["access_token"]

        adv_view = self.client.get(f"/api/advocate/cases/{cid}", headers={**self.advocate_headers, "X-Case-Access": token})
        self.assertEqual(adv_view.status_code, 200)
        self.assertIn("case_file", adv_view.json()["case"])

    # 17. revoked/cancelled consent prevents access where applicable
    def test_17_revoked_consent_prevents_access(self):
        cid = self._create_and_run_case()
        self.client.post(f"/api/cases/{cid}/request-advocate", headers=self.citizen_headers, json={"advocate_id": self.advocate["id"]})
        self.client.post(f"/api/advocate/requests/{cid}/accept", headers=self.advocate_headers)
        grant_res = self.client.post(
            f"/api/cases/{cid}/sharing",
            headers=self.citizen_headers,
            json={"scopes": ["story", "case_file"], "evidence_ids": [], "expires_in_hours": 168}
        )
        gid = grant_res.json()["grant"]["id"]

        # Revoke grant
        rev_res = self.client.delete(f"/api/cases/{cid}/sharing/{gid}", headers=self.citizen_headers)
        self.assertEqual(rev_res.status_code, 200)

        # Advocate access is now immediately blocked
        tok_res = self.client.post(f"/api/advocate/cases/{cid}/access-token", headers=self.advocate_headers)
        self.assertEqual(tok_res.status_code, 403)

    # 18. another citizen cannot access the case
    def test_18_another_citizen_cannot_access_the_case(self):
        cid = self._create_and_run_case()
        other_get = self.client.get(f"/api/cases/{cid}", headers=self.other_headers)
        self.assertEqual(other_get.status_code, 403)

        other_update = self.client.patch(f"/api/cases/{cid}", headers=self.other_headers, json={"client_story": "hacked"})
        self.assertEqual(other_update.status_code, 403)

    # 19. unauthorized advocate cannot access the case
    def test_19_unauthorized_advocate_cannot_access_the_case(self):
        cid = self._create_and_run_case()
        unauth_view = self.client.get(f"/api/advocate/cases/{cid}", headers=self.advocate_headers)
        self.assertEqual(unauth_view.status_code, 403)

    # 20. no private advocate verification document leaks
    def test_20_no_private_advocate_verification_document_leaks(self):
        res = self.client.get("/api/advocates", headers=self.citizen_headers)
        text = json.dumps(res.json())
        self.assertNotIn("bar_enrolment_cert", text)
        self.assertNotIn("private/doc1.pdf", text)
        self.assertNotIn("verification_documents", text)

    # 21. handoff binds exact Case File version
    def test_21_handoff_binds_exact_case_file_version(self):
        cid = self._create_and_run_case()
        self.client.post(f"/api/cases/{cid}/request-advocate", headers=self.citizen_headers, json={"advocate_id": self.advocate["id"]})
        self.client.post(f"/api/advocate/requests/{cid}/accept", headers=self.advocate_headers)
        self.client.post(f"/api/cases/{cid}/sharing", headers=self.citizen_headers, json={"scopes": ["case_file"], "evidence_ids": [], "expires_in_hours": 168})

        handoff_res = self.client.get(f"/api/cases/{cid}/handoff", headers=self.citizen_headers)
        self.assertEqual(handoff_res.status_code, 200)
        h = handoff_res.json()["handoff"]
        self.assertEqual(h["engine1_case_file_version"], 1)
        self.assertEqual(h["case_id"], cid)

    # 22. Engine-2 version/disclosure included correctly
    def test_22_engine2_version_disclosure_included_correctly(self):
        cid = self._create_and_run_case()
        # Skipped E2
        self.client.post(f"/api/cases/{cid}/engine2", headers=self.citizen_headers, json={"run": False})
        h_res = self.client.get(f"/api/cases/{cid}/handoff", headers=self.citizen_headers)
        h = h_res.json()["handoff"]
        self.assertTrue(h["engine2_skipped"])
        self.assertEqual(h["engine2_disclosure"], "Case Challenge / Argument Analysis was not run.")

        # Ran E2
        run_engine2(self.app, cid)
        h_res2 = self.client.get(f"/api/cases/{cid}/handoff", headers=self.citizen_headers)
        h2 = h_res2.json()["handoff"]
        self.assertFalse(h2["engine2_skipped"])
        self.assertIn("current Case File", h2["engine2_disclosure"])

    # 23. original evidence remains immutable
    def test_23_original_evidence_remains_immutable(self):
        cid = self._create_and_run_case()
        content = b"ORIGINAL CONTRACT SIGNED"
        up_res = self.client.post(
            f"/api/cases/{cid}/evidence",
            headers=self.citizen_headers,
            files={"file": ("contract.pdf", content, "application/pdf")}
        )
        eid = up_res.json()["evidence"]["evidence_id"]
        before_hash = hashlib.sha256(content).hexdigest()

        # Run E2 and check evidence again
        run_engine2(self.app, cid)
        db = self.app.state.adapters.database
        case = db.get("cases", cid)
        ev_item = next(e for e in case["evidence"] if e["evidence_id"] == eid)
        stored_hash = ev_item.get("content_hash") or ev_item.get("extraction", {}).get("content_hash")
        self.assertEqual(stored_hash, before_hash)

    # 24. no automatic Engine-3 invocation
    def test_24_no_automatic_engine3_invocation(self):
        cid = self._create_and_run_case()
        run_engine2(self.app, cid)
        case = self.app.state.adapters.database.get("cases", cid)
        self.assertEqual(case["status"], "ENGINE2_DONE")
        self.assertNotIn("draft_document", case)
        self.assertNotIn("engine3", case)
        self.assertNotIn("GENERATING_DOCUMENTS", case.get("stage_statuses", {}))


if __name__ == "__main__":
    unittest.main()
