"""No real login or review retries. Test copies use fictional local identities."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from fastapi.testclient import TestClient
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.adapters.mock.auth import MockAuthAdapter


class ReviewClientDiagnosticTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.script = runpy.run_path('scripts/record-authority-review.py')

    def error(self, body, status=422):
        return HTTPError('http://127.0.0.1/unused', status, 'failure', {}, io.BytesIO(json.dumps(body).encode()))

    def test_diagnostics_allowlist_excludes_echoed_secrets_and_unknown_fields(self):
        secret = 'FICTIONAL-SECRET-MUST-NOT-APPEAR'
        body = {'detail':[{'type':'missing','loc':['body','note'], 'msg':secret, 'input':{'password':secret}, 'ctx':{'error':secret}},
            {'type':secret,'loc':['body',secret], 'msg':secret}], 'password':secret,'cookies':secret}
        out = self.script['safe_http_failure'](self.error(body), 'record_review_decision')
        self.assertNotIn(secret,out)
        self.assertEqual(json.loads(out)['detail'][0]['loc'],['body','note'])
        self.assertEqual(json.loads(out)['status'],422)
        for detail in (secret, {'message':secret,'fields':{'password':secret}}, {'message':{'password':secret}}):
            self.assertNotIn(secret,self.script['safe_http_failure'](self.error({'detail':detail}), 'login'))

    def test_login_field_error_remains_structured_without_echoing_input(self):
        from backend.routes.auth import LoginBody, login
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as result:
            login(LoginBody(email='<your admin email>', password='FICTIONAL-SECRET'), None)
        self.assertEqual(result.exception.status_code,422)
        out = json.loads(self.script['safe_http_failure'](self.error({'detail':result.exception.detail}), 'login'))
        self.assertEqual(out['detail']['fields']['email'],'Enter a valid email address.')

    def test_request_failure_is_not_masked_by_logout_failure(self):
        reason=self.root/'reason.txt';reason.write_text('Test reason',encoding='utf-8')
        def fake_http(request, timeout):
            if request.full_url.endswith('/login'):
                return io.BytesIO(b'{"session_token":"fictional-session"}')
            if request.full_url.endswith('/me'):
                return io.BytesIO(b'{"user":{"id":"test-admin"}}')
            if request.full_url.endswith('/logout'):
                raise self.error({'detail':'unknown-private-error'},500)
            raise self.error({'detail':[{'type':'string_too_long','loc':['body','note'],'input':'DO-NOT-ECHO'}]})
        main=self.script['main']
        with contextlib.redirect_stderr(io.StringIO()) as err, patch.dict(main.__globals__,{'urlopen':fake_http}), patch('sys.argv',['review','--email','test@example.test','--source-id','fixture','--revision','old','--decision','NEEDS_NEW_REVISION','--reason-file',str(reason)]), patch('sys.stdin.isatty',return_value=True), patch('sys.stderr.isatty',return_value=True), patch('getpass.getpass',return_value='fictional-password'):
            with self.assertRaises(SystemExit) as result: main()
        self.assertIn('record_review_decision',str(result.exception))
        self.assertIn('422',str(result.exception))
        for secret in ('fictional-session','fictional-password','DO-NOT-ECHO','unknown-private-error'):
            self.assertNotIn(secret,str(result.exception)+err.getvalue())

    def exercise_synthetic_review(self, correction=False):
        from backend.services.verified_corpus import VerifiedCorpus
        from backend.services.authority_review import AuthorityReview
        from backend.tests.legal_test_support import authority, publish_reviewed, test_knowledge
        db = MockDatabaseAdapter(self.root / 'authority.json')
        corpus = VerifiedCorpus(db, test_knowledge())
        published = publish_reviewed(corpus, authority())
        value = {k: v for k, v in published.items() if k not in {'version_id', 'reason'}}
        value['version_note'] = 'Synthetic diagnostic revision'
        pending = AuthorityReview(corpus).submit(value, actor='synthetic-preparer')
        sid, old = pending['source_id'], pending['version_id']
        identity = MockDatabaseAdapter(self.root / 'identity.json')
        auth = MockAuthAdapter(identity, seed_demo=False)
        # Test-only identity fixture. No production user or review data is copied.
        user = auth.provision_local_review_admin('fixture@example.test', 'FictionalTestPassword', allow_bootstrap=True, operator='test-only')
        identity.update('users', user['id'], {'role': 'advocate', 'verification_status': 'VERIFIED', 'capabilities': ['LEGAL_AUTHORITY_REVIEW']})
        factory = runpy.run_path('scripts/serve-authority-review.py')['create_app']
        client = TestClient(factory(identity.path, db.path))
        requests = []
        def local_http(request, timeout):
            requests.append((request.get_method(), request.full_url))
            response = client.request(request.get_method(), request.full_url, content=request.data, headers=dict(request.header_items()))
            if response.status_code >= 400:
                raise self.error(response.json(), response.status_code)
            return io.BytesIO(response.content)
        reason = self.root / 'reason.txt'
        reason.write_text('Synthetic revision rationale')
        args = ['review', '--email', 'fixture@example.test', '--source-id', sid, '--revision', old,
                '--decision', 'NEEDS_NEW_REVISION', '--reason-file', str(reason)]
        if correction:
            value['version_note'] = 'Synthetic corrected metadata'
            for key in ('reviewed_by', 'reviewed_at', 'review_id', 'revision_status', 'parent_revision', 'revision_request_id'):
                value.pop(key, None)
            corrected = self.root / 'corrected.json'
            corrected.write_text(json.dumps(value))
            args += ['--corrected-source-file', str(corrected)]
        main = self.script['main']
        before = db.path.read_bytes()
        with patch.dict(main.__globals__, {'urlopen': local_http}), patch('sys.stdin.isatty', return_value=True), patch('sys.stderr.isatty', return_value=True), patch('getpass.getpass', return_value='FictionalTestPassword'), patch.dict(os.environ, {'ADMIN_TOKEN': ''}), patch('backend.routes.authorities.VerifiedCorpus', side_effect=lambda database: VerifiedCorpus(database, test_knowledge())), contextlib.redirect_stdout(io.StringIO()) as output:
            with patch('sys.argv', args + ['--check-access-only']):
                main()
            self.assertEqual(before, db.path.read_bytes())
            self.assertFalse(any(method == 'POST' and '/authorities' in path for method, path in requests))
            with patch('sys.argv', args):
                main()
        self.assertNotIn('FictionalTestPassword', output.getvalue())
        receipts = [r for r in db.list('legal_authority_reviews') if r['input_version'] == old]
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]['reviewer_id'], user['id'])
        self.assertEqual(identity.list('sessions'), [])
        if correction:
            self.assertIn('"immutable_receipt_verified": true', output.getvalue())
            self.assertIsNone(corpus.get(sid)['review_id'])
            self.assertEqual(corpus.get(sid)['review_state'], 'REVIEW_PENDING')

    def test_synthetic_access_check_never_posts(self):
        self.exercise_synthetic_review()

    def test_synthetic_http_contract_corrected_payload(self):
        self.exercise_synthetic_review(correction=True)
