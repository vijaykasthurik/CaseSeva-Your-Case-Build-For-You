"""Offline regressions for bounded fixes against audit baseline 4fab446."""
import ast
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.database import mongo_client
from backend.adapters.mongo.storage import MongoGridFSStorageAdapter


class CurrentGenericityTests(unittest.TestCase):
    def test_connections_are_scoped_by_uri_and_reused_only_for_same_uri(self):
        # No real connections or credentials. Different deployments must not alias.
        with patch.object(mongo_client, '_clients', {}), patch.object(mongo_client.pymongo, 'MongoClient') as constructor:
            first, second = Mock(), Mock()
            constructor.side_effect = [first, second]
            self.assertIs(mongo_client.get_mongo_client('mongodb://localhost:27017'), first)
            self.assertIs(mongo_client.get_mongo_client('mongodb://localhost:27018'), second)
            self.assertIs(mongo_client.get_mongo_client('mongodb://localhost:27017'), first)
            self.assertEqual(constructor.call_count, 2)

    def test_gridfs_prefix_is_literal_like_other_object_stores(self):
        adapter = object.__new__(MongoGridFSStorageAdapter)
        keys = ['case.a/[1]/proof', 'caseXa/1/proof', 'other/proof']
        adapter.fs = Mock()
        adapter.fs.find.side_effect = lambda query: [SimpleNamespace(filename=k) for k in keys
            if not query or re.search(query['filename']['$regex'], k)]
        self.assertEqual(adapter.list('case.a/[1]/'), ['case.a/[1]/proof'])
        self.assertEqual(adapter.list('.*'), [])
        self.assertEqual(adapter.list(), sorted(keys))

    def test_legacy_fixture_guard_uses_supplied_application(self):
        # Execute only the guard expression; do not execute Engine 2 stages.
        path = Path(__file__).resolve().parents[1] / 'services/legal_analysis.py'
        tree = ast.parse(path.read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_legal_pipeline')
        guard = next(n.test for n in ast.walk(fn) if isinstance(n, ast.If)
                     and ast.unparse(n.test) == "llm_is_mock(app.state.adapters)")
        expression = compile(ast.Expression(guard), '<fixture guard>', 'eval')
        from backend.adapters.capabilities import llm_is_mock
        for mode in ('mock', 'mongodb', 'real', 'hybrid'):
            app = SimpleNamespace(state=SimpleNamespace(adapters=SimpleNamespace(mode=mode)))
            self.assertFalse(eval(expression, {'app': app, 'llm_is_mock': llm_is_mock}))
        for capability in ('mock', 'live', 'unavailable'):
            app.state.adapters.llm_processing_mode = capability
            self.assertEqual(eval(expression, {'app': app, 'llm_is_mock': llm_is_mock}), capability == 'mock')
