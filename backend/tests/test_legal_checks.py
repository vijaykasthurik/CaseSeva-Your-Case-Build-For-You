import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.models.legal_outputs import validate_issues, Applications
from backend.services.legal_checks import LegalChecks, compact
from backend.services.verified_corpus import VerifiedCorpus
from backend.tests.legal_test_support import authority, test_knowledge, publish_reviewed


class LegalChecksTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = MockDatabaseAdapter(Path(temp.name) / 'db.json')
        self.corpus = VerifiedCorpus(self.db, test_knowledge())
        self.source = publish_reviewed(self.corpus, authority())
        self.checks = LegalChecks(None, self.corpus)
        self.issue = {'domain': 'CONSUMER', 'jurisdiction': 'IN', 'jurisdiction_fact_ids': ['F001'],
                      'date_fact_ids': ['F001'], 'fact_ids': ['F001'], 'contradicting_fact_ids': []}
        self.fact = {'certainty': 'STATED', 'date': {'normalized': '2026-09-03', 'precision': 'EXACT_DATE'}}
        self.values = {'legal_issues.L001': self.issue, 'facts.F001': self.fact,
                       'legal_sources.candidates.L001': {'candidates': [compact(self.source)]}}

    def temporal(self):
        return self.checks.temporal('L001')({'inputs': self.values}).outputs['temporal_findings.L001']

    def citation(self):
        self.values['temporal_findings.L001'] = self.temporal()
        return self.checks.citation('L001')({'inputs': self.values}).outputs['citation_verification.L001']['decisions'][0]

    def test_exact_dates_verified_unknown_dates_pending(self):
        self.assertEqual(self.citation()['status'], 'VERIFIED')
        self.fact['date']['normalized'] = None
        self.assertEqual(self.citation()['status'], 'PENDING')

    def test_approximate_and_conflicting_dates_remain_pending(self):
        self.fact['date']['precision'] = 'YEAR_ONLY'
        self.assertEqual(self.temporal()['decisions']['fixture_act']['status'], 'PENDING')
        self.fact['date']['precision'] = 'EXACT_DATE'
        self.fact['certainty'] = 'CONFLICTED'
        self.assertEqual(self.citation()['status'], 'PENDING')

    def test_precommencement_and_repealed_intervals_not_applicable(self):
        self.fact['date']['normalized'] = '2019-01-01'
        self.assertEqual(self.citation()['status'], 'NOT_APPLICABLE')
        self.source = publish_reviewed(self.corpus, authority(effective_until='2025-01-01'))
        self.values['legal_sources.candidates.L001']['candidates'] = [compact(self.source)]
        self.fact['date']['normalized'] = '2026-01-01'
        self.assertEqual(self.citation()['status'], 'NOT_APPLICABLE')

    def test_missing_temporal_support_cannot_establish_law(self):
        self.source = publish_reviewed(self.corpus, authority(temporal_source_ids=['missing']))
        self.values['legal_sources.candidates.L001']['candidates'] = [compact(self.source)]
        self.assertEqual(self.citation()['status'], 'PENDING')

    def test_fabricated_section_title_quote_and_citation_rejected(self):
        for field in ('title', 'section', 'quote', 'citation'):
            with self.subTest(field=field):
                self.values['legal_sources.candidates.L001']['candidates'] = [{**compact(self.source), field: 'Fabrication'}]
                self.assertEqual(self.citation()['status'], 'REJECTED')

    def test_old_source_version_cannot_publish_as_current(self):
        publish_reviewed(self.corpus, authority(version_note='new'))
        self.assertEqual(self.citation()['status'], 'OUTDATED')

    def test_wrong_domain_and_state_are_not_applicable(self):
        self.issue['domain'] = 'CRIMINAL_POLICE'
        self.assertEqual(self.citation()['status'], 'NOT_APPLICABLE')
        self.issue['domain'] = 'CONSUMER'
        self.source = publish_reviewed(self.corpus, authority(jurisdiction='IN-KA'))
        self.values['legal_sources.candidates.L001']['candidates'] = [compact(self.source)]
        self.issue['jurisdiction'] = 'IN-TN'
        self.assertEqual(self.citation()['status'], 'NOT_APPLICABLE')

    def test_fake_judgment_court_and_citation_rejected(self):
        for changes in ({'court': 'Imaginary Court'}, {'citation': 'Invented 999'}):
            self.assertFalse(self.corpus.validate_identity(authority(source_type='JUDGMENT', **changes))[0])

    def application_values(self, source):
        self.values['legal_applications.L001'] = {'applications': [{'source_id': source['source_id'], 'source_version': source['version_id']}]}

    def test_jurisdiction_inputs_need_version_bound_review(self):
        source = publish_reviewed(self.corpus, authority(rules={'forums': [{'quote': 'Fixture Forum', 'requires': ['amount']}], 'remedies': [{'quote': 'refund'}]}))
        self.application_values(source)
        self.values['legal_context'] = {'amount': 24500}
        self.assertEqual(self.checks.jurisdiction('L001')({'inputs': self.values}).outputs['jurisdiction_remedy.L001']['status'], 'REVIEW_REQUIRED')
        self.values['legal_context'] = {source['source_id']: {'facts': {'amount': 24500}, 'reviewed_by': 'test', 'source_version': source['version_id'], 'applicable': True}}
        self.assertEqual(self.checks.jurisdiction('L001')({'inputs': self.values}).outputs['jurisdiction_remedy.L001']['status'], 'SOURCE_VERIFIED')

    def test_limitation_requires_reviewed_trigger_version_and_exclusions(self):
        source = publish_reviewed(self.corpus, authority(rules={'limitation': {'quote': 'purchase', 'years': 2}}))
        self.application_values(source)
        run = lambda: self.checks.limitation('L001')({'inputs': self.values}).outputs['limitation.L001']
        self.assertIsNone(run()['deadline'])
        decision = {'source_id': source['source_id'], 'source_version': source['version_id'], 'fact_id': 'F001', 'reviewed_by': 'test', 'exclusions_reviewed': True}
        self.values['limitation_triggers.L001'] = decision
        self.assertEqual(run()['deadline'], '2028-09-03')
        decision['fact_id'] = 'F999'
        self.assertIsNone(run()['deadline'])
        decision['fact_id'] = 'F001'
        decision['source_version'] = 'old'
        self.assertIsNone(run()['deadline'])

    def test_evidence_elements_do_not_inherit_all_issue_facts(self):
        self.values['legal_applications.L001'] = {'applications': [{'source_id': 'fixture_act', 'fact_ids': ['F001'],
            'required_elements': ['purchase', 'refund'], 'element_mapping': [{'element': 'purchase', 'fact_ids': ['F001']}]}]}
        self.values['evidence_mapping'] = {'fact_support': {'F001': {'state': 'USER_STATED', 'evidence_ids': []}}, 'unavailable_evidence': ['receipt unavailable']}
        output = self.checks.evidence('L001')({'inputs': self.values}).outputs['evidence_law.L001']
        self.assertTrue(output['missing_elements'])
        self.assertEqual(output['elements'][1]['fact_ids'], [])
        self.assertEqual(output['unavailable'], [{'ref': '/evidence_mapping/unavailable_evidence/0'}])

    def test_persisted_application_rejects_private_and_unknown_fields(self):
        with self.assertRaises(ValueError):
            Applications.model_validate({'issue_id': 'L001', 'status': 'SOURCE_VERIFIED', 'applications': [], 'unknowns': [], 'output_b': 'private'})

    def test_reviewed_application_cannot_bypass_authority_revalidation(self):
        app = {k: self.source[k] for k in ('source_id', 'citation', 'title', 'section', 'quote')}
        app.update(fact_ids=['F001'], explanation='fixture', source_version=self.source['version_id'],
                   authority_state='SOURCE_VERIFIED', applicability_state='ADVOCATE_REVIEW_REQUIRED')
        value = {'issue_id': 'L001', 'status': 'SOURCE_VERIFIED', 'applications': [app], 'unknowns': []}
        self.checks.validate_applications(value)
        app['quote'] = 'Human-entered invented law'
        with self.assertRaises(ValueError):
            self.checks.validate_applications(value)
