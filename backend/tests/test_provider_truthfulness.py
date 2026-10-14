"""Offline provider matrix; no AWS SDK or network required."""
import builtins
from contextlib import ExitStack
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.adapters import factory
from backend.adapters.capabilities import llm_is_live
from backend.routes.health import router
from backend.storage.object_store import get_object_store


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.constructors = {}
        for name in ('MongoDatabaseAdapter', 'MongoGridFSStorageAdapter', 'MockDatabaseAdapter',
                     'MockStorageAdapter', 'MockAuthAdapter'):
            self.constructors[name] = self.stack.enter_context(patch.object(factory, name))
        original = builtins.__import__
        def no_aws(name, *args, **kwargs):
            if name.split('.')[0] in {'boto3', 'botocore'}:
                raise AssertionError('AWS dependency attempted')
            return original(name, *args, **kwargs)
        self.stack.enter_context(patch('builtins.__import__', side_effect=no_aws))

    def test_absent_defaults_and_health(self):
        adapters = factory.load_adapters()
        self.assertEqual(adapters.providers, {'database': 'mongodb', 'object_store': 'mongodb', 'llm': 'mock', 'workflow': 'mock'})
        self.assertEqual(adapters.mode, 'mock')
        self.assertFalse(llm_is_live(adapters))
        app = FastAPI(); app.state.adapters = adapters; app.include_router(router)
        body = TestClient(app).get('/api/health').json()
        self.assertEqual(body['providers'], adapters.providers)
        self.assertEqual(body['processing_mode'], 'mock')
        self.assertEqual(body['capabilities'], {'llm': 'mock', 'workflow': 'mock'})
        with self.assertRaises(AttributeError):
            adapters.mode = 'mongodb'

    def test_matrix_validated_doubles(self):
        for llm in ('mock', 'live', 'unavailable'):
            for workflow in ('mock', 'live', 'unavailable'):
                with self.subTest(llm=llm, workflow=workflow):
                    adapters = factory.load_adapters()
                    adapters.llm = SimpleNamespace(processing_capability=llm)
                    adapters.workflow = SimpleNamespace(processing_capability=workflow)
                    expected = 'unavailable' if 'unavailable' in (llm, workflow) else llm if llm == workflow else 'hybrid'
                    self.assertEqual(adapters.processing_mode, expected)
                    self.assertEqual(llm_is_live(adapters), llm == 'live')
                    self.assertEqual(adapters.persistence_provider, 'mongodb')
                    app = FastAPI(); app.state.adapters = adapters; app.include_router(router)
                    body = TestClient(app).get('/api/health').json()
                    self.assertEqual(body['processing_mode'], expected)
                    self.assertEqual(body['capabilities'], {'llm': llm, 'workflow': workflow})

    def test_unknown_and_blank_fail_before_construction(self):
        for key in ('DATABASE_PROVIDER', 'OBJECT_STORE_PROVIDER', 'LLM_PROVIDER', 'WORKFLOW_PROVIDER', 'EMAIL_PROVIDER'):
            for value in ('unknown', '', '   ', 'mongodbb'):
                with self.subTest(key=key, value=value), patch.dict(os.environ, {key: value, 'USE_MONGODB': 'true', 'USE_REAL_STORAGE': 'true'}):
                    with self.assertRaises(factory.ProviderConfigurationError):
                        factory.load_adapters()
        for constructor in self.constructors.values():
            constructor.assert_not_called()

    def test_storage_and_database_are_independent_including_explicit_aws(self):
        import sys
        from unittest.mock import Mock
        database_module = SimpleNamespace(RealDatabaseAdapter=Mock())
        storage_module = SimpleNamespace(RealStorageAdapter=Mock())
        with patch.dict(sys.modules, {'backend.adapters.real.database': database_module,
                                     'backend.adapters.real.storage': storage_module}):
            for database in ('mongodb', 'mock', 'dynamodb'):
                for storage in ('mongodb', 'mock', 's3'):
                    with self.subTest(database=database, storage=storage), patch.dict(os.environ, {
                            'DATABASE_PROVIDER': database, 'OBJECT_STORE_PROVIDER': storage}):
                        adapters = factory.load_adapters()
                        self.assertEqual(adapters.persistence_provider, database)
                        self.assertEqual(adapters.object_store_provider, storage)
                        self.assertEqual(adapters.processing_mode, 'mock')
            self.assertEqual(database_module.RealDatabaseAdapter.call_count, 3)
            self.assertEqual(storage_module.RealStorageAdapter.call_count, 3)

    def test_storage_blank_argument_does_not_fallback(self):
        with self.assertRaises(ValueError):
            get_object_store('')

    def test_explicit_dimensions_override_legacy_flags(self):
        with patch.dict(os.environ, {'DATABASE_PROVIDER': 'mongodb', 'OBJECT_STORE_PROVIDER': 'gridfs', 'LLM_PROVIDER': 'mock', 'WORKFLOW_PROVIDER': 'mock', 'USE_REAL_DATABASE': 'true', 'USE_REAL_STORAGE': 'true', 'USE_REAL_LLM': 'true'}):
            self.assertEqual(factory.load_adapters().processing_mode, 'mock')
        with patch.dict(os.environ, {'USE_MOCK_AWS': 'false'}):
            self.assertEqual(factory.load_adapters().persistence_provider, 'mongodb')
        with patch.dict(os.environ, {'USE_MOCK_AWS': 'true'}):
            self.assertEqual(factory.load_adapters().persistence_provider, 'mock')

    def test_real_workflow_stub_and_unconfigured_llm_unavailable(self):
        with patch.dict(os.environ, {'WORKFLOW_PROVIDER': 'real'}):
            self.assertEqual(factory.load_adapters().processing_mode, 'unavailable')
        with patch.dict(os.environ, {'LLM_PROVIDER': 'bedrock'}):
            adapters = factory.load_adapters()
            self.assertEqual(adapters.processing_mode, 'unavailable')
            self.assertFalse(llm_is_live(adapters))
        with patch.dict(os.environ, {'LLM_PROVIDER': 'bedrock', 'AWS_BEARER_TOKEN_BEDROCK': 'synthetic-test-token'}):
            adapters = factory.load_adapters()
            self.assertEqual(adapters.processing_mode, 'hybrid')
            self.assertTrue(llm_is_live(adapters))

    def test_legacy_mode_never_authorizes_llm(self):
        for mode in ('mongodb', 'real', 'hybrid', 'mock'):
            self.assertFalse(llm_is_live(SimpleNamespace(mode=mode)))

    def test_malformed_legacy_flags_fail(self):
        with patch.dict(os.environ, {'USE_REAL_LLM': 'yes'}):
            with self.assertRaises(factory.ProviderConfigurationError):
                factory.load_adapters()


class MongoStartupWithoutAWSTests(unittest.TestCase):
    def test_application_startup_without_aws_sdk_or_credentials(self):
        import subprocess
        import sys
        from uuid import uuid4
        from backend.database.mongo_client import get_mongo_client
        name = "caseseva_provider_test_" + uuid4().hex
        client = get_mongo_client("mongodb://127.0.0.1:27017")
        self.addCleanup(lambda: client.drop_database(name))
        env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_")}
        env.update(DATABASE_PROVIDER="mongodb", OBJECT_STORE_PROVIDER="mongodb", LLM_PROVIDER="mock",
                   WORKFLOW_PROVIDER="mock", EMAIL_PROVIDER="disabled", USE_MOCK_AWS="false",
                   USE_REAL_DATABASE="false", USE_REAL_STORAGE="false", USE_REAL_LLM="false",
                   USE_MONGODB="false", APP_ENV="development", MONGODB_DATABASE=name,
                   MONGODB_URI="mongodb://127.0.0.1:27017", AWS_BEARER_TOKEN_BEDROCK="",
                   AWS_ACCESS_KEY_ID="", AWS_SECRET_ACCESS_KEY="", AWS_SESSION_TOKEN="")
        code = """
import builtins
original = builtins.__import__
def no_aws(name, *args, **kwargs):
    if name.split('.')[0] in {'boto3', 'botocore'}:
        raise AssertionError('AWS dependency attempted')
    return original(name, *args, **kwargs)
builtins.__import__ = no_aws
from backend.main import app
from fastapi.testclient import TestClient
with TestClient(app) as client:
    body = client.get('/api/health').json()
    assert body['providers'] == {'database': 'mongodb', 'object_store': 'mongodb', 'llm': 'mock', 'workflow': 'mock'}, body
    assert body['processing_mode'] == 'mock', body
    adapters = app.state.adapters
    adapters.database.create('cases', {'id': 'synthetic-provider-case', 'case_id': 'synthetic-provider-case'})
    assert adapters.database.get('cases', 'synthetic-provider-case')
    adapters.storage.upload('synthetic/proof.txt', b'synthetic provider test', 'text/plain')
    assert adapters.storage.download('synthetic/proof.txt') == b'synthetic provider test'
"""
        result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
