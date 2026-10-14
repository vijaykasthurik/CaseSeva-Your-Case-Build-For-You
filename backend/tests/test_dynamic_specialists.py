"""Synthetic unseen-domain orchestration; no network or legal coverage assumptions."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.services.case_blackboard import CaseBlackboard
from backend.services.legal_team import LegalTeamAgents
from backend.services.legal_registry import legal_registry
from backend.services.legal_workflow import run_legal_foundation
from backend.services.legal_checks import LegalChecks
from backend.services.legal_artifacts import load_specialist
from backend.services.specialist_packs import descriptor, validate_descriptor, PACKS
from backend.models.legal_outputs import validate_team, validate_issues
from backend.services.verified_corpus import VerifiedCorpus
from backend.tests.core_test_support import CoreTestModel, core_case
from backend.tests.legal_test_support import test_knowledge

UNKNOWN = 'AVIATION_PASSENGER_COMPENSATION'


class DynamicModel(CoreTestModel):
    def __init__(self, domains):
        super().__init__()
        self.domain = domains[0]
        self.domains = domains
        self.overlap = False
        self.fail_specialist = False

    def generate(self, prompt, schema):
        if schema['stage'].startswith('core_'):
            return super().generate(prompt, schema)
        context = json.loads(prompt.split('CASE DATA:\n', 1)[1])
        stage = schema['stage']
        if stage == 'foundation_team_builder':
            return {'needs': [{'issue_key': 'issue' if self.overlap else 'issue_' + str(i),
                'domain': d, 'capability': 'ISSUE_ANALYSIS', 'fact_ids': ['F001'],
                'reason': 'Synthetic disputed service question'} for i, d in enumerate(self.domains)],
                'limitation_relevant': False, 'precedent_useful': False, 'optional_reason': 'Synthetic test'}
        if stage == 'foundation_legal_issues':
            selections = context['agent_team']['selected']
            issues = {}
            for name, item in selections.items():
                key = item['issue_key'] or 'legacy'
                issue = issues.setdefault(key, {'key': key, 'statement': 'Synthetic service question',
                    'category': 'SERVICE', 'domain': item['domain'], 'domain_contexts': [],
                    'fact_ids': ['F001'], 'specialist_origins': [], 'query': 'service cancellation requested compensation',
                    'limitation_relevant': False, 'precedent_useful': False})
                issue['specialist_origins'].append(name)
                issue['domain_contexts'].append(item['domain'])
            return {'issues': list(issues.values())}
        if self.fail_specialist:
            raise RuntimeError('Synthetic generation unavailable')
        return {'observations': [{'observation': 'Synthetic question', 'fact_ids': ['F001']}],
                'issue_families': ['service']}


class DynamicSpecialistTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = MockDatabaseAdapter(Path(self.temp.name) / 'db.json')
        core_case(self.db, legal_foundation_requested=True)
        self.model = DynamicModel([UNKNOWN])
        self.adapters = SimpleNamespace(database=self.db, llm=self.model, mode='mongodb',
            llm_processing_mode='mock', processing_mode='mock', phase3_test_double=True, phase4_test_double=True)
        self.corpus = VerifiedCorpus(self.db, test_knowledge())
        self.adapters.verified_corpus = self.corpus
        self.agents = LegalTeamAgents(self.adapters)
        self.values = {'domain_classification': {'primary_domain': UNKNOWN, 'secondary_domains': []},
            'facts': {'F001': {'proposition': 'Synthetic disputed service', 'evidence_ids': [], 'superseded': False}},
            'parties': {}, 'input.evidence_ids': [], 'legal_capabilities': {}}
        self.claim = {'inputs': self.values, 'case_id': 'c', 'execution_id': 'test', 'previous_outputs': {}}

    def team(self):
        value = self.agents.team(self.claim).outputs['agent_team']
        validate_team(value)
        self.values['agent_team'] = value
        return value

    def test_domain_matrix_and_neutral_query_abstention(self):
        for domains in (["CONSUMER"], [UNKNOWN], ['CONSUMER', 'CIVIL_CONTRACT'],
                        ['CONSUMER', UNKNOWN], ['CIVIL_CONTRACT', 'CYBER', UNKNOWN],
                        [UNKNOWN, 'MARITIME_ADMIRALTY', 'EMERGING_DIGITAL_PLATFORM_LIABILITY_2026']):
            with self.subTest(domains=domains):
                self.model.domains = domains
                team = self.team()
                self.assertEqual({v['domain'] for v in team['selected'].values()}, set(domains))
                registry, plan = legal_registry(self.adapters, self.corpus, {'data': {'agent_team': team}})
                for name, item in team['selected'].items():
                    self.assertEqual(item['registered_pack'], item['domain'] in PACKS)
                    registration = registry.get(name)
                    self.assertTrue(registration.available)
                    result = registration.handler(self.claim)
                    self.values.update(result.outputs)
                    artifact = load_specialist(self.db, 'c', result.outputs['specialists.' + name])
                    self.assertTrue(artifact['producer']['test_double'])
                issues = self.agents.issues(self.claim).outputs['legal_issues']
                validate_issues(issues)
                self.assertEqual({v['domain'] for v in issues.values()}, set(domains))
                checks = LegalChecks(self.adapters, self.corpus)
                for iid, issue in issues.items():
                    self.assertTrue(issue['producers'])
                    retrieval = checks.retrieval(iid)({'inputs': {'legal_issues.' + iid: issue}}).outputs
                    self.assertEqual(retrieval['legal_sources.candidates.' + iid]['status'], 'LEGAL_SOURCE_PENDING')
                    application = checks.application(iid)({'inputs': {'legal_issues.' + iid: issue,
                        'citation_verification.' + iid: {'decisions': []}}}).outputs
                    self.assertEqual(application['legal_applications.' + iid]['status'], 'PENDING_SOURCE')

    def test_overlap_and_conflicting_provenance(self):
        self.model.domains = ['CIVIL_CONTRACT', UNKNOWN]
        self.model.overlap = True
        self.team()
        issues = self.agents.issues(self.claim).outputs['legal_issues']
        self.assertEqual(len(issues), 1)
        self.assertEqual(len(issues['L001']['producers']), 2)
        selected = self.values['agent_team']['selected']
        # A producer for a different need cannot be attributed to this issue.
        name = next(iter(selected))
        bad = descriptor({'issue_key': 'unrelated', 'domain': UNKNOWN, 'fact_ids': ['F001'], 'reason': 'test'})
        selected[name] = bad
        with self.assertRaises(ValueError):
            self.agents.issues(self.claim)

    def test_deduplication_and_label_security(self):
        self.model.domains = [UNKNOWN, UNKNOWN]
        self.model.overlap = True
        self.assertEqual(len(self.team()['selected']), 1)
        self.assertEqual(self.team(), self.team())
        for label in ('../CONSUMER', 'x;import os', 'A' * 81, '', 'A\nB'):
            self.model.domains = [label]
            with self.assertRaises(ValueError):
                self.team()
        self.model.domains = [UNKNOWN]
        team = self.team()
        name, value = next(iter(team['selected'].items()))
        for bad_name in ('os.system', '../../evil', 'DYNAMIC_FORGED'):
            with self.assertRaises(ValueError):
                legal_registry(self.adapters, self.corpus, {'data': {'agent_team': {'selected': {bad_name: value}}}})
        value['registered_pack'] = True
        with self.assertRaises(ValueError):
            validate_descriptor(name, value)

    def test_processing_availability_never_inferred_from_mongo(self):
        team = self.team()
        name = next(iter(team['selected']))
        self.adapters.phase4_test_double = False
        for mode, available in [('mock', False), ('unavailable', False), ('live', True)]:
            self.adapters.llm_processing_mode = mode
            registry, _ = legal_registry(self.adapters, self.corpus, {'data': {'agent_team': team}})
            self.assertEqual(registry.get(name).available, available)
            if not available:
                with self.assertRaises(RuntimeError):
                    self.agents.specialist(name)(self.claim)

    def test_known_enrichment_and_unknown_generic_coexist(self):
        original = self.model.generate
        def generate(prompt, schema):
            value = original(prompt, schema)
            if schema['stage'] == 'foundation_team_builder':
                value['selected'] = [{'agent': 'CONTRACT_RELATIONSHIP', 'fact_ids': ['F001'], 'reason': 'Synthetic contract'}]
            return value
        self.model.generate = generate
        team = self.team()
        self.assertIn('CONTRACT_RELATIONSHIP', team['selected'])
        self.assertEqual(len(team['selected']), 2)

    def test_full_workflow_unknown_no_corpus(self):
        run_legal_foundation(SimpleNamespace(state=SimpleNamespace(adapters=self.adapters)), 'c')
        case = self.db.get('cases', 'c')
        board = CaseBlackboard(self.db).read_board('c')
        self.assertEqual(case['status'], 'LEGAL_CORPUS_NOT_READY')
        self.assertNotIn('case_file', case)
        self.assertEqual(board['data']['legal_issues']['L001']['domain'], UNKNOWN)
        self.assertEqual(board['data']['legal_foundation']['status'], 'REVIEW_REQUIRED')

    def test_specialist_failure_preserves_case(self):
        self.model.fail_specialist = True
        run_legal_foundation(SimpleNamespace(state=SimpleNamespace(adapters=self.adapters)), 'c')
        case = self.db.get('cases', 'c')
        board = CaseBlackboard(self.db).read_board('c')
        self.assertEqual(case['status'], 'LEGAL_FOUNDATION_REVIEW_REQUIRED')
        self.assertIn('F001', board['data']['facts'])
        self.assertNotIn('case_file', case)
        self.assertTrue(any(n['status'] == 'FAILED' for n in board['nodes'].values()))
