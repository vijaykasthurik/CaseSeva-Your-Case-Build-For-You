"""No real login or review retries. Test copies use fictional local identities."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import socket
import threading
import time
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

    def test_real_pending_candidate_copy_accepts_intended_transition_and_check_only_does_not_post(self):
        # Optional local reproduction: read only the public authority/ingestion records,
        # never the real identity database, password hashes or administrator credentials.
        source_path=Path('.localdev/phase4-authority-review/database.json')
        if not source_path.exists(): self.skipTest('Local genuine authority bundle not available')
        original=source_path.read_bytes()
        real=json.loads(original)
        sid='cpa2019_s2_7'
        old='d9804b732b3d855c06cf5c0143b721a5e9d0ad775092810c2f236150a51a024e'
        record=real['legal_authority_versions'][old]
        db=MockDatabaseAdapter(self.root/'authority.json')
        db.create('legal_authority_versions',record)
        db.create('legal_authority_heads',{'id':sid,'version':old})
        db.create('legal_ingestion_requests',real['legal_ingestion_requests'][record['source']['ingestion_id']])
        identity=MockDatabaseAdapter(self.root/'identity.json')
        auth=MockAuthAdapter(identity,seed_demo=False)
        admin=auth.provision_local_review_admin('fixture@example.test','FictionalTestPassword',allow_bootstrap=True,operator='test-only')
        factory=runpy.run_path('scripts/serve-authority-review.py')['create_app']
        client=TestClient(factory(identity.path,db.path))
        requests=[]
        def local_http(request,timeout):
            requests.append((request.get_method(),request.full_url))
            response=client.request(request.get_method(),request.full_url,content=request.data,headers=dict(request.header_items()))
            if response.status_code>=400: raise self.error(response.json(),response.status_code)
            return io.BytesIO(response.content)
        reason=Path('.localdev/phase4-authority-review/record-1/reason.txt')
        args=['review','--email','fixture@example.test','--source-id',sid,'--revision',old,'--decision','NEEDS_NEW_REVISION','--reason-file',str(reason)]
        main=self.script['main']
        before=db.path.read_bytes()
        with patch.dict(main.__globals__,{'urlopen':local_http}), patch('sys.argv',args+['--check-access-only']), patch('sys.stdin.isatty',return_value=True), patch('sys.stderr.isatty',return_value=True), patch('getpass.getpass',return_value='FictionalTestPassword'), patch.dict(os.environ,{'ADMIN_TOKEN':''}), contextlib.redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(before,db.path.read_bytes())
        self.assertFalse(any(method=='POST' and '/authorities' in path for method,path in requests))
        self.assertEqual(identity.list('sessions'),[])
        with patch.dict(main.__globals__,{'urlopen':local_http}), patch('sys.argv',args), patch('sys.stdin.isatty',return_value=True), patch('sys.stderr.isatty',return_value=True), patch('getpass.getpass',return_value='FictionalTestPassword'), patch.dict(os.environ,{'ADMIN_TOKEN':''}), contextlib.redirect_stdout(io.StringIO()):
            main()
        receipts=db.list('legal_authority_reviews')
        self.assertEqual(len(receipts),1)
        self.assertEqual(receipts[0]['reviewer_id'],admin['id'])
        self.assertEqual(receipts[0]['decision'],'NEEDS_NEW_REVISION')
        self.assertEqual(source_path.read_bytes(),original)

    def test_real_http_client_with_exact_official_candidate_and_corrected_payload(self):
        """Exercise urllib + Uvicorn, not a mocked transport; only temporary DBs mutate."""
        import uvicorn
        folder=Path('.localdev/phase4-authority-review')
        if not (folder/'database.json').exists(): self.skipTest('Local official review bundle not available')
        real_bytes=(folder/'database.json').read_bytes()
        # Compare the real identity file without parsing or copying credential fields.
        identity_bytes=(folder/'identity.json').read_bytes() if (folder/'identity.json').exists() else None
        real=json.loads(real_bytes)
        sid='cpa2019_s2_7'
        old='d9804b732b3d855c06cf5c0143b721a5e9d0ad775092810c2f236150a51a024e'
        record=real['legal_authority_versions'][old]
        db=MockDatabaseAdapter(self.root/'http-authorities.json')
        db.create('legal_authority_versions',record)
        db.create('legal_authority_heads',{'id':sid,'version':old})
        db.create('legal_ingestion_requests',real['legal_ingestion_requests'][record['source']['ingestion_id']])
        identity=MockDatabaseAdapter(self.root/'http-identity.json')
        auth=MockAuthAdapter(identity,seed_demo=False)
        auth.provision_local_review_admin('http-fixture@example.test','FictionalHttpPassword',allow_bootstrap=True,operator='test-only')
        factory=runpy.run_path('scripts/serve-authority-review.py')['create_app']
        app=factory(identity.path,db.path)
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_config=None,log_level='critical',access_log=False))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True)
        thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started and time.monotonic()<deadline: time.sleep(.01)
            self.assertTrue(server.started)
            args=['review','--port',str(port),'--email','http-fixture@example.test','--source-id',sid,'--revision',old,
                  '--decision','NEEDS_NEW_REVISION','--reason-file',str(folder/'record-1/reason.txt'),
                  '--corrected-source-file',str(folder/'record-1/corrected-source-submission.json')]
            with patch('sys.argv',args), patch('sys.stdin.isatty',return_value=True), patch('sys.stderr.isatty',return_value=True), patch('getpass.getpass',return_value='FictionalHttpPassword'), patch.dict(os.environ,{'ADMIN_TOKEN':''}), contextlib.redirect_stdout(io.StringIO()) as output:
                self.script['main']()
            self.assertIn('"immutable_receipt_verified": true',output.getvalue())
            self.assertNotIn('FictionalHttpPassword',output.getvalue())
            self.assertEqual(len(db.list('legal_authority_reviews')),1)
            self.assertEqual(identity.list('sessions'),[])
            current=db.get('legal_authority_heads',sid)['version']
            source=db.get('legal_authority_versions',current)['source']
            self.assertEqual(source['review_state'],'REVIEW_PENDING')
            self.assertFalse(source['source_reviewed'])
            self.assertIsNone(source['review_id'])
        finally:
            server.should_exit=True
            thread.join(timeout=10)
            sock.close()
            self.assertEqual((folder/'database.json').read_bytes(),real_bytes)
            if identity_bytes is not None: self.assertEqual((folder/'identity.json').read_bytes(),identity_bytes)
