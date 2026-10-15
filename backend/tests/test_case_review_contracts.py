"""Case-review and future-engine contracts only; no downstream job execution."""
import copy
import unittest
from unittest.mock import patch
from backend.tests import test_review as review_tests
from backend.services.review_contracts import reviewed_engine1_current, ENGINE2_NOT_RUN_DISCLOSURE
from backend.services.engine3 import approved_content


class CaseReviewContractTests(unittest.TestCase):
    setUp = review_tests.ReviewTests.setUp
    tearDown = review_tests.ReviewTests.tearDown
    accepted = review_tests.ReviewTests.accepted
    grant = review_tests.ReviewTests.grant
    def test_future_engine_eligibility_requires_current_reviewed_e1_not_e2(self):
        case = {'case_file': {'version': 3, 'input_version': 1}, 'input_version': 1,
                'advocate_approved_case_file_version': 3, 'engines': {'1': {'status': 'COMPLETE'}}}
        self.assertTrue(reviewed_engine1_current(case))
        self.assertEqual(approved_content(case)['argument_analysis_note'], ENGINE2_NOT_RUN_DISCLOSURE)
        for changes in ({'case_file': {}}, {'advocate_approved_case_file_version': 2},
                        {'input_version': 2}, {'engines': {'1': {'status': 'STALE'}}},
                        {'case_file': {'version': 3, 'kind': 'SOURCE_VERIFIED_ENGINE1', 'input_version': 1}, 'legal_case_file_current': False}):
            self.assertFalse(reviewed_engine1_current({**case, **changes}))
        case.update(engine2={'overview_ready': True}, engine2_stale=True)
        self.assertTrue(reviewed_engine1_current(case))
        self.assertNotIn('argument_results', approved_content(case))

    def test_evidence_original_cannot_be_overwritten(self):
        db = self.app.state.adapters.database
        grant = db.list('case_grants')[0]
        db.update('case_grants', grant['id'], {'scopes': ['case_file', 'evidence'], 'evidence_ids': ['E001']})
        db.update('cases', self.id, {'evidence': [{'evidence_id': 'E001', 'filename': 'synthetic.txt', 'storage_key': 'original'}]})
        before = copy.deepcopy(db.get('cases', self.id)['evidence'])
        response = self.client.post(f'/api/advocate/cases/{self.id}/review', headers=self.access,
            json={'kind': 'evidence', 'target_id': 'E001', 'action': 'edit',
                  'value': {'storage_key': 'replacement'}, 'reason': 'test'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(db.get('cases', self.id)['evidence'], before)

    def test_correction_history_retains_ai_and_both_human_versions(self):
        db = self.app.state.adapters.database
        old = copy.deepcopy(db.get('cases', self.id)['case_file'])
        for text in ('First correction', 'Second correction'):
            response = self.client.post(f'/api/advocate/cases/{self.id}/review', headers=self.access,
                json={'kind': 'fact', 'target_id': 'F001', 'action': 'edit', 'value': {'text': text}, 'reason': 'Checked record'})
            self.assertEqual(response.status_code, 200)
        case = db.get('cases', self.id)
        history = case['professional_overrides']
        self.assertEqual(history[0]['previous']['text'], old['facts'][0]['text'])
        self.assertEqual(history[-1]['previous']['text'], 'First correction')
        self.assertEqual(case['case_file']['facts'][0]['text'], 'Second correction')
        self.assertEqual(case['case_file']['version'], old['version'] + 2)
        self.assertTrue(all(v['timestamp'] and v['advocate_id'] and v['reason'] for v in history))
    def test_final_review_can_skip_stale_optional_engine2(self):
        db = self.app.state.adapters.database
        case = db.get('cases', self.id)
        file = case['case_file']
        approvals = [f"fact:{v['fact_id']}" for v in file.get('facts', [])]
        approvals += [f"provision:{v['provision_id']}" for v in file.get('applicable_law', [])]
        db.update('cases', self.id, {'status': 'ADVOCATE_REVIEW', 'advocate_approved_items': approvals,
            'engine2': {'overview_ready': True}, 'engine2_stale': True})
        response = self.client.post(f'/api/advocate/cases/{self.id}/approve', headers=self.access)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.get('cases', self.id)['advocate_approved_case_file_version'], file['version'])
