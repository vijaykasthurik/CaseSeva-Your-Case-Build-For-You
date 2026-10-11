"""Capability edge cases through production transformations, without paid calls."""
import unittest
from types import SimpleNamespace
from backend.models.understanding import StageCandidates, PartyCandidates, FactCandidates, EvidenceCandidates, ClarificationCandidates
from backend.services.understanding_agents import CoreAgents
from backend.services.understanding_sources import passages
from backend.services.input_layer import build_raw_package
from backend.tests.core_test_support import LANGUAGE


class CoreContractTests(unittest.TestCase):
    def setUp(self):
        self.raw = build_raw_package({'case_id': 'c', 'client_story': 'A seller contacted me around September 2026. The visitor name is unknown.', 'evidence': []}, SimpleNamespace(mode='mock'), working_language_required=False)
        self.indexed = passages(self.raw)
        self.agents = CoreAgents(None)
        self.claim = {'execution_id': 'unit', 'board_version': 1, 'inputs': {'facts': {'F001': {'certainty': 'STATED'}}}, 'previous_outputs': {}}

    def test_stage_variants_and_ambiguous_stage(self):
        for stage in ['NEW_CONSULTATION', 'COMPLAINT_OR_FIR_STAGE', 'EXISTING_CASE', 'ONGOING_OR_OLD_CASE', 'UNKNOWN']:
            result = StageCandidates.model_validate({'language': LANGUAGE, 'stage': stage, 'sources': [{'passage': 0}], 'review_required': False})
            value = self.agents.case_stage(self.claim, result, self.indexed, self.raw).outputs['case_understanding.stage']
            self.assertEqual(value['stage'], stage)
            self.assertEqual(value['review_required'], stage == 'UNKNOWN')

    def test_approximate_date_and_unknown_party_name(self):
        value = FactCandidates.model_validate({'language': LANGUAGE, 'facts': [{'key': 'contact', 'proposition': 'Seller contact', 'category': 'CONTACT',
            'sources': [{'passage': 0}], 'date': {'expression': 'around September 2026', 'precision': 'APPROXIMATE'}}], 'incidents': []})
        output = self.agents.fact_timeline(self.claim, value, self.indexed, self.raw).outputs
        self.assertIsNone(output['facts']['F001']['date']['normalized'])
        parties = PartyCandidates.model_validate({'language': LANGUAGE, 'parties': [{'key': 'visitor', 'name': None, 'role': 'UNKNOWN_VISITOR', 'sources': [{'passage': 0}], 'fact_ids': ['F001'], 'review_required': True}]})
        output = self.agents.party_relationship(self.claim, parties, self.indexed, self.raw).outputs
        self.assertIsNone(output['parties']['P001']['name'])
        self.assertTrue(output['parties']['P001']['review_required'])

    def test_uploaded_support_and_contradiction_stay_unverified_and_separate(self):
        self.raw.update(evidence_ids=['E001'], evidence=[{'evidence_id': 'E001', 'extraction': {'status': 'COMPLETED'}}],
                        declared_evidence=[{'description': 'receipt'}], unavailable_evidence=[{'description': 'recording'}], unknown_evidence=[{'description': 'report'}])
        self.raw['provenance'].append({'source_id': 'UPLOAD_E001', 'evidence_id': 'E001', 'original_text': 'Seller contacted buyer.', 'extraction_status': 'COMPLETED', 'text_hash': 'test'})
        indexed = passages(self.raw)
        for relation, state in [('SUPPORTS', 'SUPPORTED_BY_UPLOADED_EVIDENCE'), ('CONTRADICTS', 'CONTRADICTED')]:
            result = EvidenceCandidates.model_validate({'language': LANGUAGE, 'links': [{'evidence_id': 'E001', 'fact_id': 'F001', 'relation': relation, 'sources': [{'passage': len(indexed)-1}]}]})
            output = self.agents.evidence_mapping(self.claim, result, indexed, self.raw).outputs['evidence_mapping']
            self.assertEqual(output['fact_support']['F001']['state'], state)
            self.assertFalse(output['links'][0]['verified'])
            self.assertEqual(output['uploaded_evidence_ids'], ['E001'])
            self.assertEqual(output['declared_evidence'], [{'description': 'receipt'}])
            self.assertEqual(output['unavailable_evidence'], [{'description': 'recording'}])
            self.assertEqual(output['unknown_evidence'], [{'description': 'report'}])

    def test_reworded_question_with_overlapping_facts_is_not_repeated(self):
        self.claim['inputs'].update({'facts': {'F001': {'certainty': 'STATED'}, 'F002': {'certainty': 'STATED'}},
            'human.CLARIFICATION': [{'topic': 'earlier wording', 'need': 'IDENTIFY_EVENT', 'fact_ids': ['F001'], 'response': 'UNKNOWN'}]})
        result = ClarificationCandidates.model_validate({'language': LANGUAGE, 'questions': [{'topic': 'changed wording', 'question': 'Tell us again?',
            'need': 'IDENTIFY_EVENT', 'fact_ids': ['F001', 'F002'], 'priority': 'HIGH', 'essential': True, 'response_kind': 'DETAIL',
            'affected': ['FACT_TIMELINE'], 'material_reason': 'related event'}]})
        output = self.agents.clarification(self.claim, result, self.indexed, self.raw)
        self.assertEqual(output.status, 'COMPLETED')
        self.assertEqual(output.outputs['clarification']['suggestions'], [])
        self.claim['inputs']['human.CLARIFICATION'] = []
        self.claim['inputs']['facts']['F002']['certainty'] = 'UNKNOWN'
        output = self.agents.clarification(self.claim, result, self.indexed, self.raw)
        self.assertEqual(output.status, 'COMPLETED')
        self.assertEqual(len(output.outputs['clarification']['suggestions']), 1)
