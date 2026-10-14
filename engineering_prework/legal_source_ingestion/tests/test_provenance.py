"""Offline negative and fixture-boundary regressions. Never fetch official sources."""
import ast
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
from .. import test_ingestion_harness
from ..models import AuthorityType, VersionRelationship, ReviewStatus
from ..adapters import IndiaCodeAdapter, MinistryPortalAdapter, JudgmentSourceAdapter
from ..adapters.unsupported_adapter import AcquisitionUnavailable
from ..version_graph import VersionGraph
from .fixtures.adapters import FixtureIndiaCodeAdapter, FixtureMinistryAdapter, FixtureJudgmentAdapter


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        harness = test_ingestion_harness.IngestionTestHarness()
        harness.setUp()
        self.metadata = harness.meta_indiacode
        self.network = patch("socket.socket", side_effect=AssertionError("Internet forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_real_adapters_fail_closed_at_every_acquisition_boundary(self):
        for cls in (IndiaCodeAdapter, MinistryPortalAdapter, JudgmentSourceAdapter):
            adapter = cls(self.metadata)
            for method, args in [("discover_documents", ()), ("fetch_document", ("arbitrary", "https://indiacode.gov.in/doc")),
                                 ("extract_text", (object(),)), ("extract_metadata", (object(),)),
                                 ("build_provenance", (object(), object())), ("discover_related_amendments", ("cpa_2019",))]:
                with self.subTest(adapter=cls.__name__, method=method):
                    with self.assertRaises(AcquisitionUnavailable) as failure:
                        getattr(adapter, method)(*args)
                    self.assertEqual(failure.exception.status, "NOT_FETCHED")
            with self.assertRaises(TypeError):
                adapter.fetch_document("arbitrary", "https://indiacode.gov.in/doc", text_payload="pretend official")
            with self.assertRaises(TypeError):
                adapter.extract_text(object(), text_override="pretend official")

    def test_unknown_capability_and_manual_sources(self):
        for cls in (IndiaCodeAdapter, MinistryPortalAdapter, JudgmentSourceAdapter):
            for changes, expected in [({"source_id": "unknown"}, "NOT_FETCHED"),
                                      ({"captcha_required": True}, "MANUAL_OR_BROWSER_REVIEW_REQUIRED"),
                                      ({"implementation_status": "MANUAL_BROWSER_ONLY"}, "MANUAL_OR_BROWSER_REVIEW_REQUIRED"),
                                      ({"recommended_acquisition_method": "MANUAL_OR_BROWSER_REVIEW_REQUIRED"}, "MANUAL_OR_BROWSER_REVIEW_REQUIRED")]:
                adapter = cls(self.metadata.model_copy(update=changes))
                with self.assertRaises(AcquisitionUnavailable) as failure:
                    adapter.fetch_document("anything", "https://indiacode.gov.in/doc")
                self.assertEqual(failure.exception.status, expected)
                with self.assertRaises(AcquisitionUnavailable):
                    adapter.discover_documents()

    def test_arbitrary_documents_share_generic_offline_fixture_path(self):
        for cls, kind in [(FixtureIndiaCodeAdapter, AuthorityType.ACT),
                          (FixtureMinistryAdapter, AuthorityType.RULE),
                          (FixtureMinistryAdapter, AuthorityType.NOTIFICATION),
                          (FixtureMinistryAdapter, AuthorityType.ORDINANCE),
                          (FixtureMinistryAdapter, AuthorityType.REGULATION),
                          (FixtureJudgmentAdapter, AuthorityType.JUDGMENT)]:
            with self.subTest(kind=kind):
                adapter = cls(self.metadata)
                text = "PART I\nGENERAL\nCHAPTER I\nGENERAL\n1. Scope.—Synthetic orbital habitat duties.\n(1) Keep records.\n(a) Retain logs.\n"
                raw = adapter.fetch_document("orbital_" + kind.value.lower(), "ignored", text, authority_type=kind)
                extracted = adapter.extract_text(raw, text)
                provisions = adapter.enumerate_sections(extracted, "SPACE_LAW")
                self.assertTrue(provisions)
                self.assertEqual(provisions[0].part, "PART I")
                self.assertEqual(provisions[0].chapter, "CHAPTER I")
                records = [raw, extracted, *provisions, *adapter.discover_related_amendments(raw.document_id)]
                for record in records:
                    self.assertEqual(record.source_mode, "TEST_FIXTURE")
                    self.assertFalse(record.officially_retrieved)
                    self.assertFalse(record.review_eligible)
                    with self.assertRaises(ValidationError):
                        record.review_eligible = True
                receipt = adapter.build_provenance(raw, extracted)
                self.assertFalse(receipt["officially_retrieved"])
                self.assertEqual(receipt["retrieval_method"], "TEST_FIXTURE")
                self.assertEqual(raw.raw_content_hash, hashlib.sha256(text.encode()).hexdigest())
                self.assertEqual(raw.file_size_bytes, len(text.encode()))
                self.assertEqual(raw.http_headers, {})
                self.assertIsNone(raw.http_status)
                with self.assertRaises(ValueError):
                    adapter.extract_text(raw, text + " forged")
                with self.assertRaises(ValidationError):
                    provisions[0].review_status = ReviewStatus.REVIEWED_PRIMARY
                self.assertEqual(provisions[0].review_status, ReviewStatus.DISCOVERED)

    def test_discovery_is_never_verification(self):
        adapter = FixtureIndiaCodeAdapter(self.metadata)
        edge = adapter.discover_related_amendments("arbitrary")[0]
        self.assertFalse(edge.verified)
        with self.assertRaises(ValidationError):
            edge.verified = True
        with self.assertRaises(ValidationError):
            VersionRelationship(**dict(edge.model_dump(), verified=True))
        graph = VersionGraph()
        graph.add_node("arbitrary", "Synthetic", AuthorityType.ACT, "https://fixtures.invalid/act")
        graph.edges.append(edge)
        self.assertEqual(graph.is_temporally_valid_on("arbitrary", "2026-05-01"),
                         (False, "COMMENCEMENT_DATE_UNRESOLVED"))
        with self.assertRaises(ValidationError):
            graph.add_relationship("notification", "arbitrary", "COMMENCED_BY", "url", "evidence", verified=True)
        self.assertEqual(len(graph.edges), 1)
        # Pydantic unchecked-copy APIs are not a review authority either.
        graph.edges = [edge.model_copy(update={"verified": True})]
        self.assertEqual(graph.is_temporally_valid_on("arbitrary", "2026-05-01"),
                         (False, "COMMENCEMENT_DATE_UNRESOLVED"))

    def test_unverified_repeal_cannot_change_node_interval(self):
        graph = VersionGraph()
        graph.add_node("act", "Synthetic", AuthorityType.ACT, "url", effective_from="2020-01-01")
        graph.add_relationship("amendment", "act", "AMENDED_BY", "url", "possible repeal", repeal_date="2021-01-01")
        self.assertEqual(graph.is_temporally_valid_on("act", "2022-01-01"), (True, "IN_FORCE"))

    def test_fixture_discovery_markers_and_no_fixture_imports_in_common_code(self):
        for cls in (FixtureIndiaCodeAdapter, FixtureMinistryAdapter, FixtureJudgmentAdapter):
            for candidate in cls(self.metadata).discover_documents():
                self.assertEqual(candidate["source_mode"], "TEST_FIXTURE")
                self.assertFalse(candidate["officially_retrieved"])
                self.assertFalse(candidate["review_eligible"])
        root = Path(__file__).resolve().parents[1]
        for path in root.rglob("*.py"):
            if "tests" in path.parts or path.name.startswith("test_"):
                continue
            code = path.read_text(encoding="utf-8")
            for forbidden in ("cpa_2019", "Consumer Protection", "Section 2(7)", "Section 35", "Official Text for", "Official Enactment Text for"):
                self.assertNotIn(forbidden, code, str(path))
            for node in ast.walk(ast.parse(code)):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn("fixtures", node.module or "", str(path))
