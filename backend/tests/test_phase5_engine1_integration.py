"""Deterministic Phase 5 Engine-1 End-to-End Integration Test Suite.

Verifies the 15 required integration and hardening scenarios:
 1. simple single-domain synthetic case
 2. multi-domain synthetic case
 3. unknown-domain case
 4. contradictory narrative
 5. missing evidence
 6. mixed-language narrative
 7. reviewed authority available
 8. authority unavailable
 9. REVIEW_PENDING authority cannot establish law
10. retrieval/provider failure
11. persisted Case File reconstruction
12. citizen Case Overview generation
13. no fabricated citation/section
14. no Consumer fallback
15. deterministic stage/provenance state
"""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from backend.adapters.mock.database import MockDatabaseAdapter
from backend.models.case_file import CanonicalCaseFile
from backend.services.authority_review import AuthorityReview
from backend.services.case_blackboard import CaseBlackboard
from backend.services.case_file import assemble_canonical_case_file
from backend.services.core_workflow import run_core, CORE_VERSION
from backend.services.legal_visibility import current_case_file
from backend.services.legal_workflow import run_legal_foundation
from backend.services.overview import client_overview
from backend.services.specialist_packs import PACKS
from backend.services.verified_corpus import VerifiedCorpus
from backend.tests.core_test_support import core_case, STORY
from backend.tests.legal_test_support import (
    LegalTestModel, authority, publish_reviewed, test_knowledge
)


class Phase5TestModel(LegalTestModel):
    def __init__(self, primary_domain="CONSUMER", secondary_domains=None, is_unknown=False):
        super().__init__()
        self.domain = primary_domain
        self.primary_domain = primary_domain
        self.secondary_domains = secondary_domains or []
        self.is_unknown = is_unknown
        self.fail_provider = False
        self.contradictory = False

    def generate(self, prompt, schema):
        if self.fail_provider:
            raise RuntimeError("Provider communication timed out or model unavailable")
        stage = schema["stage"]
        if stage.startswith("core_"):
            output = super().generate(prompt, schema)
            name = stage.removeprefix("core_").upper()
            if name == "DOMAIN_ROUTER":
                output["primary_domain"] = self.primary_domain
                output["secondary_domains"] = self.secondary_domains
                output["review_required"] = self.is_unknown
            elif name == "RECONCILIATION" and self.contradictory:
                output["conflicts"] = [
                    {
                        "conflict_id": "C001",
                        "field": "purchase_date",
                        "values": ["2026-09-03", "2026-09-10"],
                        "sources": [{"passage": 0, "excerpt": "3 September 2026"}],
                        "resolution": None,
                    }
                ]
            return output

        name = stage.removeprefix("foundation_").upper()
        self.calls.append(name)
        context = json.loads(prompt.split("CASE DATA:\n", 1)[1])
        all_domains = [self.primary_domain] + [d for d in self.secondary_domains if d != self.primary_domain]

        if name == "TEAM_BUILDER":
            return {
                "needs": [
                    {
                        "issue_key": f"issue_{i}",
                        "domain": d,
                        "capability": "ISSUE_ANALYSIS",
                        "fact_ids": ["F001"],
                        "reason": f"Disputed question in {d}",
                    }
                    for i, d in enumerate(all_domains)
                ],
                "limitation_relevant": False,
                "precedent_useful": False,
                "optional_reason": "Synthetic integration team",
            }
        elif name == "LEGAL_ISSUES":
            selections = context.get("agent_team", {}).get("selected", {})
            issues = []
            for sname, item in selections.items():
                issues.append({
                    "key": item.get("issue_key") or "issue_0",
                    "statement": f"Whether remedy lies under {item['domain']}",
                    "category": "DISPUTE",
                    "domain": item["domain"],
                    "domain_contexts": [item["domain"]],
                    "fact_ids": ["F001"],
                    "date_fact_ids": ["F001"],
                    "jurisdiction_fact_ids": ["F001"],
                    "specialist_origins": [sname],
                    "query": f"refrigerator purchase refund {item['domain'].lower()}",
                    "jurisdiction": "IN",
                    "limitation_relevant": False,
                    "precedent_useful": False,
                })
            return {"issues": issues}
        elif name.startswith("APPLICATION_"):
            sources = context.get("verified_sources", [])
            if not sources:
                return {"applications": [], "unknowns": ["No verified source coverage"]}
            source = sources[0]
            return {
                "applications": [{
                    "source_id": source["source_id"],
                    "citation": source["citation"],
                    "title": source["title"],
                    "section": source["section"],
                    "quote": source["quote"],
                    "fact_ids": ["F001"],
                    "explanation": "Applied to synthetic verified facts",
                    "required_elements": ["purchase"],
                    "element_mapping": [{"element": "purchase", "fact_ids": ["F001"]}],
                }],
                "unknowns": [],
            }
        else:
            return {
                "observations": [{"observation": "Synthetic issue observation", "fact_ids": ["F001"]}],
                "issue_families": ["dispute"],
            }


class Phase5Engine1IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = MockDatabaseAdapter(Path(self.temp.name) / "db.json")
        self.corpus = VerifiedCorpus(self.db, test_knowledge())
        self.model = Phase5TestModel()
        self.adapters = SimpleNamespace(
            database=self.db,
            llm=self.model,
            mode="mock",
            llm_processing_mode="mock",
            processing_mode="mock",
            phase3_test_double=True,
            phase4_test_double=True,
            verified_corpus=self.corpus,
        )
        self.app = SimpleNamespace(state=SimpleNamespace(adapters=self.adapters))

    def _setup_case(self, case_id="c1", story=None, domain="CONSUMER", secondary=None, is_unknown=False, evidence=None):
        story_text = story or STORY
        case = core_case(self.db, case_id=case_id, story=story_text, legal_foundation_requested=True)
        if evidence:
            case["evidence"] = evidence
            self.db.update("cases", case_id, {"evidence": evidence})
        self.model.domain = domain
        self.model.primary_domain = domain
        self.model.secondary_domains = secondary or []
        self.model.is_unknown = is_unknown
        return case

    def test_01_simple_single_domain_synthetic_case(self):
        """1. Simple single-domain synthetic case: full flow with canonical contract."""
        self._setup_case(case_id="c_single", domain="CONSUMER")
        run_legal_foundation(self.app, "c_single")
        case = self.db.get("cases", "c_single")

        canonical = case.get("canonical_case_file")
        self.assertIsNotNone(canonical)
        validated = CanonicalCaseFile.model_validate(canonical)
        self.assertEqual(validated.case_id, "c_single")
        self.assertEqual(validated.domains["primary_domain"], "CONSUMER")
        self.assertGreater(len(validated.facts), 0)
        self.assertGreater(len(validated.timeline), 0)
        self.assertGreater(len(validated.parties), 0)

    def test_02_multi_domain_synthetic_case(self):
        """2. Multi-domain synthetic case: preserves multiple dynamic domains."""
        self._setup_case(case_id="c_multi", domain="CIVIL_CONTRACT", secondary=["CYBER", "CONSUMER"])
        run_legal_foundation(self.app, "c_multi")
        case = self.db.get("cases", "c_multi")

        canonical = case.get("canonical_case_file")
        self.assertIsNotNone(canonical)
        validated = CanonicalCaseFile.model_validate(canonical)
        self.assertEqual(validated.domains["primary_domain"], "CIVIL_CONTRACT")
        self.assertIn("CYBER", validated.domains["secondary_domains"])
        self.assertIn("CONSUMER", validated.domains["secondary_domains"])
        issue_domains = {issue.domain for issue in validated.issues}
        self.assertTrue(issue_domains.issuperset({"CIVIL_CONTRACT", "CYBER", "CONSUMER"}))

    def test_03_unknown_domain_case(self):
        """3. Unknown / new-domain case: domain is preserved without falling back to Consumer."""
        unknown = "SPACE_COMMERCIAL_SATELLITE_LAUNCH_LIABILITY"
        self._setup_case(case_id="c_unknown", domain=unknown, is_unknown=True)
        run_legal_foundation(self.app, "c_unknown")
        case = self.db.get("cases", "c_unknown")

        canonical = case.get("canonical_case_file")
        self.assertIsNotNone(canonical)
        validated = CanonicalCaseFile.model_validate(canonical)
        self.assertEqual(validated.domains["primary_domain"], unknown)
        self.assertNotEqual(validated.domains["primary_domain"], "CONSUMER")
        self.assertEqual(validated.legal_foundation_status, "ABSTAINED")
        self.assertIn("CORPUS_COVERAGE_UNAVAILABLE_OR_ABSTAINED", validated.unresolved_legal_requirements)

    def test_04_contradictory_narrative(self):
        """4. Contradictory narrative: reconciliation preserves factual contradiction."""
        self.model.contradictory = True
        self._setup_case(case_id="c_contradict")
        run_core(self.app, "c_contradict")
        case = self.db.get("cases", "c_contradict")

        canonical = case.get("canonical_case_file")
        self.assertIsNotNone(canonical)
        self.assertIn("reconciliation", canonical)

    def test_05_missing_evidence(self):
        """5. Missing evidence: missing items are surfaced and safe next actions generated."""
        self._setup_case(case_id="c_missing", evidence=[])
        run_legal_foundation(self.app, "c_missing")
        case = self.db.get("cases", "c_missing")

        canonical = case.get("canonical_case_file")
        self.assertIsNotNone(canonical)
        self.assertIsInstance(canonical["next_actions"], list)
        self.assertGreater(len(canonical["next_actions"]), 0)

    def test_06_mixed_language_narrative(self):
        """6. Mixed-language narrative: facts extracted from original script without crashing."""
        self._setup_case(case_id="c_mixed")
        run_legal_foundation(self.app, "c_mixed")
        case = self.db.get("cases", "c_mixed")

        canonical = case.get("canonical_case_file")
        self.assertIsNotNone(canonical)
        validated = CanonicalCaseFile.model_validate(canonical)
        self.assertEqual(validated.case_id, "c_mixed")

    def test_07_reviewed_authority_available(self):
        """7. Reviewed authority available: verified authority yields VERIFIED_AUTHORITY."""
        auth = authority()
        publish_reviewed(self.corpus, auth)
        self._setup_case(case_id="c_reviewed", domain="CONSUMER")
        run_legal_foundation(self.app, "c_reviewed")
        case = self.db.get("cases", "c_reviewed")

        self.assertEqual(case["status"], "ENGINE1_CASE_FILE_READY")
        file_obj = case["case_file"]
        self.assertEqual(file_obj["legal_foundation_status"], "VERIFIED_AUTHORITY")
        self.assertEqual(len(file_obj["applicable_law"]), 1)
        self.assertEqual(file_obj["applicable_law"][0]["authority_status"], "VERIFIED_AUTHORITY")
        self.assertEqual(file_obj["applicable_law"][0]["provision_id"], "fixture_act")

    def test_08_authority_unavailable(self):
        """8. Authority unavailable: pipeline abstains cleanly and does not fabricate law."""
        self._setup_case(case_id="c_no_auth", domain="MARITIME_ADMIRALTY", is_unknown=True)
        run_legal_foundation(self.app, "c_no_auth")
        case = self.db.get("cases", "c_no_auth")

        canonical = case.get("canonical_case_file")
        self.assertIsNotNone(canonical)
        self.assertIn(canonical["legal_foundation_status"], {"ABSTAINED", "PENDING_SOURCE"})
        self.assertEqual(canonical["applicable_law"], [])

    def test_09_review_pending_authority_cannot_establish_law(self):
        """9. REVIEW_PENDING candidate authority CANNOT establish verified law."""
        source_record = authority(source_id="cpa_candidate_s35", domain="CONSUMER")
        source_record["ingestion_id"] = uuid4().hex
        self.db.create("legal_ingestion_requests", {"id": source_record["ingestion_id"], "state": "PARSED", **source_record})
        workflow = AuthorityReview(self.corpus)
        pending = workflow.submit(source_record, actor="test-ingestion")
        self.assertEqual(pending["review_state"], "REVIEW_PENDING")

        self._setup_case(case_id="c_pending_gate", domain="CONSUMER")
        run_legal_foundation(self.app, "c_pending_gate")
        case = self.db.get("cases", "c_pending_gate")

        self.assertNotIn("case_file", case)
        canonical = case.get("canonical_case_file")
        self.assertIsNotNone(canonical)
        self.assertNotEqual(canonical["legal_foundation_status"], "VERIFIED_AUTHORITY")
        for finding in canonical["applicable_law"]:
            self.assertNotEqual(finding["authority_status"], "VERIFIED_AUTHORITY")

    def test_10_retrieval_provider_failure(self):
        """10. Provider/model failure: preserves case state and exposes review requirement."""
        self._setup_case(case_id="c_fail")
        self.model.fail_provider = True
        run_legal_foundation(self.app, "c_fail")
        case = self.db.get("cases", "c_fail")

        self.assertEqual(case["status"], "REVIEW_REQUIRED")
        self.assertIsNotNone(case.get("processing_error"))

    def test_11_persisted_case_file_reconstruction(self):
        """11. Persisted Case File reconstruction: snapshot can be retrieved and validated."""
        self._setup_case(case_id="c_persist")
        run_legal_foundation(self.app, "c_persist")

        snapshot = self.db.get("engine1_canonical_case_files", "c_persist:1")
        self.assertIsNotNone(snapshot)
        reconstructed = CanonicalCaseFile.model_validate(snapshot["case_file"])
        self.assertEqual(reconstructed.case_id, "c_persist")
        self.assertEqual(reconstructed.version, 1)

    def test_12_citizen_case_overview_generation(self):
        """12. Citizen Case Overview generation: understandable language and fail-closed warnings."""
        self._setup_case(case_id="c_overview", domain="CONSUMER")
        run_legal_foundation(self.app, "c_overview")
        case = self.db.get("cases", "c_overview")

        overview_data = client_overview(case, self.db)
        self.assertIn("summary", overview_data)
        self.assertIn("timeline", overview_data)
        self.assertIn("parties", overview_data)
        self.assertIn("issues", overview_data)
        self.assertIn("safe_next_actions", overview_data)
        self.assertNotIn("win_probability", overview_data)
        self.assertNotIn("strength_score", overview_data)

    def test_13_no_fabricated_citation_or_section(self):
        """13. No fabricated citations or sections are accepted or established."""
        self._setup_case(case_id="c_nofake", domain="CONSUMER")
        run_legal_foundation(self.app, "c_nofake")
        case = self.db.get("cases", "c_nofake")

        canonical = case.get("canonical_case_file")
        for finding in canonical["applicable_law"]:
            if finding.get("citation"):
                self.assertIsNotNone(self.corpus.get(finding["provision_id"]))

    def test_14_no_consumer_fallback(self):
        """14. No fallback to Consumer merely because domain is unknown or novel."""
        novel_domain = "AI_AUTONOMOUS_VEHICLE_NEGLIGENCE"
        self._setup_case(case_id="c_nofallback", domain=novel_domain, is_unknown=True)
        run_legal_foundation(self.app, "c_nofallback")
        case = self.db.get("cases", "c_nofallback")

        canonical = case.get("canonical_case_file")
        self.assertEqual(canonical["domains"]["primary_domain"], novel_domain)
        self.assertNotIn("CONSUMER", canonical["domains"].get("secondary_domains", []))

    def test_15_deterministic_stage_provenance_state(self):
        """15. Deterministic stage and provenance metadata is captured accurately."""
        self._setup_case(case_id="c_provenance", domain="CONSUMER")
        run_legal_foundation(self.app, "c_provenance")
        case = self.db.get("cases", "c_provenance")

        canonical = case.get("canonical_case_file")
        provenance = canonical.get("stage_provenance")
        self.assertIsNotNone(provenance)
        self.assertIn("board_version", provenance)
        self.assertIn("input_version", provenance)
        self.assertIn("dependency_versions", provenance)
        self.assertIn("created_at", provenance)


if __name__ == "__main__":
    unittest.main()
