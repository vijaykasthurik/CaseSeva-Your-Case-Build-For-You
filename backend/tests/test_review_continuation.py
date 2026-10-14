"""Continuation against copied genuine request state; never writes the real DB."""
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


class CorrectionContinuationTests(unittest.TestCase):
    def setUp(self):
        root = Path('.localdev/phase4-authority-review')
        if not (root/'database.json').exists():
            self.skipTest('Genuine local review bundle unavailable')
        self.original_path = root/'database.json'
        self.original = self.original_path.read_bytes()
        data = json.loads(self.original)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name)/'copy.json'
        path.write_text(json.dumps({k:v for k,v in data.items() if k.startswith('legal_')}), encoding='utf-8')
        self.db = MockDatabaseAdapter(path)
        self.service = AuthorityReview(VerifiedCorpus(self.db))
        self.payload = json.loads((root/'record-1/external-request-correction/corrected-source-submission.json').read_text(encoding='utf-8'))
        self.head = '53fd4f1a3956c751ea8f270d161c6611c414f0e92d19af78eaed99c24a089e9d'
        self.receipt = '1e4dffb85d2b4e3b9cb99bf680990061'
        self.continue_only = runpy.run_path('scripts/record-authority-review.py')['continue_correction']
        self.posts = 0

    def call(self, path, body=None, *, operation):
        if body is not None:
            self.assertEqual(path, '/api/admin/authorities')  # No decision endpoint.
            self.posts += 1
            return self.service.submit(body, actor='isolated-test-submitter')
        return {'current_revision':self.service.corpus.get('cpa2019_s2_7')['version_id'],
                'versions':[v for v in self.db.list('legal_authority_versions') if v['source']['source_id']=='cpa2019_s2_7'],
                'reviews':[r for r in self.db.list('legal_authority_reviews') if r['source_id']=='cpa2019_s2_7'],
                'submissions':self.db.list('legal_review_submissions')}

    def execute(self, call=None, payload=None):
        self.continue_only(call or self.call, 'cpa2019_s2_7', self.head, self.receipt,
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
        self.assertEqual(self.original, self.original_path.read_bytes())

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
        self.assertNotEqual(self.service.corpus.get('cpa2019_s2_7')['version_id'], self.head)
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
        args = ['review','--source-id','cpa2019_s2_7','--revision',self.head,
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
