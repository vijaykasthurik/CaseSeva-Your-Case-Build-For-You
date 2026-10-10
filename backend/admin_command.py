"""Operator-only provisioning; never exposed as an HTTP registration endpoint.

Run: python -m backend.admin_command --email operator@example.com
Requires an existing account and the configured database credentials.
"""
import argparse
from uuid import uuid4
from .adapters.factory import load_adapters
from .models.case import utc_now


def main():
    parser = argparse.ArgumentParser(description="Grant administrator role to an existing account.")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    adapters = load_adapters()
    db = adapters.database
    matches = [user for user in db.list("users") if user.get("email", "").lower() == args.email.strip().lower()]
    if len(matches) != 1:
        parser.error("Exactly one existing account must match; no account was changed.")
    user = matches[0]
    if user.get("role") == "admin":
        print("This account already has the administrator role.")
        return
    db.create("admin_role_audit", {"id": uuid4().hex, "user_id": user["id"], "previous_role": user.get("role"), "new_role": "admin", "assigned_at": utc_now(), "method": "OPERATOR_CLI"})
    db.update("users", user["id"], {"role": "admin"})
    print("Administrator role assigned. Sign in again before opening verification administration.")


if __name__ == "__main__":
    main()
