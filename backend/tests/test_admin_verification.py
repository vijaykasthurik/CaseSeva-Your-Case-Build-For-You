import os
import unittest
from unittest.mock import patch
from backend.tests.helpers import test_app, client_account
from backend.routes.advocates import router
from backend.models.case import utc_now


class AdminVerificationTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app, self.client = test_app()
        self.app.include_router(router)
        self.user, self.headers = client_account(self.client)
        self.admin, self.admin_headers = client_account(self.client, 'operator')
        self.app.state.adapters.database.update('users', self.admin['id'], {'role': 'admin'})
        self.id = 'seed-pending-advocate'
        self.app.state.adapters.database.update('users', self.id, {'verification_documents': [{'filename': 'test.pdf'}]})
        self.url = f'/api/admin/advocates/{self.id}/verification'

    def tearDown(self): self.directory.cleanup()

    def test_client_cannot_verify_even_with_admin_secret(self):
        with patch.dict(os.environ, {'ADMIN_TOKEN': 'test-secret'}):
            self.assertEqual(self.client.post(self.url, headers={**self.headers, 'X-Admin-Token': 'test-secret'}, json={'status': 'VERIFIED', 'reason': 'Unauthorized'}).status_code, 403)

    def test_verification_requires_official_record_and_reviewer_and_timestamp(self):
        with patch.dict(os.environ, {'ADMIN_TOKEN': '', 'ADMIN_VERIFICATION_HOSTS': 'official.test'}):
            self.assertEqual(self.client.post(self.url, headers=self.admin_headers, json={'status': 'VERIFIED', 'reason': 'Checked'}).status_code, 422)
            payload = {'status': 'VERIFIED', 'reason': 'Synthetic official-record review test', 'official_source_url': 'https://official.test/record', 'official_record_reference': 'TEST-ONLY', 'reviewer_id': self.admin['id'], 'reviewed_at': utc_now()}
            response = self.client.post(self.url, headers=self.admin_headers, json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            audit = self.app.state.adapters.database.list('verification_audit')[0]
            self.assertEqual(audit['reviewer_id'], self.admin['id'])
            self.assertEqual(audit['official_record_reference'], 'TEST-ONLY')
            self.assertEqual(len(self.app.state.adapters.database.list('notifications')), 1)
