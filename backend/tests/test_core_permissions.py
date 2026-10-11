import unittest
from unittest.mock import patch
from backend.tests.helpers import test_app, client_account
from backend.tests.core_test_support import CoreTestModel, STORY
from backend.routes.engines import router
from backend.services.core_workflow import run_core
from backend.services.case_blackboard import CaseBlackboard


class CorePermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp, self.app, self.client = test_app()
        self.app.include_router(router)
        self.user, self.headers = client_account(self.client, 'core-owner')
        _, self.other = client_account(self.client, 'core-other')
        self.db = self.app.state.adapters.database
        self.cid = self.client.post('/api/cases', headers=self.headers).json()['case']['case_id']
        self.db.update('cases', self.cid, {'stage': 'NEW_CONSULTATION', 'stage_details': {}, 'client_story': STORY})
        self.url = f'/api/cases/{self.cid}/core-understanding'

    def tearDown(self):
        self.temp.cleanup()

    def test_owner_only_atomic_path_selection_and_duplicate_rejection(self):
        with patch('backend.routes.engines.dispatch') as dispatch:
            self.assertEqual(self.client.post(self.url).status_code, 401)
            self.assertEqual(self.client.post(self.url, headers=self.other).status_code, 403)
            self.assertEqual(self.client.post(self.url, headers=self.headers).status_code, 200)
            self.assertEqual(self.client.post(self.url, headers=self.headers).status_code, 409)
            self.assertEqual(dispatch.call_count, 1)

    def test_completed_legacy_case_cannot_switch_pipeline(self):
        self.db.update('cases', self.cid, {'case_file': {'existing': True}, 'status': 'ENGINE1_DONE'})
        with patch('backend.routes.engines.dispatch') as dispatch:
            self.assertEqual(self.client.post(self.url, headers=self.headers).status_code, 409)
            dispatch.assert_not_called()

    def test_dispatch_error_is_safe_and_saved(self):
        with patch('backend.routes.engines.dispatch', side_effect=RuntimeError('PRIVATE_AWS_ACCESS_CONFIG')):
            response = self.client.post(self.url, headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('PRIVATE_', response.text)
        self.assertEqual(self.db.get('cases', self.cid)['status'], 'REVIEW_REQUIRED')

    def test_citizen_overview_exposes_only_safe_core_status(self):
        with patch('backend.routes.engines.dispatch'):
            self.client.post(self.url, headers=self.headers)
        self.app.state.adapters.llm = CoreTestModel()
        self.app.state.adapters.phase3_test_double = True
        run_core(self.app, self.cid)
        CaseBlackboard(self.db).append_change(self.cid, {'professional.private': 'ADVOCATE_INTERNAL_OUTPUT_B'}, actor='system', reason='permission fixture')
        response = self.client.get(f'/api/cases/{self.cid}/client-case-overview', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('ADVOCATE_INTERNAL_OUTPUT_B', response.text)
        self.assertNotIn('understanding_snapshot', response.text)
        self.assertNotIn('source_refs', response.text)
        self.assertIn('PENDING', response.text)
        self.assertIn('READY', response.text)
