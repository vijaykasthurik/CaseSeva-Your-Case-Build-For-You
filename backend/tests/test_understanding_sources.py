import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.models.understanding import FactCandidates, SourceSpan, Dated
from backend.services.input_layer import build_raw_package
from backend.services.understanding_sources import passages, ground, checked_date, assign_ids, synchronized_raw, InputNotReady


class UnderstandingSourceTests(unittest.TestCase):
    def raw(self, story="Paid Rs. 24,500 on 3 September 2026."):
        return build_raw_package({"case_id": "c", "input_version": 1, "client_story": story, "evidence": []}, SimpleNamespace(mode="mock", processing_mode="mock", llm_processing_mode="mock"))

    def test_multilingual_originals_survive_without_translation(self):
        for text in ("என் பெயர் காவியா", "मेरा नाम काव्या है", "నా పేరు కావ్య", "My name is Kavya", "என் receipt 24,500"):
            raw = self.raw(text)
            indexed = passages(raw)
            self.assertEqual(indexed[0]["text"], text)
            ref = ground([SourceSpan(passage=0, excerpt=text)], indexed)[0]
            self.assertEqual(ref["wording"], text)
            self.assertIsNone(ref["evidence_id"])

    def test_reject_invented_quote_and_pending_extraction(self):
        indexed = passages(self.raw())
        with self.assertRaises(ValueError):
            ground([SourceSpan(passage=0, excerpt="Compressor failure")], indexed)
        raw = self.raw()
        raw["provenance"].append({"source_id": "E001", "evidence_id": "E001", "original_text": "unreadable guessed text", "extraction_status": "PENDING"})
        self.assertEqual(len(passages(raw)), 1)

    def test_index_only_selection_copies_exact_original(self):
        indexed = passages(self.raw("என் பெயர் காவியா. Receipt உள்ளது."))
        self.assertEqual(ground([SourceSpan(passage=0)], indexed)[0]["wording"], indexed[0]["text"])
        with self.assertRaises(ValueError):
            ground([SourceSpan(passage=99)], indexed)

    def test_dates_are_checked_against_originals_and_unknowns_remain_unknown(self):
        indexed = passages(self.raw())
        refs = ground([SourceSpan(passage=0, excerpt=indexed[0]["text"])], indexed)
        exact = Dated(expression="3 September 2026", precision="EXACT_DATE", normalized="2026-09-03")
        self.assertEqual(checked_date(exact, refs, indexed)["normalized"], "2026-09-03")
        with self.assertRaises(ValueError):
            checked_date(exact.model_copy(update={"normalized": "2026-09-04"}), refs, indexed)
        with self.assertRaises(ValueError):
            checked_date(Dated(precision="UNKNOWN", normalized="2026-09-03"), refs, indexed)
        self.assertIsNone(checked_date(Dated(), refs, indexed)["normalized"])

    def test_relative_words_cannot_be_resolved_against_worker_clock(self):
        indexed = passages(self.raw('The product failed today.'))
        refs = ground([SourceSpan(passage=0)], indexed)
        value = checked_date(Dated(expression='today', precision='EXACT_DATE', normalized='2026-10-11'), refs, indexed)
        self.assertIsNone(value['normalized'])
        self.assertTrue(value['normalization_review_required'])

    def test_ids_are_preserved_and_new_items_do_not_renumber_old(self):
        a = {"identity_anchor": "a", "semantic_key": "purchase", "source_refs": []}
        b = {"identity_anchor": "b", "semantic_key": "delivery", "source_refs": []}
        old = assign_ids([a, b], {}, "F", "fact_id")
        new = assign_ids([b, {"identity_anchor": "c", "semantic_key": "complaint", "source_refs": []}, a], old, "F", "fact_id")
        self.assertEqual(new["F001"]["semantic_key"], "purchase")
        self.assertEqual(new["F002"]["semantic_key"], "delivery")
        self.assertEqual(new["F003"]["semantic_key"], "complaint")
        changed = assign_ids([{**a, "identity_anchor": "updated"}], old, "F", "fact_id")
        self.assertIn("F001", changed)
        self.assertTrue(changed["F002"]["superseded"])

    def test_duplicate_sources_merge_without_duplicate_fact_ids(self):
        a = {"identity_anchor": "same-claim", "semantic_key": "paid", "source_refs": [{"source_id": "STORY"}]}
        b = {**a, "source_refs": [{"source_id": "E001"}]}
        result = assign_ids([a, b], {}, "F", "fact_id")
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result["F001"]["source_refs"]), 2)

    def test_sync_rejects_stale_or_wrong_case_raw_before_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            db = MockDatabaseAdapter(Path(directory) / "db.json")
            raw = self.raw()
            db.create("cases", {"id": "c", "case_id": "c", "input_version": 1, "evidence": [], "raw_package": raw})
            self.assertEqual(synchronized_raw(db, "c")[0], raw)
            db.update("cases", "c", {"input_version": 2})
            with self.assertRaises(InputNotReady):
                synchronized_raw(db, "c")

    def test_model_cannot_supply_persistent_ids_or_extra_fields(self):
        with self.assertRaises(ValueError):
            FactCandidates.model_validate({"language": {"detected_languages": ["en"], "supported": True},
                "facts": [{"key": "paid", "fact_id": "F001", "proposition": "paid", "category": "payment", "sources": [{"passage": 0, "excerpt": "paid"}]}], "incidents": []})
