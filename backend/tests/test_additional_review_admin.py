"""Additional reviewers are fictional and confined to temporary test databases."""
import contextlib
import copy
import io
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.adapters.mock.auth import MockAuthAdapter
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.services.authority_review import AuthorityReview
from backend.services.verified_corpus import VerifiedCorpus
from backend.tests.legal_test_support import authority, publish_reviewed, test_knowledge


class AdditionalReviewerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = MockDatabaseAdapter(self.root/'identity.json')
        self.auth = MockAuthAdapter(self.db, seed_demo=False)
        self.first = self.auth.provision_local_review_admin('first@example.test', 'FirstFixturePassword',
            allow_bootstrap=True, operator='test-only')
        self.token = self.auth.login('first@example.test', 'FirstFixturePassword')['session_token']
        self.bootstrap = copy.deepcopy(self.db.list('review_admin_bootstrap'))

    def add(self, email='second@example.test', token=None):
        return self.auth.provision_additional_review_admin(email, 'SecondFixturePassword',
            session_token=self.token if token is None else token, allow_onboarding=True, operator='test-only')

    def normal_user(self, role):
        return self.auth.signup({'email':role+'@example.test','role':role,'full_name':'Fixture',
            'mobile_number':'9876543210','preferred_language':'English','state':'Tamil Nadu','district_city':'Chennai'},'NormalFixturePassword')

    def test_distinct_account_audit_and_bootstrap_preserved(self):
        first_before = copy.deepcopy(self.db.get('users', self.first['id']))
        result = self.add()
        self.assertNotEqual(result['id'], self.first['id'])
        self.assertEqual(result['role'], 'admin')
        self.assertNotIn('password_hash', result)
        stored = self.db.get('users', result['id'])
        self.assertNotEqual(stored['password_hash'], first_before['password_hash'])
        self.assertEqual(self.db.get('users', self.first['id']), first_before)
        self.assertEqual(self.db.list('review_admin_bootstrap'), self.bootstrap)
        audit = self.db.get('review_admin_provisioning', result['id'])
        self.assertEqual(audit['authorized_by'], self.first['id'])
        self.assertEqual(audit['created_at'], stored['created_at'])
        self.assertFalse(audit['human_independence_verified'])
        self.assertNotIn(self.token, str(audit))
        self.assertNotIn('SecondFixturePassword', self.db.path.read_text())
        session = self.auth.login('second@example.test', 'SecondFixturePassword')
        self.assertEqual(session['user']['id'], result['id'])
        with self.assertRaises(ValueError):
            self.auth.provision_local_review_admin('third@example.test','AnotherFixturePassword',allow_bootstrap=True,operator='test')

    def test_requires_existing_authenticated_admin_and_flag(self):
        for token in ('missing-session', self.normal_user('client')['session_token'], self.normal_user('advocate')['session_token']):
            before = self.db.path.read_bytes()
            with self.assertRaises(ValueError): self.add(token=token)
            self.assertEqual(self.db.path.read_bytes(), before)
        with self.assertRaises(ValueError):
            self.auth.provision_additional_review_admin('second@example.test','SecondFixturePassword',session_token=self.token,allow_onboarding=False,operator='test')
        self.auth.logout(self.token)
        with self.assertRaises(ValueError): self.add()

    def test_duplicate_email_never_promotes_client_or_advocate(self):
        self.add()
        for email in ('first@example.test','SECOND@example.test', self.normal_user('client')['user']['email'], self.normal_user('advocate')['user']['email']):
            before = self.db.path.read_bytes()
            with self.assertRaises(ValueError): self.add(email)
            self.assertEqual(self.db.path.read_bytes(), before)

    def test_role_revocation_rechecked_inside_atomic_creation(self):
        original = self.db.create_additional_review_admin
        def revoke_then_create(user, *, session_token):
            self.db.update('users', self.first['id'], {'role':'client'})
            return original(user, session_token=session_token)
        with patch.object(self.db, 'create_additional_review_admin', side_effect=revoke_then_create):
            with self.assertRaises(ValueError): self.add()
        self.assertEqual(len(self.db.list('users')),1)
        self.assertEqual(self.db.list('review_admin_provisioning'),[])
        self.assertEqual(self.db.list('review_admin_bootstrap'),self.bootstrap)

    def test_onboarding_cannot_replace_bootstrap(self):
        self.db.delete('review_admin_bootstrap','one-time')  # Temporary fixture only.
        with self.assertRaisesRegex(ValueError,'bootstrap history'): self.add()
        self.assertEqual(len(self.db.list('users')),1)

    def test_second_reviewer_access_does_not_approve_and_submitter_stays_blocked(self):
        authorities = MockDatabaseAdapter(self.root/'authorities.json')
        corpus = VerifiedCorpus(authorities,test_knowledge())
        fixture = publish_reviewed(corpus, authority())
        workflow = AuthorityReview(corpus,accounts_db=self.db)
        value = {k:v for k,v in fixture.items() if k not in {'version_id','reason'}}
        value['version_note'] = 'Corrected fixture requiring fresh review'
        pending = workflow.submit(value,actor=self.first['id'])
        before = authorities.path.read_bytes()
        second = self.add()
        self.assertEqual(authorities.path.read_bytes(),before)
        with self.assertRaises(PermissionError):
            workflow.decide(pending['source_id'],pending['version_id'],reviewer=self.first,decision='REVIEWED_PRIMARY',note='Self-review must remain prohibited')
        factory = runpy.run_path('scripts/serve-authority-review.py')['create_app']
        client = TestClient(factory(self.db.path,authorities.path))
        session = client.post('/api/auth/login',json={'email':second['email'],'password':'SecondFixturePassword'})
        self.assertEqual(session.status_code,200)
        headers = {'Authorization':'Bearer '+session.json()['session_token']}
        with patch.dict(os.environ,{'ADMIN_TOKEN':''}):
            self.assertEqual(client.get('/api/admin/authorities/fixture_act/history',headers=headers).status_code,200)
        self.assertEqual(authorities.path.read_bytes(),before)
        self.assertEqual(corpus.get('fixture_act')['review_state'],'REVIEW_PENDING')
        self.assertFalse(corpus.validate_source({k:v for k,v in pending.items() if k not in {'version_id','reason'}})[0])

    def test_cli_flag_secrets_confirmation_and_no_automatic_review(self):
        main = runpy.run_path('scripts/add-review-administrator.py')['main']
        secret = 'NeverEchoThisFixtureSecret'
        for argv in ([],['--password',secret],['--host','0.0.0.0']):
            with contextlib.redirect_stderr(io.StringIO()) as capture:
                with self.assertRaises(SystemExit): main(argv)
            self.assertNotIn(secret,capture.getvalue())
        self.auth.logout(self.token)
        for confirmation, expected in [('NO',1),('ADD REVIEW ADMIN',0)]:
            with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as errors, patch.dict(main.__globals__,{'validate_local_environment':lambda root:self.db.path}), patch('builtins.input',side_effect=['first@example.test',confirmation,'new-reviewer@example.test']), patch('getpass.getpass',side_effect=['FirstFixturePassword',secret,secret]):
                self.assertEqual(main(['--allow-reviewer-onboarding']),expected)
            self.assertNotIn(secret,output.getvalue()+errors.getvalue())
            self.assertNotIn('FirstFixturePassword',output.getvalue()+errors.getvalue())
            self.assertEqual(self.db.list('sessions'),[])
            self.assertEqual(self.db.list('review_admin_bootstrap'),self.bootstrap)
            self.assertEqual(self.db.list('legal_authority_reviews'),[])
            self.assertEqual(len(self.db.list('users')),1 if expected else 2)
