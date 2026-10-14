import unittest
from unittest.mock import patch
from backend.tests.helpers import test_app, client_account
from backend.routes.advocates import router as advocates
from backend.routes.sharing import router as sharing
from backend.routes.guest_claims import router as claims
from backend.services.ingestion import run_ingestion


class EntryRouteTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app, self.client = test_app()
        for router in (advocates, sharing, claims): self.app.include_router(router)
        self.user, self.headers = client_account(self.client)
        login = self.client.post('/api/auth/login', json={'email': 'demo.advocate@caseseva.local', 'password': 'DemoPassword123'}).json()
        self.advocate = {'Authorization': 'Bearer ' + login['session_token']}

    def tearDown(self): self.directory.cleanup()

    def walkin(self):
        response = self.client.post('/api/cases', headers=self.advocate, json={'origin': 'ADVOCATE_WALK_IN', 'client_name': 'Walk-in Client', 'client_email': self.user['email'], 'consent': True})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['case']['case_id']

    def test_direct_path_prepares_input_without_any_engine(self):
        case_id = self.client.post('/api/cases', headers=self.headers).json()['case']['case_id']
        self.client.patch('/api/cases/' + case_id, headers=self.headers, json={'stage': 'NEW_CONSULTATION', 'client_story': 'My account of what happened'})
        with patch('backend.services.jobs.dispatch') as dispatch:
            response = self.client.post(f'/api/cases/{case_id}/submit', headers=self.headers, json={'path': 'legal_help'})
        self.assertEqual(response.status_code, 200)
        dispatch.assert_called_once_with(self.app, 0, case_id)
        with patch('backend.services.engine1.run_engine1', side_effect=AssertionError('No engine on direct route')):
            run_ingestion(self.app, case_id)
        case = self.app.state.adapters.database.get('cases', case_id)
        self.assertEqual(case['origin'], 'CITIZEN_DIRECT_ADVOCATE')
        self.assertNotIn('case_file', case)
        self.assertEqual(case['raw_package']['original_story'], 'My account of what happened')
        self.assertEqual(self.client.post(f'/api/cases/{case_id}/request-advocate', headers=self.headers, json={'advocate_id': 'seed-verified-advocate'}).status_code, 200)

    def test_walkin_creator_access_requires_verification_and_recorded_consent(self):
        self.assertEqual(self.client.post('/api/cases', headers=self.advocate, json={'origin': 'ADVOCATE_WALK_IN', 'client_name': 'Client'}).status_code, 422)
        case_id = self.walkin()
        self.assertEqual(self.client.get(f'/api/advocate/cases/{case_id}', headers=self.advocate).status_code, 200)
        self.assertEqual(self.client.get(f'/api/cases/{case_id}', headers=self.headers).status_code, 403)
        self.app.state.adapters.database.update('walkin_consents', case_id, {'revoked_at': 'now'})
        self.assertEqual(self.client.get(f'/api/advocate/cases/{case_id}', headers=self.advocate).status_code, 403)

    def test_walkin_submission_prepares_input_then_runs_foundation(self):
        case_id = self.walkin()
        self.client.patch(f'/api/cases/{case_id}', headers=self.advocate, json={'stage': 'NEW_CONSULTATION', 'client_story': 'The client account'})
        with patch('backend.services.jobs.dispatch') as dispatch:
            response = self.client.post(f'/api/cases/{case_id}/submit', headers=self.advocate, json={'path': 'legal_help'})
        self.assertEqual(response.status_code, 200)
        dispatch.assert_called_once_with(self.app, 0, case_id, understand=True)

    def test_guest_claim_links_same_case_and_does_not_expose_professional_outputs(self):
        case_id = self.walkin()
        self.app.state.adapters.database.update('cases', case_id, {'engine2': {'private': 'INTERNAL STRATEGY'}})
        claim = self.client.post('/api/guest-claims', headers=self.headers, json={'case_id': case_id}).json()
        response = self.client.post('/api/guest-claims/confirm', headers=self.headers, json={'claim_id': claim['claim_id'], 'code': claim['development_code']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['case_id'], case_id)
        self.assertEqual(len(self.app.state.adapters.database.list('cases')), 1)
        response = self.client.get(f'/api/cases/{case_id}', headers=self.headers)
        self.assertNotIn('INTERNAL STRATEGY', response.text)
        self.assertEqual(self.client.get(f'/api/advocate/cases/{case_id}', headers=self.advocate).status_code, 403)
        self.assertEqual(self.client.post('/api/guest-claims/confirm', headers=self.headers, json={'claim_id': claim['claim_id'], 'code': claim['development_code']}).status_code, 403)

    def test_disabled_email_does_not_follow_legacy_processing_mode(self):
        case_id = self.walkin()
        self.app.state.adapters.email_provider = 'disabled'
        for mode in ('mock', 'mongodb', 'real'):
            self.app.state.adapters.mode = mode
            with patch('boto3.client', side_effect=AssertionError('No implicit SES')):
                response = self.client.post('/api/guest-claims', headers=self.headers, json={'case_id': case_id})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('development_code', response.json())
        self.assertEqual(self.app.state.adapters.database.list('guest_claims'), [])
