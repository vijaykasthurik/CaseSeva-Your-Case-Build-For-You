"""Bootstrap exercises use temporary identity files and fictional credentials only."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from backend.adapters.mock.auth import MockAuthAdapter
from backend.adapters.mock.database import MockDatabaseAdapter


class ReviewAdminBootstrapTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.db = MockDatabaseAdapter(self.root / 'identity.json')
        self.auth = MockAuthAdapter(self.db, seed_demo=False)
        self.password = 'Fictional-Test-Password-Only'
        self.script = runpy.run_path('scripts/provision-review-admin.py')

    def create(self, email='reviewer@example.test'):
        return self.auth.provision_local_review_admin(email, self.password,
            allow_bootstrap=True, operator='fictional-local-test-operator')

    def test_create_audited_admin_and_authenticate_without_bootstrap_session(self):
        result = self.create(' Reviewer@Example.Test ')
        self.assertEqual(result['role'], 'admin')
        self.assertEqual(result['email'], 'reviewer@example.test')
        self.assertNotIn('password_hash', result)
        stored = self.db.get('users', result['id'])
        self.assertNotIn(self.password, self.db.path.read_text())
        self.assertEqual(stored['created_at'], stored['provisioning']['created_at'])
        self.assertEqual(stored['provisioning']['scope'], 'PHASE4_REVIEW_ONLY')
        self.assertEqual(self.db.list('sessions'), [])
        self.assertEqual(self.db.get('review_admin_bootstrap', 'one-time')['user_id'], result['id'])
        session = self.auth.login(result['email'], self.password)
        self.assertEqual(self.auth.get_current_user(session['session_token'])['role'], 'admin')

    def test_duplicate_email_and_client_advocate_escalation_rejected(self):
        for role in ('client', 'advocate'):
            account = self.auth.signup({'email': role+'@example.test', 'role': role,
                'full_name': 'Test', 'mobile_number': '9876543210', 'preferred_language': 'English',
                'state': 'Tamil Nadu', 'district_city': 'Chennai'}, self.password)['user']
            before = self.db.path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'never promotes'):
                self.create(role.upper()+'@example.test')
            self.assertEqual(self.db.path.read_bytes(), before)
            self.assertEqual(self.db.get('users', account['id'])['role'], role)
        self.create()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.create()

    def test_bootstrap_is_one_time_even_if_account_removed_and_atomic(self):
        def attempt(email):
            try:
                return self.create(email)
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ['one@example.test', 'two@example.test']))
        self.assertEqual(sum(r is not None for r in results), 1)
        user = next(r for r in results if r)
        self.db.delete('users', user['id'])
        with self.assertRaisesRegex(ValueError, 'already been used'):
            self.create('third@example.test')

    def test_adapter_requires_flag_and_existing_password_email_rules(self):
        with self.assertRaises(ValueError):
            self.auth.provision_local_review_admin('reviewer@example.test', self.password, allow_bootstrap=False, operator='test')
        for email, password in [('invalid', self.password), ('reviewer@example.test', 'short')]:
            with self.assertRaises(ValueError):
                self.auth.provision_local_review_admin(email, password, allow_bootstrap=True, operator='test')
        self.assertEqual(self.db.list('users'), [])

    def test_cli_refuses_missing_flag_and_secret_arguments_without_echo(self):
        for arguments in ([], ['--password', self.password], ['--host', '0.0.0.0'], ['--identity-database', '//server/share/db.json']):
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                with self.assertRaises(SystemExit) as error:
                    self.script['main'](arguments)
            self.assertEqual(error.exception.code, 2)
            self.assertNotIn(self.password, capture.getvalue())

    def test_environment_rejects_remote_redirected_wrong_project_and_interpreter(self):
        validate = self.script['validate_local_environment']
        with patch('pathlib.Path.cwd', return_value=self.root), patch('sys.executable', str(self.root / '.venv/Scripts/python.exe')), patch('sys.stdin.isatty', return_value=True), patch('sys.stderr.isatty', return_value=True), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(validate(self.root), self.root / '.localdev/phase4-authority-review/identity.json')
            for key in ('SSH_CONNECTION', 'SSH_CLIENT', 'SSH_TTY', 'REMOTEHOST', 'SESSIONNAME'):
                with patch.dict(os.environ, {key: 'RDP-test'}):
                    with self.assertRaises(ValueError):
                        validate(self.root)
            with patch('sys.stdin.isatty', return_value=False):
                with self.assertRaises(ValueError):
                    validate(self.root)
            with patch('pathlib.Path.cwd', return_value=self.root.parent):
                with self.assertRaises(ValueError):
                    validate(self.root)
            with patch('sys.executable', str(self.root / 'other/python.exe')):
                with self.assertRaises(ValueError):
                    validate(self.root)
            with patch('pathlib.Path.is_symlink', return_value=True):
                with self.assertRaises(ValueError):
                    validate(self.root)

    def test_interactive_cli_does_not_output_password_or_create_without_confirmation(self):
        target = self.root / 'interactive.json'
        main = self.script['main']
        for confirmation, expected in [('NO', 1), ('CREATE REVIEW ADMIN', 0)]:
            capture = io.StringIO()
            with patch.dict(main.__globals__, {'validate_local_environment': lambda root: target}), patch('builtins.input', side_effect=[confirmation, 'interactive@example.test']), patch('getpass.getpass', return_value=self.password), contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                self.assertEqual(main(['--allow-admin-bootstrap']), expected)
            self.assertNotIn(self.password, capture.getvalue())
            if expected:
                self.assertFalse(target.exists())
        db = MockDatabaseAdapter(target)
        self.assertEqual(len(db.list('users')), 1)
        self.assertEqual(db.list('sessions'), [])

    def test_created_admin_has_review_access_non_admin_does_not(self):
        self.create()
        self.auth.signup({'email': 'client@example.test', 'role': 'client', 'full_name': 'Test',
            'mobile_number': '9876543210', 'preferred_language': 'English', 'state': 'Tamil Nadu', 'district_city': 'Chennai'}, self.password)
        authorities = MockDatabaseAdapter(self.root / 'authority.json')
        factory = runpy.run_path('scripts/serve-authority-review.py')['create_app']
        client = TestClient(factory(self.db.path, authorities.path))
        with patch.dict(os.environ, {'ADMIN_TOKEN': ''}):
            self.assertEqual(client.get('/api/admin/authorities').status_code, 401)
            for email, status in [('reviewer@example.test', 200), ('client@example.test', 403)]:
                session = client.post('/api/auth/login', json={'email': email, 'password': self.password})
                self.assertEqual(session.status_code, 200)
                headers = {'Authorization': 'Bearer '+session.json()['session_token']}
                self.assertEqual(client.get('/api/admin/authorities', headers=headers).status_code, status)
            self.assertEqual(client.post('/api/auth/signup', json={}).status_code, 404)
        self.assertEqual(authorities.list('users'), [])

    def test_public_signup_cannot_create_admin(self):
        from backend.tests.helpers import test_app
        folder, app, client = test_app()
        self.addCleanup(folder.cleanup)
        response = client.post('/api/auth/signup', json={'email': 'noadmin@example.test', 'password': self.password,
            'role': 'admin', 'full_name': 'Test', 'mobile_number': '9876543210', 'preferred_language': 'English', 'state': 'Tamil Nadu', 'district_city': 'Chennai'})
        self.assertEqual(response.status_code, 422)
        self.assertFalse(any(u['role']=='admin' for u in app.state.adapters.database.list('users')))

    def test_authenticated_client_records_receipt_then_submits_new_pending_revision(self):
        from backend.services.verified_corpus import VerifiedCorpus
        from backend.services.authority_review import AuthorityReview
        from backend.tests.legal_test_support import authority, publish_reviewed, test_knowledge
        # Bootstrap an admin in the identity DB (needed for serve-authority-review startup check).
        self.create()
        # Also create a verified advocate with LEGAL_AUTHORITY_REVIEW capability as the reviewer.
        advocate_password = 'AdvocateFixturePassword-Review123'
        signup = self.auth.signup({
            'email': 'advocate-reviewer@example.test', 'role': 'advocate',
            'full_name': 'Test Advocate Reviewer', 'mobile_number': '9876543211',
            'preferred_language': 'English', 'state': 'Tamil Nadu', 'district_city': 'Chennai',
            'bar_council': 'Fixture Bar Council', 'enrolment_number': 'TN/TEST/2020',
            'enrolment_year': 2020, 'place_of_practice': 'Chennai',
            'court_region': 'Madras High Court', 'practice_domains': ['Consumer'],
            'languages': ['English'],
        }, advocate_password)
        advocate = signup['user']
        self.auth.logout(signup['session_token'])
        # Grant LEGAL_AUTHORITY_REVIEW to the advocate in the identity DB.
        self.auth.database.update('users', advocate['id'], {
            'verification_status': 'VERIFIED',
            'capabilities': ['LEGAL_AUTHORITY_REVIEW'],
            'permissions': ['LEGAL_AUTHORITY_REVIEW'],
        })
        db = MockDatabaseAdapter(self.root / 'authority.json')
        corpus = VerifiedCorpus(db, test_knowledge())
        old = publish_reviewed(corpus, authority())
        value = {k:v for k,v in old.items() if k not in {'version_id','reason'}}
        value['version_note'] = 'Pending fixture'
        pending = AuthorityReview(corpus).submit(value, actor='test-source-preparer')
        value['version_note'] = 'Corrected fixture'
        for key in ('reviewed_by','reviewed_at','review_id','revision_status','parent_revision','revision_request_id'):
            value.pop(key, None)
        source_file = self.root / 'corrected.json'
        source_file.write_text(json.dumps(value), encoding='utf-8')
        reason = self.root / 'reason.txt'
        reason.write_text('Test revision needed', encoding='utf-8')
        factory = runpy.run_path('scripts/serve-authority-review.py')['create_app']
        client = TestClient(factory(self.db.path, db.path))
        def local_http(request, timeout):
            response = client.request(request.get_method(), request.full_url,
                content=request.data, headers=dict(request.header_items()))
            self.assertEqual(response.status_code, 200, response.text)
            return io.BytesIO(response.content)
        command = runpy.run_path('scripts/record-authority-review.py')['main']
        capture = io.StringIO()
        with patch.dict(command.__globals__, {'urlopen':local_http}), patch('sys.argv', ['review', '--email','advocate-reviewer@example.test', '--source-id','fixture_act', '--revision',pending['version_id'], '--decision','NEEDS_NEW_REVISION', '--reason-file',str(reason), '--corrected-source-file',str(source_file)]), patch('getpass.getpass', return_value=advocate_password), patch('sys.stdin.isatty', return_value=True), patch('sys.stderr.isatty', return_value=True), patch.dict(os.environ, {'ADMIN_TOKEN':''}), patch('backend.routes.authorities.VerifiedCorpus', side_effect=lambda database: VerifiedCorpus(database, test_knowledge())), contextlib.redirect_stdout(capture):
            command()
        self.assertNotIn(advocate_password, capture.getvalue())
        self.assertIn('"immutable_receipt_verified": true', capture.getvalue())
        self.assertEqual(self.db.list('sessions'), [])
        current = corpus.get('fixture_act')
        self.assertEqual(current['review_state'], 'REVIEW_PENDING')
        self.assertIsNone(current['review_id'])
        receipt = db.get('legal_authority_reviews', current['revision_request_id'])
        self.assertEqual(receipt['decision'], 'NEEDS_NEW_REVISION')
        self.assertEqual(receipt['reviewer_id'], advocate['id'])
        # Admin cannot perform legal authority review (platform boundary).
        admin = next((u for u in self.db.list('users') if u.get('role') == 'admin'), None)
        with self.assertRaises(PermissionError):
            AuthorityReview(corpus, accounts_db=self.db).decide('fixture_act', current['version_id'], reviewer=admin, decision='REVIEWED_PRIMARY', note='Admin review refused - must use verified advocate')
