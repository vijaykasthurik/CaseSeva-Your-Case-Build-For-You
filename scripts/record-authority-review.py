"""User-run authenticated review client. Secrets stay in memory and off argv/logs."""
import argparse
import getpass
import json
import sys
import warnings
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Invalid review command; credentials must be entered at the hidden local prompt.\n')


def hidden_input(prompt):
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        return getpass.getpass(prompt)


SAFE_FIELDS = {'body', 'query', 'path', 'header', 'email', 'password', 'expected_version',
    'decision', 'note', 'source_id', 'reviewed_by', 'reviewed_at', 'review_id', 'revision_status',
    'parent_revision', 'revision_request_id', 'official_text', 'quote', 'section_start', 'section_end'}
SAFE_VALIDATION = {
    'missing': 'Required field is missing', 'extra_forbidden': 'Unexpected field is not permitted',
    'literal_error': 'Value is not one of the permitted choices', 'string_type': 'Expected a string',
    'string_too_short': 'String is shorter than the permitted minimum',
    'string_too_long': 'String exceeds the permitted maximum', 'json_invalid': 'Invalid JSON body',
    'model_attributes_type': 'Expected an object', 'dict_type': 'Expected an object',
    'int_parsing': 'Expected an integer', 'value_error': 'Value failed validation',
}
SAFE_MESSAGES = {
    'Enter a valid email address.', 'Invalid email or password.', 'Please fix the highlighted fields.',
    'Administrator access required.', 'Additional administrator credential required.',
    'Authentication required', 'Invalid or expired session',
    'Authority revision changed; review the current revision', 'Authority changed during review',
    'Submit a new revision for independent review', 'The submitter cannot independently approve this authority',
    'Explicit decision and review rationale required',
    'Reviewer identity, time and revision lineage are server-owned',
    'Authority does not match its official download', 'A parsed official ingestion record is required',
    'A revision request requires corrected content or metadata',
    'Revision already attributed to another submitter; prepare a new revision',
}


def safe_http_failure(error, operation):
    """Allowlist structural diagnostics; never forward input, context, headers or arbitrary messages."""
    result = {'operation': operation, 'status': error.code}
    try:
        detail = json.loads(error.read(65536)).get('detail')
    except (ValueError, UnicodeError, AttributeError):
        detail = None
    if isinstance(detail, list):
        result['detail'] = []
        for item in detail[:20]:
            if not isinstance(item, dict):
                continue
            code = item.get('type')
            code = code if code in SAFE_VALIDATION else 'validation_error'
            loc = item.get('loc', [])
            if not isinstance(loc, (list, tuple)):
                loc = []
            result['detail'].append({'loc': [x if isinstance(x, str) and x in SAFE_FIELDS else '<redacted>' for x in loc[:8]],
                'type': code, 'message': SAFE_VALIDATION.get(code, 'Request validation failed')})
    elif isinstance(detail, str) and detail in SAFE_MESSAGES:
        result['detail'] = detail
    elif isinstance(detail, dict):
        message = detail.get('message')
        result['detail'] = {'message': message if isinstance(message, str) and message in SAFE_MESSAGES else 'Request validation failed'}
        fields = detail.get('fields')
        if isinstance(fields, dict):
            result['detail']['fields'] = {k if k in SAFE_FIELDS else '<redacted>':
                v if isinstance(v, str) and v in SAFE_MESSAGES else 'Field validation failed' for k,v in list(fields.items())[:20]}
    else:
        result['detail'] = 'Unrecognized server detail withheld; inspect server diagnostics locally'
    return json.dumps(result, indent=2)


class ReviewHTTPFailure(Exception):
    pass


def continue_correction(call, source_id, expected_head, receipt_id, corrected):
    """One source POST only; never make a review decision or retry a write."""
    path = '/api/admin/authorities/' + source_id + '/history'
    history = call(path, operation='preflight_correction_history')
    versions = {v['id']: v['source'] for v in history['versions']}
    current = versions.get(expected_head, {})
    receipt = next((r for r in history['reviews'] if r['id'] == receipt_id), None)
    if (history['current_revision'] != expected_head or not receipt
            or receipt['source_id'] != source_id or receipt['decision'] != 'NEEDS_NEW_REVISION'
            or current.get('review_id') != receipt_id
            or current.get('revision_status') != 'REVISION_REQUESTED'
            or current.get('review_state') != 'REVIEW_PENDING'
            or any(v.get('parent_revision') == expected_head for v in versions.values())
            or any(r['reviewed_at'] > receipt['reviewed_at'] for r in history['reviews'])):
        raise SystemExit('Continuation preflight failed; no source posted. Inspect history before proceeding.')
    protected = ('official_text', 'quote', 'content_hash', 'raw_hash', 'section_start', 'section_end')
    if (corrected.get('source_id') != source_id
            or set(corrected) & {'reviewed_by', 'reviewed_at', 'review_id', 'revision_status', 'parent_revision', 'revision_request_id'}
            or any(corrected.get(k) != current.get(k) for k in protected)):
        raise SystemExit('Correction payload binding failed; no source posted.')
    fresh = call('/api/admin/authorities', corrected, operation='submit_correction_only')
    final = call(path, operation='verify_correction_only')
    stored = next((v['source'] for v in final['versions'] if v['id'] == fresh['version_id']), None)
    expected = {'parent_revision': expected_head, 'revision_request_id': receipt_id,
                'review_state': 'REVIEW_PENDING', 'revision_status': 'NONE', 'verification': 'PENDING',
                'source_reviewed': False, 'review_id': None, 'reviewed_by': None, 'reviewed_at': None}
    prior = {v['id']: v for v in history['versions']}
    after = {v['id']: v for v in final['versions']}
    if (fresh['version_id'] in prior or final['current_revision'] != fresh['version_id'] or not stored
            or final['reviews'] != history['reviews']
            or any(after.get(k) != v for k, v in prior.items())
            or any(stored.get(k) != v or fresh.get(k) != v for k, v in expected.items())
            or any(stored.get(k) != current.get(k) for k in protected)):
        raise SystemExit('Post-write verification failed. Do not retry; inspect history for partial writes.')
    print(json.dumps({'operation': 'submit_correction_only', 'new_revision': fresh['version_id'],
        **expected, 'approved': False, 'existing_receipt_unchanged': True,
        'statutory_binding_unchanged': True}, indent=2))


def main():
    parser = SafeParser()
    parser.add_argument('--port', type=int, default=8012)
    parser.add_argument('--email')
    parser.add_argument('--source-id', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--decision', choices=['NEEDS_NEW_REVISION', 'REVIEWED_PRIMARY', 'REJECTED', 'STALE'])
    parser.add_argument('--reason-file', type=Path)
    parser.add_argument('--submit-correction-only', action='store_true')
    parser.add_argument('--existing-receipt')
    parser.add_argument('--additional-admin-credential', action='store_true')
    parser.add_argument('--corrected-source-file', type=Path,
        help='After verifying a NEEDS_NEW_REVISION receipt, submit this corrected candidate without approval')
    parser.add_argument('--check-access-only', action='store_true',
        help='Login, check identity and read authority history, then logout; never post a review or source')
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise SystemExit('A local interactive terminal is required for credential entry.')
    if args.submit_correction_only:
        if not args.corrected_source_file or not args.existing_receipt or args.decision or args.reason_file or args.check_access_only:
            parser.error('Continuation requires only an existing receipt and corrected source')
    elif not args.decision or not args.reason_file or args.existing_receipt:
        parser.error('Review mode requires decision and reason')
    if args.corrected_source_file and not args.submit_correction_only and args.decision != 'NEEDS_NEW_REVISION':
        parser.error('Corrected submission requires NEEDS_NEW_REVISION')
    reason = args.reason_file.read_text(encoding='utf-8-sig').strip() if args.reason_file else None
    corrected = json.loads(args.corrected_source_file.read_text(encoding='utf-8-sig')) if args.corrected_source_file else None
    if corrected is not None and corrected.get('source_id') != args.source_id:
        parser.error('Corrected source must match the requested authority')
    headers = {'Content-Type': 'application/json'}
    def call(path, body=None, *, operation):
        request = Request('http://127.0.0.1:' + str(args.port) + path,
            data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as error:
            raise ReviewHTTPFailure(safe_http_failure(error, operation)) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise ReviewHTTPFailure(json.dumps({'operation': operation,
                'detail': 'Transport or response failure. Do not retry; inspect history for possible partial writes.'})) from None
    try:
        email = args.email or input('Administrator email: ').strip()
        password = hidden_input('Application password (hidden): ')
        session = call('/api/auth/login', {'email': email, 'password': password}, operation='login')
        headers['Authorization'] = 'Bearer ' + session['session_token']
        try:
            if args.additional_admin_credential:
                headers['X-Admin-Token'] = hidden_input('Additional configured admin credential (hidden): ')
            reviewer = call('/api/auth/me', operation='authenticated_identity')['user']
            if args.submit_correction_only:
                continue_correction(call, args.source_id, args.revision, args.existing_receipt, corrected)
                return
            if args.check_access_only:
                history = call('/api/admin/authorities/' + args.source_id + '/history', operation='read_authority_history')
                print(json.dumps({'operation': 'check_access_only', 'current_revision': history['current_revision'],
                    'expected_revision_matches': history['current_revision'] == args.revision,
                    'review_receipt_count': len(history['reviews']), 'review_or_source_posted': False}, indent=2))
                return
            result = call('/api/admin/authorities/' + args.source_id + '/review',
                {'expected_version': args.revision, 'decision': args.decision, 'note': reason}, operation='record_review_decision')
            history = call('/api/admin/authorities/' + args.source_id + '/history', operation='verify_review_receipt')
            receipt = next((r for r in history['reviews'] if r['id'] == result['review_id']), None)
            if (not receipt or receipt['input_version'] != args.revision or receipt['decision'] != args.decision
                    or receipt['reviewer_id'] != reviewer['id'] or receipt['reviewed_at'] != result['reviewed_at']):
                raise SystemExit('Receipt verification failed; corrected source was not submitted.')
            print(json.dumps({k: result.get(k) for k in ('source_id', 'version_id', 'review_state', 'revision_status', 'review_id', 'reviewed_by', 'reviewed_at')}, indent=2))
            if corrected is not None:
                metadata = corrected.setdefault('revision_metadata', {})
                metadata['preparation'] = {'status': 'AUTHENTICATED_SUBMISSION', 'authenticated_submission_recorded': True}
                metadata.setdefault('revision_request', {})['formal_admin_receipt_recorded'] = True
                fresh = call('/api/admin/authorities', corrected, operation='submit_corrected_source')
                final_history = call('/api/admin/authorities/' + args.source_id + '/history', operation='verify_corrected_revision')
                saved = next((r for r in final_history['reviews'] if r['id'] == receipt['id']), None)
                if (saved != receipt or fresh['parent_revision'] != result['version_id']
                        or fresh['revision_request_id'] != receipt['id'] or fresh['review_state'] != 'REVIEW_PENDING'
                        or fresh['source_reviewed'] or fresh['review_id'] or fresh['version_id'] == result['version_id']):
                    raise SystemExit('Post-submission verification failed; inspect admin history. No approval was requested.')
                print(json.dumps({'corrected_revision': fresh['version_id'], 'review_state': fresh['review_state'],
                    'verification': fresh['verification'], 'immutable_receipt_verified': True, 'approved': False}, indent=2))
        finally:
            prior_failure = sys.exc_info()[0] is not None
            try:
                call('/api/auth/logout', {}, operation='logout')
            except ReviewHTTPFailure as error:
                if not prior_failure:
                    raise
                print(str(error), file=sys.stderr)
    except ReviewHTTPFailure as error:
        raise SystemExit(str(error))
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
        raise SystemExit('Hidden credential entry unavailable or cancelled.')


if __name__ == '__main__':
    main()
