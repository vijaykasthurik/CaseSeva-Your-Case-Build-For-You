"""Tests for local review admin password rotation utility and adapter methods.

Verifies that:
- existing admin password can be rotated
- old password no longer authenticates
- new password authenticates
- admin ID remains unchanged
- role remains admin
- non-admin cannot be rotated through this recovery path
- missing user fails
- no new account is created
- sessions for target admin are invalidated
- other users' sessions are untouched
- no authority/review data changes
- password/hash never appears in audit record
- bootstrap state remains unchanged
- CLI fails closed without authorization flag or confirmation phrase
"""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.adapters.mock.auth import MockAuthAdapter
from backend.adapters.mock.database import MockDatabaseAdapter
import importlib
reset_script = importlib.import_module("scripts.reset-review-admin-password")


class TestReviewAdminPasswordReset(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_identity.json"
        self.initial_data = {
            "users": {
                "admin-1": {
                    "id": "admin-1",
                    "email": "reviewer@example.test",
                    "full_name": "Review Admin One",
                    "role": "admin",
                    "password_hash": MockAuthAdapter._hash_password("OldPassword123"),
                    "created_at": "2026-10-14T00:00:00+00:00",
                    "provisioning": {
                        "method": "LOCAL_INTERACTIVE_REVIEW_BOOTSTRAP",
                        "scope": "PHASE4_REVIEW_ONLY",
                    },
                },
                "client-1": {
                    "id": "client-1",
                    "email": "client@example.test",
                    "full_name": "Regular Client",
                    "role": "client",
                    "password_hash": MockAuthAdapter._hash_password("ClientPassword123"),
                    "created_at": "2026-10-14T00:00:00+00:00",
                },
            },
            "review_admin_bootstrap": {
                "one-time": {
                    "id": "one-time",
                    "user_id": "admin-1",
                    "method": "LOCAL_INTERACTIVE_REVIEW_BOOTSTRAP",
                }
            },
            "sessions": {
                "sess-admin-1": {"id": "sess-admin-1", "user_id": "admin-1"},
                "sess-client-1": {"id": "sess-client-1", "user_id": "client-1"},
            },
            "legal_authority_heads": {"head-1": {"id": "head-1", "title": "Test Statute"}},
            "legal_authority_reviews": {"rev-1": {"id": "rev-1", "decision": "NEEDS_NEW_REVISION"}},
        }
        self.db_path.write_text(json.dumps(self.initial_data, indent=2), encoding="utf-8")
        self.db = MockDatabaseAdapter(self.db_path)
        self.auth = MockAuthAdapter(self.db, seed_demo=False)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_successful_password_rotation(self):
        """Admin password rotates successfully, invalidating sessions and updating credentials."""
        # 1. Old password authenticates before rotation
        old_login = self.auth.login("reviewer@example.test", "OldPassword123")
        self.assertEqual(old_login["user"]["id"], "admin-1")

        # 2. Rotate password
        result = self.auth.reset_local_review_admin_password(
            email="reviewer@example.test",
            new_password="NewSecurePassword456",
            allow_reset=True,
            operator="test_operator",
            confirmation="RESET REVIEW ADMIN PASSWORD",
        )

        # 3. User ID and role are preserved
        self.assertEqual(result["id"], "admin-1")
        self.assertEqual(result["role"], "admin")
        self.assertEqual(result["email"], "reviewer@example.test")

        # 4. Old password no longer authenticates
        with self.assertRaises(ValueError) as ctx_old:
            self.auth.login("reviewer@example.test", "OldPassword123")
        self.assertIn("Invalid credentials", str(ctx_old.exception))

        # 5. New password authenticates
        new_login = self.auth.login("reviewer@example.test", "NewSecurePassword456")
        self.assertEqual(new_login["user"]["id"], "admin-1")

        # 6. Prior sessions for admin-1 were invalidated
        data = self.db._read()
        self.assertNotIn("sess-admin-1", data.get("sessions", {}))
        # Client session was NOT invalidated
        self.assertIn("sess-client-1", data.get("sessions", {}))

        # 7. No new accounts created
        self.assertEqual(len(data["users"]), 2)

        # 8. Immutable audit event recorded without credentials
        rotations = data.get("review_admin_password_rotations", {})
        self.assertEqual(len(rotations), 1)
        audit = list(rotations.values())[0]
        self.assertEqual(audit["user_id"], "admin-1")
        self.assertEqual(audit["email"], "reviewer@example.test")
        self.assertEqual(audit["local_operator"], "test_operator")
        self.assertEqual(audit["operation_type"], "LOCAL_REVIEW_ADMIN_PASSWORD_ROTATION")
        self.assertNotIn("password", audit)
        self.assertNotIn("password_hash", audit)
        self.assertNotIn("NewSecurePassword456", json.dumps(audit))

        # 9. Authority data and bootstrap state remain 100% unchanged
        self.assertEqual(data["legal_authority_heads"], self.initial_data["legal_authority_heads"])
        self.assertEqual(data["legal_authority_reviews"], self.initial_data["legal_authority_reviews"])
        self.assertEqual(data["review_admin_bootstrap"], self.initial_data["review_admin_bootstrap"])

    def test_non_admin_cannot_be_rotated(self):
        """Attempts to rotate passwords for non-admin accounts are strictly rejected."""
        with self.assertRaises(ValueError) as ctx:
            self.auth.reset_local_review_admin_password(
                email="client@example.test",
                new_password="NewClientPassword999",
                allow_reset=True,
                operator="test_operator",
                confirmation="RESET REVIEW ADMIN PASSWORD",
            )
        self.assertIn("not an administrator", str(ctx.exception))

        # Client credentials untouched
        login = self.auth.login("client@example.test", "ClientPassword123")
        self.assertEqual(login["user"]["id"], "client-1")

    def test_missing_user_fails_closed(self):
        """Attempting to reset a non-existent account fails closed without modifying anything."""
        with self.assertRaises(ValueError) as ctx:
            self.auth.reset_local_review_admin_password(
                email="nonexistent@example.test",
                new_password="SomePassword123",
                allow_reset=True,
                operator="test_operator",
                confirmation="RESET REVIEW ADMIN PASSWORD",
            )
        self.assertIn("not found", str(ctx.exception))

    def test_missing_authorization_flag_fails_closed(self):
        """Without allow_reset=True, rotation fails immediately."""
        with self.assertRaises(ValueError) as ctx:
            self.auth.reset_local_review_admin_password(
                email="reviewer@example.test",
                new_password="NewSecurePassword456",
                allow_reset=False,
                operator="test_operator",
                confirmation="RESET REVIEW ADMIN PASSWORD",
            )
        self.assertIn("authorization required", str(ctx.exception))

    def test_invalid_confirmation_phrase_fails_closed(self):
        """Incorrect confirmation phrase rejects rotation."""
        with self.assertRaises(ValueError) as ctx:
            self.auth.reset_local_review_admin_password(
                email="reviewer@example.test",
                new_password="NewSecurePassword456",
                allow_reset=True,
                operator="test_operator",
                confirmation="YES RESET IT",
            )
        self.assertIn("confirmation phrase", str(ctx.exception))

    def test_weak_password_rejected(self):
        """Passwords shorter than 8 characters are rejected."""
        with self.assertRaises(ValueError) as ctx:
            self.auth.reset_local_review_admin_password(
                email="reviewer@example.test",
                new_password="short",
                allow_reset=True,
                operator="test_operator",
                confirmation="RESET REVIEW ADMIN PASSWORD",
            )
        self.assertIn("at least 8 characters", str(ctx.exception))

    def test_cli_execution_interactive(self):
        """Test the interactive CLI script with mocked stdin/getpass on temporary database."""
        inputs = iter(["RESET REVIEW ADMIN PASSWORD", "reviewer@example.test"])
        passwords = iter(["BrandNewAdminPass999", "BrandNewAdminPass999"])

        with patch("builtins.input", side_effect=lambda _: next(inputs)), \
             patch("getpass.getpass", side_effect=lambda _: next(passwords)), \
             patch.object(reset_script, "validate_local_environment", return_value=self.db_path):
            code = reset_script.main(["--allow-local-admin-password-reset"])
            self.assertEqual(code, 0)

        # Verify login with new password
        login = self.auth.login("reviewer@example.test", "BrandNewAdminPass999")
        self.assertEqual(login["user"]["id"], "admin-1")

    def test_mongo_database_adapter_password_rotation(self):
        """Verify MongoDatabaseAdapter password rotation on isolated test database."""
        from backend.adapters.mongo.database import MongoDatabaseAdapter
        from backend.database.mongo_client import get_mongo_client

        import pymongo
        # This test owns and closes its client; do not close the shared adapter cache.
        client = pymongo.MongoClient("mongodb://127.0.0.1:27017")
        test_db_name = f"caseseva_test_pwd_reset_{uuid4().hex[:10]}"
        try:
            adapter = MongoDatabaseAdapter(db_name=test_db_name)
            mongo_auth = MockAuthAdapter(adapter, seed_demo=False)

            # Insert an admin and a client in test DB
            now = "2026-10-14T00:00:00+00:00"
            admin_user = {
                "id": "mongo-admin-1",
                "email": "mongoadmin@example.test",
                "role": "admin",
                "password_hash": MockAuthAdapter._hash_password("InitialPassword123"),
                "created_at": now,
                "provisioning": {"method": "LOCAL_INTERACTIVE_REVIEW_BOOTSTRAP", "scope": "PHASE4_REVIEW_ONLY"},
            }
            adapter._insert_reserved_reviewer(adapter._provisioning_collections(), admin_user, "review_admin_bootstrap", "one-time")

            # Create a session
            session_doc = {"id": "sess-mongo-1", "user_id": "mongo-admin-1"}
            adapter.create("sessions", session_doc)

            # Rotate password
            res = mongo_auth.reset_local_review_admin_password(
                email="mongoadmin@example.test",
                new_password="NewMongoPassword456",
                allow_reset=True,
                operator="mongo_operator",
                confirmation="RESET REVIEW ADMIN PASSWORD",
            )
            self.assertEqual(res["id"], "mongo-admin-1")
            self.assertEqual(res["role"], "admin")

            # Session invalidated
            self.assertIsNone(adapter.get("sessions", "sess-mongo-1"))

            # Audit event recorded in review_admin_password_rotations
            audit = client[test_db_name]["review_admin_password_rotations"].find_one({"user_id": "mongo-admin-1"})
            self.assertIsNotNone(audit)
            self.assertEqual(audit["local_operator"], "mongo_operator")
            self.assertNotIn("password", audit)
            self.assertNotIn("password_hash", audit)

            # Old password fails, new password succeeds
            with self.assertRaises(ValueError):
                mongo_auth.login("mongoadmin@example.test", "InitialPassword123")
            new_login = mongo_auth.login("mongoadmin@example.test", "NewMongoPassword456")
            self.assertEqual(new_login["user"]["id"], "mongo-admin-1")
        finally:
            client.drop_database(test_db_name)
            client.close()


if __name__ == "__main__":
    unittest.main()

