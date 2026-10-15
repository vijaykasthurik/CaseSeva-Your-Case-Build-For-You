"""Shared mock/local disposable Mongo promotion recovery contract."""
import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from backend.adapters.mock.database import MockDatabaseAdapter
from backend.adapters.mongo.database import MongoDatabaseAdapter
from backend.services.admin_promotion import promote_existing_user_to_admin


class PromotionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = MockDatabaseAdapter(Path(temp.name) / 'test.json')
        self.seed()

    def seed(self):
        self.db.create('users', {'id': 'client', 'email': 'client@example.test',
                                'role': 'client', 'password_hash': 'synthetic-hash'})
        self.protected = {c: self.db.list(c) for c in (
            'legal_authority_heads', 'legal_authority_versions', 'legal_authority_reviews',
            'authority_reviewer_grants')}
        self.addCleanup(lambda: self.assertEqual(
            self.protected, {c: self.db.list(c) for c in self.protected}))

    def promote(self):
        return promote_existing_user_to_admin(self.db, ' CLIENT@example.test ')

    def test_supported_user_id_selector(self):
        result = promote_existing_user_to_admin(self.db, user_id='client')
        self.assertEqual(result['status'], 'promoted')

    def test_command_recovery_and_already_admin(self):
        from backend import admin_command
        self.partial()
        with patch.object(admin_command, 'load_operator_database', return_value=self.db), \
             patch('sys.argv', ['admin_command', '--user-id', 'client']), patch('builtins.print') as output:
            admin_command.main()
            self.assertIn('assigned', output.call_args.args[0])
            admin_command.main()
            self.assertIn('already', output.call_args.args[0])
        self.assertEqual(len(self.db.list('admin_role_audit')), 1)

    def test_success_identity_receipt_and_write_free_rerun(self):
        result = self.promote()
        user = self.db.get('users', 'client')
        self.assertEqual((user['id'], user['password_hash'], user['role']),
                         ('client', 'synthetic-hash', 'admin'))
        self.assertEqual(user['admin_role_intent_id'], result['intent_id'])
        self.assertEqual(len(self.db.list('admin_role_audit')), 1)
        with patch.object(self.db, 'reserve_admin_role_intent', side_effect=AssertionError('write')), \
             patch.object(self.db, 'mutate', side_effect=AssertionError('write')):
            self.assertEqual(self.promote()['status'], 'already_admin')
        self.assertEqual(user, self.db.get('users', 'client'))

    def partial(self):
        with patch.object(self.db, 'mutate', side_effect=RuntimeError('synthetic pre-CAS failure')):
            with self.assertRaises(RuntimeError):
                self.promote()
        self.assertEqual(self.db.get('users', 'client')['role'], 'client')
        self.assertNotIn('admin_role_intent_id', self.db.get('users', 'client'))
        return copy.deepcopy(self.db.list('admin_role_audit'))

    def test_partial_failure_reuses_immutable_intent(self):
        intents = self.partial()
        self.promote()
        self.assertEqual(self.db.list('admin_role_audit'), intents)
        self.assertEqual(self.db.get('users', 'client')['admin_role_intent_id'], intents[0]['id'])
        for operation in (lambda: self.db.update('admin_role_audit', intents[0]['id'], {'new_role': 'client'}),
                          lambda: self.db.delete('admin_role_audit', intents[0]['id'])):
            with self.assertRaises(ValueError):
                operation()

    def test_stale_intent_and_demoted_account_refused(self):
        intents = self.partial()
        self.db.update('users', 'client', {'password_hash': 'changed-synthetic-hash'})
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.promote()
        self.assertEqual(self.db.list('admin_role_audit'), intents)
        self.assertEqual(self.db.get('users', 'client')['role'], 'client')

    def test_missing_ambiguous_advocate_zero_writes(self):
        with self.assertRaises(ValueError):
            promote_existing_user_to_admin(self.db, 'missing@example.test')
        self.db.create('users', {'id': 'duplicate', 'email': 'CLIENT@example.test', 'role': 'client'})
        with self.assertRaises(ValueError):
            self.promote()
        self.db.delete('users', 'duplicate')
        self.db.update('users', 'client', {'role': 'advocate'})
        with self.assertRaisesRegex(ValueError, 'advocates'):
            self.promote()
        self.assertEqual(self.db.list('admin_role_audit'), [])

    def test_lost_success_response_rerun_is_write_free(self):
        original = self.db.mutate
        def applied_then_disconnected(*args):
            original(*args)
            raise RuntimeError('synthetic lost response')
        with patch.object(self.db, 'mutate', side_effect=applied_then_disconnected):
            with self.assertRaises(RuntimeError):
                self.promote()
        before = self.db.get('users', 'client')
        self.assertEqual(self.promote()['status'], 'already_admin')
        self.assertEqual(self.db.get('users', 'client'), before)
        self.assertEqual(len(self.db.list('admin_role_audit')), 1)

    def test_audit_failure_does_not_elevate(self):
        with patch.object(self.db, 'reserve_admin_role_intent', side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):
                self.promote()
        self.assertEqual(self.db.get('users', 'client')['role'], 'client')

    def test_concurrent_change_not_overwritten(self):
        original = self.db.mutate
        def race(collection, identifier, transform):
            original('users', identifier, lambda u: {'role': 'advocate'})
            return original(collection, identifier, transform)
        with patch.object(self.db, 'mutate', side_effect=race):
            with self.assertRaises(ValueError):
                self.promote()
        self.assertEqual(self.db.get('users', 'client')['role'], 'advocate')
        self.assertEqual(len(self.db.list('admin_role_audit')), 1)

    def test_concurrent_promoters_share_one_intent(self):
        barrier = Barrier(2)
        original = self.db.reserve_admin_role_intent
        def reserve(intent):
            barrier.wait(timeout=10)
            return original(intent)
        with patch.object(self.db, 'reserve_admin_role_intent', side_effect=reserve):
            with ThreadPoolExecutor(2) as pool:
                results = list(pool.map(lambda _: self.promote(), range(2)))
        self.assertEqual(len(self.db.list('admin_role_audit')), 1)
        self.assertEqual(results[0]['intent_id'], results[1]['intent_id'])

    def legacy_intent(self, identifier='legacy'):
        self.db.create('admin_role_audit', {'id': identifier, 'user_id': 'client',
            'previous_role': 'client', 'new_role': 'admin', 'method': 'OPERATOR_CLI',
            'assigned_at': '2026-10-15T07:54:19+00:00'})

    def test_ambiguous_history_refused(self):
        self.legacy_intent()
        self.legacy_intent('other')
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            self.promote()
        self.assertEqual(len(self.db.list('admin_role_audit')), 2)

    def test_applied_intent_cannot_repromote_demoted_account(self):
        self.promote()
        before = self.db.list('admin_role_audit')
        self.db.update('users', 'client', {'role': 'client'})
        with self.assertRaisesRegex(ValueError, 'Previously applied'):
            self.promote()
        self.assertEqual(self.db.list('admin_role_audit'), before)

    def test_legacy_intent_with_mutation_evidence_refused(self):
        self.legacy_intent()
        self.db.update('users', 'client', {'updated_at': '2026-10-15T08:00:00+00:00'})
        with self.assertRaisesRegex(ValueError, 'Legacy intent'):
            self.promote()
        self.assertEqual(self.db.get('users', 'client')['role'], 'client')

    def test_conflicting_intent_refused(self):
        self.db.create('admin_role_audit', {'id': 'wrong', 'user_id': 'client',
            'previous_role': 'advocate', 'new_role': 'admin', 'method': 'OPERATOR_CLI',
            'assigned_at': '2026-10-15'})
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            self.promote()
        self.assertEqual(self.db.get('users', 'client')['role'], 'client')


class MockLegacyPromotionTests(PromotionTests):
    def test_legacy_original_intent_recovered(self):
        self.legacy_intent()
        before = self.db.list('admin_role_audit')
        self.promote()
        self.assertEqual(self.db.list('admin_role_audit'), before)
        self.assertEqual(self.db.get('users', 'client')['admin_role_intent_id'], 'legacy')


class MongoPromotionTests(PromotionTests):
    def setUp(self):
        name = 'caseseva_test_admin_recovery_' + uuid4().hex
        self.db = MongoDatabaseAdapter(name, 'mongodb://127.0.0.1:27017')
        self.addCleanup(lambda: self.db.db.client.drop_database(name))
        self.seed()

    def test_legacy_missing_and_null_revision_recover_original_intent(self):
        for metadata in ({}, {'_revision': None, 'version': None, 'updated_at': None}):
            with self.subTest(metadata=metadata):
                self.db.db.users.delete_many({})
                self.db.db.admin_role_audit.delete_many({})
                self.db.db.users.insert_one({'_id': 'legacy-storage-id', 'id': 'client',
                    'email': 'client@example.test', 'role': 'client',
                    'password_hash': 'synthetic-hash', **metadata})
                self.legacy_intent()
                before = self.db.list('admin_role_audit')
                self.promote()
                user = self.db.db.users.find_one({'id': 'client'})
                self.assertEqual(user['_id'], 'legacy-storage-id')
                self.assertEqual(user['_revision'], 1)
                self.assertEqual(user['password_hash'], 'synthetic-hash')
                self.assertEqual(user['admin_role_intent_id'], 'legacy')
                self.assertEqual(self.db.list('admin_role_audit'), before)

    def test_legacy_snapshot_cas_detects_added_field_without_revision(self):
        self.db.db.users.update_one({'id': 'client'}, {'$unset': {'_revision': ''}})
        coll = self.db.db.users
        original = type(coll).replace_one
        raced = []
        def replace(instance, query, replacement, **kwargs):
            if instance.name == 'users' and not raced:
                raced.append(True)
                coll.update_one({'id': 'client'}, {'$set': {'concurrent_field': 'preserve'}})
            return original(instance, query, replacement, **kwargs)
        with patch.object(type(coll), 'replace_one', new=replace):
            with self.assertRaisesRegex(ValueError, 'changed'):
                self.promote()
        user = self.db.get('users', 'client')
        self.assertEqual(user['concurrent_field'], 'preserve')
        self.assertEqual(user['role'], 'client')

    def test_generic_mutation_legacy_migrates_and_retries_without_lost_update(self):
        self.db.db.users.update_one({'id': 'client'}, {'$set': {'_revision': None}})
        user = self.db.update('users', 'client', {'full_name': 'Synthetic'})
        self.assertEqual(user['_revision'], 1)
        self.assertEqual(self.db.update('users', 'client', {'full_name': 'Next'})['_revision'], 2)


class PromotionAuthTests(unittest.TestCase):
    def test_real_command_loader_does_not_seed_users(self):
        import os
        from backend import admin_command
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.json'
            db = MockDatabaseAdapter(path)
            db.create('users', {'id': 'existing', 'email': 'existing@example.test', 'role': 'admin'})
            before = path.read_bytes()
            with patch.dict(os.environ, {'DATABASE_PROVIDER': 'mock', 'USE_MOCK_AWS': 'true',
                                        'MOCK_DATABASE_PATH': str(path)}), \
                 patch('sys.argv', ['admin_command', '--user-id', 'existing']), patch('builtins.print'):
                admin_command.main()
            self.assertEqual(path.read_bytes(), before)


    def test_signup_login_promotion_password_session_and_public_boundary(self):
        from backend.tests.helpers import test_app, client_account
        folder, app, client = test_app()
        self.addCleanup(folder.cleanup)
        user, headers = client_account(client, 'promotion-auth')
        db = app.state.adapters.database
        original = db.get('users', user['id'])
        response = client.post('/api/auth/signup', json={
            'email': 'forbidden@example.test', 'password': 'Synthetic123', 'role': 'admin',
            'full_name': 'Fixture', 'mobile_number': '9876543210',
            'preferred_language': 'English', 'state': 'Tamil Nadu', 'district_city': 'Chennai'})
        self.assertEqual(response.status_code, 422)
        promote_existing_user_to_admin(db, user_id=user['id'])
        login = client.post('/api/auth/login', json={
            'email': 'promotion-auth@example.com', 'password': 'Password123'})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()['user']['role'], 'admin')
        self.assertEqual(db.get('users', user['id'])['password_hash'], original['password_hash'])
        self.assertEqual(client.post('/api/auth/login', json={
            'email': 'promotion-auth@example.com', 'password': 'Incorrect123'}).status_code, 401)


if __name__ == '__main__':
    unittest.main()
