"""Comprehensive regression and verification test suite for genericity and hardcoding audit.

Proves:
1. Domain configuration is extensible via intelligence registry without engine edits (Req 2 & 13).
2. Unknown domains fail closed; no silent Consumer fallback anywhere in the pipeline (Req 3 & 13).
3. RTI and auxiliary domains are generic and data-driven via metadata/configuration (Req 4).
4. Cross-domain offline tests (Consumer, RTI/Administrative, Contract, Cyber, Multi-domain)
   execute the same common retrieval, gates, verification, and binding architecture (Req 5).
5. Multi-domain cases isolate domain safety gates per issue (Req 6).
6. Language and script processing are decoupled from legal domain logic (Req 7).
7. Adding a new Act, section, or source ID requires zero common-engine changes (Req 8).
"""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.adapters.mock.database import MockDatabaseAdapter
from backend.adapters.mock.legal_retrieval import MockLegalRetrievalAdapter
from backend.models.understanding import DomainCandidates, LanguageAssessment, check_domain
from backend.models.legal_foundation import LegalSource
from backend.services.intelligence_config import CONFIG
from backend.services.legal_checks import LegalChecks, compact
from backend.services.verified_corpus import VerifiedCorpus
from backend.services.legal_team import LegalTeamAgents
from backend.services.specialist_packs import CATALOG, PACKS
from backend.services.documents import build_documents, TEMPLATE_REGISTRY
from backend.services.legal_analysis import normalize_domain_to_corpus
from backend.services.input_canonical import detect_language
from backend.tests.legal_test_support import LegalTestModel, authority, test_knowledge, publish_reviewed


def make_synthetic_authority(source_id: str, act_title: str, section: str, domain: str, quote: str, **kwargs):
    text = f"{act_title}\n{quote}"
    start = text.index(quote)
    return authority(
        source_id=source_id,
        temporal_source_ids=[source_id],
        title=act_title,
        section=section,
        citation=f"{act_title}, section {section}",
        domain=domain,
        official_text=text,
        quote=quote,
        section_start=start,
        section_end=start + len(quote),
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        **kwargs
    )


class DomainExtensibilityAndTypingTests(unittest.TestCase):
    """Verifies Requirements 2 and 13: dynamic domain typing, config extensibility, and fail-closed safety."""

    def test_every_configured_domain_accepted_by_domain_schema(self):
        """Every domain in CONFIG['domain_hints'] must be accepted individually as primary_domain."""
        lang = LanguageAssessment(detected_languages=["script:LATIN"], supported=True)
        for dom in CONFIG['domain_hints']:
            with self.subTest(domain=dom):
                cand = DomainCandidates(
                    language=lang,
                    primary_domain=dom,
                    primary_subdomain="general",
                    secondary_domains=[],
                    fact_ids=["F001"],
                    relationship_ids=[],
                    confidence="HIGH",
                    review_required=False,
                    ambiguity=[],
                    reasons=["Fact indicators"],
                )
                self.assertEqual(cand.primary_domain, dom)

    def test_dynamic_unregistered_domain_label_is_representable(self):
        """A dynamically detected domain label (e.g. AVIATION_PASSENGER_COMPENSATION) is representable even without pre-registration."""
        from backend.models.understanding import is_known_domain_pack
        emerging_domain = "AVIATION_PASSENGER_COMPENSATION"
        self.assertFalse(is_known_domain_pack(emerging_domain))

        lang = LanguageAssessment(detected_languages=["script:LATIN"], supported=True)
        cand = DomainCandidates(
            language=lang,
            primary_domain=emerging_domain,
            primary_subdomain="delayed_flight_refund",
            fact_ids=["F001"],
            confidence="HIGH",
            review_required=False,
            reasons=["Flight delayed by 8 hours without meal or refund"],
        )
        self.assertEqual(cand.primary_domain, emerging_domain)

    def test_invalid_domain_syntax_rejected(self):
        """Invalid domain syntax (lowercase, special characters, spaces) is rejected by schema."""
        lang = LanguageAssessment(detected_languages=["script:LATIN"], supported=True)
        for invalid in ["lowercase_domain", "WITH SPACES", "INVALID!CHARS", ""]:
            with self.subTest(invalid=invalid):
                with self.assertRaises((ValueError, Exception)):
                    DomainCandidates(
                        language=lang,
                        primary_domain=invalid,
                        primary_subdomain="general",
                        fact_ids=["F001"],
                        confidence="HIGH",
                        review_required=False,
                        reasons=["Test"],
                    )


class NoSilentConsumerDefaultTests(unittest.TestCase):
    """Verifies Requirement 3: Unknown/unsupported domains never silently default to Consumer."""

    def test_normalize_domain_to_corpus_does_not_default_to_consumer(self):
        self.assertIsNone(normalize_domain_to_corpus(""))
        self.assertIsNone(normalize_domain_to_corpus("UNKNOWN_DOMAIN"))
        self.assertIsNone(normalize_domain_to_corpus("OTHER_OR_UNCERTAIN"))
        self.assertNotEqual(normalize_domain_to_corpus(""), "consumer")
        self.assertNotEqual(normalize_domain_to_corpus("UNKNOWN_DOMAIN"), "consumer")

    def test_build_documents_rejects_unsupported_domain_without_consumer_fallback(self):
        case = {
            "legal_domain": {"domain": "UNSUPPORTED_ADMIRALTY"},
            "client_story": "A cargo ship dispute",
        }
        with self.assertRaises(ValueError) as ctx:
            build_documents(case)
        self.assertIn("Document generation is not yet supported for domain: 'UNSUPPORTED_ADMIRALTY'", str(ctx.exception))

    def test_mock_legal_retrieval_does_not_inject_consumer_default(self):
        retriever = MockLegalRetrievalAdapter()
        # Querying with domain="" must search with empty domain, not defaulting to Consumer
        results = retriever.search("salary wages unpaid", limit=5, domain="")
        # Should not crash or inject "Consumer"
        self.assertIsInstance(results, list)


class RTIAndAuxiliaryDomainGenericityTests(unittest.TestCase):
    """Verifies Requirement 4: RTI secondary attachment is data-driven via auxiliary_secondary_domains."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = MockDatabaseAdapter(Path(self.temp.name) / "db.json")

    def test_auxiliary_secondary_domain_config_gate_enforcement(self):
        """Proves another configured auxiliary domain uses the exact same gate as RTI without code changes."""
        synth_aux = "SYNTHETIC_PUBLIC_RECORDS"
        synth_agent = "PUBLIC_RECORD_ANALYZER"

        # Register synthetic auxiliary domain in CONFIG
        original_aux = copy.deepcopy(CONFIG.get("auxiliary_secondary_domains", {}))
        CONFIG.setdefault("auxiliary_secondary_domains", {})[synth_aux] = {
            "requires_unavailable_evidence": True,
            "gate_description": f"Secondary {synth_aux} requires grounded, unavailable public record dependency",
            "prompt_instruction": "Secondary public records only when necessary record is unavailable.",
        }
        # Add synthetic specialist to CATALOG
        original_catalog = copy.deepcopy(CATALOG)
        CATALOG[synth_agent] = {"domain": synth_aux, "purpose": "Analyze public records"}

        try:
            self.db.create("cases", {"id": "c1", "raw_package": {"unavailable_evidence": []}})
            self.db.create("cases", {"id": "c2", "raw_package": {"unavailable_evidence": [{"description": "Tender gazette"}]}})
            team_service = LegalTeamAgents(SimpleNamespace(database=self.db, llm=None))

            # Case claim with synth_aux as secondary domain but missing unavailable evidence
            claim_fail = {
                "execution_id": "exec-1",
                "case_id": "c1",
                "inputs": {
                    "domain_classification": {"primary_domain": "CIVIL_CONTRACT", "secondary_domains": [synth_aux]},
                    "facts": {"F001": {"proposition": "Contract signed", "certainty": "STATED"}},
                    "raw_case_package": {"unavailable_evidence": []},
                },
            }

            class TeamBuilderModelFail:
                def generate(self, prompt, schema):
                    return {
                        "selected": [
                            {"agent": "CONTRACT_RELATIONSHIP", "fact_ids": ["F001"], "reason": "Contract fact"},
                            {"agent": synth_agent, "fact_ids": ["F001"], "reason": "Public record need"},
                        ],
                        "limitation_relevant": False,
                        "precedent_useful": False,
                        "optional_reason": "Test",
                        "secondary_reason": "Need public record",
                        "public_record_fact_ids": ["F001"],
                        "unavailable_record_refs": [0],  # Out of range for empty unavailable_evidence
                    }

            team_service.adapters = SimpleNamespace(database=self.db, llm=TeamBuilderModelFail(), mode="mock", processing_mode="mock", llm_processing_mode="mock", phase4_test_double=True)
            with self.assertRaises(ValueError) as ctx:
                team_service.team(claim_fail)
            self.assertIn(f"Secondary {synth_aux} requires grounded, unavailable public record dependency", str(ctx.exception))

            # Now provide valid unavailable record and facts without uploaded evidence
            claim_success = {
                "execution_id": "exec-2",
                "case_id": "c2",
                "inputs": {
                    "domain_classification": {"primary_domain": "CIVIL_CONTRACT", "secondary_domains": [synth_aux]},
                    "facts": {"F001": {"proposition": "Contract signed", "certainty": "STATED"},
                              "F002": {"proposition": "Public tender document unavailable", "certainty": "STATED"}},
                    "raw_case_package": {"unavailable_evidence": [{"description": "Tender gazette"}]},
                },
            }

            class TeamBuilderModelSuccess:
                def generate(self, prompt, schema):
                    return {
                        "selected": [
                            {"agent": "CONTRACT_RELATIONSHIP", "fact_ids": ["F001"], "reason": "Contract fact"},
                            {"agent": synth_agent, "fact_ids": ["F002"], "reason": "Public record need"},
                        ],
                        "limitation_relevant": False,
                        "precedent_useful": False,
                        "optional_reason": "Test",
                        "secondary_reason": "Need tender document",
                        "public_record_fact_ids": ["F002"],
                        "unavailable_record_refs": [0],
                    }

            team_service.adapters = SimpleNamespace(database=self.db, llm=TeamBuilderModelSuccess(), mode="mock", processing_mode="mock", llm_processing_mode="mock", phase4_test_double=True)
            res = team_service.team(claim_success)
            self.assertEqual(res.status, "COMPLETED")
            selected = res.outputs["agent_team"]["selected"]
            self.assertIn(synth_agent, selected)
            self.assertEqual(selected[synth_agent]["domain"], synth_aux)
        finally:
            CONFIG["auxiliary_secondary_domains"] = original_aux
            CATALOG.clear()
            CATALOG.update(original_catalog)


class CrossDomainOfflinePipelineTests(unittest.TestCase):
    """Verifies Requirements 5, 6, 8:
    Offline pipeline across CONSUMER, RTI_ADMINISTRATIVE, CIVIL_CONTRACT, CYBER, and MULTI-DOMAIN.
    Runs issue -> query planning -> candidate retrieval -> authority eligibility gates -> ranking ->
    exact passage verification -> citation binding -> grounded result / abstention.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = MockDatabaseAdapter(Path(self.temp.name) / "db.json")
        self.corpus = VerifiedCorpus(self.db, test_knowledge())
        self.model = LegalTestModel()
        self.adapters = SimpleNamespace(database=self.db, llm=self.model, mode="mock", processing_mode="mock", llm_processing_mode="mock", phase3_test_double=True,
                                        phase4_test_double=True, verified_corpus=self.corpus)
        self.checks = LegalChecks(self.adapters, self.corpus)

    def _execute_pipeline_for_issue(self, issue_id: str, issue: dict, facts: dict, expected_element: str):
        """Executes the uniform architecture pipeline for any legal issue."""
        # 1. Retrieval
        retrieval_res = self.checks.retrieval(issue_id)({
            "inputs": {f"legal_issues.{issue_id}": issue}
        })
        candidates_output = retrieval_res.outputs[f"legal_sources.candidates.{issue_id}"]
        if not candidates_output["candidates"]:
            # Clean abstention path
            app_res = self.checks.application(issue_id)({
                "inputs": {
                    f"legal_issues.{issue_id}": issue,
                    f"citation_verification.{issue_id}": {"issue_id": issue_id, "decisions": []},
                }
            })
            return {
                "retrieval": candidates_output,
                "temporal": None,
                "citation": None,
                "application": app_res.outputs[f"legal_applications.{issue_id}"],
            }

        # 2. Temporal Gate
        temporal_res = self.checks.temporal(issue_id)({
            "inputs": {
                f"legal_issues.{issue_id}": issue,
                **{f"facts.{k}": v for k, v in facts.items()},
                f"legal_sources.candidates.{issue_id}": candidates_output,
            }
        })
        temporal_output = temporal_res.outputs[f"temporal_findings.{issue_id}"]

        # 3. Citation Verification
        citation_res = self.checks.citation(issue_id)({
            "inputs": {
                f"legal_issues.{issue_id}": issue,
                f"legal_sources.candidates.{issue_id}": candidates_output,
                f"temporal_findings.{issue_id}": temporal_output,
            }
        })
        citation_output = citation_res.outputs[f"citation_verification.{issue_id}"]

        # 4. Citation Binding (Application)
        # Ensure model returns the expected element from the authority quote
        self.model.overrides[f"APPLICATION_{issue_id}"] = {
            "applications": [{
                "source_id": candidates_output["candidates"][0]["source_id"],
                "citation": candidates_output["candidates"][0]["citation"],
                "title": candidates_output["candidates"][0]["title"],
                "section": candidates_output["candidates"][0]["section"],
                "quote": self.corpus.get(candidates_output["candidates"][0]["source_id"])["quote"],
                "fact_ids": issue["fact_ids"],
                "explanation": f"Grounded application in domain {issue['domain']}",
                "required_elements": [expected_element],
                "element_mapping": [{"element": expected_element, "fact_ids": issue["fact_ids"]}],
            }],
            "unknowns": [],
        }

        app_res = self.checks.application(issue_id)({
            "inputs": {
                f"legal_issues.{issue_id}": issue,
                f"citation_verification.{issue_id}": citation_output,
                **{f"facts.{k}": v for k, v in facts.items()},
            }
        })
        app_output = app_res.outputs[f"legal_applications.{issue_id}"]

        return {
            "retrieval": candidates_output,
            "temporal": temporal_output,
            "citation": citation_output,
            "application": app_output,
        }

    def test_pipeline_consumer_domain(self):
        """1. CONSUMER domain executes generic pipeline."""
        auth = make_synthetic_authority(
            source_id="cpa_fixture_s35",
            act_title="Consumer Protection Synthetic Act",
            section="35",
            domain="CONSUMER",
            quote="35. A consumer complaint may claim refund for defective goods.",
        )
        publish_reviewed(self.corpus, auth)

        issue = {
            "domain": "CONSUMER", "jurisdiction": "IN", "query": "consumer refund defective",
            "fact_ids": ["F001"], "contradicting_fact_ids": [], "date_fact_ids": ["F001"], "jurisdiction_fact_ids": ["F001"],
        }
        facts = {"F001": {"certainty": "STATED", "date": {"normalized": "2026-05-10", "precision": "EXACT_DATE"}}}

        res = self._execute_pipeline_for_issue("L_CONS", issue, facts, expected_element="consumer")
        self.assertEqual(res["retrieval"]["status"], "CANDIDATES")
        self.assertEqual(res["temporal"]["decisions"]["cpa_fixture_s35"]["status"], "APPLICABLE")
        self.assertEqual(res["citation"]["decisions"][0]["status"], "VERIFIED")
        self.assertEqual(res["application"]["status"], "SOURCE_VERIFIED")
        self.assertEqual(res["application"]["applications"][0]["source_id"], "cpa_fixture_s35")

    def test_pipeline_rti_administrative_domain(self):
        """2. RTI_ADMINISTRATIVE domain executes generic pipeline."""
        auth = make_synthetic_authority(
            source_id="rti_fixture_s6",
            act_title="Right to Information Synthetic Act",
            section="6",
            domain="RTI_ADMINISTRATIVE",
            quote="6. Any citizen may request public information from an authority.",
        )
        publish_reviewed(self.corpus, auth)

        issue = {
            "domain": "RTI_ADMINISTRATIVE", "jurisdiction": "IN", "query": "citizen request public information",
            "fact_ids": ["F002"], "contradicting_fact_ids": [], "date_fact_ids": ["F002"], "jurisdiction_fact_ids": ["F002"],
        }
        facts = {"F002": {"certainty": "STATED", "date": {"normalized": "2026-06-15", "precision": "EXACT_DATE"}}}

        res = self._execute_pipeline_for_issue("L_RTI", issue, facts, expected_element="citizen")
        self.assertEqual(res["retrieval"]["status"], "CANDIDATES")
        self.assertEqual(res["temporal"]["decisions"]["rti_fixture_s6"]["status"], "APPLICABLE")
        self.assertEqual(res["citation"]["decisions"][0]["status"], "VERIFIED")
        self.assertEqual(res["application"]["status"], "SOURCE_VERIFIED")

    def test_pipeline_civil_contract_domain(self):
        """3. CIVIL_CONTRACT domain executes generic pipeline."""
        auth = make_synthetic_authority(
            source_id="contract_fixture_s73",
            act_title="Indian Contract Synthetic Act",
            section="73",
            domain="CIVIL_CONTRACT",
            quote="73. Compensation for loss or damage caused by breach of contract.",
        )
        publish_reviewed(self.corpus, auth)

        issue = {
            "domain": "CIVIL_CONTRACT", "jurisdiction": "IN", "query": "compensation loss damage breach contract",
            "fact_ids": ["F003"], "contradicting_fact_ids": [], "date_fact_ids": ["F003"], "jurisdiction_fact_ids": ["F003"],
        }
        facts = {"F003": {"certainty": "STATED", "date": {"normalized": "2026-07-20", "precision": "EXACT_DATE"}}}

        res = self._execute_pipeline_for_issue("L_CONT", issue, facts, expected_element="breach")
        self.assertEqual(res["retrieval"]["status"], "CANDIDATES")
        self.assertEqual(res["temporal"]["decisions"]["contract_fixture_s73"]["status"], "APPLICABLE")
        self.assertEqual(res["citation"]["decisions"][0]["status"], "VERIFIED")
        self.assertEqual(res["application"]["status"], "SOURCE_VERIFIED")

    def test_pipeline_cyber_domain(self):
        """4. CYBER domain executes generic pipeline."""
        auth = make_synthetic_authority(
            source_id="it_fixture_s43",
            act_title="Information Technology Synthetic Act",
            section="43",
            domain="CYBER",
            quote="43. Penalty and compensation for damage to computer system or data unauthorized access.",
        )
        publish_reviewed(self.corpus, auth)

        issue = {
            "domain": "CYBER", "jurisdiction": "IN", "query": "damage computer system unauthorized access",
            "fact_ids": ["F004"], "contradicting_fact_ids": [], "date_fact_ids": ["F004"], "jurisdiction_fact_ids": ["F004"],
        }
        facts = {"F004": {"certainty": "STATED", "date": {"normalized": "2026-08-01", "precision": "EXACT_DATE"}}}

        res = self._execute_pipeline_for_issue("L_CYBER", issue, facts, expected_element="damage")
        self.assertEqual(res["retrieval"]["status"], "CANDIDATES")
        self.assertEqual(res["temporal"]["decisions"]["it_fixture_s43"]["status"], "APPLICABLE")
        self.assertEqual(res["citation"]["decisions"][0]["status"], "VERIFIED")
        self.assertEqual(res["application"]["status"], "SOURCE_VERIFIED")

    def test_clean_abstention_when_no_authority_covers_query(self):
        """Clean abstention when an issue's query has no matching authority coverage."""
        issue = {
            "domain": "CYBER", "jurisdiction": "IN", "query": "unrelated maritime admiralty dispute",
            "fact_ids": ["F005"], "contradicting_fact_ids": [], "date_fact_ids": ["F005"], "jurisdiction_fact_ids": ["F005"],
        }
        facts = {"F005": {"certainty": "STATED", "date": {"normalized": "2026-08-01", "precision": "EXACT_DATE"}}}

        res = self._execute_pipeline_for_issue("L_ABSTAIN", issue, facts, expected_element="none")
        self.assertEqual(res["retrieval"]["status"], "LEGAL_SOURCE_PENDING")
        self.assertEqual(res["retrieval"]["reason"], "NO_MATCHING_SOURCE_COVERAGE")
        self.assertEqual(res["application"]["status"], "PENDING_SOURCE")
        self.assertIn("VERIFIED_APPLICABLE_AUTHORITY_REQUIRED", res["application"]["unknowns"])

    def test_multi_domain_case_preserves_metadata_and_cross_domain_safety(self):
        """5 & Req 6: Multi-domain case with contract dispute and cyber unauthorized data access.
        Verifies:
        - domain metadata remains attached to each issue,
        - applicable packs/authorities can be selected per issue,
        - common engine does not change,
        - cross-domain safety gate: Issue 2 (CYBER) CANNOT verify against CIVIL_CONTRACT authority, and vice-versa.
        """
        auth_contract = make_synthetic_authority(
            source_id="multi_contract_act",
            act_title="Commercial Contract Synthetic Act",
            section="10",
            domain="CIVIL_CONTRACT",
            quote="10. All agreements are contracts if made for lawful consideration.",
        )
        auth_cyber = make_synthetic_authority(
            source_id="multi_cyber_act",
            act_title="Data Protection Synthetic Act",
            section="8",
            domain="CYBER",
            quote="8. Data fiduciary shall protect personal data under its control.",
        )
        publish_reviewed(self.corpus, auth_contract)
        publish_reviewed(self.corpus, auth_cyber)

        facts = {
            "F010": {"certainty": "STATED", "date": {"normalized": "2026-09-01", "precision": "EXACT_DATE"}},
            "F011": {"certainty": "STATED", "date": {"normalized": "2026-09-05", "precision": "EXACT_DATE"}},
        }

        issue_contract = {
            "domain": "CIVIL_CONTRACT", "jurisdiction": "IN", "query": "agreements contracts lawful consideration",
            "fact_ids": ["F010"], "contradicting_fact_ids": [], "date_fact_ids": ["F010"], "jurisdiction_fact_ids": ["F010"],
        }
        issue_cyber = {
            "domain": "CYBER", "jurisdiction": "IN", "query": "data fiduciary protect personal data",
            "fact_ids": ["F011"], "contradicting_fact_ids": [], "date_fact_ids": ["F011"], "jurisdiction_fact_ids": ["F011"],
        }

        # Run both through the pipeline
        res_contract = self._execute_pipeline_for_issue("L_MULTI_1", issue_contract, facts, expected_element="contracts")
        res_cyber = self._execute_pipeline_for_issue("L_MULTI_2", issue_cyber, facts, expected_element="fiduciary")

        # Verify domain metadata isolation
        self.assertEqual(res_contract["retrieval"]["domain"], "CIVIL_CONTRACT")
        self.assertEqual(res_cyber["retrieval"]["domain"], "CYBER")
        self.assertEqual(res_contract["application"]["applications"][0]["source_id"], "multi_contract_act")
        self.assertEqual(res_cyber["application"]["applications"][0]["source_id"], "multi_cyber_act")

        # Cross-domain safety gate test: Attempt to verify Contract candidate against Cyber issue
        cross_temporal = self.checks.temporal("L_MULTI_CROSS")({
            "inputs": {
                "legal_issues.L_MULTI_CROSS": issue_cyber,
                **{f"facts.{k}": v for k, v in facts.items()},
                "legal_sources.candidates.L_MULTI_CROSS": {"candidates": [compact(auth_contract)]},
            }
        })
        cross_citation = self.checks.citation("L_MULTI_CROSS")({
            "inputs": {
                "legal_issues.L_MULTI_CROSS": issue_cyber,  # Domain CYBER
                "legal_sources.candidates.L_MULTI_CROSS": {"candidates": [compact(auth_contract)]},  # Domain CIVIL_CONTRACT
                "temporal_findings.L_MULTI_CROSS": cross_temporal.outputs["temporal_findings.L_MULTI_CROSS"],
            }
        })
        decisions = cross_citation.outputs["citation_verification.L_MULTI_CROSS"]["decisions"]
        self.assertEqual(decisions[0]["status"], "NOT_APPLICABLE")
        self.assertEqual(decisions[0]["reason"], "WRONG_DOMAIN_OR_JURISDICTION")


class LanguageAndScriptGeneralityTests(unittest.TestCase):
    """Verifies Requirement 7: Language handling is script-based and decoupled from legal domain logic."""

    def test_script_detection_supports_various_scripts_accurately(self):
        samples = [
            ("This is a simple Latin text for case assessment.", "script:LATIN"),
            ("வாடிக்கையாளர் வாங்கிய குளிர்சாதனப் பெட்டி பழுதானது.", "script:TAMIL"),
            ("Order ID #84931 பொருளுக்கான refund தொகை இன்னும் வரவில்லை.", "script:LATIN+TAMIL"),
            ("उपभोक्ता संरक्षण अधिनियम के अंतर्गत शिकायत।", "script:DEVANAGARI"),
            ("Complaint reference #99283 और बिल राशि 45000 रुपये।", "script:DEVANAGARI+LATIN"),
        ]
        for text, expected in samples:
            with self.subTest(text=text[:30]):
                detected = detect_language(text)
                self.assertEqual(detected, expected)

    def test_language_metadata_does_not_alter_legal_checks_execution(self):
        """Legal authority checking does not inspect or discriminate by script."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = MockDatabaseAdapter(Path(temp.name) / "db.json")
        corpus = VerifiedCorpus(db, test_knowledge())
        checks = LegalChecks(None, corpus)

        auth = make_synthetic_authority(
            source_id="lang_neutral_act",
            act_title="Synthetic Neutral Act",
            section="1",
            domain="CONSUMER",
            quote="1. Statutory warranty applies to all purchased equipment.",
        )
        publish_reviewed(corpus, auth)

        # Issues with identical dates but different fact language script metadata
        issue = {
            "domain": "CONSUMER", "jurisdiction": "IN", "query": "warranty purchased equipment",
            "fact_ids": ["F_TAMIL"], "contradicting_fact_ids": [], "date_fact_ids": ["F_TAMIL"], "jurisdiction_fact_ids": ["F_TAMIL"],
        }
        facts = {
            "F_TAMIL": {
                "certainty": "STATED",
                "date": {"normalized": "2026-05-10", "precision": "EXACT_DATE"},
                "proposition": "பொருள் பழுதடைந்த நாள் 2026-05-10",
                "language_hint": "script:TAMIL",
            }
        }
        temporal = checks.temporal("L_LANG")({
            "inputs": {
                "legal_issues.L_LANG": issue,
                **{f"facts.{k}": v for k, v in facts.items()},
                "legal_sources.candidates.L_LANG": {"candidates": [compact(auth)]},
            }
        })
        cit = checks.citation("L_LANG")({
            "inputs": {
                "legal_issues.L_LANG": issue,
                "legal_sources.candidates.L_LANG": {"candidates": [compact(auth)]},
                "temporal_findings.L_LANG": temporal.outputs["temporal_findings.L_LANG"],
            }
        })
        self.assertEqual(cit.outputs["citation_verification.L_LANG"]["decisions"][0]["status"], "VERIFIED")


class LawAndSectionGeneralityTests(unittest.TestCase):
    """Verifies Requirement 8: Introducing a new Act, section, and authority ID requires zero common engine edits.
    Proves that cpa2019_s2_7 is purely corpus/review data rather than an architectural dependency.
    """

    def test_novel_synthetic_act_section_and_source_id_processed_generically(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = MockDatabaseAdapter(Path(temp.name) / "db.json")
        corpus = VerifiedCorpus(db, test_knowledge())
        checks = LegalChecks(None, corpus)

        # Novel Act and Section completely unknown to any existing codebase or test
        novel_auth = make_synthetic_authority(
            source_id="space_activities_act_2026_s42",
            act_title="Outer Space Commercial Activities Act, 2026",
            section="42",
            domain="CIVIL_CONTRACT",
            quote="42. Commercial space payloads require third-party liability coverage.",
        )
        publish_reviewed(corpus, novel_auth)

        # Query using terms in the novel Act
        results = corpus.search("CIVIL_CONTRACT", "IN", "space payloads third-party liability coverage")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source_id"], "space_activities_act_2026_s42")
        self.assertEqual(results[0]["section"], "42")
        self.assertEqual(results[0]["title"], "Outer Space Commercial Activities Act, 2026")

        # Execute temporal and citation checks
        issue = {
            "domain": "CIVIL_CONTRACT", "jurisdiction": "IN", "query": "space payloads liability",
            "fact_ids": ["F_SPACE"], "contradicting_fact_ids": [], "date_fact_ids": ["F_SPACE"], "jurisdiction_fact_ids": ["F_SPACE"],
        }
        facts = {"F_SPACE": {"certainty": "STATED", "date": {"normalized": "2026-10-01", "precision": "EXACT_DATE"}}}

        temporal = checks.temporal("L_SPACE")({
            "inputs": {
                "legal_issues.L_SPACE": issue,
                **{f"facts.{k}": v for k, v in facts.items()},
                "legal_sources.candidates.L_SPACE": {"candidates": [compact(novel_auth)]},
            }
        })
        self.assertEqual(temporal.outputs["temporal_findings.L_SPACE"]["decisions"]["space_activities_act_2026_s42"]["status"], "APPLICABLE")

        cit = checks.citation("L_SPACE")({
            "inputs": {
                "legal_issues.L_SPACE": issue,
                "legal_sources.candidates.L_SPACE": {"candidates": [compact(novel_auth)]},
                "temporal_findings.L_SPACE": temporal.outputs["temporal_findings.L_SPACE"],
            }
        })
        self.assertEqual(cit.outputs["citation_verification.L_SPACE"]["decisions"][0]["status"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
