import unittest
from unittest.mock import patch
from backend.tests.helpers import test_app, client_account
from backend.routes.engines import router
from backend.services.overview import client_case


class LegalPermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp, self.app, self.client = test_app()
        self.addCleanup(self.temp.cleanup)
        self.app.include_router(router)
        self.owner, self.headers = client_account(self.client, 'legal-owner')
        _, self.other = client_account(self.client, 'legal-other')
        self.db = self.app.state.adapters.database
        self.cid = self.client.post('/api/cases', headers=self.headers).json()['case']['case_id']
        self.db.update('cases', self.cid, {'engine1_execution': 'ORCHESTRATED_CORE_V1', 'status': 'CASE_UNDERSTANDING_READY'})
        self.url = f'/api/cases/{self.cid}/legal-foundation'

    def test_owner_access_and_atomic_duplicate_rejection(self):
        with patch('backend.routes.engines.dispatch') as dispatch:
            self.assertEqual(self.client.post(self.url).status_code, 401)
            self.assertEqual(self.client.post(self.url, headers=self.other).status_code, 403)
            self.assertEqual(self.client.post(self.url, headers=self.headers).status_code, 200)
            self.assertEqual(self.client.post(f'/api/cases/{self.cid}/input/retry', headers=self.headers).status_code, 409)
            self.assertEqual(self.client.post(self.url, headers=self.headers).status_code, 409)
            self.assertEqual(dispatch.call_count, 1)

    def test_legacy_case_cannot_switch(self):
        self.db.update('cases', self.cid, {'case_file': {'existing': True}})
        with patch('backend.routes.engines.dispatch') as dispatch:
            self.assertEqual(self.client.post(self.url, headers=self.headers).status_code, 409)
            dispatch.assert_not_called()

    def test_dispatch_diagnostics_never_reach_citizen(self):
        with patch('backend.routes.engines.dispatch', side_effect=RuntimeError('PRIVATE_AWS_CONFIG')):
            response = self.client.post(self.url, headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('PRIVATE_', response.text)
        case = client_case(self.db.get('cases', self.cid))
        self.assertEqual(case['legal_foundation_status'], 'PENDING_SOURCE')
        self.assertEqual(case['status'], 'LEGAL_FOUNDATION_REVIEW_REQUIRED')
        self.assertNotIn('PRIVATE_', str(case))

    def test_stale_legal_file_and_internal_state_hidden(self):
        self.db.update('cases', self.cid, {'legal_foundation_requested': True, 'legal_case_file_current': False,
            'case_file': {'kind': 'SOURCE_VERIFIED_ENGINE1', 'applicable_law': [{'verification_status': 'VERIFIED', 'title': 'OUTDATED_LAW'}]},
            'legal_foundation_snapshot': {'private': 'ADVOCATE_INTERNAL_OUTPUT_B'}})
        case = client_case(self.db.get('cases', self.cid))
        self.assertFalse(case['engine1_available'])
        self.assertNotIn('OUTDATED_LAW', str(case))
        self.assertNotIn('ADVOCATE_INTERNAL_OUTPUT_B', str(case))

    def test_engine2_consumes_pending_source_case_factually(self):
        self.db.update('cases', self.cid, {'legal_foundation_requested': True, 'status': 'LEGAL_CORPUS_NOT_READY',
                                         'case_file': {'kind': 'SOURCE_VERIFIED_ENGINE1', 'version': 1}})
        with patch('backend.routes.engines.dispatch') as dispatch:
            result = self.client.post(f'/api/cases/{self.cid}/engine2', headers=self.headers, json={'run': True})
            self.assertEqual(result.status_code, 200)
            dispatch.assert_called_once()
        self.db.update('cases', self.cid, {'case_file': None, 'canonical_case_file': None})
        with patch('backend.routes.engines.dispatch') as dispatch:
            result = self.client.post(f'/api/cases/{self.cid}/engine2', headers=self.headers, json={'run': True})
            self.assertEqual(result.status_code, 409)
            dispatch.assert_not_called()
