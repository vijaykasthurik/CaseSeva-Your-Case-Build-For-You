"""CLI safety tests use in-process doubles; never contact a server."""
import contextlib
import io
import runpy
import unittest
from unittest.mock import patch


class CapabilityCliTests(unittest.TestCase):
    def run_cli(self, confirmation, fail=False):
        module = runpy.run_path('scripts/grant-legal-authority-review.py')
        main = module['main']
        calls = []
        def api(base, method, path, **kwargs):
            calls.append(path)
            if path.endswith('/login'):
                return {'session_token': 'SYNTHETIC_SECRET_SESSION'}
            if path.endswith('/me'):
                return {'user': {'role': 'admin'}}
            if 'capabilities' in path and fail:
                raise RuntimeError('Synthetic failure')
            return {}
        output = io.StringIO()
        with patch.dict(main.__globals__, {'_api': api}), patch('sys.stdin.isatty', return_value=True), patch('sys.stderr.isatty', return_value=True), patch('builtins.input', side_effect=['admin@example.test', confirmation]), patch('getpass.getpass', return_value='SYNTHETIC_PASSWORD'), contextlib.redirect_stdout(output):
            try:
                main(['--advocate-id', 'synthetic', '--action', 'grant', '--reason', 'Synthetic qualification'])
            except SystemExit:
                pass
        self.assertEqual(calls[-1], '/api/auth/logout')
        self.assertNotIn('SYNTHETIC_PASSWORD', output.getvalue())
        self.assertNotIn('SYNTHETIC_SECRET_SESSION', output.getvalue())
        return calls

    def test_cancel_logs_out_without_change(self):
        self.assertFalse(any('capabilities' in p for p in self.run_cli('cancel')))

    def test_success_and_failure_log_out(self):
        for fail in (False, True):
            self.assertEqual(sum('capabilities' in p for p in self.run_cli('GRANT LEGAL AUTHORITY REVIEW', fail)), 1)

    def test_password_argv_and_noninteractive_refused(self):
        main = runpy.run_path('scripts/grant-legal-authority-review.py')['main']
        capture = io.StringIO()
        with contextlib.redirect_stderr(capture), self.assertRaises(SystemExit):
            main(['--password', 'SHOULD_NOT_ECHO'])
        self.assertNotIn('SHOULD_NOT_ECHO', capture.getvalue())
        with patch('sys.stdin.isatty', return_value=False), self.assertRaises(SystemExit):
            main(['--advocate-id', 'synthetic', '--action', 'grant', '--reason', 'test'])
