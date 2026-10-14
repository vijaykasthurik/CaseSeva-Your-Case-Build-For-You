"""Synthetic fixtures only; these are not legal authorities or human reviews."""
from dataclasses import replace
from datetime import date
from hashlib import sha256
import unittest
from .evaluation import BenchmarkCase, evaluate, metrics
from .retrieval import (CitationTrace, ConservativeGate, DomainPack, Issue,
                        OfflineRetrieval, Passage, bm25, exact_passage, plan, verify_trace)


def fixture():
    text = "synthetic remedy repayment"
    p = Passage("p1", "synthetic1", "revision1", "example", "EX", "en", True,
                text, sha256(text.encode()).hexdigest(), 0, len(text), text, "SYNTHETIC:1",
                "REVIEWED_PRIMARY", "synthetic-receipt", "VERIFIED", True,
                date(2020, 1, 1), None, date(2026, 1, 1), True, True, True)
    issue = Issue("L001", "repayment", "example", "en", "EX", date(2025, 1, 1),
                  ("F001",), ("E001",), ("remedy",))
    return p, issue, DomainPack("example")


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.p, self.issue, self.pack = fixture()
        self.engine = OfflineRetrieval(enabled=True)

    def test_disabled_default(self):
        with self.assertRaises(RuntimeError):
            OfflineRetrieval().search(self.issue, self.pack, (self.p,))

    def test_issue_identity_multiple_queries(self):
        queries = plan(self.issue, self.pack)
        self.assertEqual([q.text for q in queries], ["repayment", "remedy"])
        self.assertTrue(all(q.issue_id == "L001" for q in queries))
        with self.assertRaises(ValueError):
            plan(replace(self.issue, issue_id="bad"), self.pack)
        with self.assertRaises(ValueError):
            plan(self.issue, DomainPack("other"))

    def test_bm25_deterministic_and_no_match(self):
        self.assertEqual(bm25("repayment", (self.p,)), ["p1"])
        self.assertEqual(bm25("unrelated", (self.p,)), [])
        self.assertEqual(bm25("repayment", ()), [])

    def test_exact_binding_tampering(self):
        self.assertTrue(exact_passage(self.p))
        for changed in (replace(self.p, quote="repay"), replace(self.p, start=-1),
                        replace(self.p, document_hash="bad"), replace(self.p, end=999)):
            self.assertFalse(exact_passage(changed))

    def test_each_gate_abstains(self):
        for kwargs in ({"review_state": "REVIEW_PENDING"}, {"receipt_id": None},
                       {"review_state": "STALE"}, {"verification": "PENDING"},
                       {"official": False}, {"domain": "other"}, {"jurisdiction": "OTHER"},
                       {"temporal_reviewed": False}, {"effective_from": None},
                       {"coverage_through": None}, {"version_verified": False},
                       {"citation_covered": False}, {"hierarchy_verified": False},
                       {"revision": ""}, {"quote": "tampered"}):
            with self.subTest(kwargs=kwargs):
                result = self.engine.search(self.issue, self.pack, (replace(self.p, **kwargs),))
                self.assertTrue(result.abstained)
                self.assertTrue(result.excluded)

    def test_temporal_boundaries(self):
        p = replace(self.p, effective_until=date(2026, 1, 1))
        for when, permitted in ((date(2019, 12, 31), False), (date(2020, 1, 1), True),
                                (date(2025, 12, 31), True), (date(2026, 1, 1), False)):
            with self.subTest(when=when):
                self.assertEqual(not ConservativeGate().reasons(p, replace(self.issue, on_date=when)), permitted)
        self.assertIn("temporal", ConservativeGate().reasons(self.p, replace(self.issue, on_date=date(2026, 1, 2))))

    def test_provider_cannot_bypass_gate_or_invent_ids(self):
        class Provider:
            def rank(inner, query, candidates):
                self.assertEqual([p.passage_id for p in candidates], ["p1"])
                return ["pending", "invented", "p1", "p1"]
        pending = replace(self.p, passage_id="pending", review_state="REVIEW_PENDING")
        engine = OfflineRetrieval(enabled=True, dense=Provider(), reranker=Provider())
        result = engine.search(self.issue, self.pack, (pending, self.p))
        self.assertEqual([p.passage_id for p in result.passages], ["p1"])

    def test_dense_can_recover_cross_language_without_language_branch(self):
        class FakeDense:
            def rank(inner, query, candidates):
                self.assertEqual(query.language, "xx")
                return ["p1"]
        issue = replace(self.issue, language="xx", statement="differentlanguage", candidate_queries=())
        self.assertTrue(self.engine.search(issue, self.pack, (self.p,)).abstained)
        self.assertFalse(OfflineRetrieval(enabled=True, dense=FakeDense()).search(issue, self.pack, (self.p,)).abstained)

    def test_duplicate_identity_and_k_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.search(self.issue, self.pack, (self.p, self.p))
        with self.assertRaises(ValueError):
            self.engine.search(self.issue, self.pack, (self.p,), 0)

    def test_trace_links_and_revision_binding(self):
        result = self.engine.search(self.issue, self.pack, (self.p,))
        trace = CitationTrace("U001", "F001", "E001", "L001", "synthetic1", "revision1", "p1", "SYNTHETIC:1", "LF001")
        def valid(t, links={("F001", "E001")}):
            return verify_trace(t, self.issue, result, {("U001", "F001")}, links)
        self.assertTrue(valid(trace))
        for kwargs in ({"revision": "old"}, {"issue_id": "L002"}, {"citation": "invented"}, {"finding_id": ""}):
            self.assertFalse(valid(replace(trace, **kwargs)))
        self.assertFalse(valid(trace, set()))

    def test_metrics_known_ranking(self):
        self.assertEqual(metrics(["wrong", "p1", "p1"], {"p1", "p2"}, 3),
                         {"recall_at_k": .5, "precision_at_k": 1/3, "mrr_at_k": .5})

    def test_offline_benchmark_integration(self):
        wrong_date = replace(self.p, passage_id="old", coverage_through=date(2024, 1, 1))
        wrong_place = replace(self.p, passage_id="elsewhere", jurisdiction="OTHER")
        case = BenchmarkCase(self.issue, self.pack, (self.p, wrong_date, wrong_place),
                             frozenset({"p1"}), frozenset({("synthetic1", "revision1", "p1", "SYNTHETIC:1")}),
                             False, frozenset({"old", "elsewhere"}))
        report = evaluate(self.engine, case, 1)
        self.assertEqual(report["recall_at_k"], 1)
        self.assertEqual(report["exact_citation_recovery"], 1)
        self.assertTrue(report["filters_correct"])
        self.assertTrue(report["abstention_correct"])
        pending = replace(self.p, review_state="REVIEW_PENDING")
        empty = replace(case, corpus=(pending,), relevant=frozenset(), exact_citations=frozenset(), expected_abstention=True)
        self.assertTrue(evaluate(self.engine, empty)["abstention_correct"])


if __name__ == "__main__":
    unittest.main()
