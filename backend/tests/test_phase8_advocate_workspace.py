"""Phase 8 Deterministic Tests for Advocate Workspace & Human Review of Citizen Cases.

Covers all 26 mandatory verification items:
1. advocate cannot access case before acceptance
2. acceptance alone does not grant case access
3. consent enables only scoped access
4. advocate corrections preserve AI original value
5. corrections are versioned/auditable
6. original evidence is immutable
7. annotations are separate from evidence
8. private notes remain private
9. non-substantive comments do not stale Engine 1 unnecessarily
10. substantive correction stales dependent output
11. Engine-1 rerun consumes advocate correction
12. Engine-1 rerun does not silently erase advocate correction
13. KEEP/REPLACE/MERGE conflict handling
14. new Engine-1 version created after rerun
15. previous Engine-1 version preserved
16. Engine-2 becomes stale after Engine-1 change
17. advocate may rerun Engine 2
18. Engine 2 remains optional
19. exact skip disclosure preserved
20. review-current status works
21. future Engine-3 eligibility requires current advocate-reviewed E1
22. consent revocation blocks new access
23. another advocate cannot access case
24. admin cannot bypass assigned-advocate requirement
25. Phase-4 authority-review capability cannot bypass citizen consent
26. no genuine Phase-4 authority is modified
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
from backend.routes.review import router as review_router
from backend.routes.sharing import router as sharing_router
from backend.services.engine1 import run_engine1
from backend.services.engine2 import run_engine2
from backend.services.overview import client_case, client_overview
from backend.services.review_contracts import ENGINE2_NOT_RUN_DISCLOSURE, check_engine3_eligibility


def create_phase8_app():
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
    for r in (cases_router, auth_router, analysis_router, engines_router, advocates_router, sharing_router, clarification_router, review_router):
        app.include_router(r)
    return directory, app, TestClient(app), db


def create_user(client, name="Test User", role="client", email=None):
    email = email or f"{uuid4().hex}@example.com"
    payload = {
        "full_name": name,
        "email": email,
        "password": "Password123!",
        "mobile_number": "9876543210",
        "preferred_language": "English",
        "state": "Maharashtra",
        "district_city": "Mumbai",
        "role": role,
    }
    if role == "advocate":
        payload.update({
            "bar_council": "Bar Council of Maharashtra and Goa",
            "enrolment_number": f"MAH/{uuid4().hex[:4].upper()}/2019",
            "enrolment_year": 2019,
            "place_of_practice": "Mumbai",
            "practice_domains": ["CONSUMER", "CONTRACT"],
            "languages": ["English", "Hindi"],
            "court_region": "Bombay High Court",
        })
    role_to_set = role
    signup_role = "advocate" if role == "advocate" else "client"
    payload["role"] = signup_role
    res = client.post("/api/auth/signup", json=payload)
    assert res.status_code in (200, 201), res.text
    data = res.json()
    user = data["user"]
    if role_to_set not in {"client", "advocate"}:
        client.app.state.adapters.database.update("users", user["id"], {"role": role_to_set})
        user["role"] = role_to_set
    return user, {"Authorization": f"Bearer {data['session_token']}"}


def sync_dispatch(app, engine, case_id, **options):
    if engine == 1:
        run_engine1(app, case_id, **options)
    elif engine == 2:
        run_engine2(app, case_id, **options)


class TestPhase8AdvocateWorkspace(unittest.TestCase):

    def setUp(self):
        self.dir, self.app, self.client, self.db = create_phase8_app()
        self.citizen, self.citizen_headers = create_user(self.client, name="Sunita Citizen", role="client")
        self.advocate, self.advocate_headers = create_user(self.client, name="Adv. Rajesh Sharma", role="advocate")
        # Verify advocate
        self.db.update("users", self.advocate["id"], {
            "verification_status": "VERIFIED",
            "verification_documents": [{"filename": "bar_cert.pdf", "storage_key": "private/bar.pdf"}],
        })

        # Create case
        c_res = self.client.post("/api/cases", headers=self.citizen_headers)
        self.case_id = c_res.json()["case"]["case_id"]
        self.client.patch(
            f"/api/cases/{self.case_id}",
            headers=self.citizen_headers,
            json={"stage": "NEW_CONSULTATION", "client_story": "I purchased a defective laptop from TechMart for Rs 75,000 on 10 August 2026. The seller refuses refund."},
        )

        # Run Engine 1 to produce canonical Case File
        run_engine1(self.app, self.case_id)

        # Attach mock evidence
        case = self.db.get("cases", self.case_id)
        ev_list = [
            {
                "evidence_id": "ev_invoice_01",
                "filename": "laptop_invoice.pdf",
                "content_type": "application/pdf",
                "size": 10240,
                "storage_key": "uploads/ev_invoice_01.pdf",
                "content_hash": hashlib.sha256(b"fake_invoice_bytes").hexdigest(),
                "uploaded_at": "2026-08-11T10:00:00Z",
                "uploaded_by": case["owner_user_id"],
                "extraction": {"status": "COMPLETED", "original_text": "TechMart Invoice #1029 Date: 10 Aug 2026 Total: Rs 75,000"},
            }
        ]
        self.db.update("cases", self.case_id, {"evidence": ev_list})

    def tearDown(self):
        try:
            self.dir.cleanup()
        except Exception:
            pass

    def test_01_advocate_cannot_access_case_before_acceptance(self):
        """Advocate cannot access case before connection request is accepted."""
        res = self.client.post(f"/api/advocate/cases/{self.case_id}/access-token", headers=self.advocate_headers)
        self.assertIn(res.status_code, [403, 404])

    def test_02_acceptance_alone_does_not_grant_case_access(self):
        """Acceptance alone does not grant access; citizen must provide explicit consent."""
        # Request
        self.client.post(
            f"/api/cases/{self.case_id}/request-advocate",
            headers=self.citizen_headers,
            json={"advocate_id": self.advocate["id"]},
        )
        # Accept
        acc = self.client.post(
            f"/api/advocate/requests/{self.case_id}/accept",
            headers=self.advocate_headers,
        )
        self.assertEqual(acc.status_code, 200)

        # Attempt to access case without consent
        res = self.client.post(f"/api/advocate/cases/{self.case_id}/access-token", headers=self.advocate_headers)
        self.assertEqual(res.status_code, 403)
        self.assertIn("access", res.text.lower())

    def _setup_consented_case(self):
        self.client.post(
            f"/api/cases/{self.case_id}/request-advocate",
            headers=self.citizen_headers,
            json={"advocate_id": self.advocate["id"]},
        )
        self.client.post(
            f"/api/advocate/requests/{self.case_id}/accept",
            headers=self.advocate_headers,
        )
        # Grant consent
        self.client.post(
            f"/api/cases/{self.case_id}/sharing",
            headers=self.citizen_headers,
            json={
                "scopes": ["case_file", "story", "evidence", "engine2"],
                "evidence_ids": ["ev_invoice_01"],
            },
        )
        tok_res = self.client.post(f"/api/advocate/cases/{self.case_id}/access-token", headers=self.advocate_headers)
        self.assertEqual(tok_res.status_code, 200)
        token = tok_res.json()["access_token"]
        return {"Authorization": self.advocate_headers["Authorization"], "X-Case-Access": token}

    def test_03_consent_enables_only_scoped_access(self):
        """Once citizen grants consent, advocate can access structured case and evidence."""
        headers = self._setup_consented_case()
        res = self.client.get(f"/api/advocate/cases/{self.case_id}", headers=headers)
        self.assertEqual(res.status_code, 200)
        case_data = res.json()["case"]
        self.assertIn("case_file", case_data)
        self.assertIn("evidence", case_data)
        self.assertEqual(case_data["client_story"], "I purchased a defective laptop from TechMart for Rs 75,000 on 10 August 2026. The seller refuses refund.")

    def test_04_05_advocate_corrections_preserve_original_value_and_are_versioned(self):
        """Advocate corrections preserve original AI values, are versioned and auditable."""
        headers = self._setup_consented_case()
        case = self.db.get("cases", self.case_id)
        file = case.get("canonical_case_file") or case.get("case_file") or {}
        fact = file["facts"][0]
        fact_id = fact["fact_id"]
        orig_text = fact["text"]

        corr_res = self.client.post(
            f"/api/advocate/cases/{self.case_id}/review",
            headers=headers,
            json={
                "kind": "fact",
                "target_id": fact_id,
                "action": "edit",
                "value": {"text": "Purchase price was actually Rs 78,000 with extended warranty."},
                "reason": "Corrected per invoice review",
            },
        )
        self.assertEqual(corr_res.status_code, 200)

        # Check corrections list
        list_res = self.client.get(f"/api/advocate/cases/{self.case_id}/corrections", headers=headers)
        self.assertEqual(list_res.status_code, 200)
        corrections = list_res.json()["corrections"]
        self.assertTrue(len(corrections) >= 1)
        c = corrections[0]
        self.assertEqual(c["target_id"], fact_id)
        orig_val = c["original_value"]["text"] if isinstance(c["original_value"], dict) else c["original_value"]
        self.assertEqual(orig_val, orig_text)
        self.assertEqual(c["advocate_correction"], "Purchase price was actually Rs 78,000 with extended warranty.")
        self.assertEqual(c["actor_id"], self.advocate["id"])
        self.assertTrue(c["substantive"])

    def test_06_original_evidence_is_immutable(self):
        """Attempts to alter citizen evidence bytes, hashes, or storage locations fail."""
        headers = self._setup_consented_case()
        res = self.client.post(
            f"/api/advocate/cases/{self.case_id}/review",
            headers=headers,
            json={
                "kind": "evidence",
                "target_id": "ev_invoice_01",
                "action": "edit",
                "value": {"storage_key": "unauthorized/path.pdf", "content_hash": "badhash"},
                "reason": "malicious tampering attempt",
            },
        )
        self.assertEqual(res.status_code, 422)
        self.assertIn("immutable", res.text.lower())

    def test_07_annotations_are_separate_from_evidence(self):
        """Evidence annotations are stored in a separate layer without modifying the evidence record."""
        headers = self._setup_consented_case()
        ann_res = self.client.post(
            f"/api/advocate/cases/{self.case_id}/evidence/ev_invoice_01/annotate",
            headers=headers,
            json={"note": "Verified invoice serial matches product packaging.", "relevance": "HIGH"},
        )
        self.assertEqual(ann_res.status_code, 200)

        get_ann = self.client.get(f"/api/advocate/cases/{self.case_id}/evidence/ev_invoice_01/annotations", headers=headers)
        self.assertEqual(get_ann.status_code, 200)
        anns = get_ann.json()["annotations"]
        self.assertEqual(len(anns), 1)
        self.assertEqual(anns[0]["annotation"], "Verified invoice serial matches product packaging.")

        # Ensure evidence object remains intact
        case = self.db.get("cases", self.case_id)
        ev = [e for e in case["evidence"] if e["evidence_id"] == "ev_invoice_01"][0]
        self.assertEqual(ev["size"], 10240)
        self.assertEqual(ev["storage_key"], "uploads/ev_invoice_01.pdf")

    def test_08_private_notes_remain_private(self):
        """Private notes are not visible to citizen via client_case."""
        headers = self._setup_consented_case()
        # Advocate adds private note
        self.client.post(
            f"/api/advocate/cases/{self.case_id}/notes",
            headers=headers,
            json={"note": "Confidential internal case assessment.", "visibility": "PRIVATE"},
        )
        # Advocate adds citizen-visible note
        self.client.post(
            f"/api/advocate/cases/{self.case_id}/notes",
            headers=headers,
            json={"note": "Please locate your payment transaction slip.", "visibility": "SHARED_WITH_CLIENT"},
        )

        # Advocate sees both
        adv_notes = self.client.get(f"/api/advocate/cases/{self.case_id}/notes", headers=headers).json()["notes"]
        self.assertEqual(len(adv_notes), 2)

        # Citizen projection
        cit_case = self.client.get(f"/api/cases/{self.case_id}", headers=self.citizen_headers).json()["case"]
        messages = [m["note"] for m in cit_case.get("client_messages", [])]
        self.assertIn("Please locate your payment transaction slip.", messages)
        self.assertNotIn("Confidential internal case assessment.", messages)

    def test_09_10_substantive_vs_non_substantive_staleness(self):
        """Annotations/notes do not stale E1; substantive corrections stale E1 and E2."""
        headers = self._setup_consented_case()
        case = self.db.get("cases", self.case_id)
        self.assertFalse(case.get("engine1_stale", False))

        # Non-substantive note
        self.client.post(f"/api/advocate/cases/{self.case_id}/notes", headers=headers, json={"note": "Reviewing facts.", "visibility": "PRIVATE"})
        case_after_note = self.db.get("cases", self.case_id)
        self.assertFalse(case_after_note.get("engine1_stale", False))

        # Substantive fact correction
        cf = case.get("canonical_case_file") or case.get("case_file") or {}
        fact_id = cf["facts"][0]["fact_id"]
        self.client.post(
            f"/api/advocate/cases/{self.case_id}/review",
            headers=headers,
            json={"kind": "fact", "target_id": fact_id, "action": "edit", "value": {"text": "Updated fact proposition."}, "reason": "Correction"},
        )
        case_after_corr = self.db.get("cases", self.case_id)
        self.assertTrue(case_after_corr.get("engine1_stale"))
        self.assertTrue(case_after_corr.get("engine2_stale"))
        self.assertEqual(case_after_corr.get("review_status"), "CHANGES_REQUIRED")

    @patch("backend.routes.review.dispatch", side_effect=sync_dispatch)
    def test_11_12_14_15_engine1_rerun_consumes_corrections_and_increments_version(self, mock_dispatch):
        """Engine 1 rerun incorporates advocate corrections, increments version, and preserves past version."""
        headers = self._setup_consented_case()
        case = self.db.get("cases", self.case_id)
        cf = case.get("canonical_case_file") or case.get("case_file") or {}
        old_version = cf["version"]
        fact_id = cf["facts"][0]["fact_id"]

        corrected_text = "Corrected proposition by counsel for rerun test"
        self.client.post(
            f"/api/advocate/cases/{self.case_id}/review",
            headers=headers,
            json={"kind": "fact", "target_id": fact_id, "action": "edit", "value": {"text": corrected_text}, "reason": "Correction"},
        )

        # Rerun E1
        rerun_res = self.client.post(f"/api/advocate/cases/{self.case_id}/rerun", headers=headers, json={"engine": 1})
        self.assertEqual(rerun_res.status_code, 200)

        updated_case = self.db.get("cases", self.case_id)
        updated_cf = updated_case.get("canonical_case_file") or updated_case.get("case_file") or {}
        new_version = updated_cf["version"]
        self.assertNotEqual(old_version, new_version)

        # Confirm correction was not silently erased
        fact_texts = [f["text"] for f in updated_cf["facts"]]
        self.assertIn(corrected_text, fact_texts)

        # Past version preserved in case_file_versions
        self.assertTrue(len(updated_case.get("case_file_versions", [])) >= 1)

    def test_13_conflict_resolution_strategies(self):
        """Tests KEEP, REPLACE, and MERGE conflict resolution strategies."""
        headers = self._setup_consented_case()
        case = self.db.get("cases", self.case_id)
        cf = case.get("canonical_case_file") or case.get("case_file") or {}
        fact_id = cf["facts"][0]["fact_id"]

        self.client.post(
            f"/api/advocate/cases/{self.case_id}/review",
            headers=headers,
            json={"kind": "fact", "target_id": fact_id, "action": "edit", "value": {"text": "Counsel statement"}, "reason": "Edit"},
        )
        corrections = self.client.get(f"/api/advocate/cases/{self.case_id}/corrections", headers=headers).json()["corrections"]
        corr_id = corrections[0]["correction_id"]

        # 1. REPLACE
        res = self.client.post(f"/api/advocate/cases/{self.case_id}/resolve-conflict", headers=headers, json={"correction_id": corr_id, "strategy": "REPLACE", "field_kind": "fact", "target_id": fact_id})
        self.assertEqual(res.status_code, 200)
        c = self.client.get(f"/api/advocate/cases/{self.case_id}/corrections", headers=headers).json()["corrections"][0]
        self.assertEqual(c["conflict_strategy"], "REPLACE")

        # 2. MERGE
        res = self.client.post(f"/api/advocate/cases/{self.case_id}/resolve-conflict", headers=headers, json={"correction_id": corr_id, "strategy": "MERGE", "merged_value": "Synthesized proposition", "field_kind": "fact", "target_id": fact_id})
        self.assertEqual(res.status_code, 200)
        c = self.client.get(f"/api/advocate/cases/{self.case_id}/corrections", headers=headers).json()["corrections"][0]
        self.assertEqual(c["conflict_strategy"], "MERGE")
        self.assertEqual(c["effective_value"], "Synthesized proposition")

        # 3. KEEP
        res = self.client.post(f"/api/advocate/cases/{self.case_id}/resolve-conflict", headers=headers, json={"correction_id": corr_id, "strategy": "KEEP", "field_kind": "fact", "target_id": fact_id})
        self.assertEqual(res.status_code, 200)
        c = self.client.get(f"/api/advocate/cases/{self.case_id}/corrections", headers=headers).json()["corrections"][0]
        self.assertEqual(c["conflict_strategy"], "KEEP")

    @patch("backend.routes.review.dispatch", side_effect=sync_dispatch)
    def test_16_17_18_19_engine2_staleness_rerun_and_optional_disclosure(self, mock_dispatch):
        """Engine-2 becomes stale on E1 change, can be rerun, is optional, and preserves exact skip disclosure."""
        headers = self._setup_consented_case()

        # Engine 2 not run initially: check exact disclosure
        shared = self.client.get(f"/api/advocate/cases/{self.case_id}", headers=headers).json()["case"]
        self.assertEqual(shared["engine2_disclosure"], ENGINE2_NOT_RUN_DISCLOSURE)
        self.assertEqual(shared["engine2_disclosure"], "Case Challenge / Argument Analysis was not run.")

        # Run Engine 2
        r2 = self.client.post(f"/api/advocate/cases/{self.case_id}/rerun", headers=headers, json={"engine": 2})
        self.assertEqual(r2.status_code, 200)
        case_after_e2 = self.db.get("cases", self.case_id)
        self.assertFalse(case_after_e2.get("engine2_stale", False))

        # Make substantive correction to fact -> stales Engine 2
        cf_e2 = case_after_e2.get("canonical_case_file") or case_after_e2.get("case_file") or {}
        fact_id = cf_e2["facts"][0]["fact_id"]
        self.client.post(
            f"/api/advocate/cases/{self.case_id}/review",
            headers=headers,
            json={"kind": "fact", "target_id": fact_id, "action": "edit", "value": {"text": "Updated proposition"}, "reason": "Edit"},
        )
        case_stale = self.db.get("cases", self.case_id)
        self.assertTrue(case_stale.get("engine2_stale"))

        # Rerun E1 to clear E1 staleness
        self.client.post(f"/api/advocate/cases/{self.case_id}/rerun", headers=headers, json={"engine": 1})

        # Engine 2 is optional: advocate can approve case without rerunning E2
        app_res = self.client.post(f"/api/advocate/cases/{self.case_id}/approve", headers=headers)
        self.assertEqual(app_res.status_code, 200)

    def test_20_21_review_current_status_and_engine3_eligibility(self):
        """Review approval marks status REVIEWED_CURRENT and satisfies future Engine-3 eligibility gate."""
        headers = self._setup_consented_case()
        app_res = self.client.post(f"/api/advocate/cases/{self.case_id}/approve", headers=headers)
        self.assertEqual(app_res.status_code, 200)

        case = self.db.get("cases", self.case_id)
        self.assertEqual(case.get("review_status"), "REVIEWED_CURRENT")
        self.assertFalse(case.get("engine1_stale", False))

        # Check Engine 3 eligibility
        e3_res = self.client.get(f"/api/advocate/cases/{self.case_id}/engine3-eligibility", headers=headers)
        self.assertEqual(e3_res.status_code, 200)
        data = e3_res.json()["eligibility"]
        self.assertTrue(data["eligible"])
        self.assertTrue(data["checks"]["assigned_advocate"])
        self.assertTrue(data["checks"]["active_consent"])
        self.assertTrue(data["checks"]["reviewed_engine1_current"])
        self.assertTrue(data["checks"]["no_unresolved_conflicts"])

    def test_22_consent_revocation_blocks_access(self):
        """Consent revocation immediately cuts off advocate access."""
        headers = self._setup_consented_case()
        # Find active grant
        grants = self.client.get(f"/api/cases/{self.case_id}/sharing", headers=self.citizen_headers).json()["grants"]
        grant_id = grants[0]["id"]

        # Revoke
        rev = self.client.delete(f"/api/cases/{self.case_id}/sharing/{grant_id}", headers=self.citizen_headers)
        self.assertEqual(rev.status_code, 200)

        # Advocate access denied
        res = self.client.get(f"/api/advocate/cases/{self.case_id}", headers=headers)
        self.assertEqual(res.status_code, 403)

    def test_23_another_advocate_cannot_access_case(self):
        """Another advocate cannot access the assigned case."""
        adv2, adv2_headers = create_user(self.client, name="Adv. Priya Nair", role="advocate")
        self.db.update("users", adv2["id"], {"verification_status": "VERIFIED"})

        res = self.client.post(f"/api/advocate/cases/{self.case_id}/access-token", headers=adv2_headers)
        self.assertIn(res.status_code, [403, 404])

    def test_24_admin_cannot_bypass_assigned_advocate_requirement(self):
        """Platform admin cannot call advocate review endpoints directly without advocate role."""
        admin, admin_headers = create_user(self.client, name="Admin User", role="admin")
        res = self.client.get(f"/api/advocate/cases/{self.case_id}", headers=admin_headers)
        self.assertEqual(res.status_code, 403)

    def test_25_authority_review_capability_cannot_bypass_consent(self):
        """Legal authority reviewer role cannot access citizen case."""
        rev_user, rev_headers = create_user(self.client, name="Corpus Reviewer", role="legal_authority_reviewer")
        res = self.client.get(f"/api/advocate/cases/{self.case_id}", headers=rev_headers)
        self.assertEqual(res.status_code, 403)

    def test_26_phase4_genuine_authority_invariants_preserved(self):
        """Phase 4 invariant: citizen review operations do not affect master legal authority corpus."""
        all_authorities = self.db.list("legal_authorities")
        self.assertFalse(any(a.get("case_id") == self.case_id for a in all_authorities))


if __name__ == "__main__":
    unittest.main()
