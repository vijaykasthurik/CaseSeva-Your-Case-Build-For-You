"""Deterministic test suite for Case-Driven Multi-Domain Issue Model.

Verifies:
1. One-domain case: Case with issues in a single domain.
2. Two-domain case: Case with concurrent issues across two domains (e.g. CONTRACT + CYBER).
3. Three-domain case: Case with issues across three domains (CONTRACT + CYBER + CONSUMER).
4. Unknown / new-domain case: Case with an unregistered emerging domain (e.g. AVIATION_PASSENGER_COMPENSATION)
   where the domain label is preserved on the issue, schema validation succeeds, and authority gate cleanly
   abstains (NO_MATCHING_SOURCE_COVERAGE) without falling back to Consumer.
5. Overlapping issue across two domain packs: Issue touching multiple packs evaluated against respective
   authorities with strict cross-domain safety.
"""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.adapters.mock.database import MockDatabaseAdapter
from backend.models.understanding import DomainCandidates, LanguageAssessment, is_known_domain_pack
from backend.models.legal_foundation import IssueCandidate
from backend.services.case_blackboard import CaseBlackboard
from backend.services.legal_checks import LegalChecks, compact
from backend.services.verified_corpus import VerifiedCorpus
from backend.tests.legal_test_support import LegalTestModel, authority, test_knowledge, publish_reviewed


def make_test_authority(source_id: str, title: str, section: str, domain: str, quote: str):
    text = f"{title}\n{quote}"
    start = text.index(quote)
    return authority(
        source_id=source_id,
        temporal_source_ids=[source_id],
        title=title,
        section=section,
        citation=f"{title}, section {section}",
        domain=domain,
        official_text=text,
        quote=quote,
        section_start=start,
        section_end=start + len(quote),
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )


class CaseDrivenMultiDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = MockDatabaseAdapter(Path(self.temp.name) / "db.json")
        self.corpus = VerifiedCorpus(self.db, test_knowledge())
        self.model = LegalTestModel()
        self.adapters = SimpleNamespace(
            database=self.db, llm=self.model, mode="mock", processing_mode="mock", llm_processing_mode="mock", phase3_test_double=True, phase4_test_double=True
        )
        self.checks = LegalChecks(self.adapters, self.corpus)
        self.store = CaseBlackboard(self.db)

        # Seed authorities for standard domains
        self.auth_contract = make_test_authority(
            "act_contract_s73", "Commercial Contract Act", "73", "CIVIL_CONTRACT",
            "73. Compensation for breach of contract or agreement.",
        )
        self.auth_cyber = make_test_authority(
            "act_cyber_s43", "Information Technology Act", "43", "CYBER",
            "43. Penalty for unauthorized digital access and data destruction.",
        )
        self.auth_consumer = make_test_authority(
            "act_consumer_s35", "Consumer Protection Act", "35", "CONSUMER",
            "35. Consumer complaint against deficiency of goods or services.",
        )
        publish_reviewed(self.corpus, self.auth_contract)
        publish_reviewed(self.corpus, self.auth_cyber)
        publish_reviewed(self.corpus, self.auth_consumer)

    def test_one_domain_case(self):
        """Case with issues confined to a single domain (CONSUMER)."""
        issue1 = IssueCandidate(
            key="defective_phone",
            statement="Is the seller liable to refund the cost of the defective phone?",
            category="DEFECT",
            domain="CONSUMER",
            fact_ids=["F001"],
            query="seller refund defective goods",
            jurisdiction="IN",
            date_fact_ids=["F001"],
            jurisdiction_fact_ids=["F001"],
            limitation_relevant=False,
            precedent_useful=False,
        )
        self.assertEqual(issue1.domain, "CONSUMER")

        # Execute candidate search for issue
        candidates = self.corpus.search(issue1.domain, "IN", issue1.query)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["source_id"], "act_consumer_s35")

    def test_two_domain_case(self):
        """Case with concurrent issues across two distinct domains (CONTRACT and CYBER)."""
        issue_contract = IssueCandidate(
            key="sla_breach",
            statement="Did the cloud vendor breach the guaranteed 99.9% uptime SLA?",
            category="BREACH",
            domain="CIVIL_CONTRACT",
            fact_ids=["F001"],
            query="breach contract agreement uptime",
            jurisdiction="IN",
            date_fact_ids=["F001"],
            jurisdiction_fact_ids=["F001"],
            limitation_relevant=False,
            precedent_useful=False,
        )
        issue_cyber = IssueCandidate(
            key="data_leak",
            statement="Is the vendor liable for unauthorized exfiltration of customer database?",
            category="DATA_BREACH",
            domain="CYBER",
            fact_ids=["F002"],
            query="unauthorized access data destruction",
            jurisdiction="IN",
            date_fact_ids=["F002"],
            jurisdiction_fact_ids=["F002"],
            limitation_relevant=False,
            precedent_useful=False,
        )

        # Both issues retain their own independent domain metadata
        self.assertEqual(issue_contract.domain, "CIVIL_CONTRACT")
        self.assertEqual(issue_cyber.domain, "CYBER")

        # Search runs per issue domain
        contract_cands = self.corpus.search(issue_contract.domain, "IN", issue_contract.query)
        cyber_cands = self.corpus.search(issue_cyber.domain, "IN", issue_cyber.query)

        self.assertEqual(len(contract_cands), 1)
        self.assertEqual(contract_cands[0]["source_id"], "act_contract_s73")
        self.assertEqual(len(cyber_cands), 1)
        self.assertEqual(cyber_cands[0]["source_id"], "act_cyber_s43")

    def test_three_domain_case(self):
        """Case representing concurrent issues across three domains (CONTRACT, CYBER, CONSUMER)."""
        issues = [
            IssueCandidate(
                key="supply_contract",
                statement="Breach of software procurement contract terms",
                category="CONTRACT",
                domain="CIVIL_CONTRACT",
                fact_ids=["F001"],
                query="breach contract",
                jurisdiction="IN",
                date_fact_ids=["F001"],
                jurisdiction_fact_ids=["F001"],
                limitation_relevant=False,
                precedent_useful=False,
            ),
            IssueCandidate(
                key="system_hack",
                statement="Unauthorized intrusion into host system",
                category="CYBER",
                domain="CYBER",
                fact_ids=["F002"],
                query="unauthorized digital access",
                jurisdiction="IN",
                date_fact_ids=["F002"],
                jurisdiction_fact_ids=["F002"],
                limitation_relevant=False,
                precedent_useful=False,
            ),
            IssueCandidate(
                key="end_user_refund",
                statement="Deficiency of service to individual consumer",
                category="CONSUMER",
                domain="CONSUMER",
                fact_ids=["F003"],
                query="consumer complaint deficiency services",
                jurisdiction="IN",
                date_fact_ids=["F003"],
                jurisdiction_fact_ids=["F003"],
                limitation_relevant=False,
                precedent_useful=False,
            ),
        ]

        domains = [i.domain for i in issues]
        self.assertEqual(domains, ["CIVIL_CONTRACT", "CYBER", "CONSUMER"])

        # Verify each issue retrieves only its domain authority
        for issue in issues:
            cands = self.corpus.search(issue.domain, "IN", issue.query)
            self.assertEqual(len(cands), 1)
            self.assertEqual(cands[0]["domain"], issue.domain)

    def test_unknown_new_domain_case(self):
        """Case with an unregistered emerging domain (e.g. AVIATION_PASSENGER_COMPENSATION).
        Verifies:
        - Domain label is preserved on the issue,
        - Schema validation accepts it without error,
        - System marks no matching source coverage and cleanly abstains,
        - Does NOT crash and does NOT fall back to Consumer.
        """
        emerging_domain = "AVIATION_PASSENGER_COMPENSATION"
        self.assertFalse(is_known_domain_pack(emerging_domain))

        issue = IssueCandidate(
            key="flight_cancellation_compensation",
            statement="Is the airline liable for statutory passenger compensation for flight cancellation?",
            category="PASSENGER_RIGHTS",
            domain=emerging_domain,
            fact_ids=["F010"],
            query="airline passenger compensation cancellation",
            jurisdiction="IN",
            date_fact_ids=["F010"],
            jurisdiction_fact_ids=["F010"],
            limitation_relevant=False,
            precedent_useful=False,
        )

        # Domain label is strictly preserved on the issue model
        self.assertEqual(issue.domain, "AVIATION_PASSENGER_COMPENSATION")

        # Execute retrieval via LegalChecks: No authority exists in corpus for this emerging domain
        res = self.checks.retrieval("L_AVIA")({
            "inputs": {"legal_issues.L_AVIA": issue.model_dump()}
        })
        output = res.outputs["legal_sources.candidates.L_AVIA"]
        self.assertEqual(output["domain"], "AVIATION_PASSENGER_COMPENSATION")
        self.assertEqual(output["status"], "LEGAL_SOURCE_PENDING")
        self.assertEqual(output["reason"], "NO_MATCHING_SOURCE_COVERAGE")
        self.assertEqual(len(output["candidates"]), 0)

        # Authority application gate must cleanly abstain
        app_res = self.checks.application("L_AVIA")({
            "inputs": {
                "legal_issues.L_AVIA": issue.model_dump(),
                "citation_verification.L_AVIA": {"issue_id": "L_AVIA", "decisions": []},
            }
        })
        app_output = app_res.outputs["legal_applications.L_AVIA"]
        self.assertEqual(app_output["status"], "PENDING_SOURCE")
        self.assertIn("VERIFIED_APPLICABLE_AUTHORITY_REQUIRED", app_output["unknowns"])
        self.assertEqual(len(app_output["applications"]), 0)

    def test_overlapping_issue_across_two_domain_packs(self):
        """An overlapping dispute involving both contract obligations and consumer defect.
        Verifies that domain safety gates reject cross-domain authority contamination.
        """
        facts = {
            "F001": {"certainty": "STATED", "date": {"normalized": "2026-09-10", "precision": "EXACT_DATE"}}
        }
        issue_consumer = {
            "domain": "CONSUMER", "jurisdiction": "IN", "query": "defective equipment warranty",
            "fact_ids": ["F001"], "contradicting_fact_ids": [], "date_fact_ids": ["F001"], "jurisdiction_fact_ids": ["F001"],
        }
        issue_contract = {
            "domain": "CIVIL_CONTRACT", "jurisdiction": "IN", "query": "commercial supplier warranty",
            "fact_ids": ["F001"], "contradicting_fact_ids": [], "date_fact_ids": ["F001"], "jurisdiction_fact_ids": ["F001"],
        }

        # Attempt to verify Consumer authority against the Contract issue
        temporal_contract = self.checks.temporal("L_OVERLAP_CONT")({
            "inputs": {
                "legal_issues.L_OVERLAP_CONT": issue_contract,
                "facts.F001": facts["F001"],
                "legal_sources.candidates.L_OVERLAP_CONT": {"candidates": [compact(self.auth_consumer)]},
            }
        })
        citation_contract = self.checks.citation("L_OVERLAP_CONT")({
            "inputs": {
                "legal_issues.L_OVERLAP_CONT": issue_contract,
                "legal_sources.candidates.L_OVERLAP_CONT": {"candidates": [compact(self.auth_consumer)]},
                "temporal_findings.L_OVERLAP_CONT": temporal_contract.outputs["temporal_findings.L_OVERLAP_CONT"],
            }
        })
        decisions = citation_contract.outputs["citation_verification.L_OVERLAP_CONT"]["decisions"]
        self.assertEqual(decisions[0]["status"], "NOT_APPLICABLE")
        self.assertEqual(decisions[0]["reason"], "WRONG_DOMAIN_OR_JURISDICTION")


if __name__ == "__main__":
    unittest.main()
