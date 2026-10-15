"""Fictional accounts/authorities exist only inside isolated test databases."""
import copy
import unittest
import runpy
from pathlib import Path
from unittest.mock import patch
from backend.tests import test_authority_review as support
from backend.tests.legal_test_support import authority, publish_reviewed


class RevisionRequestTests(unittest.TestCase):
    setUp = support.AuthorityReviewTests.setUp
    def pending(self):
        reviewed = publish_reviewed(self.corpus, authority())
        value = {k: v for k, v in reviewed.items() if k not in {'version_id', 'reason'}}
        value['version_note'] = 'Pending revision for test'
        return self.workflow.submit(value, actor='fixture-author')

    def request(self, pending):
        reviewer = self.db.get('users', 'test-verified-reviewer-advocate')
        return self.workflow.decide(pending['source_id'], pending['version_id'],
            reviewer=reviewer, decision='NEEDS_NEW_REVISION', note='Temporal metadata needs correction')

    def test_revision_request_persists_without_approving_and_preserves_history(self):
        pending = self.pending()
        old = copy.deepcopy(self.db.get('legal_authority_versions', pending['version_id']))
        with patch('backend.services.authority_review.utc_now', return_value='2026-10-13T01:02:03+00:00'):
            requested = self.request(pending)
        self.assertEqual(requested['review_state'], 'REVIEW_PENDING')
        self.assertEqual(requested['revision_status'], 'REVISION_REQUESTED')
        self.assertEqual(requested['verification'], 'PENDING')
        self.assertFalse(requested['source_reviewed'])
        receipt = self.db.get('legal_authority_reviews', requested['review_id'])
        self.assertEqual(receipt['decision'], 'NEEDS_NEW_REVISION')
        self.assertEqual(receipt['reviewer_id'], 'test-verified-reviewer-advocate')
        self.assertEqual(receipt['reviewed_at'], '2026-10-13T01:02:03+00:00')
        self.assertEqual(receipt['input_version'], pending['version_id'])
        self.assertEqual(self.db.get('legal_authority_versions', pending['version_id']), old)
        with self.assertRaises(ValueError):
            self.db.create('legal_authority_reviews', {**receipt, 'note': 'overwrite'})
        with self.assertRaises(ValueError):
            reviewer = self.db.get('users', 'test-verified-reviewer-advocate')
            self.workflow.decide(requested['source_id'], requested['version_id'], reviewer=reviewer, decision='REVIEWED_PRIMARY', note='Cannot approve requested revision')

    def test_corrected_revision_requires_fresh_independent_review(self):
        pending = self.pending()
        requested = self.request(pending)
        receipt = copy.deepcopy(self.db.get('legal_authority_reviews', requested['review_id']))
        value = {k: v for k, v in requested.items() if k not in {'version_id', 'reason'}}
        with self.assertRaises(ValueError):
            self.workflow.submit(value, actor='test-verified-reviewer-advocate')
        value['revision_metadata'] = {'correction': 'Fictional temporal support note'}
        corrected = self.workflow.submit(value, actor='test-verified-reviewer-advocate')
        self.assertNotEqual(corrected['version_id'], requested['version_id'])
        self.assertEqual(corrected['parent_revision'], requested['version_id'])
        self.assertEqual(corrected['revision_request_id'], receipt['id'])
        self.assertEqual(corrected['review_state'], 'REVIEW_PENDING')
        self.assertIsNone(corrected['reviewed_by'])
        self.assertIsNone(corrected['reviewed_at'])
        self.assertIsNone(corrected['review_id'])
        self.assertEqual(corrected['revision_status'], 'NONE')
        for record in (pending, requested, corrected):
            self.assertFalse(self.corpus.validate_source({k: v for k, v in record.items() if k not in {'version_id', 'reason'}})[0])
        reviewer = self.db.get('users', 'test-verified-reviewer-advocate')
        with self.assertRaises(PermissionError):
            self.workflow.decide(corrected['source_id'], corrected['version_id'], reviewer=reviewer, decision='REVIEWED_PRIMARY', note='Self review')
        independent = self.db.create('users', {'id': 'second-test-reviewer-advocate',
            'role': 'advocate', 'verification_status': 'VERIFIED',
            'capabilities': ['LEGAL_AUTHORITY_REVIEW'], 'permissions': ['LEGAL_AUTHORITY_REVIEW']})
        approved = self.workflow.decide(corrected['source_id'], corrected['version_id'], reviewer=independent, decision='REVIEWED_PRIMARY', note='Independent fictional fixture review')
        self.assertEqual(approved['verification'], 'VERIFIED')
        self.assertNotEqual(approved['review_id'], receipt['id'])
        self.assertEqual(self.db.get('legal_authority_reviews', receipt['id']), receipt)
        self.assertFalse(self.corpus.validate_source({k: v for k, v in requested.items() if k not in {'version_id', 'reason'}})[0])

    def test_inactive_draft_does_not_move_head_or_allow_review(self):
        pending = self.pending()
        value = {k: v for k, v in pending.items() if k not in {'version_id', 'reason'}}
        value['version_note'] = 'Prepared correction, not submitted'
        draft = self.workflow.submit(value, actor='automated-draft-preparer', activate=False)
        self.assertNotEqual(draft['version_id'], pending['version_id'])
        self.assertEqual(self.corpus.get(pending['source_id'])['version_id'], pending['version_id'])
        self.assertIsNotNone(self.db.get('legal_authority_versions', draft['version_id']))
        self.assertIsNone(self.db.get('legal_review_submissions', draft['version_id']))
        with self.assertRaises(ValueError):
            reviewer = self.db.get('users', 'test-verified-reviewer-advocate')
            self.workflow.decide(draft['source_id'], draft['version_id'], reviewer=reviewer, decision='REVIEWED_PRIMARY', note='Inactive')
        activated = self.workflow.submit(value, actor='test-verified-reviewer-advocate')
        self.assertEqual(activated['version_id'], draft['version_id'])
        self.assertEqual(self.db.get('legal_review_submissions', activated['version_id'])['actor'], 'test-verified-reviewer-advocate')
        with self.assertRaises(PermissionError):
            self.workflow.decide(activated['source_id'], activated['version_id'], reviewer=self.db.get('users', 'test-verified-reviewer-advocate'), decision='REVIEWED_PRIMARY', note='No preparer bypass')

    def test_http_revision_request_uses_existing_authenticated_external_account(self):
        from backend.tests.helpers import test_app, client_account
        from fastapi.testclient import TestClient
        temp, identity_app, identity_client = test_app()
        self.addCleanup(temp.cleanup)
        user, headers = client_account(identity_client, 'real-test-session')
        identity_db = identity_app.state.adapters.database
        identity_db.update('users', user['id'], {
            'role': 'advocate',
            'verification_status': 'VERIFIED',
            'capabilities': ['LEGAL_AUTHORITY_REVIEW'],
            'permissions': ['LEGAL_AUTHORITY_REVIEW'],
        })  # Isolated test fixture only — grant authority review to this advocate.
        pending = self.pending()
        factory = runpy.run_path(str(Path('scripts/serve-authority-review.py')))['create_app']
        app = factory(identity_db.path, self.db.path)
        client = TestClient(app)
        url = '/api/admin/authorities/fixture_act/review'
        body = {'expected_version': pending['version_id'], 'decision': 'NEEDS_NEW_REVISION', 'note': 'Real session, fictional test records'}
        with patch.dict('os.environ', {'ADMIN_TOKEN': ''}):
            self.assertEqual(client.post(url, json=body).status_code, 401)
            for field in ('reviewed_by', 'reviewed_at', 'reviewer_id'):
                self.assertEqual(client.post(url, headers=headers, json={**body, field: 'forged'}).status_code, 422)
            result = client.post(url, headers=headers, json=body)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['reviewed_by'], user['id'])
            self.assertEqual(result.json()['revision_status'], 'REVISION_REQUESTED')
            history = client.get('/api/admin/authorities/fixture_act/history', headers=headers)
            self.assertEqual(history.status_code, 200)
            self.assertTrue(any(r['decision'] == 'NEEDS_NEW_REVISION' for r in history.json()['reviews']))
            self.assertEqual(client.post(url, headers=headers, json=body).status_code, 409)
            self.assertIsNone(self.db.get('users', user['id']))
            self.assertEqual(client.post('/api/auth/signup', json={}).status_code, 404)
            identity_db.update('users', user['id'], {'role': 'client'})
            self.assertEqual(client.get('/api/admin/authorities/fixture_act/history', headers=headers).status_code, 403)

    def test_existing_preparation_attribution_cannot_bypass_self_review(self):
        pending = self.pending()
        value = {k: v for k, v in pending.items() if k not in {'version_id', 'reason'}}
        value['version_note'] = 'Old preparation attribution fixture'
        draft = self.workflow.submit(value, actor='preparer', activate=False)
        self.db.create('legal_review_submissions', {'id': draft['version_id'], 'actor': 'preparer', 'source_id': draft['source_id']})
        with self.assertRaisesRegex(ValueError, 'another submitter'):
            self.workflow.submit(value, actor='test-verified-reviewer-advocate')
        self.assertEqual(self.corpus.get(pending['source_id'])['version_id'], pending['version_id'])

    def test_optional_defaults_preserve_existing_receipt_signatures(self):
        from backend.services.authority_review import authority_digest, REVIEW_FIELDS
        from backend.services.case_blackboard import digest
        from backend.models.legal_foundation import LegalSource
        value = LegalSource.model_validate(authority()).model_dump()
        legacy = {k: v for k, v in value.items() if k not in REVIEW_FIELDS | {'parent_revision', 'revision_request_id', 'revision_metadata'}}
        self.assertEqual(authority_digest(value), digest(legacy))
        value['revision_metadata'] = {'correction': 'fixture'}
        self.assertNotEqual(authority_digest(value), digest(legacy))

    def test_review_server_refuses_to_provision_missing_admin(self):
        factory = runpy.run_path(str(Path('scripts/serve-authority-review.py')))['create_app']
        before = self.db.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'No existing'):
            factory(self.db.path, self.db.path)
        self.assertEqual(self.db.path.read_bytes(), before)
        missing = self.db.path.parent / 'missing.json'
        with self.assertRaises(ValueError):
            factory(missing, self.db.path)
        self.assertFalse(missing.exists())


