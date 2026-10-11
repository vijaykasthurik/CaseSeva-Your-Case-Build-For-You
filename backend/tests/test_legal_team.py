import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.services.legal_team import LegalTeamAgents, compact_context
from backend.services.verified_corpus import VerifiedCorpus
from backend.services.case_blackboard import CaseBlackboard, path_version
from backend.tests.legal_test_support import LegalTestModel, test_knowledge, authority
from backend.tests.core_test_support import core_case


class LegalTeamTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = MockDatabaseAdapter(Path(temp.name) / 'db.json')
        core_case(self.db)
        self.model = LegalTestModel()
        self.agents = LegalTeamAgents(SimpleNamespace(mode='mock', phase4_test_double=True, llm=self.model, database=self.db))
        self.values = {'facts': {'F001': {'proposition': 'Fictional purchase', 'evidence_ids': [], 'superseded': False}},
            'parties': {}, 'input.evidence_ids': [], 'domain_classification': {'primary_domain': 'CONSUMER', 'secondary_domains': []},
            'legal_capabilities': {}}
        self.claim = {'inputs': self.values, 'case_id': 'c', 'execution_id': 'test', 'previous_outputs': {}}

    def test_unknown_agent_and_unknown_fact_rejected(self):
        for selection in ({'agent': 'INVENTED_AGENT', 'fact_ids': ['F001'], 'reason': 'test'},
                          {'agent': 'CONSUMER_DOMAIN', 'fact_ids': ['F999'], 'reason': 'test'}):
            self.model.overrides['TEAM_BUILDER'] = {'selected': [selection]}
            with self.assertRaises(ValueError):
                self.agents.team(self.claim)

    def test_secondary_rti_needs_explicit_unavailable_record_dependency(self):
        selection = [{'agent': 'CONSUMER_DOMAIN', 'fact_ids': ['F001'], 'reason': 'test'},
                     {'agent': 'PUBLIC_AUTHORITY', 'fact_ids': ['F001'], 'reason': 'test'}]
        self.model.overrides['TEAM_BUILDER'] = {'selected': selection}
        with self.assertRaises(ValueError):
            self.agents.team(self.claim)
        raw = self.db.get('cases', 'c')['raw_package']
        raw['unavailable_evidence'] = ['Necessary public record not available']
        self.db.update('cases', 'c', {'raw_package': raw})
        self.model.overrides['TEAM_BUILDER'].update(secondary_reason='Fictional necessary public record', public_record_fact_ids=['F001'], unavailable_record_refs=[0])
        self.assertIn('PUBLIC_AUTHORITY', self.agents.team(self.claim).outputs['agent_team']['selected'])
        self.values['facts']['F001']['evidence_ids'] = ['E001']
        with self.assertRaises(ValueError):
            self.agents.team(self.claim)

    def test_issues_keep_ids_versions_and_reject_invented_evidence(self):
        self.values['agent_team'] = self.agents.team(self.claim).outputs['agent_team']
        first = self.agents.issues(self.claim).outputs['legal_issues']
        self.claim['previous_outputs'] = {'legal_issues': first}
        self.assertEqual(first, self.agents.issues(self.claim).outputs['legal_issues'])
        def invented(output, context):
            output['issues'][0]['evidence_ids'] = ['E999']
            return output
        self.model.overrides['LEGAL_ISSUES'] = invented
        with self.assertRaises(ValueError):
            self.agents.issues(self.claim)

    def test_duplicate_issues_rejected_and_unknown_jurisdiction_preserved(self):
        self.values['agent_team'] = self.agents.team(self.claim).outputs['agent_team']
        def duplicate(output, context):
            output['issues'].append(copy.deepcopy(output['issues'][0]))
            return output
        self.model.overrides['LEGAL_ISSUES'] = duplicate
        with self.assertRaises(ValueError):
            self.agents.issues(self.claim)
        def unknown(output, context):
            output['issues'][0].update(jurisdiction=None, jurisdiction_fact_ids=[])
            return output
        self.model.overrides['LEGAL_ISSUES'] = unknown
        self.assertIsNone(self.agents.issues(self.claim).outputs['legal_issues']['L001']['jurisdiction'])

    def test_context_keeps_original_tamil_once_without_translation(self):
        ref = {'wording': 'குளிர்சாதனப் பெட்டி', 'source_id': 'STORY', 'start': 0, 'end': 20}
        context = compact_context({'facts': {'F001': {'source_refs': [ref]}, 'F002': {'source_refs': [ref]}}})
        self.assertEqual(len(context['original_excerpts']), 1)
        self.assertEqual(next(iter(context['original_excerpts'].values()))['wording'], ref['wording'])
        self.assertEqual(context['facts']['F001']['original_excerpt_refs'], context['facts']['F002']['original_excerpt_refs'])

    def test_unrelated_source_does_not_invalidate_other_issue_fingerprint(self):
        store = CaseBlackboard(self.db)
        corpus = VerifiedCorpus(self.db, test_knowledge())
        store.append_change('c', {'legal_issues.L001': {'domain': 'CONSUMER', 'jurisdiction': 'IN', 'query': 'refrigerator'},
                                 'legal_issues.L002': {'domain': 'CONSUMER', 'jurisdiction': 'IN', 'query': 'airplane'}}, actor='test', reason='test')
        corpus.publish(authority())
        first = corpus.sync_case('c')
        corpus.publish(authority(version_note='new fixture revision'))
        second = corpus.sync_case('c')
        self.assertGreater(path_version(second, 'corpus_inputs.L001'), path_version(first, 'corpus_inputs.L001'))
        self.assertEqual(path_version(second, 'corpus_inputs.L002'), path_version(first, 'corpus_inputs.L002'))
