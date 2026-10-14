"""Interactive, local-only password rotation for an existing Phase-4 review administrator."""
import argparse
import getpass
from pathlib import Path
import runpy
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
validate_local_environment = runpy.run_path(str(ROOT / "scripts" / "provision-review-admin.py"))["validate_local_environment"]


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # Unknown arguments might contain an accidentally supplied credential
        self.exit(
            2,
            "Unsupported invocation. Use --allow-local-admin-password-reset; all credentials are entered interactively.\n",
        )


def hidden_input(prompt: str) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(prompt)


def main(argv=None) -> int:
    parser = SafeParser(description=__doc__)
    parser.add_argument("--allow-local-admin-password-reset", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_local_admin_password_reset:
        parser.error("Explicit flag --allow-local-admin-password-reset required")

    try:
        target = validate_local_environment(ROOT)
        if not target.is_file():
            raise ValueError("Existing review identity database required; no identity database found")

        print("Local Phase-4 review administrator password recovery.")
        print("Target database: isolated review identity database.")
        print("This utility rotates credentials for an ALREADY-EXISTING review administrator.")
        print("It never promotes users, never creates accounts, and invalidates all existing sessions.")

        confirmation = input("Type RESET REVIEW ADMIN PASSWORD to authorize: ").strip()
        if confirmation != "RESET REVIEW ADMIN PASSWORD":
            raise ValueError("Confirmation phrase not received; password reset aborted")

        email = input("Administrator email: ").strip()
        new_password = hidden_input("New administrator password (hidden, at least 8 characters): ")
        repeat_password = hidden_input("Confirm new administrator password (hidden): ")

        if new_password != repeat_password:
            raise ValueError("Passwords do not match; password reset aborted")

        from backend.adapters.mock.auth import MockAuthAdapter
        from backend.adapters.mock.database import MockDatabaseAdapter

        auth = MockAuthAdapter(MockDatabaseAdapter(target), seed_demo=False)
        user = auth.reset_local_review_admin_password(
            email=email,
            new_password=new_password,
            allow_reset=True,
            operator=getpass.getuser(),
            confirmation=confirmation,
        )

        print(f"Password successfully rotated for review administrator '{user['email']}' (ID: {user['id']}).")
        print("All prior sessions have been invalidated. Sign in using the review CLI.")
        return 0
    except (ValueError, getpass.GetPassWarning) as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, EOFError, KeyboardInterrupt):
        print(
            "Password rotation stopped; no credentials displayed. Check local terminal and file access.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
