"""Comprehensive persistence tests for local MongoDB Community Server & GridFS in CaseSeva.

Uses isolated test database 'caseseva_test'. Never mutates real authority JSON databases.
Validates:
- MongoDB connectivity & indexes
- Repository CRUD
- Unique constraints
- User & advocate auth persistence
- Case persistence & application restart simulation
- Case Blackboard versioning & CAS atomicity
- Dynamic multi-domain issue persistence
- GridFS upload, download, SHA-256 verification
- Storage provider abstraction
- JSON -> Mongo migration idempotency & lineage preservation
- AWS-disabled end-to-end local operation
- Immutability safety of original JSON DBs
"""
import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]

from backend.database.mongo_client import get_mongo_client, get_mongo_db, ping_mongodb, get_gridfs
from backend.database.mongo_indexes import ensure_indexes
from backend.adapters.mongo.database import MongoDatabaseAdapter
from backend.adapters.mongo.storage import MongoGridFSStorageAdapter
from backend.storage.object_store import get_object_store, MongoGridFSObjectStore
from backend.repositories import (
    MongoUserRepository,
    MongoIdentityRepository,
    MongoCaseRepository,
    MongoBlackboardRepository,
    MongoDocumentRepository,
    MongoEvidenceRepository,
    MongoAuthorityRepository,
    MongoReviewRepository,
    MongoAuditRepository,
)
from backend.services.case_blackboard import CaseBlackboard, VersionConflict
from backend.adapters.factory import load_adapters

TEST_DB_NAME = "caseseva_test_" + uuid4().hex
TEST_MONGO_URI = "mongodb://127.0.0.1:27017"

BASELINE_AUTH_HASH = "b96220116ac40a01b4f96e6b620edc7eebfa35d39d11dfb33b677b9bf67716c3"
BASELINE_IDENT_HASH = "bd055fe4bd996aba38a243fbb3572f68646be7cd469e0382a3b57920a9a15b17"


class MongoPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ping_mongodb(TEST_MONGO_URI):
            raise unittest.SkipTest("MongoDB Community Server not reachable on 127.0.0.1:27017")
        cls.client = get_mongo_client(TEST_MONGO_URI)
        cls.db = cls.client[TEST_DB_NAME]
        # Clean test database
        cls.client.drop_database(TEST_DB_NAME)
        ensure_indexes(cls.db)

    @classmethod
    def tearDownClass(cls):
        # Clean up test database after suite
        if hasattr(cls, "client"):
            cls.client.drop_database(TEST_DB_NAME)

    def test_01_mongo_connection_and_indexes(self):
        self.assertTrue(ping_mongodb(TEST_MONGO_URI))
        indexes = ensure_indexes(self.db)
        self.assertIn("users", indexes)
        self.assertIn("cases", indexes)
        self.assertIn("case_board_heads", indexes)
        self.assertIn("case_board_snapshots", indexes)

    def test_02_unique_identity_constraints(self):
        user_repo = MongoUserRepository(self.db)
        uid1 = uuid4().hex
        uid2 = uuid4().hex
        user_repo.create_user({
            "id": uid1,
            "email": "unique.test@example.com",
            "full_name": "Test User 1",
            "role": "client",
        })
        # Duplicate email must fail
        with self.assertRaises(Exception):
            user_repo.create_user({
                "id": uid2,
                "email": "unique.test@example.com",
                "full_name": "Test User 2",
                "role": "client",
            })

    def test_03_user_and_advocate_persistence_across_restart(self):
        from backend.adapters.mock.auth import MockAuthAdapter
        db_adapter = MongoDatabaseAdapter(db_name=TEST_DB_NAME)
        auth = MockAuthAdapter(db_adapter, seed_demo=False)

        # 1. Register citizen
        citizen = auth.signup({
            "full_name": "Citizen Ramesh",
            "email": "ramesh.citizen@test.local",
            "mobile_number": "9876543210",
            "preferred_language": "English",
            "state": "Tamil Nadu",
            "district_city": "Chennai",
            "role": "client",
        }, "Password123!")
        self.assertEqual(citizen["user"]["email"], "ramesh.citizen@test.local")

        # 2. Register advocate
        advocate = auth.signup({
            "full_name": "Advocate Priya",
            "email": "priya.advocate@test.local",
            "mobile_number": "9876543211",
            "preferred_language": "English",
            "state": "Karnataka",
            "district_city": "Bengaluru",
            "role": "advocate",
            "bar_council": "Karnataka State Bar Council",
            "enrolment_number": "KAR/2018/1234",
            "enrolment_year": 2018,
            "place_of_practice": "Bengaluru",
            "court_region": "High Court of Karnataka",
            "practice_domains": ["Consumer", "Civil"],
            "languages": ["English", "Kannada"],
        }, "AdvocatePass123!")
        self.assertEqual(advocate["user"]["role"], "advocate")
        self.assertEqual(advocate["user"]["verification_status"], "VERIFICATION_PENDING")

        # 3. Simulate backend restart by instantiating new adapter and auth
        restarted_db = MongoDatabaseAdapter(db_name=TEST_DB_NAME)
        restarted_auth = MockAuthAdapter(restarted_db, seed_demo=False)

        # Login with correct password
        login_res = restarted_auth.login("ramesh.citizen@test.local", "Password123!")
        self.assertEqual(login_res["user"]["full_name"], "Citizen Ramesh")
        self.assertTrue(restarted_auth.verify_session(login_res["session_token"]))

        # Invalid password must fail
        with self.assertRaises(ValueError):
            restarted_auth.login("ramesh.citizen@test.local", "WrongPassword!")

    def test_04_role_authorization_and_separation_of_duties(self):
        db_adapter = MongoDatabaseAdapter(db_name=TEST_DB_NAME)
        from backend.adapters.mock.auth import MockAuthAdapter
        auth = MockAuthAdapter(db_adapter, seed_demo=False)

        # Bootstrap review admin
        admin = auth.provision_local_review_admin("admin.reviewer@test.local", "AdminPass123!", allow_bootstrap=True, operator="test-operator")
        self.assertEqual(admin["role"], "admin")

        # Re-bootstrap must be refused (separation of duties / one-time gate)
        with self.assertRaises(ValueError):
            auth.provision_local_review_admin("second.admin@test.local", "AdminPass123!", allow_bootstrap=True, operator="test-operator")

    def test_05_case_persistence_and_restart(self):
        case_repo = MongoCaseRepository(self.db)
        cid = f"CASE-{uuid4().hex[:8]}"
        case_data = {
            "id": cid,
            "case_id": cid,
            "owner_user_id": "user-123",
            "status": "DRAFT",
            "client_story": "Purchased an electric vehicle that stopped working within 2 days.",
            "dynamic_domains": ["CONSUMER", "AUTOMOTIVE_REGULATORY"],
            "version": 1,
        }
        case_repo.create_case(case_data)

        # Restart simulation
        restarted_repo = MongoCaseRepository(self.client[TEST_DB_NAME])
        fetched = restarted_repo.get_case(cid)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["case_id"], cid)
        self.assertEqual(fetched["client_story"], case_data["client_story"])
        self.assertEqual(fetched["dynamic_domains"], ["CONSUMER", "AUTOMOTIVE_REGULATORY"])

    def test_06_case_blackboard_versioning_and_cas(self):
        db_adapter = MongoDatabaseAdapter(db_name=TEST_DB_NAME)
        cid = f"CASE-{uuid4().hex[:8]}"
        db_adapter.create("cases", {"id": cid, "case_id": cid, "owner_user_id": "u1", "status": "DRAFT"})

        board_store = CaseBlackboard(db_adapter)
        initial_board = board_store.read_board(cid)
        self.assertEqual(initial_board["version"], 1)

        # Append change
        b2 = board_store.append_change(cid, {"facts.core": ["Fact 1", "Fact 2"]}, actor="citizen", reason="Intake details")
        self.assertEqual(b2["version"], 2)
        self.assertEqual(b2["data"]["facts"]["core"], ["Fact 1", "Fact 2"])

        # History pagination
        history = board_store.history(cid, limit=10)
        self.assertGreaterEqual(len(history["events"]), 1)
        self.assertEqual(history["events"][0]["type"], "HUMAN_CHANGE")

        # Concurrent update with stale expected_version must fail
        with self.assertRaises(VersionConflict):
            board_store.change(cid, lambda b: {"notes": "stale edit"}, actor="user", expected_version=1)

    def test_07_dynamic_and_multi_domain_persistence(self):
        case_repo = MongoCaseRepository(self.db)
        cid = f"MULTI-DOMAIN-{uuid4().hex[:8]}"
        issues = {
            "L001": {"issue_id": "L001", "domain": "CIVIL_CONTRACT", "query": "breach of warranty"},
            "L002": {"issue_id": "L002", "domain": "CYBER", "query": "data exfiltration breach"},
            "L003": {"issue_id": "L003", "domain": "CONSUMER", "query": "deficiency in goods"},
            "L004": {"issue_id": "L004", "domain": "AVIATION_PASSENGER_COMPENSATION", "query": "cancelled flight refund"},
            "L005": {"issue_id": "L005", "domain": "UNKNOWN_CUSTOM_TELECOM_DOMAIN", "query": "spectrum licensing dispute"},
        }
        case_repo.create_case({
            "id": cid,
            "case_id": cid,
            "legal_issues": issues,
            "status": "DRAFT",
        })

        reloaded = MongoCaseRepository(self.db).get_case(cid)
        self.assertIn("AVIATION_PASSENGER_COMPENSATION", [i["domain"] for i in reloaded["legal_issues"].values()])
        self.assertIn("UNKNOWN_CUSTOM_TELECOM_DOMAIN", [i["domain"] for i in reloaded["legal_issues"].values()])

    def test_08_gridfs_upload_download_sha256_verification(self):
        storage = MongoGridFSStorageAdapter(db_name=TEST_DB_NAME)
        sample_bytes = b"%PDF-1.4 Mock legal judgment and evidence document content for testing"
        key = f"cases/test_case/E001-job_sheet.pdf"

        # Upload
        uri = storage.upload(key, sample_bytes, content_type="application/pdf")
        self.assertTrue(uri.startswith("gridfs://"))

        # Download & verify
        downloaded = storage.download(key)
        self.assertEqual(downloaded, sample_bytes)
        self.assertEqual(hashlib.sha256(downloaded).hexdigest(), hashlib.sha256(sample_bytes).hexdigest())

        # Metadata verification
        meta = storage.get_file_metadata(key)
        self.assertEqual(meta["size"], len(sample_bytes))
        self.assertEqual(meta["contentType"], "application/pdf")
        self.assertEqual(meta["sha256"], hashlib.sha256(sample_bytes).hexdigest())

        # Duplicate upload replaces safely
        new_bytes = sample_bytes + b" updated"
        storage.upload(key, new_bytes, content_type="application/pdf")
        reloaded = storage.download(key)
        self.assertEqual(reloaded, new_bytes)

    def test_09_storage_abstraction_provider(self):
        store = get_object_store("mongodb", db_name=TEST_DB_NAME)
        self.assertIsInstance(store, MongoGridFSObjectStore)
        data = b"Testing generic ObjectStore abstraction"
        key = "docs/test_doc.txt"
        store.put_object(key, data, content_type="text/plain")

        self.assertTrue(store.object_exists(key))
        self.assertEqual(store.get_object(key), data)
        self.assertIn(key, store.list_objects("docs/"))

        store.delete_object(key)
        self.assertFalse(store.object_exists(key))

    def test_10_migration_lineage_preservation_and_idempotency(self):
        from scripts import migrate_to_mongodb as migration
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review = root / '.localdev/phase4-authority-review'
            review.mkdir(parents=True)
            receipt = {'id': 'synthetic-migration-receipt', 'source_id': 'synthetic-source',
                       'input_version': 'synthetic-parent', 'decision': 'NEEDS_NEW_REVISION'}
            (review / 'database.json').write_text(json.dumps({'legal_authority_reviews': {receipt['id']: receipt}}))
            (review / 'identity.json').write_text('{}')
            with patch.object(migration, 'ROOT', root), patch.object(migration, 'probe_s3_and_build_manifest',
                    return_value={'unresolved_reason': 'OFFLINE_TEST_NO_S3'}) as probe:
                for _ in range(2):
                    result = migration.run_migration(db_name=TEST_DB_NAME, mongo_uri=TEST_MONGO_URI)
                    self.assertEqual(result['status'], 'SUCCESS')
                    stored = self.db['legal_authority_reviews'].find_one({'_id': receipt['id']})
                    self.assertEqual({key: stored[key] for key in receipt}, receipt)
                    self.assertEqual(self.db['legal_authority_reviews'].count_documents({'id': receipt['id']}), 1)
                self.assertEqual(probe.call_count, 2)

    def test_11_aws_disabled_local_operation(self):
        """End-to-end flow with complete absence of AWS credentials."""
        clean_env = {
            "AWS_ACCESS_KEY_ID": "",
            "AWS_SECRET_ACCESS_KEY": "",
            "AWS_SESSION_TOKEN": "",
            "DATABASE_PROVIDER": "mongodb",
            "OBJECT_STORE_PROVIDER": "mongodb",
            "MONGODB_DATABASE": TEST_DB_NAME,
            "MONGODB_URI": TEST_MONGO_URI,
            "USE_MOCK_AWS": "false",
            "LLM_PROVIDER": "mock",
            "WORKFLOW_PROVIDER": "mock",
        }
        with patch.dict(os.environ, clean_env):
            adapters = load_adapters()
            self.assertEqual(adapters.persistence_provider, "mongodb")
            self.assertEqual(adapters.processing_mode, "mock")
            self.assertIsInstance(adapters.database, MongoDatabaseAdapter)
            self.assertIsInstance(adapters.storage, MongoGridFSStorageAdapter)

            # 1. Citizen login & create case
            auth = adapters.auth
            user = auth.signup({
                "full_name": "Local Citizen",
                "email": "local.citizen@caseseva.test",
                "mobile_number": "9999999999",
                "preferred_language": "English",
                "state": "Delhi",
                "district_city": "New Delhi",
                "role": "client",
            }, "TestPassword123!")

            cid = f"LOCAL-{uuid4().hex[:6]}"
            adapters.database.create("cases", {
                "id": cid,
                "case_id": cid,
                "owner_user_id": user["user"]["id"],
                "status": "DRAFT",
                "version": 1,
            })

            # 2. Upload evidence to GridFS
            content = b"Local evidence invoice without AWS"
            key = f"cases/{cid}/E001-invoice.txt"
            adapters.storage.upload(key, content, "text/plain")

            # 3. Retrieve evidence
            downloaded = adapters.storage.download(key)
            self.assertEqual(downloaded, content)

            # 4. Read case back
            case = adapters.database.get("cases", cid)
            self.assertEqual(case["case_id"], cid)

    def test_12_original_json_databases_remain_untouched(self):
        auth_db = ROOT / ".localdev" / "phase4-authority-review" / "database.json"
        ident_db = ROOT / ".localdev" / "phase4-authority-review" / "identity.json"

        curr_auth_hash = hashlib.sha256(auth_db.read_bytes()).hexdigest()
        curr_ident_hash = hashlib.sha256(ident_db.read_bytes()).hexdigest()

        self.assertEqual(curr_auth_hash, BASELINE_AUTH_HASH, "Original authority JSON database was modified!")
        self.assertEqual(curr_ident_hash, BASELINE_IDENT_HASH, "Original identity JSON database was modified!")


if __name__ == "__main__":
    unittest.main()
