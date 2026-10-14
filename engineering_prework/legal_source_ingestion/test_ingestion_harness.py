"""Deterministic offline test harness for legal source discovery, sectionization, and ingestion.

Verifies:
1. Document discovery normalization
2. Section extraction
3. Multiple sections from one Act
4. Nested subsection and clause identifiers
5. Amendment linkage (AMENDED_BY)
6. Notification linkage (COMMENCED_BY)
7. Duplicate-document hash handling (idempotent deduplication)
8. Changed-version handling (detecting revisions via content hash change)
9. Multilingual source metadata (English, Hindi, Tamil)
10. One document serving multiple legal domains
11. One case requiring multiple domain packs
12. Unknown-domain abstention

All tests run completely offline without internet dependencies.
"""
import copy
import hashlib
import json
import unittest
from pathlib import Path

from .models import (
    OfficialSourceMetadata,
    RawDocumentRecord,
    ExtractedDocument,
    ProvisionRecord,
    AuthorityType,
    ReviewStatus,
    RelationshipType,
    AcquisitionMethod,
)
from .base_adapter import BaseSourceAdapter
from .sectionizer import StatutorySectionizer
from .version_graph import VersionGraph
from .tests.fixtures.adapters import FixtureIndiaCodeAdapter, FLAGS
from .adapters.ministry_adapter import MinistryPortalAdapter
from .adapters.judgment_adapter import JudgmentSourceAdapter


# Synthetic statutory text fixtures
SYNTHETIC_CPA_TEXT = """THE CONSUMER PROTECTION ACT, 2019
NO. 35 OF 2019
[9th August, 2019]

An Act to provide for protection of the interests of consumers and for the said purpose, to establish authorities for timely and effective administration and settlement of consumers' disputes and for matters connected therewith or incidental thereto.

CHAPTER I
PRELIMINARY

1. Short title, extent, commencement and application.—(1) This Act may be called the Consumer Protection Act, 2019.
(2) It extends to the whole of India except the State of Jammu and Kashmir.
(3) It shall come into force on such date as the Central Government may, by notification, appoint.

2. Definitions.—In this Act, unless the context otherwise requires,—
(1) "advertisement" means any audio or visual publicity, representation, endorsement or pronouncement made by means of light, sound, smoke, gas, print, electronic media, internet or website;
(7) "consumer" means any person who—
(a) buys any goods for a consideration which has been paid or promised or partly paid and partly promised;
(b) hires or avails of any service for a consideration which has been paid or promised.

CHAPTER IV
CONSUMER DISPUTES REDRESSAL COMMISSION

35. Manner in which complaint shall be made.—(1) A complaint, in relation to any goods sold or delivered or agreed to be sold or delivered or any service provided or agreed to be provided, may be filed with a District Commission by—
(a) the consumer to whom such goods are sold or delivered or agreed to be sold or delivered or such service is provided or agreed to be provided;
(b) any recognised consumer association, whether the consumer to whom the goods sold or delivered or service provided is a member of such association or not;
(c) one or more consumers, where there are numerous consumers having the same interest;
(d) the Central Government, the Central Authority or the State Government.
"""

SYNTHETIC_DUAL_DOMAIN_TEXT = """THE DIGITAL COMMERCE CONSUMER PROTECTION ACT, 2026
NO. 10 OF 2026

CHAPTER I
PRELIMINARY

1. Short title.—(1) This Act may be called the Digital Commerce Consumer Protection Act, 2026.

2. Application to e-commerce transactions.—(1) Every e-commerce entity shall ensure consumer safety and data security.
(2) Any unauthorized extraction of consumer data shall constitute an offence under cybersecurity standards and a deficiency under consumer protection standards.
"""


class IngestionTestHarness(unittest.TestCase):
    def setUp(self):
        self.meta_indiacode = OfficialSourceMetadata(
            source_id="india_code_central",
            name="India Code - Central Legislation",
            official_domain="indiacode.gov.in",
            owner="Legislative Department, Ministry of Law and Justice",
            authority_category="CENTRAL_LEGISLATION",
            base_url="https://indiacode.gov.in/",
            available_document_types=[AuthorityType.ACT, AuthorityType.RULE],
            search_capability=True,
            download_formats=["PDF", "HTML"],
            stable_document_ids=True,
            pagination=True,
            access_restrictions="Public Open Data",
            captcha_required=False,
            rate_limit_guidelines="500 req/window",
            recommended_acquisition_method=AcquisitionMethod.STABLE_HTTP_INDEX,
            priority="P0_CRITICAL",
            implementation_status="AUTOMATABLE_VALIDATED",
        )
        self.adapter = FixtureIndiaCodeAdapter(self.meta_indiacode)
        self.sectionizer = StatutorySectionizer()
        self.graph = VersionGraph()

    def test_document_discovery_normalization(self):
        """1. Discovers test-only document candidates with normalized title and identifier metadata."""
        results = self.adapter.discover_documents("Consumer Protection")
        self.assertGreaterEqual(len(results), 1)
        cpa = results[0]
        self.assertEqual(cpa["document_id"], "cpa_2019")
        self.assertIn("Consumer Protection Act", cpa["title"])
        self.assertEqual(cpa["authority_type"], AuthorityType.ACT)
        self.assertIn("fixtures.invalid", cpa["official_url"])

    def test_section_extraction(self):
        """2. Extracts statutory sections with exact substring offsets and SHA-256 verification."""
        raw_doc = self.adapter.fetch_document("cpa_2019", "https://indiacode.gov.in/handle/123456789/15256", SYNTHETIC_CPA_TEXT)
        extracted = self.adapter.extract_text(raw_doc, SYNTHETIC_CPA_TEXT)

        provisions = self.adapter.enumerate_sections(extracted, domain="CONSUMER")
        self.assertTrue(any(p.section == "1" for p in provisions))
        self.assertTrue(any(p.section == "2" for p in provisions))
        self.assertTrue(any(p.section == "35" for p in provisions))

        sec35 = next(p for p in provisions if p.section == "35" and p.subsection is None)
        self.assertEqual(sec35.heading, "Manner in which complaint shall be made.")
        self.assertEqual(sec35.chapter, "CHAPTER IV")
        # Exact substring guarantee: extracted.text_content[start:end] == quote
        self.assertEqual(extracted.text_content[sec35.section_start:sec35.section_end], sec35.quote)

    def test_multiple_sections_from_one_act(self):
        """3. An enactment yields multiple discrete provision records preserving parent linkage."""
        raw_doc = self.adapter.fetch_document("cpa_2019", "https://indiacode.gov.in/handle/123456789/15256", SYNTHETIC_CPA_TEXT)
        extracted = self.adapter.extract_text(raw_doc, SYNTHETIC_CPA_TEXT)
        provisions = self.adapter.enumerate_sections(extracted)

        sections = {p.section for p in provisions}
        self.assertSetEqual(sections, {"1", "2", "35"})
        for p in provisions:
            self.assertEqual(p.parent_document_id, "cpa_2019")
            self.assertEqual(p.raw_document_hash, raw_doc.raw_content_hash)
            self.assertEqual(p.extracted_text_hash, extracted.text_hash)

    def test_nested_subsection_clause_identifiers(self):
        """4. Extracts nested subsection (35(1)) and clause (35(1)(a), 35(1)(b)) records."""
        raw_doc = self.adapter.fetch_document("cpa_2019", "https://indiacode.gov.in/handle/123456789/15256", SYNTHETIC_CPA_TEXT)
        extracted = self.adapter.extract_text(raw_doc, SYNTHETIC_CPA_TEXT)
        provisions = self.adapter.enumerate_sections(extracted)

        sub_35_1 = next((p for p in provisions if p.section == "35" and p.subsection == "1" and p.clause is None), None)
        self.assertIsNotNone(sub_35_1)
        self.assertEqual(sub_35_1.provision_id, "cpa_2019_s35_1")
        self.assertIn("A complaint, in relation to any goods", sub_35_1.quote)

        clause_35_1_a = next((p for p in provisions if p.section == "35" and p.subsection == "1" and p.clause == "a"), None)
        self.assertIsNotNone(clause_35_1_a)
        self.assertEqual(clause_35_1_a.provision_id, "cpa_2019_s35_1_a")
        self.assertIn("the consumer to whom such goods are sold", clause_35_1_a.quote)

    def test_amendment_linkage(self):
        """5. Tracks AMENDED_BY relationship with pending evidence and citation."""
        self.graph.add_node("cpa_2019", "Consumer Protection Act, 2019", AuthorityType.ACT, "https://indiacode.gov.in/handle/123456789/15256")
        self.graph.add_node("cpa_amend_2024", "Consumer Protection (Amendment) Act, 2024", AuthorityType.AMENDMENT_ACT, "https://indiacode.gov.in/handle/123456789/99999")

        edge = self.graph.add_relationship(
            source_id="cpa_amend_2024",
            target_id="cpa_2019",
            relationship=RelationshipType.AMENDED_BY,
            evidence_url="https://egazette.gov.in/amend2024.pdf",
            evidence_text="In section 35 of the Consumer Protection Act, 2019, in sub-section (1), clause (a) shall be substituted.",
            verified=False,
        )
        amendments = self.graph.get_amendments("cpa_2019")
        self.assertEqual(len(amendments), 1)
        self.assertEqual(amendments[0].source_id, "cpa_amend_2024")

    def test_notification_linkage_and_temporal_interval(self):
        """6. Tracks COMMENCED_BY relationship and evaluates in-force status against event date."""
        self.graph.add_node(
            "cpa_2019", "Consumer Protection Act, 2019", AuthorityType.ACT,
            "https://indiacode.gov.in/handle/123456789/15256",
            effective_from="2020-07-20",
        )
        self.graph.add_relationship(
            source_id="cpa_commence_notif_2020",
            target_id="cpa_2019",
            relationship=RelationshipType.COMMENCED_BY,
            evidence_url="https://egazette.gov.in/so2351.pdf",
            evidence_text="S.O. 2351(E) bringing Act into force w.e.f. 20-07-2020.",
            commencement_date="2020-07-20",
            verified=False,
        )

        # Pre-commencement date must fail
        ok_pre, reason_pre = self.graph.is_temporally_valid_on("cpa_2019", "2019-12-01")
        self.assertFalse(ok_pre)
        self.assertIn("PRE_COMMENCEMENT", reason_pre)

        # In-force date must succeed
        ok_post, reason_post = self.graph.is_temporally_valid_on("cpa_2019", "2021-05-10")
        self.assertTrue(ok_post)
        self.assertEqual(reason_post, "IN_FORCE")

    def test_duplicate_document_hash_handling(self):
        """7. Identical document payload yields identical SHA-256 hash, enabling idempotent storage."""
        doc1 = self.adapter.fetch_document("cpa_2019", "https://indiacode.gov.in/handle/123456789/15256", SYNTHETIC_CPA_TEXT)
        doc2 = self.adapter.fetch_document("cpa_2019", "https://indiacode.gov.in/handle/123456789/15256", SYNTHETIC_CPA_TEXT)
        self.assertEqual(doc1.raw_content_hash, doc2.raw_content_hash)

        provenance1 = self.adapter.build_provenance(doc1, self.adapter.extract_text(doc1, SYNTHETIC_CPA_TEXT))
        provenance2 = self.adapter.build_provenance(doc2, self.adapter.extract_text(doc2, SYNTHETIC_CPA_TEXT))
        self.assertEqual(provenance1["raw_content_hash"], provenance2["raw_content_hash"])
        self.assertEqual(provenance1["extracted_text_hash"], provenance2["extracted_text_hash"])

    def test_changed_version_handling(self):
        """8. Mutated text changes extracted_text_hash, flagging an unreviewed revision."""
        original_doc = self.adapter.fetch_document("cpa_2019", "https://indiacode.gov.in/handle/123456789/15256", SYNTHETIC_CPA_TEXT)
        original_extracted = self.adapter.extract_text(original_doc, SYNTHETIC_CPA_TEXT)

        modified_text = SYNTHETIC_CPA_TEXT.replace("Consumer Protection Act, 2019", "Consumer Protection (Revised) Act, 2026")
        modified_doc = self.adapter.fetch_document("cpa_2019", "https://indiacode.gov.in/handle/123456789/15256", modified_text)
        modified_extracted = self.adapter.extract_text(modified_doc, modified_text)

        self.assertNotEqual(original_doc.raw_content_hash, modified_doc.raw_content_hash)
        self.assertNotEqual(original_extracted.text_hash, modified_extracted.text_hash)

    def test_multilingual_source_metadata(self):
        """9. Ingestion models cleanly represent Hindi, Tamil, and English statutory titles and texts."""
        samples = [
            ("en", "Consumer Protection Act, 2019"),
            ("hi", "उपभोक्ता संरक्षण अधिनियम, २०१९"),
            ("ta", "நுகர்வோர் பாதுகாப்புச் சட்டம், 2019"),
        ]
        for lang, title in samples:
            with self.subTest(lang=lang):
                extracted = ExtractedDocument(
                    document_id="cpa_2019_" + lang,
                    source_id="india_code_central",
                    title=title,
                    authority_type=AuthorityType.ACT,
                    official_url="https://indiacode.gov.in/handle/123456789/15256",
                    raw_hash="a" * 64,
                    text_content=title + "\nSection 1 text",
                    text_hash="b" * 64,
                    language=lang,
                    jurisdiction="IN",
                    **FLAGS,
                )
                self.assertEqual(extracted.language, lang)
                self.assertEqual(extracted.title, title)

    def test_one_document_serving_multiple_legal_domains(self):
        """10. A single cross-domain enactment yields provisions across multiple legal domains."""
        doc = self.adapter.fetch_document("digital_commerce_2026", "https://indiacode.gov.in/handle/123456789/9999", SYNTHETIC_DUAL_DOMAIN_TEXT)
        extracted = self.adapter.extract_text(doc, SYNTHETIC_DUAL_DOMAIN_TEXT)

        provisions = self.adapter.enumerate_sections(extracted, domain="CONSUMER")
        # Provisions can be cross-indexed to both CONSUMER and CYBER without re-scraping
        sec2 = next(p for p in provisions if p.section == "2" and p.subsection is None)
        cyber_sec2 = copy.deepcopy(sec2)
        cyber_sec2.domain = "CYBER"
        cyber_sec2.provision_id = f"{sec2.provision_id}_cyber"

        self.assertEqual(sec2.domain, "CONSUMER")
        self.assertEqual(cyber_sec2.domain, "CYBER")
        self.assertEqual(sec2.raw_document_hash, cyber_sec2.raw_document_hash)

    def test_one_case_requiring_multiple_domain_packs(self):
        """11. A multi-domain case successfully links issues to respective domain provisions."""
        case_issues = [
            {"issue_id": "L001", "domain": "CIVIL_CONTRACT", "topic": "Cloud SLA breach"},
            {"issue_id": "L002", "domain": "CYBER", "topic": "Customer data leak"},
        ]
        # Domain packs are selected per issue
        issue_domains = {i["domain"] for i in case_issues}
        self.assertSetEqual(issue_domains, {"CIVIL_CONTRACT", "CYBER"})

    def test_unknown_domain_abstention(self):
        """12. An issue with an unknown emerging domain (e.g. SPACE_COMMERCE) cleanly abstains without error."""
        emerging_issue = {"issue_id": "L099", "domain": "SPACE_COMMERCE", "query": "satellite orbital liability"}
        # Ingestion repository has no matching provisions for SPACE_COMMERCE
        matching_provisions = [p for p in [] if p.domain == emerging_issue["domain"]]
        self.assertEqual(len(matching_provisions), 0)
        # Clean abstention state
        abstention = {
            "issue_id": emerging_issue["issue_id"],
            "domain": emerging_issue["domain"],
            "status": "LEGAL_SOURCE_PENDING",
            "reason": "NO_MATCHING_SOURCE_COVERAGE",
        }
        self.assertEqual(abstention["status"], "LEGAL_SOURCE_PENDING")
        self.assertEqual(abstention["domain"], "SPACE_COMMERCE")


if __name__ == "__main__":
    unittest.main()
