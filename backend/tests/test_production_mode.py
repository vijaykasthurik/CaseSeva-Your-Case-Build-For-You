import os
import unittest
from unittest.mock import patch
from backend.adapters import factory


class ProductionModeTests(unittest.TestCase):
    def test_production_refuses_explicit_mock_configuration(self):
        with patch.dict(factory.env_vals_before_dotenv, {'USE_MOCK_AWS': 'true'}), patch.dict(os.environ, {'APP_ENV': 'production'}):
            with self.assertRaisesRegex(RuntimeError, 'refuses mock'):
                factory.load_adapters()
