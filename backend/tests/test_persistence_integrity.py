"""Real standalone Mongo tests: UUID databases, synthetic records, no external I/O."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
import unittest

from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from backend.adapters.mongo.database import MongoDatabaseAdapter
from backend.adapters.mock.auth import MockAuthAdapter
from backend.repositories.authority_repository import MongoAuthorityRepository, MongoReviewRepository, VersionConflict
from backend.repositories.immutable import HistoryConflict
from backend.repositories.audit_repository import MongoAuditRepository


class PersistenceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.name = 'caseseva_integrity_test_' + uuid4().hex
        self.adapter = MongoDatabaseAdapter(self.name, 'mongodb://127.0.0.1:27017')
        self.db = self.adapter.db
        self.db.client.admin.command('ping')
        self.addCleanup(lambda: self.db.client.drop_database(self.name))

    def user(self, uid='founder', authorizer=None):
        audit = {'scope': 'PHASE4_REVIEW_ONLY', 'created_at': 'synthetic-time',
                 'method': 'AUTHENTICATED_LOCAL_REVIEW_ONBOARDING' if authorizer else 'LOCAL_INTERACTIVE_REVIEW_BOOTSTRAP'}
        if authorizer:
            audit['authorized_by'] = authorizer
        return {'id': uid, 'email': uid+'@synthetic.test', 'role': 'admin',
                'provisioning': audit, 'password_hash': MockAuthAdapter._hash_password('Synthetic123!')}

    def bootstrap(self):
        self.adapter.create_local_review_admin(self.user())
        self.adapter.create('sessions', {'id': 'session', 'user_id': 'founder'})

    def onboard(self, user):
        self.adapter.create_additional_review_admin(user, session_token='session')

    def race(self, functions):
        barrier = Barrier(len(functions))
        def attempt(fn):
            barrier.wait(timeout=10)
            try:
                fn()
                return 'ok'
            except ValueError:
                return 'conflict'
        with ThreadPoolExecutor(len(functions)) as pool:
            return list(pool.map(attempt, functions))

    def assert_audited(self):
        for user in self.db.users.find({'role': 'admin'}):
            self.assertTrue(self.adapter._has_review_audit(user))

    def test_concurrent_bootstrap_and_retry(self):
        users = [self.user('one'), self.user('two')]
        self.assertCountEqual(self.race([lambda u=u: self.adapter.create_local_review_admin(u) for u in users]), ['ok', 'conflict'])
        self.assertEqual(self.db.users.count_documents({}), 1)
        self.assertEqual(self.db.review_admin_bootstrap.count_documents({}), 1)
        self.assert_audited()
        before = self.db.review_admin_bootstrap.find_one({})
        for u in users:
            with self.assertRaises(ValueError):
                self.adapter.create_local_review_admin(u)
        self.assertEqual(before, self.db.review_admin_bootstrap.find_one({}))

    def inject_insert_failure(self, collection, *, after=False):
        original = Collection.insert_one
        def insert(coll, doc, *args, **kwargs):
            if coll.database.name == self.name and coll.name == collection:
                if after:
                    original(coll, doc, *args, **kwargs)
                raise RuntimeError('synthetic write/ack failure')
            return original(coll, doc, *args, **kwargs)
        return patch.object(Collection, 'insert_one', insert)

    def test_bootstrap_audit_failure(self):
        with self.inject_insert_failure('review_admin_bootstrap'), self.assertRaises(RuntimeError):
            self.adapter.create_local_review_admin(self.user())
        self.assertEqual(self.db.users.count_documents({}), 0)
        self.assertEqual(self.db.review_admin_bootstrap.count_documents({}), 0)
        self.bootstrap()
        self.assert_audited()

    def test_bootstrap_claim_ack_failure(self):
        with self.inject_insert_failure('review_admin_bootstrap', after=True), self.assertRaises(RuntimeError):
            self.adapter.create_local_review_admin(self.user())
        self.assertEqual(self.db.users.count_documents({}), 0)
        self.assertEqual(self.db.review_admin_bootstrap.count_documents({}), 1)
        with self.assertRaises(ValueError):
            self.adapter.create_local_review_admin(self.user())

    def test_failure_after_claim_before_identity(self):
        with self.inject_insert_failure('users'), self.assertRaises(RuntimeError):
            self.adapter.create_local_review_admin(self.user())
        self.assertEqual(self.db.users.count_documents({}), 0)
        self.assertEqual(self.db.review_admin_bootstrap.count_documents({}), 1)
        with self.assertRaises(ValueError):
            self.adapter.create_local_review_admin(self.user('retry'))

    def test_identity_ack_failure_is_audited_and_retry_fails(self):
        with self.inject_insert_failure('users', after=True), self.assertRaises(RuntimeError):
            self.adapter.create_local_review_admin(self.user())
        self.assert_audited()
        with self.assertRaises(ValueError):
            self.adapter.create_local_review_admin(self.user())
        self.assertEqual(self.db.users.count_documents({}), 1)

    def test_onboarding_failure_boundaries(self):
        self.bootstrap()
        for index, (collection, after) in enumerate([('review_admin_provisioning', False), ('review_admin_provisioning', True), ('users', False), ('users', True)]):
            u = self.user('target'+str(index), 'founder')
            with self.inject_insert_failure(collection, after=after), self.assertRaises(RuntimeError):
                self.onboard(u)
            exists = self.db.users.count_documents({'id': u['id']})
            self.assertEqual(exists, int(collection == 'users' and after))
            self.assert_audited()
            if collection == 'review_admin_provisioning' and not after:
                self.onboard(u)
            else:
                with self.assertRaises(ValueError):
                    self.onboard(u)

    def test_concurrent_onboarding_same_id(self):
        self.bootstrap()
        u = self.user('target', 'founder')
        self.assertCountEqual(self.race([lambda: self.onboard(u), lambda: self.onboard(u)]), ['ok', 'conflict'])
        self.assertEqual(self.db.review_admin_provisioning.count_documents({}), 1)
        self.assertEqual(self.db.users.count_documents({'id': 'target'}), 1)
        self.assert_audited()

    def test_concurrent_onboarding_same_email(self):
        self.bootstrap()
        users = [self.user('a', 'founder'), self.user('b', 'founder')]
        for u in users:
            u['email'] = 'same@synthetic.test'
        self.assertCountEqual(self.race([lambda u=u: self.onboard(u) for u in users]), ['ok', 'conflict'])
        self.assertEqual(self.db.users.count_documents({'email': 'same@synthetic.test'}), 1)
        self.assert_audited()

    def test_existing_normal_user_never_promoted(self):
        u = self.user()
        self.adapter.create('users', {**u, 'role': 'client'})
        with self.assertRaises(ValueError):
            self.adapter.create_local_review_admin(u)
        self.assertEqual(self.adapter.get('users', u['id'])['role'], 'client')
        self.assertEqual(self.db.review_admin_bootstrap.count_documents({}), 0)

    def test_onboarding_rejects_forged_authorizer_and_plain_admin(self):
        self.bootstrap()
        with self.assertRaises(ValueError):
            self.onboard(self.user('target', 'forged'))
        self.adapter.create('users', {'id': 'manual', 'email': 'manual@synthetic.test', 'role': 'admin'})
        self.adapter.create('sessions', {'id': 'manual-token', 'user_id': 'manual'})
        with self.assertRaises(ValueError):
            self.adapter.create_additional_review_admin(self.user('target', 'manual'), session_token='manual-token')
        with self.assertRaises(ValueError):
            self.adapter.create_additional_review_admin(self.user('target', 'founder'), session_token='missing')
        self.assertEqual(self.db.review_admin_provisioning.count_documents({}), 0)

    def test_wrong_scope_and_reserved_audit_fields(self):
        u = self.user(); u['provisioning']['scope'] = 'ALL'
        with self.assertRaises(ValueError): self.adapter.create_local_review_admin(u)
        u = self.user(); u['provisioning'].update(id='evil', _id='evil', user_id='evil')
        with self.assertRaises(ValueError): self.adapter.create_local_review_admin(u)
        self.assertEqual(self.db.users.count_documents({}), 0)

    def test_onboarding_existing_id_and_email_no_promotion(self):
        self.bootstrap()
        self.adapter.create('users', {'id': 'normal', 'email': 'normal@synthetic.test', 'role': 'client'})
        for uid, email in [('normal', 'other@synthetic.test'), ('other', 'normal@synthetic.test')]:
            u = self.user(uid, 'founder'); u['email'] = email
            with self.assertRaises(ValueError): self.onboard(u)
        self.assertEqual(self.adapter.get('users', 'normal')['role'], 'client')
        self.assertEqual(self.db.review_admin_provisioning.count_documents({}), 0)

    def test_missing_bootstrap_history_blocks_onboarding(self):
        self.bootstrap()
        # Synthetic corruption fixture, never a repair of real state.
        self.db.review_admin_bootstrap.delete_many({})
        with self.assertRaises(ValueError): self.onboard(self.user('target', 'founder'))
        self.assertEqual(self.db.review_admin_provisioning.count_documents({}), 0)

    def test_successful_onboarding_preserves_bootstrap_and_auth_contract(self):
        self.bootstrap()
        before = self.db.review_admin_bootstrap.find_one({})
        self.onboard(self.user('target', 'founder'))
        auth = MockAuthAdapter(self.adapter, seed_demo=False)
        result = auth.login('target@synthetic.test', 'Synthetic123!')
        self.assertEqual(auth.get_current_user(result['session_token'])['role'], 'admin')
        self.assertEqual(before, self.db.review_admin_bootstrap.find_one({}))
        self.assert_audited()
        with self.assertRaises(ValueError): self.onboard(self.user('target', 'founder'))

    def test_history_write_and_ack_failures(self):
        repo = MongoAuthorityRepository(self.db)
        with self.inject_insert_failure('legal_authority_versions'), self.assertRaises(RuntimeError):
            repo.save_version('v', {'source_id': 's'}, 'synthetic')
        self.assertIsNone(repo.get_version('v'))
        with self.inject_insert_failure('legal_authority_versions', after=True), self.assertRaises(RuntimeError):
            repo.save_version('v', {'source_id': 's'}, 'synthetic')
        repo.save_version('v', {'source_id': 's'}, 'synthetic')
        self.assertEqual(self.db.legal_authority_versions.count_documents({}), 1)

    def test_repository_id_indexes_reject_legacy_alias_duplicates(self):
        MongoAuthorityRepository(self.db); MongoReviewRepository(self.db)
        for name in ['legal_authority_heads', 'legal_authority_versions', 'legal_authority_reviews', 'legal_review_submissions']:
            self.db[name].insert_one({'_id': 'legacy', 'id': 'same'})
            with self.assertRaises(DuplicateKeyError): self.db[name].insert_one({'_id': 'other', 'id': 'same'})

    def test_unique_user_constraints_without_startup_indexes(self):
        self.bootstrap()
        for u in [{'id': 'founder', 'email': 'other@synthetic.test'}, {'id': 'other', 'email': 'founder@synthetic.test'}]:
            with self.assertRaises(DuplicateKeyError):
                self.db.users.insert_one({'_id': uuid4().hex, **u})

    def test_versions_canonical_retry_and_conflict(self):
        repo = MongoAuthorityRepository(self.db)
        repo.save_version('v', {'source_id': 's', 'text': 'original'}, 'synthetic')
        repo.save_version('v', {'text': 'original', 'source_id': 's'}, 'synthetic')
        with self.assertRaises(HistoryConflict): repo.save_version('v', {'source_id': 's', 'text': 'changed'}, 'synthetic')
        self.assertEqual(repo.get_version('v')['source']['text'], 'original')
        self.assertEqual(self.db.legal_authority_versions.count_documents({}), 1)

    def test_receipt_all_bindings_immutable_and_no_replay(self):
        authority = MongoAuthorityRepository(self.db); repo = MongoReviewRepository(self.db)
        authority.set_head('s', 'v')
        receipt = {'id': 'r', 'source_id': 's', 'reviewed_by': 'reviewer', 'decision': 'NEEDS_NEW_REVISION', 'rationale': 'synthetic', 'reviewed_at': 'time', 'input_version': 'v'}
        repo.save_review(receipt); repo.save_review(dict(reversed(list(receipt.items()))))
        for key in set(receipt) - {'id'}:
            with self.subTest(key=key), self.assertRaises(HistoryConflict):
                repo.save_review({**receipt, key: 'changed'})
        self.assertEqual(repo.get_review('r'), receipt)
        self.assertEqual(authority.get_head('s')['version'], 'v')
        self.assertEqual(self.db.legal_authority_reviews.count_documents({}), 1)

    def test_submissions_append_only(self):
        repo = MongoReviewRepository(self.db)
        item = {'id': 's', 'source_id': 'source', 'actor': 'synthetic'}
        repo.save_submission(item); repo.save_submission(item)
        with self.assertRaises(HistoryConflict): repo.save_submission({**item, 'actor': 'other'})

    def test_concurrent_head_cas_and_stale_or_missing(self):
        repo = MongoAuthorityRepository(self.db); repo.set_head('source', 'v1')
        self.assertCountEqual(self.race([lambda: repo.set_head('source', 'v2', 'v1'), lambda: repo.set_head('source', 'v3', 'v1')]), ['ok', 'conflict'])
        for args in [('source', 'v4', 'v1'), ('source', 'v5'), ('missing', 'v2', 'v1')]:
            with self.assertRaises(VersionConflict): repo.set_head(*args)
        self.assertEqual(self.db.legal_authority_heads.count_documents({}), 1)

    def test_head_interoperation_preserves_adapter_revision_and_metadata(self):
        repo = MongoAuthorityRepository(self.db)
        repo.set_head('s', 'v1')
        self.adapter.update('legal_authority_heads', 's', {'version': 'v2', 'extra': 'preserved'})
        repo.set_head('s', 'v3', 'v2')
        head = self.adapter.get('legal_authority_heads', 's')
        self.assertEqual(head['_revision'], 3)
        self.assertEqual(head['extra'], 'preserved')
        self.adapter.update('legal_authority_heads', 's', {'version': 'v4'})
        self.assertEqual(repo.get_head('s')['version'], 'v4')

    def test_concurrent_initial_heads(self):
        repo = MongoAuthorityRepository(self.db)
        self.assertCountEqual(self.race([lambda: repo.set_head('s', 'v1'), lambda: repo.set_head('s', 'v2')]), ['ok', 'conflict'])

    def test_concurrent_immutable_writes(self):
        repo = MongoAuthorityRepository(self.db)
        self.assertEqual(self.race([lambda: repo.save_version('v', {'source_id': 's'}, 'same') for _ in range(2)]), ['ok', 'ok'])
        self.assertCountEqual(self.race([lambda: repo.save_version('other', {'source_id': 's'}, 'one'), lambda: repo.save_version('other', {'source_id': 's'}, 'two')]), ['ok', 'conflict'])

    def test_adapter_history_cannot_be_mutated_or_deleted(self):
        for collection in self.adapter.IMMUTABLE_COLLECTIONS:
            self.adapter.create(collection, {'id': 'synthetic'})
            with self.assertRaises(ValueError): self.adapter.update(collection, 'synthetic', {'changed': True})
            with self.assertRaises(ValueError): self.adapter.delete(collection, 'synthetic')
            with self.assertRaises(ValueError): self.adapter.create(collection, {'id': 'synthetic', 'changed': True})

    def test_audit_events_insert_only(self):
        repo = MongoAuditRepository(self.db)
        with patch('backend.repositories.audit_repository.uuid4') as uuid:
            uuid.return_value.hex = 'fixed'
            repo.record_event('case', 'type', 'actor', {'synthetic': True})
            with self.assertRaises(DuplicateKeyError): repo.record_event('case', 'changed', 'actor', {})
        self.assertEqual(self.db.audit_events.find_one({})['event_type'], 'type')

    def test_active_mongo_review_service_contract(self):
        from backend.services.authority_review import AuthorityReview
        from backend.services.verified_corpus import VerifiedCorpus
        from backend.models.legal_foundation import LegalSource
        from backend.tests.legal_test_support import authority, test_knowledge
        self.bootstrap()
        workflow = AuthorityReview(VerifiedCorpus(self.adapter, test_knowledge()))
        value = LegalSource.model_validate(authority(ingestion_id='synthetic')).model_dump()
        self.adapter.create('legal_ingestion_requests', {'id': 'synthetic', 'state': 'PARSED',
            **{k: value[k] for k in ('registry_id', 'official_url', 'final_url', 'retrieved_at', 'raw_hash', 'content_hash', 'official_text')}})
        pending = workflow.submit(value, actor='synthetic-submitter')
        before = self.adapter.get('legal_authority_versions', pending['version_id'])
        requested = workflow.decide('fixture_act', pending['version_id'],
            reviewer=self.adapter.get('users', 'founder'), decision='NEEDS_NEW_REVISION', note='Synthetic correction')
        self.assertEqual(before, self.adapter.get('legal_authority_versions', pending['version_id']))
        repo = MongoReviewRepository(self.db)
        receipt = repo.get_review(requested['review_id'])
        self.assertEqual(receipt['input_version'], pending['version_id'])
        for field in ['reviewer_id', 'note', 'source_digest', 'source_id', 'reviewed_at', 'decision', 'input_version']:
            with self.assertRaises(HistoryConflict): repo.save_review({**receipt, field: 'changed'})
        repo.save_review(receipt)
        self.assertEqual(workflow.corpus.get('fixture_act')['version_id'], requested['version_id'])
        with self.assertRaises(ValueError):
            workflow.decide('fixture_act', pending['version_id'], reviewer=self.adapter.get('users', 'founder'),
                decision='NEEDS_NEW_REVISION', note='Stale synthetic retry')

    def test_repository_reads_adapter_history(self):
        self.adapter.create('legal_authority_versions', {'id': 'v', 'source': {'source_id': 's'}, 'reason': 'synthetic'})
        self.adapter.create('legal_authority_reviews', {'id': 'r', 'source_id': 's', 'decision': 'NEEDS_NEW_REVISION'})
        self.assertEqual(MongoAuthorityRepository(self.db).get_version('v')['source']['source_id'], 's')
        self.assertEqual(MongoReviewRepository(self.db).get_review('r')['decision'], 'NEEDS_NEW_REVISION')


if __name__ == '__main__':
    unittest.main()
