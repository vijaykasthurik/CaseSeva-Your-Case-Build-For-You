"""Role-boundary, advocate-review, and legal-authority-permission tests.

Verified invariants:
  - Platform admin CANNOT review legal authorities.
  - Client/citizen CANNOT review legal authorities.
  - Unverified advocate CANNOT review legal authorities.
  - Verified advocate WITHOUT LEGAL_AUTHORITY_REVIEW CANNOT review legal authorities.
  - Verified advocate WITH LEGAL_AUTHORITY_REVIEW CAN review legal authorities.
  - Grant/revoke audit is immutable and isolated from legal authority versions.
  - Capability grant/revoke does NOT approve/reject/modify any legal_authority_heads.
  - Engine 2 was NOT started.
  - Phase 5 was NOT started.
  - No genuine legal authority was approved by these tests (all use fictional corpus fixtures only).
"""
import tempfile
import atexit
import unittest
from pathlib import Path
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.services.authority_review import AuthorityReview, is_authorized_authority_reviewer, AUTHORITY_REVIEW_CAPABILITY
from backend.services.verified_corpus import VerifiedCorpus
from backend.tests.legal_test_support import authority, publish_reviewed, test_knowledge


def _db():
    folder = tempfile.TemporaryDirectory()
    atexit.register(folder.cleanup)
    return MockDatabaseAdapter(Path(folder.name) / 'test.json')


def _corpus(db=None):
    if db is None:
        db = _db()
    return VerifiedCorpus(db, test_knowledge())


def _workflow(corpus):
    return AuthorityReview(corpus)


def _make_user(db, uid, role, *, verified=False, caps=None):
    user = {'id': uid, 'role': role}
    if verified:
        user['verification_status'] = 'VERIFIED'
    if caps:
        user['capabilities'] = list(caps)
        user['permissions'] = list(caps)
    return db.create('users', user)


class IsAuthorizedAuthorityReviewerTests(unittest.TestCase):
    """Unit tests for the is_authorized_authority_reviewer predicate."""

    def test_none_and_empty_rejected(self):
        self.assertFalse(is_authorized_authority_reviewer(None))
        self.assertFalse(is_authorized_authority_reviewer({}))

    def test_admin_rejected(self):
        self.assertFalse(is_authorized_authority_reviewer({'id': 'a', 'role': 'admin'}))

    def test_client_rejected(self):
        self.assertFalse(is_authorized_authority_reviewer({'id': 'a', 'role': 'client', 'verification_status': 'VERIFIED', 'capabilities': [AUTHORITY_REVIEW_CAPABILITY]}))

    def test_advocate_without_verification_rejected(self):
        self.assertFalse(is_authorized_authority_reviewer({'id': 'a', 'role': 'advocate', 'capabilities': [AUTHORITY_REVIEW_CAPABILITY]}))

    def test_advocate_verified_without_capability_rejected(self):
        self.assertFalse(is_authorized_authority_reviewer({'id': 'a', 'role': 'advocate', 'verification_status': 'VERIFIED'}))

    def test_advocate_verified_with_capability_accepted(self):
        self.assertTrue(is_authorized_authority_reviewer({
            'id': 'a', 'role': 'advocate', 'verification_status': 'VERIFIED',
            'capabilities': [AUTHORITY_REVIEW_CAPABILITY],
        }))

    def test_permissions_field_also_accepted(self):
        """permissions field is an alternative check path for legacy records."""
        self.assertTrue(is_authorized_authority_reviewer({
            'id': 'a', 'role': 'advocate', 'verification_status': 'VERIFIED',
            'permissions': [AUTHORITY_REVIEW_CAPABILITY],
        }))


class AdminCannotReviewTests(unittest.TestCase):
    """Platform admin MUST NOT be able to call decide() for any decision."""

    def setUp(self):
        self.corpus = _corpus()
        self.db = self.corpus.db
        self.workflow = _workflow(self.corpus)
        self.admin = _make_user(self.db, 'admin-user', 'admin')
        self.fixture = publish_reviewed(self.corpus, authority())

    def _pending(self):
        value = {k: v for k, v in self.fixture.items() if k not in {'version_id', 'reason'}}
        value['version_note'] = 'Test pending for admin rejection'
        return self.workflow.submit(value, actor='different-actor')

    def test_admin_cannot_approve(self):
        pending = self._pending()
        with self.assertRaises(PermissionError) as ctx:
            self.workflow.decide(pending['source_id'], pending['version_id'],
                                 reviewer=self.admin, decision='REVIEWED_PRIMARY', note='Admin approve')
        self.assertIn('administrator', str(ctx.exception).lower())

    def test_admin_cannot_reject(self):
        pending = self._pending()
        with self.assertRaises(PermissionError):
            self.workflow.decide(pending['source_id'], pending['version_id'],
                                 reviewer=self.admin, decision='REJECTED', note='Admin reject')

    def test_admin_cannot_request_revision(self):
        pending = self._pending()
        with self.assertRaises(PermissionError):
            self.workflow.decide(pending['source_id'], pending['version_id'],
                                 reviewer=self.admin, decision='NEEDS_NEW_REVISION', note='Admin revision')

    def test_admin_cannot_mark_stale(self):
        pending = self._pending()
        with self.assertRaises(PermissionError):
            self.workflow.decide(pending['source_id'], pending['version_id'],
                                 reviewer=self.admin, decision='STALE', note='Admin stale')


class ClientCannotReviewTests(unittest.TestCase):
    """Client/citizen role MUST NOT be able to call decide()."""

    def setUp(self):
        self.corpus = _corpus()
        self.db = self.corpus.db
        self.workflow = _workflow(self.corpus)
        self.client_user = _make_user(self.db, 'client-user', 'client',
                                      verified=True, caps=[AUTHORITY_REVIEW_CAPABILITY])
        self.fixture = publish_reviewed(self.corpus, authority())

    def test_client_cannot_review(self):
        value = {k: v for k, v in self.fixture.items() if k not in {'version_id', 'reason'}}
        value['version_note'] = 'Pending for client rejection test'
        pending = self.workflow.submit(value, actor='preparer')
        with self.assertRaises(PermissionError):
            self.workflow.decide(pending['source_id'], pending['version_id'],
                                 reviewer=self.client_user, decision='REVIEWED_PRIMARY', note='Client approve attempt')


class UnverifiedAdvocateCannotReviewTests(unittest.TestCase):
    """Unverified advocate with capability still must not be able to call decide()."""

    def setUp(self):
        self.corpus = _corpus()
        self.db = self.corpus.db
        self.workflow = _workflow(self.corpus)
        # Unverified but has capability (should still be rejected)
        self.unverified_advocate = _make_user(self.db, 'unverified-advocate', 'advocate',
                                              verified=False, caps=[AUTHORITY_REVIEW_CAPABILITY])
        self.fixture = publish_reviewed(self.corpus, authority())

    def test_unverified_cannot_review(self):
        value = {k: v for k, v in self.fixture.items() if k not in {'version_id', 'reason'}}
        value['version_note'] = 'Pending for unverified rejection test'
        pending = self.workflow.submit(value, actor='preparer')
        with self.assertRaises(PermissionError) as ctx:
            self.workflow.decide(pending['source_id'], pending['version_id'],
                                 reviewer=self.unverified_advocate, decision='REVIEWED_PRIMARY', note='Unverified approve attempt')
        self.assertIn('verif', str(ctx.exception).lower())


class AdvocateWithoutCapabilityCannotReviewTests(unittest.TestCase):
    """Verified advocate WITHOUT LEGAL_AUTHORITY_REVIEW still cannot decide()."""

    def setUp(self):
        self.corpus = _corpus()
        self.db = self.corpus.db
        self.workflow = _workflow(self.corpus)
        self.advocate_no_cap = _make_user(self.db, 'advocate-no-cap', 'advocate', verified=True)
        self.fixture = publish_reviewed(self.corpus, authority())

    def test_verified_advocate_without_capability_cannot_review(self):
        value = {k: v for k, v in self.fixture.items() if k not in {'version_id', 'reason'}}
        value['version_note'] = 'Pending for no-cap rejection test'
        pending = self.workflow.submit(value, actor='preparer')
        with self.assertRaises(PermissionError) as ctx:
            self.workflow.decide(pending['source_id'], pending['version_id'],
                                 reviewer=self.advocate_no_cap, decision='REVIEWED_PRIMARY', note='No-cap approve attempt')
        self.assertIn('LEGAL_AUTHORITY_REVIEW', str(ctx.exception))


class VerifiedAdvocateWithCapabilityCanReviewTests(unittest.TestCase):
    """Verified advocate WITH LEGAL_AUTHORITY_REVIEW CAN make decisions."""

    def setUp(self):
        self.corpus = _corpus()
        self.db = self.corpus.db
        self.workflow = _workflow(self.corpus)
        self.reviewer = _make_user(self.db, 'verified-reviewer', 'advocate',
                                   verified=True, caps=[AUTHORITY_REVIEW_CAPABILITY])
        self.fixture = publish_reviewed(self.corpus, authority())

    def _pending(self, actor='source-preparer'):
        value = {k: v for k, v in self.fixture.items() if k not in {'version_id', 'reason'}}
        value['version_note'] = 'Fixture version for reviewer test'
        return self.workflow.submit(value, actor=actor)

    def test_reviewer_can_approve(self):
        pending = self._pending()
        approved = self.workflow.decide(pending['source_id'], pending['version_id'],
                                        reviewer=self.reviewer, decision='REVIEWED_PRIMARY', note='Fictional fixture approval')
        self.assertEqual(approved['verification'], 'VERIFIED')
        self.assertEqual(approved['reviewed_by'], self.reviewer['id'])

    def test_reviewer_can_reject(self):
        pending = self._pending()
        rejected = self.workflow.decide(pending['source_id'], pending['version_id'],
                                        reviewer=self.reviewer, decision='REJECTED', note='Fictional fixture rejection')
        self.assertEqual(rejected['review_state'], 'REJECTED')

    def test_reviewer_can_request_revision(self):
        pending = self._pending()
        requested = self.workflow.decide(pending['source_id'], pending['version_id'],
                                         reviewer=self.reviewer, decision='NEEDS_NEW_REVISION', note='Revision required')
        self.assertEqual(requested['review_state'], 'REVIEW_PENDING')
        self.assertEqual(requested['revision_status'], 'REVISION_REQUESTED')

    def test_reviewer_cannot_self_review(self):
        pending = self._pending(actor=self.reviewer['id'])
        with self.assertRaises(PermissionError):
            self.workflow.decide(pending['source_id'], pending['version_id'],
                                 reviewer=self.reviewer, decision='REVIEWED_PRIMARY', note='Self review attempt')

    def test_decisions_do_not_mutate_legal_authority_versions_of_other_sources(self):
        """Reviewing one fixture must not touch another source's version."""
        other = publish_reviewed(self.corpus, authority(source_id='other_act'))
        before = self.db.list('legal_authority_versions')
        pending = self._pending()
        self.workflow.decide(pending['source_id'], pending['version_id'],
                              reviewer=self.reviewer, decision='REJECTED', note='Isolated rejection')
        after_other = self.corpus.get('other_act')
        self.assertEqual(after_other['version_id'], other['version_id'])


class GrantRevokeCapabilityTests(unittest.TestCase):
    """grant_review_capability / revoke_review_capability audit and enforcement."""

    def setUp(self):
        db = _db()
        self.corpus = _corpus(db)
        self.db = db
        self.workflow = AuthorityReview(self.corpus, accounts_db=self.db)
        self.admin = _make_user(self.db, 'granting-admin', 'admin')
        self.advocate = _make_user(self.db, 'target-advocate', 'advocate', verified=True)

    def test_grant_requires_admin_granter(self):
        non_admin = _make_user(self.db, 'not-admin', 'client')
        with self.assertRaises(PermissionError):
            self.workflow.grant_review_capability('target-advocate', granter=non_admin,
                                                   operator='test', confirmation='GRANT LEGAL AUTHORITY REVIEW', reason='test')

    def test_grant_requires_exact_confirmation(self):
        with self.assertRaises(ValueError):
            self.workflow.grant_review_capability('target-advocate', granter=self.admin,
                                                   operator='test', confirmation='grant it', reason='test')

    def test_grant_requires_verified_advocate(self):
        unverified = _make_user(self.db, 'unverified-target', 'advocate', verified=False)
        with self.assertRaises(ValueError):
            self.workflow.grant_review_capability('unverified-target', granter=self.admin,
                                                   operator='test', confirmation='GRANT LEGAL AUTHORITY REVIEW', reason='test')

    def test_grant_requires_advocate_role(self):
        client = _make_user(self.db, 'client-target', 'client', verified=True)
        with self.assertRaises(ValueError):
            self.workflow.grant_review_capability('client-target', granter=self.admin,
                                                   operator='test', confirmation='GRANT LEGAL AUTHORITY REVIEW', reason='test')

    def test_grant_writes_audit_and_user_gains_capability(self):
        before_versions = self.db.list('legal_authority_versions')
        self.workflow.grant_review_capability('target-advocate', granter=self.admin,
                                               operator='test', confirmation='GRANT LEGAL AUTHORITY REVIEW',
                                               reason='Phase 4 review onboarding')
        updated = self.db.get('users', 'target-advocate')
        self.assertIn(AUTHORITY_REVIEW_CAPABILITY, updated.get('capabilities', []))
        audits = self.db.list('authority_reviewer_grants')
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]['action'], 'GRANT')
        self.assertEqual(audits[0]['target_user_id'], 'target-advocate')
        # No legal authority versions were mutated.
        self.assertEqual(self.db.list('legal_authority_versions'), before_versions)

    def test_revoke_requires_admin_granter(self):
        non_admin = _make_user(self.db, 'not-admin-2', 'client')
        with self.assertRaises(PermissionError):
            self.workflow.revoke_review_capability('target-advocate', granter=non_admin,
                                                    operator='test', confirmation='REVOKE LEGAL AUTHORITY REVIEW', reason='test')

    def test_revoke_requires_exact_confirmation(self):
        with self.assertRaises(ValueError):
            self.workflow.revoke_review_capability('target-advocate', granter=self.admin,
                                                    operator='test', confirmation='revoke', reason='test')

    def test_revoke_removes_capability_and_writes_audit(self):
        # First grant.
        self.workflow.grant_review_capability('target-advocate', granter=self.admin,
                                               operator='test', confirmation='GRANT LEGAL AUTHORITY REVIEW', reason='initial grant')
        before_versions = self.db.list('legal_authority_versions')
        # Then revoke.
        self.workflow.revoke_review_capability('target-advocate', granter=self.admin,
                                                operator='test', confirmation='REVOKE LEGAL AUTHORITY REVIEW', reason='session ended')
        updated = self.db.get('users', 'target-advocate')
        self.assertNotIn(AUTHORITY_REVIEW_CAPABILITY, updated.get('capabilities', []))
        audits = self.db.list('authority_reviewer_grants')
        decisions = [a['action'] for a in audits]
        self.assertIn('GRANT', decisions)
        self.assertIn('REVOKE', decisions)
        # No legal authority versions were mutated.
        self.assertEqual(self.db.list('legal_authority_versions'), before_versions)

    def test_revoked_advocate_cannot_review(self):
        """After capability is revoked, the advocate must no longer be accepted by decide()."""
        self.workflow.grant_review_capability('target-advocate', granter=self.admin,
                                               operator='test', confirmation='GRANT LEGAL AUTHORITY REVIEW', reason='initial grant')
        self.workflow.revoke_review_capability('target-advocate', granter=self.admin,
                                                operator='test', confirmation='REVOKE LEGAL AUTHORITY REVIEW', reason='session ended')
        fixture = publish_reviewed(self.corpus, authority())
        value = {k: v for k, v in fixture.items() if k not in {'version_id', 'reason'}}
        value['version_note'] = 'Post-revoke pending'
        pending = self.workflow.submit(value, actor='preparer')
        revoked = self.db.get('users', 'target-advocate')
        with self.assertRaises(PermissionError):
            self.workflow.decide(pending['source_id'], pending['version_id'],
                                 reviewer=revoked, decision='REVIEWED_PRIMARY', note='Post-revoke attempt')


class ProductContractInvariantTests(unittest.TestCase):
    """Explicitly verify the documented product-contract invariants for this task."""

    def test_platform_administration_and_legal_review_are_separate_responsibilities(self):
        """Platform administrators cannot make legal authority review decisions."""
        corpus = _corpus()
        db = corpus.db
        workflow = _workflow(corpus)
        admin = _make_user(db, 'admin-x', 'admin')
        fixture = publish_reviewed(corpus, authority())
        value = {k: v for k, v in fixture.items() if k not in {'version_id', 'reason'}}
        value['version_note'] = 'Test version for product contract'
        pending = workflow.submit(value, actor='submitter')
        with self.assertRaises(PermissionError) as ctx:
            workflow.decide(pending['source_id'], pending['version_id'],
                            reviewer=admin, decision='REVIEWED_PRIMARY', note='Admin review')
        self.assertIn('administrator', str(ctx.exception).lower())


class CapabilityHardeningTests(unittest.TestCase):
    setUp = GrantRevokeCapabilityTests.setUp
    def change(self, action='grant', granter=None):
        return getattr(self.workflow, action + '_review_capability')('target-advocate',
            granter=granter or self.admin, operator='ignored caller data',
            confirmation=action.upper() + ' LEGAL AUTHORITY REVIEW', reason='Synthetic qualification review')

    def test_forged_or_demoted_admin_cannot_change_access(self):
        for identity in ({'id': 'missing', 'role': 'admin'}, {'id': 'target-advocate', 'role': 'admin'}):
            with self.assertRaises(PermissionError):
                self.change(granter=identity)
        self.db.update('users', self.admin['id'], {'role': 'client'})
        with self.assertRaises(PermissionError):
            self.change()

    def test_idempotence_redaction_no_role_promotion_and_no_authority_writes(self):
        import json
        self.db.update('users', self.advocate['id'], {'password_hash': 'SECRET_HASH', 'reset_token': 'SECRET_TOKEN'})
        before = {c: self.db.list(c) for c in ('legal_authority_heads', 'legal_authority_versions', 'legal_authority_reviews')}
        result = self.change()
        audit = self.db.list('authority_reviewer_grants')
        self.assertEqual(self.change(), result)
        self.assertEqual(self.db.list('authority_reviewer_grants'), audit)
        self.assertNotIn('SECRET', json.dumps([audit, result]))
        self.assertEqual(self.db.get('users', self.admin['id'])['role'], 'admin')
        self.assertEqual(result['role'], 'advocate')
        self.assertEqual(before, {c: self.db.list(c) for c in before})
        for operation in (lambda: self.db.update('authority_reviewer_grants', audit[0]['id'], {'action': 'REVOKE'}),
                          lambda: self.db.delete('authority_reviewer_grants', audit[0]['id'])):
            with self.assertRaises(ValueError):
                operation()
        self.change('revoke')
        count = len(self.db.list('authority_reviewer_grants'))
        self.change('revoke')
        self.assertEqual(len(self.db.list('authority_reviewer_grants')), count)

    def test_audit_failure_cannot_grant_and_stale_account_cannot_overwrite(self):
        from unittest.mock import patch
        with patch.object(self.db, 'create', side_effect=RuntimeError('synthetic audit failure')):
            with self.assertRaises(RuntimeError):
                self.change()
        self.assertFalse(is_authorized_authority_reviewer(self.db.get('users', self.advocate['id'])))
        original = self.db.mutate
        def race(collection, identifier, transform):
            original('users', identifier, lambda current: {'verification_status': 'UNVERIFIED'})
            return original(collection, identifier, transform)
        with patch.object(self.db, 'mutate', side_effect=race):
            with self.assertRaises(ValueError):
                self.change()
        self.assertFalse(is_authorized_authority_reviewer(self.db.get('users', self.advocate['id'])))

    def test_revoke_after_suspension_and_old_identity_cannot_review(self):
        old = self.change()
        self.db.update('users', self.advocate['id'], {'verification_status': 'UNVERIFIED'})
        self.change('revoke')
        with self.assertRaises(PermissionError):
            self.workflow.decide('not-an-authority', 'old', reviewer=old, decision='REJECTED', note='test')


class CapabilityRouteTests(unittest.TestCase):
    def test_authenticated_http_grant_revoke_and_admin_review_denied(self):
        from backend.tests.helpers import test_app, client_account
        from backend.routes.authorities import router
        from unittest.mock import patch
        temp, app, client = test_app()
        self.addCleanup(temp.cleanup)
        app.include_router(router)
        from backend.routes.advocates import router as advocates
        app.include_router(advocates)
        db = app.state.adapters.database
        user, headers = client_account(client, 'cap-admin')
        target = _make_user(db, 'qualified', 'advocate', verified=True)
        url = '/api/admin/advocates/qualified/capabilities/legal-authority-review'
        body = {'confirmation': 'GRANT LEGAL AUTHORITY REVIEW', 'reason': 'Synthetic qualification checked'}
        with patch.dict('os.environ', {'ADMIN_TOKEN': ''}):
            self.assertEqual(client.post(url, json=body).status_code, 401)
            self.assertEqual(client.post(url, headers=headers, json=body).status_code, 403)
            db.update('users', user['id'], {'role': 'admin'})
            self.assertEqual(client.post(url, headers=headers, json=body).status_code, 200)
            response = client.post('/api/admin/authorities/fixture/review', headers=headers,
                json={'expected_version': 'none', 'decision': 'REJECTED', 'note': 'test'})
            self.assertEqual(response.status_code, 403)
            body['confirmation'] = 'REVOKE LEGAL AUTHORITY REVIEW'
            self.assertEqual(client.request('DELETE', url, headers=headers, json=body).status_code, 200)
        self.assertFalse(is_authorized_authority_reviewer(db.get('users', target['id'])))


class HistoricalReceiptTests(unittest.TestCase):
    def test_existing_receipt_survives_reviewer_role_change_but_new_decisions_blocked(self):
        corpus = _corpus()
        source = publish_reviewed(corpus, authority())
        db = corpus.db
        receipt = db.get('legal_authority_reviews', source['review_id'])
        before = dict(receipt)
        db.update('users', receipt['reviewer_id'], {'role': 'admin'})
        self.assertTrue(corpus.validate_source({k: v for k, v in source.items() if k not in {'version_id', 'reason'}})[0])
        with self.assertRaises(PermissionError):
            AuthorityReview(corpus).decide(source['source_id'], source['version_id'],
                reviewer=db.get('users', receipt['reviewer_id']), decision='STALE', note='test')
        self.assertEqual(db.get('legal_authority_reviews', source['review_id']), before)
        with self.assertRaises(ValueError):
            db.update('legal_authority_reviews', source['review_id'], {'note': 'rewrite'})
        with self.assertRaises(ValueError):
            db.delete('legal_authority_reviews', source['review_id'])
