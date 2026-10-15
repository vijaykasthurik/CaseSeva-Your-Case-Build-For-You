"""Interactive, loopback-only administrative capability change; never legal review."""
import argparse
import getpass
import json
import sys
import warnings
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Invalid command. Enter credentials only at interactive prompts.\n')


def hidden(prompt):
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        return getpass.getpass(prompt)


def _api(base_url, method, path, *, token='', body=None, admin_token=''):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if admin_token:
        headers['X-Admin-Token'] = admin_token
    req = Request(base_url + path, data=json.dumps(body).encode() if body is not None else None,
                  method=method, headers=headers)
    try:
        with urlopen(req, timeout=30) as response:
            # Never print arbitrary server responses (which may include secrets).
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f'Capability request failed (HTTP {exc.code}); inspect local server diagnostics.') from None
    except (URLError, OSError, ValueError):
        raise RuntimeError('Transport/response failure; inspect account and audit before retrying.') from None


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('--advocate-id', required=True)
    parser.add_argument('--action', required=True, choices=['grant', 'revoke'])
    parser.add_argument('--reason', required=True)
    parser.add_argument('--host', default='127.0.0.1', choices=['127.0.0.1', 'localhost'])
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--additional-admin-credential', action='store_true')
    args = parser.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise SystemExit('A local interactive terminal is required.')
    if not 1 <= args.port <= 65535 or not args.reason.strip() or len(args.reason) > 1000:
        parser.error('Invalid port or reason')
    base = f'http://{args.host}:{args.port}'
    token = ''
    try:
        email = input('Platform administrator email: ').strip()
        password = hidden('Administrator password (hidden): ')
        session = _api(base, 'POST', '/api/auth/login', body={'email': email, 'password': password})
        token = session['session_token']
        password = None
        identity = _api(base, 'GET', '/api/auth/me', token=token)['user']
        if identity.get('role') != 'admin':
            raise RuntimeError('An authenticated platform administrator is required.')
        extra = hidden('Additional administrator credential (hidden): ') if args.additional_admin_credential else ''
        phrase = args.action.upper() + ' LEGAL AUTHORITY REVIEW'
        print(f'Target advocate: {args.advocate_id!r}; action: {args.action}. No legal decision will be made.')
        if input(f'Type {phrase!r}: ').strip() != phrase:
            raise RuntimeError('Confirmation did not match; no capability change requested.')
        _api(base, 'POST' if args.action == 'grant' else 'DELETE',
             '/api/admin/advocates/' + quote(args.advocate_id, safe='') + '/capabilities/legal-authority-review',
             token=token, admin_token=extra, body={'confirmation': phrase, 'reason': args.reason})
        print('Capability change completed. No legal authority decision occurred.')
        return 0
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
        raise SystemExit('Hidden credential entry unavailable or cancelled.')
    except (RuntimeError, KeyError):
        # RuntimeError messages above are fixed safe diagnostics.
        error = sys.exc_info()[1]
        raise SystemExit(str(error) if isinstance(error, RuntimeError) else 'Invalid authentication response.') from None
    finally:
        if token:
            try:
                _api(base, 'POST', '/api/auth/logout', token=token, body={})
            except RuntimeError:
                print('Session logout failed; end this session through the application.', file=sys.stderr)


if __name__ == '__main__':
    main()
