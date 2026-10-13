"""Interactive, one-time provisioning for this checkout's isolated review identity DB."""
import argparse
import getpass
import os
from pathlib import Path
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # Unknown arguments might contain a mistakenly supplied credential.
        self.exit(2, 'Unsupported invocation. Use --allow-admin-bootstrap; credentials are interactive only.\n')


def validate_local_environment(root):
    if Path.cwd().resolve() != root.resolve():
        raise ValueError('Run this command from the local project root')
    if not Path(sys.executable).resolve().is_relative_to((root / '.venv').resolve()):
        raise ValueError('Use this project virtual environment Python')
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ValueError('A local interactive terminal is required; redirected input is refused')
    if any(os.environ.get(k) for k in ('SSH_CONNECTION', 'SSH_CLIENT', 'SSH_TTY', 'REMOTEHOST')):
        raise ValueError('Remote bootstrap is not supported')
    if os.environ.get('SESSIONNAME', '').upper().startswith('RDP'):
        raise ValueError('Use a local console, not a remote desktop session')
    target = root / '.localdev' / 'phase4-authority-review' / 'identity.json'
    for path in (root, *root.parents, target.parent.parent, target.parent, target):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ValueError('Linked review paths are not supported')
    if str(root).startswith(('\\\\', '//')):
        raise ValueError('Network paths are not supported')
    if os.name == 'nt':
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(str(root.anchor)) != 3:
            raise ValueError('Bootstrap requires a fixed local drive')
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Identity database must stay inside this project')
    return target


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('--allow-admin-bootstrap', action='store_true')
    args = parser.parse_args(argv)
    if not args.allow_admin_bootstrap:
        parser.error('Bootstrap flag required')
    try:
        target = validate_local_environment(ROOT)
        print('Create one dedicated Phase 4 review administrator in the local identity database.')
        print('This is a development/review workflow, not production IAM/Cognito.')
        if input('Type CREATE REVIEW ADMIN to authorize: ').strip() != 'CREATE REVIEW ADMIN':
            raise ValueError('Confirmation not received; no account created')
        email = input('Administrator email: ')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('Administrator password (hidden, at least 8 characters): ')
            repeat = getpass.getpass('Confirm password (hidden): ')
        if password != repeat:
            raise ValueError('Passwords do not match; no account created')
        from backend.adapters.mock.auth import MockAuthAdapter
        from backend.adapters.mock.database import MockDatabaseAdapter
        MockAuthAdapter.validate_credentials(email, password)
        auth = MockAuthAdapter(MockDatabaseAdapter(target), seed_demo=False)
        auth.provision_local_review_admin(email, password, allow_bootstrap=True, operator=getpass.getuser())
        print('Local review administrator created. No session issued. Sign in normally to review authorities.')
        return 0
    except (ValueError, getpass.GetPassWarning) as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, EOFError, KeyboardInterrupt):
        print('Provisioning stopped; no credentials displayed. Check local terminal and file access.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
