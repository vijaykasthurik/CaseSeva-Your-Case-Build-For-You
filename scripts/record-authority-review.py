"""User-run authenticated review client. Secrets stay in memory and off argv/logs."""
import argparse
import getpass
import json
import sys
import warnings
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Invalid review command; credentials must be entered at the hidden local prompt.\n')


def hidden_input(prompt):
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        return getpass.getpass(prompt)


def main():
    parser = SafeParser()
    parser.add_argument('--port', type=int, default=8012)
    parser.add_argument('--email', required=True)
    parser.add_argument('--source-id', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--decision', choices=['NEEDS_NEW_REVISION', 'REVIEWED_PRIMARY', 'REJECTED', 'STALE'], required=True)
    parser.add_argument('--reason-file', type=Path, required=True)
    parser.add_argument('--additional-admin-credential', action='store_true')
    parser.add_argument('--corrected-source-file', type=Path,
        help='After verifying a NEEDS_NEW_REVISION receipt, submit this corrected candidate without approval')
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise SystemExit('A local interactive terminal is required for credential entry.')
    if args.corrected_source_file and args.decision != 'NEEDS_NEW_REVISION':
        parser.error('Corrected submission requires NEEDS_NEW_REVISION')
    reason = args.reason_file.read_text(encoding='utf-8').strip()
    corrected = json.loads(args.corrected_source_file.read_text(encoding='utf-8')) if args.corrected_source_file else None
    if corrected is not None and corrected.get('source_id') != args.source_id:
        parser.error('Corrected source must match the requested authority')
    headers = {'Content-Type': 'application/json'}
    def call(path, body=None):
        request = Request('http://127.0.0.1:' + str(args.port) + path,
            data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    try:
        password = hidden_input('Application password (hidden): ')
        session = call('/api/auth/login', {'email': args.email, 'password': password})
        headers['Authorization'] = 'Bearer ' + session['session_token']
        try:
            if args.additional_admin_credential:
                headers['X-Admin-Token'] = hidden_input('Additional configured admin credential (hidden): ')
            reviewer = call('/api/auth/me')['user']
            result = call('/api/admin/authorities/' + args.source_id + '/review',
                {'expected_version': args.revision, 'decision': args.decision, 'note': reason})
            history = call('/api/admin/authorities/' + args.source_id + '/history')
            receipt = next((r for r in history['reviews'] if r['id'] == result['review_id']), None)
            if (not receipt or receipt['input_version'] != args.revision or receipt['decision'] != args.decision
                    or receipt['reviewer_id'] != reviewer['id'] or receipt['reviewed_at'] != result['reviewed_at']):
                raise SystemExit('Receipt verification failed; corrected source was not submitted.')
            print(json.dumps({k: result.get(k) for k in ('source_id', 'version_id', 'review_state', 'revision_status', 'review_id', 'reviewed_by', 'reviewed_at')}, indent=2))
            if corrected is not None:
                metadata = corrected.setdefault('revision_metadata', {})
                metadata['preparation'] = {'status': 'AUTHENTICATED_SUBMISSION', 'authenticated_submission_recorded': True}
                metadata.setdefault('revision_request', {})['formal_admin_receipt_recorded'] = True
                fresh = call('/api/admin/authorities', corrected)
                final_history = call('/api/admin/authorities/' + args.source_id + '/history')
                saved = next((r for r in final_history['reviews'] if r['id'] == receipt['id']), None)
                if (saved != receipt or fresh['parent_revision'] != result['version_id']
                        or fresh['revision_request_id'] != receipt['id'] or fresh['review_state'] != 'REVIEW_PENDING'
                        or fresh['source_reviewed'] or fresh['review_id'] or fresh['version_id'] == result['version_id']):
                    raise SystemExit('Post-submission verification failed; inspect admin history. No approval was requested.')
                print(json.dumps({'corrected_revision': fresh['version_id'], 'review_state': fresh['review_state'],
                    'verification': fresh['verification'], 'immutable_receipt_verified': True, 'approved': False}, indent=2))
        finally:
            call('/api/auth/logout', {})
    except HTTPError as error:
        raise SystemExit('Review request failed with HTTP ' + str(error.code) + '; no credentials or response body printed.')
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
        raise SystemExit('Hidden credential entry unavailable or cancelled.')


if __name__ == '__main__':
    main()
