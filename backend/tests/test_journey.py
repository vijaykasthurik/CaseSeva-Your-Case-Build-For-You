import os
import unittest
from unittest.mock import patch
from backend.tests import test_sharing_overview as sharing_tests
from backend.routes.journey import router as journey
from backend.routes.retention import router as retention


class JourneyTests(unittest.TestCase):
    accepted = sharing_tests.SharingTests.accepted
    grant = sharing_tests.SharingTests.grant
    tearDown = sharing_tests.SharingTests.tearDown

    def setUp(self):
        sharing_tests.SharingTests.setUp(self)
        self.app.include_router(journey)
        self.app.include_router(retention)
        self.accepted()
        self.grant()

    def test_private_notes_and_notifications_are_isolated(self):
        url = f'/api/advocate/cases/{self.id}/notes'
        self.assertEqual(self.client.post(url, headers=self.headers, json={'text': 'PRIVATE STRATEGY'}).status_code, 403)
        self.assertEqual(self.client.post(url, headers=self.access, json={'text': 'PRIVATE STRATEGY'}).status_code, 200)
        self.client.post(url, headers=self.access, json={'text': 'Please bring your receipt', 'visibility': 'SHARED_WITH_CLIENT'})
        client_case = self.client.get(f'/api/cases/{self.id}', headers=self.headers)
        self.assertNotIn('PRIVATE STRATEGY', client_case.text)
        self.assertIn('Please bring your receipt', client_case.text)
        notifications = self.client.get('/api/notifications', headers=self.headers).json()['notifications']
        self.assertTrue(all(item['user_id'] == self.user['id'] for item in notifications))
        self.assertNotIn('PRIVATE STRATEGY', str(notifications))

    def test_information_answer_invalidates_foundation_and_documents(self):
        url = f'/api/advocate/cases/{self.id}/information-requests'
        item = self.client.post(url, headers=self.access, json={'question': 'When did this happen?'}).json()['request']
        self.app.state.adapters.database.update('cases', self.id, {'document_version': 1})
        answer = self.client.post(f'/api/cases/{self.id}/information-requests/{item["id"]}/answer', headers=self.headers, json={'response': 'I do not know the exact date.'})
        self.assertEqual(answer.status_code, 200)
        case = self.app.state.adapters.database.get('cases', self.id)
        self.assertEqual(case['engines']['1']['status'], 'STALE')
        self.assertTrue(case['documents_outdated'])
        self.assertEqual(case['information_requests'][0]['response'], 'I do not know the exact date.')

    def test_filing_requires_reviewed_documents_and_labels_advocate_source(self):
        url = f'/api/advocate/cases/{self.id}/filing'
        body = {'status': 'READY_TO_FILE', 'explanation': 'Reviewed the current documents.'}
        self.assertEqual(self.client.post(url, headers=self.headers, json=body).status_code, 403)
        self.assertEqual(self.client.post(url, headers=self.access, json=body).status_code, 409)
        self.app.state.adapters.database.update('cases', self.id, {'status': 'DOCUMENTS_READY', 'documents_outdated': False})
        self.assertEqual(self.client.post(url, headers=self.access, json=body).status_code, 200)
        body.update({'status': 'FILED', 'source_label': 'Official Court Status'})
        update = self.client.post(url, headers=self.access, json=body).json()['update']
        self.assertEqual(update['source_label'], 'Advocate Update')
        self.assertEqual(update['filing_number'], '')

    def test_deletion_revokes_access_and_preserves_restricted_audit(self):
        with patch.dict(os.environ, {'CASE_RETENTION_DAYS': '0'}):
            response = self.client.post(f'/api/cases/{self.id}/deletion-request', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['request']['status'], 'DELETED')
        self.assertEqual(self.client.get(f'/api/advocate/cases/{self.id}', headers=self.access).status_code, 403)
        case = self.app.state.adapters.database.get('cases', self.id)
        self.assertEqual(case['client_story'], '')
        self.assertEqual(len(self.app.state.adapters.database.list('retained_case_audit')), 1)

    def test_retention_hold_records_request_without_erasing_content(self):
        self.app.state.adapters.database.update('cases', self.id, {'legal_hold': True})
        with patch.dict(os.environ, {'CASE_RETENTION_DAYS': '0'}):
            response = self.client.post(f'/api/cases/{self.id}/deletion-request', headers=self.headers)
        self.assertEqual(response.json()['request']['status'], 'LEGAL_HOLD')
        self.assertEqual(self.app.state.adapters.database.get('cases', self.id)['client_story'], 'Private client story')
