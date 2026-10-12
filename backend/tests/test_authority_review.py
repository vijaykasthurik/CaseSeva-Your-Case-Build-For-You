import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.adapters.real.official_sources import OfficialSourceAdapter
from backend.services.authority_review import AuthorityReview
from backend.services.verified_corpus import VerifiedCorpus
from backend.services.legal_visibility import authority_manifest, current_case_file
from backend.services.overview import client_case
from backend.services.sharing import shared_case
from backend.tests.legal_test_support import authority, test_knowledge, publish_reviewed
from backend.tests.helpers import test_app, client_account
from backend.routes.authorities import router


class AuthorityReviewTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = MockDatabaseAdapter(Path(folder.name) / 'db.json')
        self.corpus = VerifiedCorpus(self.db, test_knowledge())
        self.workflow = AuthorityReview(self.corpus)

    def test_download_is_not_review_and_timeout_is_persisted(self):
        adapter = Mock()
        adapter.fetch.side_effect = TimeoutError()
        failed = self.workflow.ingest('fixture', 'https://example.test/fixture', adapter=adapter)
        self.assertTrue(failed['retryable'])
        self.assertEqual(failed['state'], 'DISCOVERED')
        self.assertEqual(len(self.db.list('legal_ingestion_requests')), 1)
        self.assertFalse(self.corpus.validate_source(authority())[0])
        self.assertEqual(self.corpus.publish(authority())['verification'], 'PENDING')

    def test_receipt_is_bound_to_all_authority_content(self):
        source = publish_reviewed(self.corpus, authority())
        value = {k: v for k, v in source.items() if k not in {'version_id', 'reason'}}
        self.assertTrue(self.corpus.validate_source(value)[0])
        for field, replacement in [('effective_from', '1900-01-01'), ('quote', 'invented'),
            ('rules', {'forums': []}), ('reviewed_by', 'fake'), ('reviewed_at', '2020-01-01'),
            ('review_state', 'REJECTED'), ('source_reviewed', False), ('temporal_source_ids', [])]:
            with self.subTest(field=field):
                self.assertFalse(self.corpus.validate_source({**value, field: replacement})[0])

    def test_submitter_cannot_self_review_or_use_stale_revision(self):
        source = publish_reviewed(self.corpus, authority())
        value = {k: v for k, v in source.items() if k not in {'version_id', 'reason'}}
        value['version_note'] = 'Self-submitted revision'
        admin = self.db.get('users', 'test-independent-admin')
        pending = self.workflow.submit(value, actor=admin['id'])
        with self.assertRaises(PermissionError):
            self.workflow.decide(source['source_id'], pending['version_id'], reviewer=admin,
                                 decision='REVIEWED_PRIMARY', note='Self review')
        with self.assertRaises(ValueError):
            self.workflow.decide(source['source_id'], source['version_id'], reviewer=admin,
                                 decision='STALE', note='Old version')
        with self.assertRaises(PermissionError):
            self.workflow.decide(source['source_id'], pending['version_id'], reviewer={'id': 'fake', 'role': 'admin'},
                                 decision='REJECTED', note='Forged account')

    def test_download_binding_and_lifecycle(self):
        source = authority(raw_hash='bytes')
        def fetch(registry, url, on_download):
            on_download({'final_url': url, 'retrieved_at': source['retrieved_at'], 'raw_hash': 'bytes'})
            return {k: v for k, v in source.items() if k in {'registry_id', 'official_url', 'final_url', 'retrieved_at', 'raw_hash', 'content_hash', 'official_text'}}
        parsed = self.workflow.ingest('fixture', source['official_url'], adapter=SimpleNamespace(fetch=fetch))
        self.assertEqual([e['state'] for e in parsed['events']], ['DISCOVERED', 'DOWNLOADED', 'PARSED'])
        value = {**source, 'ingestion_id': parsed['id']}
        pending = self.workflow.submit(value, actor='ingestion')
        self.assertEqual(pending['review_state'], 'REVIEW_PENDING')
        self.assertEqual(pending['verification'], 'PENDING')
        self.assertIsNone(pending['reviewed_by'])
        with self.assertRaises(ValueError):
            self.workflow.submit({**value, 'official_text': 'replaced'}, actor='ingestion')

    def test_revocation_revision_staleness_and_removed_temporal_support_hide_file(self):
        for failure in ('REJECTED', 'STALE', 'revision', 'support_removed', 'expired'):
            with self.subTest(failure=failure):
                support = publish_reviewed(self.corpus, authority(source_id='commencement'))
                source = publish_reviewed(self.corpus, authority(temporal_source_ids=['commencement']))
                file = {'kind': 'SOURCE_VERIFIED_ENGINE1', 'version': 1, 'input_version': 1,
                    'authority_versions': authority_manifest(self.corpus, ['fixture_act']),
                    'applicable_law': [{'provision_id': 'fixture_act', 'source_version': source['version_id'],
                                       'title': 'Fixture', 'verification_status': 'VERIFIED'}]}
                case = {'case_id': 'c', 'owner_user_id': 'owner', 'input_version': 1, 'case_file': file,
                    'engine1_execution': 'ORCHESTRATED_CORE_V1', 'legal_foundation_requested': True,
                    'legal_foundation_status': 'READY', 'legal_case_file_current': True}
                self.assertEqual(current_case_file(case, corpus=self.corpus), file)
                if failure in {'REJECTED', 'STALE'}:
                    self.workflow.decide('fixture_act', source['version_id'], reviewer=self.db.get('users', 'test-independent-admin'), decision=failure, note='Test revocation')
                elif failure == 'revision':
                    publish_reviewed(self.corpus, authority(version_note='changed'))
                elif failure == 'expired':
                    self.corpus.knowledge.sources['fixture']['refresh_days'] = -1
                else:
                    self.db.delete('legal_authority_heads', 'commencement')
                self.assertEqual(current_case_file(case, corpus=self.corpus), {})
                with patch('backend.services.verified_corpus.VerifiedCorpus', return_value=self.corpus):
                    self.assertFalse(client_case(case, self.db)['engine1_available'])
                    self.assertEqual(shared_case(case, {'scopes': ['case_file'], 'evidence_ids': []}, self.db)['case_file'], {})
                self.corpus.knowledge.sources['fixture']['refresh_days'] = 30

    def test_official_adapter_bounded_retries_and_redirect_rejection(self):
        adapter = OfficialSourceAdapter(test_knowledge())
        with patch.object(adapter, '_fetch', side_effect=TimeoutError()), patch('backend.adapters.real.official_sources.time.sleep'):
            with self.assertRaises(TimeoutError):
                adapter.fetch('fixture', 'https://example.test/fixture')
            self.assertEqual(adapter._fetch.call_count, 2)
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.geturl.return_value = 'https://attacker.test/redirect'
        with patch('backend.adapters.real.official_sources.build_opener') as opener:
            opener.return_value.open.return_value = response
            with self.assertRaises(ValueError):
                adapter.fetch('fixture', 'https://example.test/fixture')


class AuthorityRouteTests(unittest.TestCase):
    def test_authentication_admin_gate_and_server_owned_identity(self):
        temp, app, client = test_app()
        self.addCleanup(temp.cleanup)
        app.include_router(router)
        user, headers = client_account(client, 'review')
        url = '/api/admin/authorities'
        self.assertEqual(client.get(url).status_code, 401)
        self.assertEqual(client.get(url, headers=headers).status_code, 403)
        self.assertEqual(client.post(url, headers=headers, json=authority()).status_code, 403)
        app.state.adapters.database.update('users', user['id'], {'role': 'admin'})
        with patch.dict('os.environ', {'ADMIN_TOKEN': ''}):
            self.assertEqual(client.get(url, headers=headers).status_code, 200)
            forged = {'expected_version': 'v', 'decision': 'REVIEWED_PRIMARY', 'note': 'review', 'reviewer_id': 'forged'}
            self.assertEqual(client.post(url+'/fixture_act/review', headers=headers, json=forged).status_code, 422)
        with patch.dict('os.environ', {'ADMIN_TOKEN': 'test-secret'}):
            self.assertEqual(client.get(url, headers=headers).status_code, 403)
