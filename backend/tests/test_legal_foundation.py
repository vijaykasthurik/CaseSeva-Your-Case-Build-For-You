import copy
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.services.case_blackboard import CaseBlackboard, SnapshotCapacityExceeded
from backend.services.core_workflow import run_core
from backend.services.legal_workflow import run_legal_foundation
from backend.services.legal_registry import legal_registry
from backend.services.verified_corpus import VerifiedCorpus
from backend.services.specialist_packs import PACKS
from backend.tests.core_test_support import core_case
from backend.tests.legal_test_support import LegalTestModel, authority, test_knowledge, publish_reviewed


class LegalFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = MockDatabaseAdapter(Path(self.temp.name) / 'db.json')
        self.model = LegalTestModel()
        self.corpus = VerifiedCorpus(self.db, test_knowledge())
        self.adapters = SimpleNamespace(database=self.db, llm=self.model, mode='mock', processing_mode="mock", llm_processing_mode="mock", phase3_test_double=True,
                                        phase4_test_double=True, verified_corpus=self.corpus)
        self.app = SimpleNamespace(state=SimpleNamespace(adapters=self.adapters))
        core_case(self.db, legal_foundation_requested=True)
        self.store = CaseBlackboard(self.db)

    def run_foundation(self):
        run_legal_foundation(self.app, 'c')
        board = self.store.read_board('c')
        self.assertFalse(self.db.get('cases', 'c').get('processing_error'),
                         {k: (n['status'], n.get('failure_reason')) for k, n in board['nodes'].items()})
        return board

    def test_missing_corpus_preserves_understanding_without_case_file(self):
        board = self.run_foundation()
        self.assertEqual(self.db.get('cases', 'c')['status'], 'LEGAL_CORPUS_NOT_READY')
        self.assertNotIn('case_file', self.db.get('cases', 'c'))
        self.assertEqual(board['data']['legal_foundation']['status'], 'REVIEW_REQUIRED')
        self.assertEqual(set(board['data']['facts']), {'F001'})
        self.assertNotIn('APPLICATION_L001', self.model.calls)
        self.assertEqual(len(board['data']['agent_team']['selected']), 1)

    def test_reviewed_fixture_path_and_repeat_are_idempotent(self):
        publish_reviewed(self.corpus, authority())
        self.run_foundation()
        case = self.db.get('cases', 'c')
        self.assertEqual(case['status'], 'ENGINE1_CASE_FILE_READY')
        calls = list(self.model.calls)
        self.run_foundation()
        self.assertEqual(self.model.calls, calls)
        self.assertEqual(self.db.get('cases', 'c')['case_file']['version'], case['case_file']['version'])

    def test_fake_application_citation_fails_closed(self):
        publish_reviewed(self.corpus, authority())
        def fake(output, context):
            output['applications'][0]['citation'] = 'Invented Citation'
            return output
        self.model.overrides['APPLICATION_L001'] = fake
        board = self.run_foundation()
        self.assertNotIn('case_file', self.db.get('cases', 'c'))
        self.assertTrue(any(n['status'] == 'FAILED' for n in board['nodes'].values()))

    def test_all_six_packs_select_only_requested_specialist(self):
        for index, domain in enumerate(PACKS):
            with self.subTest(domain=domain):
                self.db = MockDatabaseAdapter(Path(self.temp.name) / ('domain' + str(index) + '.json'))
                self.corpus = VerifiedCorpus(self.db, test_knowledge())
                self.adapters.database = self.db
                self.adapters.verified_corpus = self.corpus
                self.store = CaseBlackboard(self.db)
                cid = 'domain' + str(index)
                core_case(self.db, cid, legal_foundation_requested=True)
                self.model.domain = domain
                run_legal_foundation(self.app, cid)
                board = self.store.read_board(cid)
                self.assertEqual(board['data']['agent_team']['primary_domain'], domain)
                self.assertEqual(len(board['data']['specialists']), 1)
                self.assertEqual(self.db.get('cases', cid)['status'], 'LEGAL_CORPUS_NOT_READY')

    def test_optional_branch_contract_changes_use_new_identity(self):
        board = self.run_foundation()
        first, plan1 = legal_registry(self.adapters, self.corpus, board)
        other = copy.deepcopy(board)
        other['data']['legal_issues']['L001']['precedent_useful'] = True
        second, plan2 = legal_registry(self.adapters, self.corpus, other)
        self.assertNotEqual(plan1['foundation'], plan2['foundation'])
        for name in set(first.graph([plan1['foundation']])) & set(second.graph([plan2['foundation']])):
            self.assertEqual(first.get(name).contract, second.get(name).contract)

    def test_source_change_reruns_legal_work_but_not_core_or_specialists(self):
        publish_reviewed(self.corpus, authority())
        self.run_foundation()
        first_version = self.db.get('cases', 'c')['case_file']['version']
        calls = list(self.model.calls)
        publish_reviewed(self.corpus, authority(version_note='amended fixture'))
        self.run_foundation()
        extra = self.model.calls[len(calls):]
        self.assertEqual(extra, ['APPLICATION_L001'])
        self.assertEqual(self.db.get('cases', 'c')['case_file']['version'], first_version + 1)

    def test_mock_without_explicit_test_flag_never_reasons(self):
        run_core(self.app, 'c')
        self.adapters.phase4_test_double = False
        calls = list(self.model.calls)
        self.run_foundation()
        self.assertEqual(calls, self.model.calls)
        self.assertNotIn('case_file', self.db.get('cases', 'c'))

    def test_capacity_failure_is_explicit_review_and_cannot_publish(self):
        run_core(self.app, 'c')
        with patch('backend.services.legal_workflow.run_plan', side_effect=SnapshotCapacityExceeded('bounded')):
            run_legal_foundation(self.app, 'c')
        case = self.db.get('cases', 'c')
        self.assertEqual(case['status'], 'LEGAL_FOUNDATION_REVIEW_REQUIRED')
        self.assertTrue(case['legal_capacity_review_required'])
        self.assertFalse(case['legal_case_file_current'])
        self.assertNotIn('case_file', case)


class CorpusTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = MockDatabaseAdapter(Path(temp.name) / 'db.json')
        self.corpus = VerifiedCorpus(self.db, test_knowledge())

    def test_identity_hash_offsets_registry_and_freshness_gates(self):
        self.assertTrue(self.corpus.validate_identity(authority())[0])
        for change in ({'title': 'Invented Act'}, {'content_hash': 'fake'}, {'section_start': 0}, {'section': '99'},
                       {'official_url': 'https://malicious.test'}, {'retrieved_at': '2001-01-01T00:00:00Z'},
                       {'registry_id': 'secondary'}, {'effective_until': '2019-01-01'}):
            with self.subTest(change=change):
                self.assertFalse(self.corpus.validate_identity(authority(**change))[0])

    def test_version_history_is_immutable(self):
        one = publish_reviewed(self.corpus, authority())
        two = publish_reviewed(self.corpus, authority(version_note='changed'))
        self.assertNotEqual(one['version_id'], two['version_id'])
        self.assertEqual(self.corpus.get('fixture_act', one['version_id'])['version_note'], 'TEST ONLY')
        self.assertEqual(self.corpus.get('fixture_act')['version_id'], two['version_id'])

    def test_metadata_filters_no_global_corpus_ready(self):
        publish_reviewed(self.corpus, authority())
        self.assertEqual(len(self.corpus.search('CONSUMER', 'IN-TN', 'purchase')), 1)
        self.assertFalse(self.corpus.search('CRIMINAL_POLICE', 'IN', 'purchase'))
        self.assertFalse(self.corpus.search('CONSUMER', None, 'purchase'))
        self.assertFalse(self.corpus.search('CONSUMER', 'IN', 'purchase', kind='JUDGMENT'))
        self.assertEqual(self.corpus.readiness()[0]['domain'], 'CONSUMER')
