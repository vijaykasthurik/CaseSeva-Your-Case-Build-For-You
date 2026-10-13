"""Authenticated local reviewer onboarding; never reopens one-time bootstrap."""
import argparse
import getpass
from pathlib import Path
import runpy
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
validate_local_environment = runpy.run_path(str(ROOT / 'scripts/provision-review-admin.py'))['validate_local_environment']


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Use --allow-reviewer-onboarding; all identities and credentials are entered interactively.\n')


def hidden_input(prompt):
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        return getpass.getpass(prompt)


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('--allow-reviewer-onboarding', action='store_true')
    args = parser.parse_args(argv)
    if not args.allow_reviewer_onboarding:
        parser.error('Explicit flag required')
    auth, token = None, None
    try:
        path = validate_local_environment(ROOT)
        if not path.is_file():
            raise ValueError('Existing review identity database required; this command cannot bootstrap')
        from backend.adapters.mock.auth import MockAuthAdapter
        from backend.adapters.mock.database import MockDatabaseAdapter
        auth = MockAuthAdapter(MockDatabaseAdapter(path), seed_demo=False)
        email = input('Existing administrator email: ')
        session = auth.login(email, hidden_input('Existing administrator password (hidden): '))
        token = session['session_token']
        if session['user'].get('role') != 'admin':
            raise ValueError('An authenticated existing administrator is required')
        print('Local development/review only. Creates a distinct account, not proof of independent human review.')
        if input('Type ADD REVIEW ADMIN to authorize: ').strip() != 'ADD REVIEW ADMIN':
            raise ValueError('Confirmation not received; no account created')
        new_email = input('Different reviewer email: ')
        password = hidden_input('New reviewer password (hidden, at least 8 characters): ')
        if password != hidden_input('Confirm new reviewer password (hidden): '):
            raise ValueError('Passwords do not match; no account created')
        auth.provision_additional_review_admin(new_email, password, session_token=token,
            allow_onboarding=True, operator=getpass.getuser())
        print('Reviewer account created. Bootstrap preserved. No authority reviewed or approved. The reviewer must sign in independently.')
        return 0
    except (ValueError, getpass.GetPassWarning) as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, EOFError, KeyboardInterrupt):
        print('Onboarding stopped. No credentials displayed. Check the local terminal and file access.', file=sys.stderr)
        return 1
    finally:
        if auth is not None and token:
            auth.logout(token)


if __name__ == '__main__':
    raise SystemExit(main())
