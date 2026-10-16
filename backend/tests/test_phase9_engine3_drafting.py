"""Phase 9 Deterministic Tests for Engine 3 / Advocate-Ready Drafting.

Covers all 32 required deterministic test scenarios:
1. only assigned verified advocate may initiate Engine 3
2. acceptance without consent is insufficient
3. revoked consent blocks drafting
4. current advocate-reviewed E1 required
5. stale E1 blocks drafting
6. unresolved correction conflict blocks drafting
7. Engine 2 optional
8. exact Engine-2-not-run disclosure preserved
9. verified Engine-2 version recorded when used
10. REVIEW_PENDING authority cannot appear in draft law
11. unverified/fabricated citation rejected
12. factual working draft behavior respects authority limitations
13. current E1 version bound to draft
14. first draft immutable
15. advocate edit creates new version
16. full regeneration creates new version
17. selective regeneration preserves untouched advocate edits
18. advocate edit wins by default on conflict
19. explicit merge/use-regenerated path works
20. old drafts preserved
21. E1 change marks draft stale
22. historical stale draft remains readable by authorized advocate
23. only advocate can approve
24. approval binds exact draft/E1 version
25. approval hash/audit exists
26. approved PDF becomes new immutable artifact if PDF generation is in scope
27. no automatic filing
28. citizen cannot invoke Engine 3
29. unrelated advocate cannot access draft
30. admin cannot approve as advocate
31. failure does not mutate Engine 1/2
32. no genuine Phase-4 authority is modified
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
from backend.routes.auth import router as auth_router
from backend.routes.cases import router as cases_router
from backend.routes.documents import router as documents_router
from backend.routes.review import router as review_router
from backend.routes.sharing import router as sharing_router
from backend.services.sharing import issue_token
from backend.services.engine3 import (
    approved_content,
    consistency,
    generate_advocate_draft,
    get_advocate_draft,
    edit_advocate_draft,
    regenerate_draft_section,
    resolve_section_conflict,
    regenerate_full_draft,
    approve_advocate_draft,
    list_advocate_drafts,
)
from backend.services.review_contracts import ENGINE2_NOT_RUN_DISCLOSURE, check_engine3_eligibility


def create_phase9_app():
    directory = tempfile.TemporaryDirectory()
    db = MockDatabaseAdapter(directory.name + "/database.json")
    storage = MockStorageAdapter(directory.name + "/uploads")
    adapters = SimpleNamespace(
        database=db,
        storage=storage,
        llm=MockLLMAdapter(),
        auth=MockAuthAdapter(db),
        llm_processing_mode="live",
    )
    app = FastAPI()
    app.state.adapters = adapters
    app.include_router(auth_router)
    app.include_router(cases_router)
    app.include_router(advocates_router)
    app.include_router(sharing_router)
    app.include_router(review_router)
    app.include_router(documents_router)
    return app, db, storage, directory


class Phase9Engine3DraftingTests(unittest.TestCase):
    def setUp(self):
        self.app, self.db, self.storage, self.dir = create_phase9_app()
        self.client = TestClient(self.app)

        # 1. Citizen
        self.citizen = {"id": "cit_1", "email": "cit@test.in", "role": "citizen"}
        self.db.create("users", self.citizen)
        self.db.create("sessions", {"id": "ses_cit", "user_id": "cit_1"})
        self.cit_headers = {"Authorization": "Bearer ses_cit"}

        # 2. Verified Advocate
        self.advocate = {
            "id": "adv_1",
            "email": "adv@bar.in",
            "role": "advocate",
            "verification_status": "VERIFIED",
            "full_name": "Advocate Sharma",
        }
        self.db.create("users", self.advocate)
        self.db.create("sessions", {"id": "ses_adv", "user_id": "adv_1"})
        self.adv_headers = {"Authorization": "Bearer ses_adv"}

        # 3. Unverified Advocate
        self.unverified_adv = {
            "id": "adv_unv",
            "email": "unv@bar.in",
            "role": "advocate",
            "verification_status": "PENDING_VERIFICATION",
        }
        self.db.create("users", self.unverified_adv)
        self.db.create("sessions", {"id": "ses_unv", "user_id": "adv_unv"})
        self.unv_headers = {"Authorization": "Bearer ses_unv"}

        # 4. Unrelated Advocate
        self.unrelated_adv = {
            "id": "adv_2",
            "email": "adv2@bar.in",
            "role": "advocate",
            "verification_status": "VERIFIED",
        }
        self.db.create("users", self.unrelated_adv)
        self.db.create("sessions", {"id": "ses_adv2", "user_id": "adv_2"})
        self.unrelated_headers = {"Authorization": "Bearer ses_adv2"}

        # 5. Platform Admin
        self.admin = {"id": "adm_1", "email": "admin@caseseva.gov.in", "role": "admin"}
        self.db.create("users", self.admin)
        self.db.create("sessions", {"id": "ses_adm", "user_id": "adm_1"})
        self.adm_headers = {"Authorization": "Bearer ses_adm"}

        # 6. Authority Reviewer
        self.auth_reviewer = {"id": "rev_1", "email": "rev@caseseva.gov.in", "role": "admin", "capabilities": ["LEGAL_AUTHORITY_REVIEW"]}
        self.db.create("users", self.auth_reviewer)
        self.db.create("sessions", {"id": "ses_rev", "user_id": "rev_1"})
        self.rev_headers = {"Authorization": "Bearer ses_rev"}

        # Base reviewed Case File
        self.case_id = "case_e3_test"
        self.case_file = {
            "version": 1,
            "case_id": self.case_id,
            "legal_foundation_status": "VERIFIED_AUTHORITY",
            "facts": [
                {"fact_id": "F001", "text": "Complainant paid Rs 50,000 for service not delivered.", "verification_status": "VERIFIED"},
                {"fact_id": "F002", "text": "Notice sent on 15 Jan 2026 was ignored.", "verification_status": "VERIFIED"},
            ],
            "timeline": [
                {"date": "2026-01-15", "description": "Payment made to opposite party."},
                {"date": "2026-01-30", "description": "Service window breached."},
            ],
            "parties": {
                "client_role": "Consumer / Complainant (Ramesh Kumar)",
                "opposite_party": "ABC Retail Services Ltd",
            },
            "forum": {
                "commission_level": "District Consumer Disputes Redressal Commission",
                "verification_status": "VERIFIED",
                "forum_id": "dcdrc_01",
            },
            "applicable_law": [
                {
                    "provision_id": "cpa_2019_s35",
                    "title": "Section 35, Consumer Protection Act, 2019",
                    "section": "35",
                    "verification_status": "VERIFIED",
                    "authority_status": "VERIFIED_AUTHORITY",
                    "review_status": "REVIEWED_CURRENT",
                    "explanation": "Provides for filing complaint before District Commission.",
                }
            ],
            "evidence_inventory": [
                {"evidence_id": "E001", "filename": "receipt_50000.pdf", "description": "Bank payment receipt"},
                {"evidence_id": "E002", "filename": "notice_email.pdf", "description": "Notice email proof"},
            ],
        }

        self.case = {
            "id": self.case_id,
            "case_id": self.case_id,
            "owner_user_id": "cit_1",
            "assigned_advocate_id": "adv_1",
            "status": "ADVOCATE_APPROVED",
            "review_status": "REVIEWED_CURRENT",
            "case_file": self.case_file,
            "canonical_case_file": self.case_file,
            "advocate_approved_case_file_version": 1,
            "engine1_stale": False,
        }
        self.db.create("cases", self.case)

        # Grant active citizen consent covering case_file and evidence
        self.grant = {
            "id": "grant_e3_1",
            "case_id": self.case_id,
            "advocate_id": "adv_1",
            "status": "ACTIVE",
            "scopes": ["case_file", "evidence", "engine2"],
            "evidence_ids": ["E001", "E002"],
            "expires_at": "2030-01-01T00:00:00+00:00",
        }
        self.db.create("case_grants", self.grant)
        self.adv_token = issue_token(self.db, self.grant)
        self.adv_headers["X-Case-Access"] = self.adv_token

    def tearDown(self):
        self.dir.cleanup()

    # 1. only assigned verified advocate may initiate Engine 3
    def test_01_only_assigned_verified_advocate_may_initiate_engine3(self):
        # unverified advocate
        res_unv = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.unv_headers)
        self.assertEqual(res_unv.status_code, 403)

        # non-advocate citizen
        res_cit = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.cit_headers)
        self.assertEqual(res_cit.status_code, 403)

        # unassigned advocate
        res_unrelated = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.unrelated_headers)
        self.assertEqual(res_unrelated.status_code, 403)

        # assigned verified advocate
        res_assigned = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        self.assertEqual(res_assigned.status_code, 200)
        self.assertIn("draft", res_assigned.json())

    # 2. acceptance without consent is insufficient
    def test_02_acceptance_without_consent_is_insufficient(self):
        self.db.delete("case_grants", "grant_e3_1")
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        self.assertEqual(res.status_code, 403)

    # 3. revoked consent blocks drafting
    def test_03_revoked_consent_blocks_drafting(self):
        self.db.update("case_grants", "grant_e3_1", {"status": "REVOKED"})
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        self.assertEqual(res.status_code, 403)

    # 4. current advocate-reviewed E1 required
    def test_04_current_advocate_reviewed_e1_required(self):
        self.db.update("cases", self.case_id, {"review_status": "NOT_REVIEWED", "advocate_approved_case_file_version": None})
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        self.assertEqual(res.status_code, 409)

    # 5. stale E1 blocks drafting
    def test_05_stale_e1_blocks_drafting(self):
        self.db.update("cases", self.case_id, {"engine1_stale": True})
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        self.assertEqual(res.status_code, 409)

    # 6. unresolved correction conflict blocks drafting
    def test_06_unresolved_correction_conflict_blocks_drafting(self):
        self.db.create("advocate_case_corrections", {
            "id": "corr_conflict",
            "case_id": self.case_id,
            "conflict_status": "CONFLICT_DETECTED",
        })
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        self.assertEqual(res.status_code, 409)

    # 7. Engine 2 optional
    def test_07_engine2_optional(self):
        case = self.db.get("cases", self.case_id)
        self.assertNotIn("engine2", case)
        self.assertNotIn("engine2_report", case)
        eligibility = check_engine3_eligibility(case, self.advocate, self.db)
        self.assertTrue(eligibility["eligible"])
        self.assertTrue(eligibility["checks"]["engine2_optional"])

    # 8. exact Engine-2-not-run disclosure preserved
    def test_08_exact_engine2_not_run_disclosure_preserved(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        self.assertEqual(res.status_code, 200)
        draft = res.json()["draft"]
        self.assertIn(ENGINE2_NOT_RUN_DISCLOSURE, draft["disclosures"])
        self.assertEqual(draft["provenance"]["engine2_disclosure"], ENGINE2_NOT_RUN_DISCLOSURE)

    # 9. verified Engine-2 version recorded when used
    def test_09_verified_engine2_version_recorded_when_used(self):
        self.db.update("cases", self.case_id, {
            "engine2": {"run_id": "e2_run_999", "overview_ready": True, "status": "COMPLETED"},
        })
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        self.assertEqual(res.status_code, 200)
        draft = res.json()["draft"]
        self.assertEqual(draft["engine2_run_id"], "e2_run_999")
        self.assertEqual(draft["engine2_status"], "COMPLETED")

    # 10. REVIEW_PENDING authority cannot appear in draft law
    def test_10_review_pending_authority_cannot_appear_in_draft_law(self):
        cf = copy.deepcopy(self.case_file)
        cf["applicable_law"].append({
            "provision_id": "candidate_dspe_s1",
            "title": "DSPE Act Section 1",
            "section": "1",
            "verification_status": "PENDING_HUMAN_REVIEW",
            "authority_status": "PENDING_SOURCE",
            "review_status": "REVIEW_PENDING",
            "explanation": "Should never be cited in draft",
        })
        self.db.update("cases", self.case_id, {"case_file": cf, "canonical_case_file": cf})
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        self.assertEqual(res.status_code, 200)
        draft = res.json()["draft"]
        all_draft_text = " ".join(" ".join(s["paragraphs"]) for s in draft["sections"])
        self.assertNotIn("candidate_dspe_s1", all_draft_text)
        self.assertNotIn("DSPE Act Section 1", all_draft_text)

    # 11. unverified/fabricated citation rejected
    def test_11_unverified_fabricated_citation_rejected(self):
        draft_dict = {
            "cited_provision_ids": ["FABRICATED_SEC_999"],
            "annexure_references": [],
            "sections": [{"heading": "Legal grounds", "paragraphs": ["Section 999 applies"], "provision_ids": ["FABRICATED_SEC_999"]}],
        }
        content = approved_content(self.db.get("cases", self.case_id))
        findings = consistency(draft_dict, content)
        failed_checks = {f["check"] for f in findings if f["result"] == "FAIL"}
        self.assertIn("approved_verified_law_only", failed_checks)
        self.assertIn("section_references", failed_checks)

    # 12. factual working draft behavior respects authority limitations
    def test_12_factual_working_draft_behavior_respects_authority_limitations(self):
        cf = copy.deepcopy(self.case_file)
        cf["legal_foundation_status"] = "PENDING_SOURCE"
        self.db.update("cases", self.case_id, {"case_file": cf, "canonical_case_file": cf})

        # Authoritative mode fails closed!
        res_auth = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition", "draft_mode": "AUTHORITATIVE"}, headers=self.adv_headers)
        self.assertEqual(res_auth.status_code, 422)
        self.assertIn("Authoritative legal drafting blocked", res_auth.json()["detail"])

        # Factual working draft mode succeeds safely
        res_work = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition", "draft_mode": "FACTUAL_WORKING_DRAFT"}, headers=self.adv_headers)
        self.assertEqual(res_work.status_code, 200)
        draft = res_work.json()["draft"]
        self.assertEqual(draft["draft_mode"], "FACTUAL_WORKING_DRAFT")
        legal_sec = next((s for s in draft["sections"] if s["section_id"] == "legal_basis"), None)
        self.assertIn("Factual Working Draft", " ".join(legal_sec["paragraphs"]))

    # 13. current E1 version bound to draft
    def test_13_current_e1_version_bound_to_draft(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft = res.json()["draft"]
        self.assertEqual(draft["engine1_case_file_version"], 1)

    # 14. first draft immutable
    def test_14_first_draft_immutable(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]
        v1_id = f"{draft_id}_v1"
        self.assertIsNotNone(self.db.get("engine3_draft_versions", v1_id))
        with self.assertRaises(ValueError):
            self.db.mutate("engine3_draft_versions", v1_id, lambda d: {**d, "mutated": True})

    # 15. advocate edit creates new version
    def test_15_advocate_edit_creates_new_version(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        edit_res = self.client.post(
            f"/api/cases/{self.case_id}/drafts/{draft_id}/edit",
            json={
                "title": "Customized Advocate Pleading",
                "section_updates": [{"section_id": "facts", "paragraphs": ["1. Advocate manually refined fact proposition."]}],
            },
            headers=self.adv_headers,
        )
        self.assertEqual(edit_res.status_code, 200)
        updated = edit_res.json()["draft"]
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["status"], "ADVOCATE_EDITED")
        self.assertEqual(updated["parent_version_id"], f"{draft_id}_v1")

    # 16. full regeneration creates new version
    def test_16_full_regeneration_creates_new_version(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        regen_res = self.client.post(f"/api/cases/{self.case_id}/drafts/{draft_id}/regenerate-full", headers=self.adv_headers)
        self.assertEqual(regen_res.status_code, 200)
        updated = regen_res.json()["draft"]
        self.assertEqual(updated["version"], 2)

    # 17. selective regeneration preserves untouched advocate edits
    def test_17_selective_regeneration_preserves_untouched_advocate_edits(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        # Advocate edits legal_basis
        self.client.post(
            f"/api/cases/{self.case_id}/drafts/{draft_id}/edit",
            json={"section_updates": [{"section_id": "legal_basis", "paragraphs": ["1. Custom advocate analysis under Section 35."]}]},
            headers=self.adv_headers,
        )

        # Selectively regenerate only "facts"
        regen_sec = self.client.post(
            f"/api/cases/{self.case_id}/drafts/{draft_id}/regenerate-section",
            json={"section_id": "facts"},
            headers=self.adv_headers,
        )
        self.assertEqual(regen_sec.status_code, 200)
        draft_v3 = regen_sec.json()["draft"]
        self.assertEqual(draft_v3["version"], 3)

        # Verify untouched advocate edit in legal_basis is 100% preserved!
        legal_sec = next((s for s in draft_v3["sections"] if s["section_id"] == "legal_basis"), None)
        self.assertEqual(legal_sec["paragraphs"], ["1. Custom advocate analysis under Section 35."])

    # 18. advocate edit wins by default on conflict
    def test_18_advocate_edit_wins_by_default_on_conflict(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        # Edit facts manually
        self.client.post(
            f"/api/cases/{self.case_id}/drafts/{draft_id}/edit",
            json={"section_updates": [{"section_id": "facts", "paragraphs": ["Advocate authoritative facts."]}]},
            headers=self.adv_headers,
        )

        # Regenerate facts -> CONFLICT DETECTED
        regen_res = self.client.post(
            f"/api/cases/{self.case_id}/drafts/{draft_id}/regenerate-section",
            json={"section_id": "facts"},
            headers=self.adv_headers,
        )
        draft_v3 = regen_res.json()["draft"]
        facts_sec = next((s for s in draft_v3["sections"] if s["section_id"] == "facts"), None)
        self.assertIsNotNone(facts_sec.get("conflict"))
        self.assertTrue(facts_sec["conflict"]["has_conflict"])
        # Advocate edits remain authoritative by default!
        self.assertEqual(facts_sec["paragraphs"], ["Advocate authoritative facts."])

    # 19. explicit merge/use-regenerated path works
    def test_19_explicit_merge_use_regenerated_path_works(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        self.client.post(
            f"/api/cases/{self.case_id}/drafts/{draft_id}/edit",
            json={"section_updates": [{"section_id": "facts", "paragraphs": ["Advocate authoritative facts."]}]},
            headers=self.adv_headers,
        )
        self.client.post(
            f"/api/cases/{self.case_id}/drafts/{draft_id}/regenerate-section",
            json={"section_id": "facts"},
            headers=self.adv_headers,
        )

        # Resolve with USE_REGENERATED
        resolve_res = self.client.post(
            f"/api/cases/{self.case_id}/drafts/{draft_id}/resolve-conflict",
            json={"section_id": "facts", "strategy": "USE_REGENERATED"},
            headers=self.adv_headers,
        )
        self.assertEqual(resolve_res.status_code, 200)
        draft_v4 = resolve_res.json()["draft"]
        facts_sec = next((s for s in draft_v4["sections"] if s["section_id"] == "facts"), None)
        self.assertIsNone(facts_sec.get("conflict"))
        self.assertNotEqual(facts_sec["paragraphs"], ["Advocate authoritative facts."])

    # 20. old drafts preserved
    def test_20_old_drafts_preserved(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        self.client.post(
            f"/api/cases/{self.case_id}/drafts/{draft_id}/edit",
            json={"title": "Version 2 Title"},
            headers=self.adv_headers,
        )

        # Fetch v1
        v1_res = self.client.get(f"/api/cases/{self.case_id}/drafts/{draft_id}?version=1", headers=self.adv_headers)
        self.assertEqual(v1_res.status_code, 200)
        self.assertEqual(v1_res.json()["draft"]["version"], 1)

        # Fetch v2
        v2_res = self.client.get(f"/api/cases/{self.case_id}/drafts/{draft_id}?version=2", headers=self.adv_headers)
        self.assertEqual(v2_res.status_code, 200)
        self.assertEqual(v2_res.json()["draft"]["version"], 2)

    # 21. E1 change marks draft stale
    def test_21_e1_change_marks_draft_stale(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        # E1 increments to version 2
        cf2 = copy.deepcopy(self.case_file)
        cf2["version"] = 2
        self.db.update("cases", self.case_id, {"case_file": cf2, "canonical_case_file": cf2, "advocate_approved_case_file_version": 2})

        draft = get_advocate_draft(self.db, self.case_id, draft_id)
        self.assertEqual(draft.status, "STALE_INPUT")

    # 22. historical stale draft remains readable by authorized advocate
    def test_22_historical_stale_draft_remains_readable_by_authorized_advocate(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        cf2 = copy.deepcopy(self.case_file)
        cf2["version"] = 2
        self.db.update("cases", self.case_id, {"case_file": cf2, "canonical_case_file": cf2})

        fetch_res = self.client.get(f"/api/cases/{self.case_id}/drafts/{draft_id}", headers=self.adv_headers)
        self.assertEqual(fetch_res.status_code, 200)
        self.assertEqual(fetch_res.json()["draft"]["status"], "STALE_INPUT")

    # 23. only advocate can approve
    def test_23_only_advocate_can_approve(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        # Citizen cannot approve
        res_cit = self.client.post(f"/api/cases/{self.case_id}/drafts/{draft_id}/approve", headers=self.cit_headers)
        self.assertEqual(res_cit.status_code, 403)

        # Admin cannot approve
        res_adm = self.client.post(f"/api/cases/{self.case_id}/drafts/{draft_id}/approve", headers=self.adm_headers)
        self.assertEqual(res_adm.status_code, 403)

    # 24. approval binds exact draft/E1 version
    def test_24_approval_binds_exact_draft_e1_version(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        app_res = self.client.post(f"/api/cases/{self.case_id}/drafts/{draft_id}/approve", headers=self.adv_headers)
        self.assertEqual(app_res.status_code, 200)
        draft = app_res.json()["draft"]
        self.assertEqual(draft["status"], "ADVOCATE_APPROVED")
        self.assertEqual(draft["approval_record"]["approved_by_advocate_id"], "adv_1")
        self.assertEqual(draft["approval_record"]["source_engine1_version"], 1)

    # 25. approval hash/audit exists
    def test_25_approval_hash_audit_exists(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        app_res = self.client.post(f"/api/cases/{self.case_id}/drafts/{draft_id}/approve", headers=self.adv_headers)
        approval = app_res.json()["draft"]["approval_record"]
        self.assertIsNotNone(approval["integrity_hash"])
        self.assertEqual(len(approval["integrity_hash"]), 64)

    # 26. approved PDF becomes new immutable artifact if PDF generation is in scope
    def test_26_approved_pdf_becomes_new_immutable_artifact(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        app_res = self.client.post(f"/api/cases/{self.case_id}/drafts/{draft_id}/approve", headers=self.adv_headers)
        draft = app_res.json()["draft"]
        self.assertIsNotNone(draft.get("pdf_artifact"))
        storage_key = draft["pdf_artifact"]["storage_key"]
        self.assertIn("approved_draft", storage_key)

        # Download PDF
        dl_res = self.client.get(f"/api/cases/{self.case_id}/drafts/{draft_id}/pdf", headers=self.adv_headers)
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res.headers["content-type"], "application/pdf")
        self.assertTrue(dl_res.content.startswith(b"%PDF"))

    # 27. no automatic filing
    def test_27_no_automatic_filing(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]
        self.client.post(f"/api/cases/{self.case_id}/drafts/{draft_id}/approve", headers=self.adv_headers)
        case = self.db.get("cases", self.case_id)
        # Never filed automatically; phase 10 is untouched
        self.assertNotIn(case["status"], {"FILED", "SUBMITTED_TO_COURT", "REGISTERED"})

    # 28. citizen cannot invoke Engine 3
    def test_28_citizen_cannot_invoke_engine3(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.cit_headers)
        self.assertEqual(res.status_code, 403)

    # 29. unrelated advocate cannot access draft
    def test_29_unrelated_advocate_cannot_access_draft(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        get_res = self.client.get(f"/api/cases/{self.case_id}/drafts/{draft_id}", headers=self.unrelated_headers)
        self.assertEqual(get_res.status_code, 403)

        edit_res = self.client.post(f"/api/cases/{self.case_id}/drafts/{draft_id}/edit", json={"title": "Hacked"}, headers=self.unrelated_headers)
        self.assertEqual(edit_res.status_code, 403)

    # 30. admin cannot approve as advocate
    def test_30_admin_cannot_approve_as_advocate(self):
        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        draft_id = res.json()["draft"]["draft_id"]

        app_res = self.client.post(f"/api/cases/{self.case_id}/drafts/{draft_id}/approve", headers=self.adm_headers)
        self.assertEqual(app_res.status_code, 403)

    # 31. failure does not mutate Engine 1/2
    def test_31_failure_does_not_mutate_engine1_2(self):
        before_case = copy.deepcopy(self.db.get("cases", self.case_id))
        with patch("backend.services.engine3.render_draft_html", side_effect=RuntimeError("Simulated generation crash")):
            res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
            self.assertEqual(res.status_code, 500)

        after_case = self.db.get("cases", self.case_id)
        self.assertEqual(before_case["case_file"], after_case["case_file"])
        self.assertEqual(before_case["canonical_case_file"], after_case["canonical_case_file"])

    # 32. no genuine Phase-4 authority is modified
    def test_32_no_genuine_phase4_authority_is_modified(self):
        # Verify that generating drafts never touches legal authority collections
        self.db.create("legal_authority_versions", {"id": "auth_v_test", "review_status": "REVIEW_PENDING"})
        before_auth = copy.deepcopy(self.db.list("legal_authority_versions"))

        res = self.client.post(f"/api/cases/{self.case_id}/drafts/generate", json={"draft_type": "complaint_petition"}, headers=self.adv_headers)
        self.assertEqual(res.status_code, 200)

        after_auth = self.db.list("legal_authority_versions")
        self.assertEqual(before_auth, after_auth)
