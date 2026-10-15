"""Continuation against synthetic request state; never reads the real review bundle."""
import contextlib
import copy
import io
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.services.authority_review import AuthorityReview
from backend.services.verified_corpus import VerifiedCorpus
from backend.models.legal_foundation import LegalSource
from backend.tests.legal_test_support import authority, test_knowledge


class CorrectionContinuationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = MockDatabaseAdapter(Path(temp.name) / 'synthetic.json')
        self.service = AuthorityReview(VerifiedCorpus(self.db, test_knowledge()))
        reviewer = self.db.create('users', {'id': 'synthetic-reviewer', 'role': 'advocate',
            'verification_status': 'VERIFIED', 'capabilities': ['LEGAL_AUTHORITY_REVIEW'],
            'permissions': ['LEGAL_AUTHORITY_REVIEW']})
        value = LegalSource.model_validate(authority(ingestion_id='synthetic-ingestion')).model_dump()
        self.db.create('legal_ingestion_requests', {'id': value['ingestion_id'], 'state': 'PARSED',
            **{k: value[k] for k in ('registry_id', 'official_url', 'final_url', 'retrieved_at', 'raw_hash', 'content_hash', 'official_text')}})
        pending = self.service.submit(value, actor='synthetic-submitter')
        requested = self.service.decide('fixture_act', pending['version_id'], reviewer=reviewer,
            decision='NEEDS_NEW_REVISION', note='Synthetic metadata correction')
        self.head, self.receipt = requested['version_id'], requested['review_id']
        excluded = {'version_id', 'reason', 'reviewed_by', 'reviewed_at', 'review_id',
                    'revision_status', 'parent_revision', 'revision_request_id'}
        self.payload = {k: v for k, v in requested.items() if k not in excluded}
        self.payload['revision_metadata'] = {'correction': 'Synthetic metadata only'}
        self.continue_only = runpy.run_path('scripts/record-authority-review.py')['continue_correction']
        self.posts = 0

    def call(self, path, body=None, *, operation):
        if body is not None:
            self.assertEqual(path, '/api/admin/authorities')  # No decision endpoint.
            self.posts += 1
            return self.service.submit(body, actor='isolated-test-submitter')
        return {'current_revision':self.service.corpus.get('fixture_act')['version_id'],
                'versions':[v for v in self.db.list('legal_authority_versions') if v['source']['source_id']=='fixture_act'],
                'reviews':[r for r in self.db.list('legal_authority_reviews') if r['source_id']=='fixture_act'],
                'submissions':self.db.list('legal_review_submissions')}

    def execute(self, call=None, payload=None):
        self.continue_only(call or self.call, 'fixture_act', self.head, self.receipt,
                 self.payload if payload is None else payload)

    def test_exact_request_state_creates_only_pending_revision_and_refuses_replay(self):
        reviews = copy.deepcopy(self.db.list('legal_authority_reviews'))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.execute()
        result = json.loads(output.getvalue())
        self.assertEqual(result['parent_revision'], self.head)
        self.assertEqual(result['revision_request_id'], self.receipt)
        self.assertFalse(result['approved'])
        self.assertEqual(result['verification'], 'PENDING')
        self.assertEqual(reviews, self.db.list('legal_authority_reviews'))
        with self.assertRaises(SystemExit): self.execute()
        self.assertEqual(self.posts, 1)

    def test_rejects_lineage_payload_and_changed_text_without_post(self):
        for key,value in [('reviewed_by','forged'),('parent_revision',self.head),('quote','changed')]:
            payload = {**self.payload,key:value}
            with self.assertRaises(SystemExit): self.execute(payload=payload)
        self.assertEqual(self.posts, 0)

    def test_partial_write_failure_never_retries_and_receipt_remains(self):
        def fail_after_write(path, body=None, *, operation):
            result = self.call(path, body, operation=operation)
            if body is not None: raise RuntimeError('simulated lost response')
            return result
        reviews = self.db.list('legal_authority_reviews')
        with self.assertRaises(RuntimeError): self.execute(call=fail_after_write)
        self.assertEqual(self.posts, 1)
        self.assertNotEqual(self.service.corpus.get('fixture_act')['version_id'], self.head)
        self.assertEqual(reviews,self.db.list('legal_authority_reviews'))
        with self.assertRaises(SystemExit): self.execute()
        self.assertEqual(self.posts,1)

    def test_cli_prompts_locally_and_never_posts_review(self):
        main = runpy.run_path('scripts/record-authority-review.py')['main']
        requests = []
        def http(request, timeout):
            path = request.full_url.removeprefix('http://127.0.0.1:8012')
            requests.append(path)
            body = json.loads(request.data) if request.data else None
            if path.endswith('/login'):
                self.assertEqual(body['email'], 'fixture@example.test')
                result = {'session_token':'fixture-session-secret'}
            elif path.endswith('/me'): result = {'user':{'id':'fixture-admin'}}
            elif path.endswith('/logout'): result = {}
            else: result = self.call(path, body, operation='test')
            return io.BytesIO(json.dumps(result).encode())
        payload = Path(self.temp_payload_path())
        payload.write_text(json.dumps(self.payload), encoding='utf-8')
        args = ['review','--source-id','fixture_act','--revision',self.head,
                '--submit-correction-only','--existing-receipt',self.receipt,
                '--corrected-source-file',str(payload)]
        with patch.dict(main.__globals__,{'urlopen':http}), patch('sys.argv',args), patch('sys.stdin.isatty',return_value=True), patch('sys.stderr.isatty',return_value=True), patch('builtins.input',return_value='fixture@example.test'), patch('getpass.getpass',return_value='fixture-password-secret'), contextlib.redirect_stdout(io.StringIO()) as output:
            main()
        self.assertEqual(self.posts,1)
        self.assertFalse(any(p.endswith('/review') for p in requests))
        self.assertEqual(requests[-1],'/api/auth/logout')
        self.assertNotIn('fixture-password-secret',output.getvalue())
        self.assertNotIn('fixture-session-secret',output.getvalue())

    def temp_payload_path(self):
        return self.db.path.parent/'payload.json'
