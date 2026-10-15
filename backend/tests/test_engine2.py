import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.tests.helpers import test_app, client_account
from backend.services.engine1 import run_engine1
from backend.services.engine2 import run_engine2, validate_references, get_canonical_foundation
from backend.routes.engines import router
from backend.models.engines import CaseChallengeReport
from backend.services.overview import client_overview
from backend.services.review_contracts import ENGINE2_NOT_RUN_DISCLOSURE


class Engine2Tests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app, self.client = test_app()
        self.app.include_router(router)
        _, self.headers = client_account(self.client)
        self.id = self.client.post("/api/cases", headers=self.headers).json()["case"]["case_id"]
        self.client.patch(
            f"/api/cases/{self.id}",
            headers=self.headers,
            json={"stage": "NEW_CONSULTATION", "client_story": "An actual dispute regarding non-delivery"}
        )
        run_engine1(self.app, self.id)

    def tearDown(self):
        self.directory.cleanup()

    def test_engine2_never_calls_engine1_or_retrieval(self):
        before = copy.deepcopy(self.app.state.adapters.database.get("cases", self.id)["case_file"])
        with patch("backend.services.engine1.run_engine1", side_effect=AssertionError("Engine 1 boundary")), \
             patch("backend.services.legal_knowledge.LegalKnowledge.search", side_effect=AssertionError("Retrieval boundary")):
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

    def test_opt_out_disclosure_remains_exact(self):
        self.client.post(f"/api/cases/{self.id}/engine2", headers=self.headers, json={"run": False})
        overview = client_overview(self.app.state.adapters.database.get("cases", self.id), self.app.state.adapters.database)
        self.assertEqual(overview["argument_analysis_note"], "Adversarial case-strengthening analysis was not run on the current Case File.")
        self.assertEqual(ENGINE2_NOT_RUN_DISCLOSURE, "Case Challenge / Argument Analysis was not run.")

    def test_unverified_authority_references_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_references({"points": [{"provision_ids": ["invented"]}]}, {"applicable_law": []})

    def test_unverified_facts_and_unreadable_evidence_cannot_be_argument_premises(self):
        foundation = {
            "facts": [{"fact_id": "F1", "verification_status": "UNVERIFIED"}],
            "evidence_index": [{"evidence_id": "E1", "verification_status": "PENDING_ADVOCATE_VERIFICATION"}]
        }
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

    def test_canonical_snapshot_consumed_and_bound_to_case_file_version(self):
        db = self.app.state.adapters.database
        canonical_snapshot = {
            "id": f"{self.id}:3",
            "case_id": self.id,
            "version": 3,
            "facts": [{"fact_id": "F001", "text": "Laptop was damaged", "verification_status": "VERIFIED", "source_status": "SUPPORTED_BY_EVIDENCE"}],
            "timeline": [],
            "parties": [{"party_id": "P1", "name": "Citizen"}],
            "issues": [{"issue_id": "Q001", "question": "Whether replacement is due?", "category": "FACTUAL_DISPUTE"}],
            "applicable_law": [],
            "legal_foundation_status": "PENDING_SOURCE",
        }
        db.create("engine1_canonical_case_files", {"id": f"{self.id}:3", "case_id": self.id, "case_file": canonical_snapshot})
        db.update("cases", self.id, {"canonical_case_file": canonical_snapshot, "status": "ENGINE1_CASE_FILE_READY"})

        foundation, version = get_canonical_foundation(db.get("cases", self.id), db)
        self.assertEqual(version, 3)

        run_engine2(self.app, self.id, actor_id="citizen_tester", actor_role="citizen")
        case = db.get("cases", self.id)
        self.assertEqual(case["engine2_case_file_version"], 3)
        self.assertEqual(case["engine2"]["engine1_case_file_version"], 3)
        self.assertFalse(case["engine2_stale"])

        # Engine 1 canonical snapshot was not mutated
        stored_snapshot = db.get("engine1_canonical_case_files", f"{self.id}:3")["case_file"]
        self.assertEqual(stored_snapshot["version"], 3)
        self.assertEqual(stored_snapshot["facts"][0]["text"], "Laptop was damaged")

    def test_pending_source_case_runs_factual_challenge_without_statutory_law(self):
        db = self.app.state.adapters.database
        canonical_snapshot = {
            "id": f"{self.id}:1",
            "case_id": self.id,
            "version": 1,
            "facts": [
                {"fact_id": "F001", "text": "Product stopped working on day 2", "verification_status": "VERIFIED", "source_status": "SUPPORTED_BY_EVIDENCE"},
                {"fact_id": "F002", "text": "Seller was called verbally", "verification_status": "UNVERIFIED", "source_status": "UNVERIFIED"}
            ],
            "timeline": [{"timeline_id": "T1", "description": "Delivery date"}],
            "parties": [{"party_id": "P1", "name": "Buyer"}, {"party_id": "P2", "name": "Seller"}],
            "issues": [{"issue_id": "Q001", "question": "Whether product had latent defect?", "category": "FACTUAL_DISPUTE"}],
            "missing_evidence": ["Courier delivery acknowledgement"],
            "applicable_law": [],
            "legal_foundation_status": "PENDING_SOURCE",
        }
        db.create("engine1_canonical_case_files", {"id": f"{self.id}:1", "case_id": self.id, "case_file": canonical_snapshot})
        db.update("cases", self.id, {"canonical_case_file": canonical_snapshot, "status": "CASE_UNDERSTANDING_READY"})

        run_engine2(self.app, self.id)

        case = db.get("cases", self.id)
        report = case["engine2_report"]
        self.assertEqual(report["status"], "COMPLETED")
        self.assertEqual(report["engine1_case_file_version"], 1)

        # Verified law was NOT manufactured
        self.assertTrue(len(report["legal_authority_limitations"]) > 0)
        self.assertIn("PENDING_SOURCE", report["legal_authority_limitations"][0])
        for arg in report["opposing_arguments"]:
            self.assertEqual(arg["provision_ids"], [])

        # Factual weaknesses and evidence gaps were produced
        self.assertTrue(len(report["factual_weaknesses"]) > 0)
        self.assertTrue(len(report["evidence_gaps"]) > 0)

    def test_abstained_case_runs_factual_challenge_without_statutory_law(self):
        db = self.app.state.adapters.database
        canonical_snapshot = {
            "id": f"{self.id}:2",
            "case_id": self.id,
            "version": 2,
            "facts": [{"fact_id": "F001", "text": "Contract breached", "verification_status": "VERIFIED", "source_status": "SUPPORTED_BY_EVIDENCE"}],
            "timeline": [],
            "parties": [],
            "issues": [{"issue_id": "Q001", "question": "Was delivery timely?", "category": "FACTUAL_DISPUTE"}],
            "applicable_law": [],
            "legal_foundation_status": "ABSTAINED",
        }
        db.create("engine1_canonical_case_files", {"id": f"{self.id}:2", "case_id": self.id, "case_file": canonical_snapshot})
        db.update("cases", self.id, {"canonical_case_file": canonical_snapshot, "status": "CASE_UNDERSTANDING_READY"})

        run_engine2(self.app, self.id)

        case = db.get("cases", self.id)
        report = case["engine2_report"]
        self.assertEqual(report["status"], "COMPLETED")
        self.assertTrue(any("ABSTAINED" in lim for lim in report["legal_authority_limitations"]))

    def test_review_pending_authority_is_never_treated_as_verified_law(self):
        db = self.app.state.adapters.database
        candidate_law = [{
            "provision_id": "dspe_act_1946_s1",
            "title": "Delhi Special Police Establishment Act, 1946",
            "verification_status": "PENDING_HUMAN_REVIEW",
            "authority_status": "PENDING_SOURCE",
        }]
        canonical_snapshot = {
            "id": f"{self.id}:1",
            "case_id": self.id,
            "version": 1,
            "facts": [{"fact_id": "F001", "text": "Dispute occurred", "verification_status": "VERIFIED", "source_status": "SUPPORTED_BY_EVIDENCE"}],
            "issues": [{"issue_id": "Q001", "question": "Investigation validity", "category": "FACTUAL_DISPUTE"}],
            "applicable_law": candidate_law,
            "legal_foundation_status": "PENDING_SOURCE",
        }
        db.create("engine1_canonical_case_files", {"id": f"{self.id}:1", "case_id": self.id, "case_file": canonical_snapshot})
        db.update("cases", self.id, {"canonical_case_file": canonical_snapshot})

        run_engine2(self.app, self.id)
        case = db.get("cases", self.id)
        report = case["engine2_report"]

        # REVIEW_PENDING candidate was NOT cited as verified law
        for arg in report["opposing_arguments"]:
            self.assertNotIn("dspe_act_1946_s1", arg["provision_ids"])

    def test_verified_authority_references_validate_and_invented_rejected(self):
        verified_case_file = {
            "facts": [{"fact_id": "F1", "verification_status": "VERIFIED"}],
            "evidence_index": [{"evidence_id": "E1", "verification_status": "VERIFIED"}],
            "applicable_law": [{
                "provision_id": "cpa2019_s2_11",
                "verification_status": "VERIFIED",
                "authority_status": "VERIFIED_AUTHORITY",
            }]
        }
        # Valid citation passes
        validate_references({"points": [{"fact_ids": ["F1"], "evidence_ids": ["E1"], "provision_ids": ["cpa2019_s2_11"]}]}, verified_case_file)

        # Invented citation is rejected
        with self.assertRaises(ValueError):
            validate_references({"points": [{"provision_ids": ["invented_section_420"]}]}, verified_case_file)

    def test_no_win_probability_or_outcome_prediction_in_report_or_overview(self):
        run_engine2(self.app, self.id)
        case = self.app.state.adapters.database.get("cases", self.id)
        report = case["engine2_report"]
        overview = client_overview(case, self.app.state.adapters.database)

        forbidden_keys = {"win_probability", "win_percentage", "success_rate", "outcome_prediction", "case_score", "likely_winner"}
        for k in forbidden_keys:
            self.assertNotIn(k, report)
            self.assertNotIn(k, overview)
            self.assertNotIn(k, case["engine2"])

    def test_immutable_engine2_run_persistence_and_rerun_versioning(self):
        db = self.app.state.adapters.database
        run_engine2(self.app, self.id)

        reports_first = [r for r in db.list("engine2_challenge_reports") if r.get("case_id") == self.id]
        self.assertEqual(len(reports_first), 1)
        self.assertEqual(reports_first[0]["version"], 1)

        # Mutating or deleting reports in append-only collection is rejected
        with self.assertRaises(ValueError):
            db.update("engine2_challenge_reports", reports_first[0]["id"], {"status": "TAMPERED"})
        with self.assertRaises(ValueError):
            db.delete("engine2_challenge_reports", reports_first[0]["id"])

        # Second run creates a new run with incremented version
        run_engine2(self.app, self.id)
        reports_second = [r for r in db.list("engine2_challenge_reports") if r.get("case_id") == self.id]
        self.assertEqual(len(reports_second), 2)
        versions = {r["version"] for r in reports_second}
        self.assertEqual(versions, {1, 2})

    def test_engine1_version_change_marks_engine2_stale(self):
        db = self.app.state.adapters.database
        canonical_v1 = {
            "id": f"{self.id}:1",
            "case_id": self.id,
            "version": 1,
            "facts": [{"fact_id": "F001", "text": "Dispute"}],
            "issues": [{"issue_id": "Q001", "question": "Question 1"}],
        }
        db.create("engine1_canonical_case_files", {"id": f"{self.id}:1", "case_id": self.id, "case_file": canonical_v1})
        db.update("cases", self.id, {"canonical_case_file": canonical_v1, "status": "CASE_UNDERSTANDING_READY"})

        run_engine2(self.app, self.id)
        overview_v1 = client_overview(db.get("cases", self.id), db)
        self.assertTrue(overview_v1["argument_analysis_run"])
        self.assertFalse(overview_v1["engine2_stale"])

        # New Engine 1 version arrived
        canonical_v2 = {
            "id": f"{self.id}:2",
            "case_id": self.id,
            "version": 2,
            "facts": [{"fact_id": "F001", "text": "Dispute"}, {"fact_id": "F002", "text": "Additional fact"}],
            "issues": [{"issue_id": "Q001", "question": "Question 1"}],
        }
        db.create("engine1_canonical_case_files", {"id": f"{self.id}:2", "case_id": self.id, "case_file": canonical_v2})
        db.update("cases", self.id, {"canonical_case_file": canonical_v2})

        overview_v2 = client_overview(db.get("cases", self.id), db)
        self.assertFalse(overview_v2["argument_analysis_run"])
        self.assertTrue(overview_v2["engine2_stale"])
        self.assertIn("is now stale", overview_v2["argument_analysis_note"])

    def test_engine2_failure_cannot_mutate_engine1(self):
        db = self.app.state.adapters.database
        before_file = copy.deepcopy(db.get("cases", self.id).get("case_file"))
        with patch.object(self.app.state.adapters.llm, "generate", side_effect=RuntimeError("Provider outage")):
            run_engine2(self.app, self.id)

        case = db.get("cases", self.id)
        self.assertEqual(case["status"], "REVIEW_REQUIRED")
        self.assertEqual(case.get("case_file"), before_file)

    def test_citizen_overview_safely_exposes_challenge_summary(self):
        run_engine2(self.app, self.id)
        overview = client_overview(self.app.state.adapters.database.get("cases", self.id), self.app.state.adapters.database)

        self.assertIn("key_challenges", overview)
        self.assertIn("evidence_gaps", overview)
        self.assertIn("unresolved_contradictions", overview)
        self.assertIn("preparation_actions", overview)
        self.assertIn("legal_authority_limitations", overview)

    def test_no_automatic_engine3_execution(self):
        with patch("backend.services.engine3.run_engine3", side_effect=AssertionError("Engine 3 should not be called")):
            run_engine2(self.app, self.id)
        case = self.app.state.adapters.database.get("cases", self.id)
        self.assertEqual(case["status"], "ENGINE2_DONE")
        self.assertNotIn("engine3", case)
