"""Operator-only provisioning; never exposed as an HTTP registration endpoint.

Run: python -m backend.admin_command --email operator@example.com
Requires an existing account and the configured database credentials.
"""
import argparse
from pymongo.errors import PyMongoError
from .adapters.factory import load_operator_database
from .services.admin_promotion import promote_existing_user_to_admin


def main():
    parser = argparse.ArgumentParser(description="Grant administrator role to an existing account.")
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--email")
    identity.add_argument("--user-id", help="Existing account ID; also checks email uniqueness")
    args = parser.parse_args()
    try:
        db = load_operator_database()
        result = promote_existing_user_to_admin(db, args.email, user_id=args.user_id)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    except PyMongoError:
        parser.error("Database operation failed; any saved audit intent is retained. Resolve database availability or conflicting audit history before rerunning this command.")
    if result['status'] == 'already_admin':
        print("This account already has the administrator role.")
        return
    print("Administrator role assigned. Sign in again before opening verification administration.")


if __name__ == "__main__":
    main()
