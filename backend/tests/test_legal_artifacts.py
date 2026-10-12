import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.services.legal_artifacts import save_specialist, load_specialist, compact_specialists
from backend.services.case_blackboard import CaseBlackboard
from backend.tests.core_test_support import core_case


class LegalArtifactTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = MockDatabaseAdapter(Path(temp.name) / 'db.json')
        core_case(self.db)
        self.value = {'agent': 'CONSUMER_DOMAIN', 'domain': 'CONSUMER', 'legal_state': 'PENDING_SOURCE', 'execution_id': 'test',
            'observations': [{'observation': 'Factual question', 'fact_ids': ['F001']}], 'issue_families': ['purchase'], 'review_requirements': []}

    def test_immutable_roundtrip_and_duplicate_write(self):
        reference = save_specialist(self.db, 'c', self.value)
        self.assertEqual(save_specialist(self.db, 'c', self.value), reference)
        self.assertEqual(load_specialist(self.db, 'c', reference), self.value)
        self.assertNotIn('observations', reference)
        self.assertEqual(len(self.db.list('legal_specialist_artifacts')), 1)

    def test_cross_case_and_tampered_references_rejected(self):
        reference = save_specialist(self.db, 'c', self.value)
        with self.assertRaises(ValueError):
            load_specialist(self.db, 'other', reference)
        with self.assertRaises(ValueError):
            load_specialist(self.db, 'c', {**reference, 'content_hash': 'tampered'})

    def test_existing_results_compact_but_protected_fields_remain(self):
        store = CaseBlackboard(self.db)
        board = store.append_change('c', {'specialists.CONSUMER_DOMAIN': self.value}, actor='test', reason='test')
        board = compact_specialists(self.db, store, 'c', board)
        self.assertEqual(load_specialist(self.db, 'c', board['data']['specialists']['CONSUMER_DOMAIN']), self.value)
        core_case(self.db, 'protected')
        store.append_change('protected', {'specialists.CONSUMER_DOMAIN': self.value}, actor='test', reason='test')
        board = store.apply_human_override('protected', 'specialists.CONSUMER_DOMAIN', self.value, actor='advocate', reason='reviewed')
        result = compact_specialists(self.db, store, 'protected', board)
        self.assertEqual(result['data']['specialists']['CONSUMER_DOMAIN'], self.value)

    def test_compaction_event_does_not_duplicate_large_prior_content(self):
        self.value['observations'] = [{'observation': 'x' * 900, 'fact_ids': ['F001']} for _ in range(16)]
        store = CaseBlackboard(self.db)
        board = store.append_change('c', {'specialists.CONSUMER_DOMAIN': self.value}, actor='test', reason='large fixture')
        with patch('backend.services.case_blackboard.MAX_SNAPSHOT_BYTES', 10000):
            compacted = compact_specialists(self.db, store, 'c', board)
        self.assertEqual(load_specialist(self.db, 'c', compacted['data']['specialists']['CONSUMER_DOMAIN']), self.value)
