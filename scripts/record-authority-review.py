"""User-run authenticated review client. Secrets stay in memory and off argv/logs."""
import argparse
import getpass
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8012)
    parser.add_argument('--email', required=True)
    parser.add_argument('--source-id', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--decision', choices=['NEEDS_NEW_REVISION', 'REVIEWED_PRIMARY', 'REJECTED', 'STALE'], required=True)
    parser.add_argument('--reason-file', type=Path, required=True)
    parser.add_argument('--additional-admin-credential', action='store_true')
    args = parser.parse_args()
    reason = args.reason_file.read_text(encoding='utf-8').strip()
    headers = {'Content-Type': 'application/json'}
    def call(path, body=None):
        request = Request('http://127.0.0.1:' + str(args.port) + path,
            data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    try:
        session = call('/api/auth/login', {'email': args.email, 'password': getpass.getpass('Application password (hidden): ')})
        headers['Authorization'] = 'Bearer ' + session['session_token']
        try:
            if args.additional_admin_credential:
                headers['X-Admin-Token'] = getpass.getpass('Additional configured admin credential (hidden): ')
            call('/api/auth/me')
            result = call('/api/admin/authorities/' + args.source_id + '/review',
                {'expected_version': args.revision, 'decision': args.decision, 'note': reason})
            print(json.dumps({k: result.get(k) for k in ('source_id', 'version_id', 'review_state', 'revision_status', 'review_id', 'reviewed_by', 'reviewed_at')}, indent=2))
        finally:
            call('/api/auth/logout', {})
    except HTTPError as error:
        raise SystemExit('Review request failed with HTTP ' + str(error.code) + '; no credentials or response body printed.')


if __name__ == '__main__':
    main()
