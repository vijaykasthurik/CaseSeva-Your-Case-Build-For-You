"""Index creation and schema constraints for MongoDB persistence in CaseSeva.

Ensures unique identities, fast case lookup, versioning consistency, and auditable history.
"""
from typing import Any
import pymongo
from pymongo import ASCENDING, DESCENDING


def ensure_indexes(db: pymongo.database.Database) -> dict[str, list[str]]:
    """Create all required indexes idempotently on the given MongoDB database."""
    created = {}

    # 1. users: unique identity and normalized email, role index
    users = db["users"]
    users.create_index([("id", ASCENDING)], unique=True, sparse=True, name="idx_users_id_unique")
    users.create_index([("email", ASCENDING)], unique=True, sparse=True, name="idx_users_email_unique")
    users.create_index([("role", ASCENDING)], name="idx_users_role")
    users.create_index([("verification_status", ASCENDING)], name="idx_users_verification_status")
    created["users"] = ["idx_users_id_unique", "idx_users_email_unique", "idx_users_role", "idx_users_verification_status"]

    # 2. sessions: token unique, user_id lookup
    sessions = db["sessions"]
    existing_sessions_indexes = [idx["name"] for idx in sessions.list_indexes()]
    if "token_hash_1" in existing_sessions_indexes:
        sessions.drop_index("token_hash_1")
    sessions.create_index([("id", ASCENDING)], unique=True, sparse=True, name="idx_sessions_id_unique")
    sessions.create_index([("user_id", ASCENDING)], name="idx_sessions_user_id")
    created["sessions"] = ["idx_sessions_id_unique", "idx_sessions_user_id"]

    # 3. cases: case_id unique, owner and advocate lookups
    cases = db["cases"]
    cases.create_index([("id", ASCENDING)], unique=True, sparse=True, name="idx_cases_id_unique")
    cases.create_index([("case_id", ASCENDING)], unique=True, sparse=True, name="idx_cases_case_id_unique")
    cases.create_index([("owner_user_id", ASCENDING)], name="idx_cases_owner_user_id")
    cases.create_index([("assigned_advocate_id", ASCENDING)], name="idx_cases_assigned_advocate_id")
    cases.create_index([("status", ASCENDING)], name="idx_cases_status")
    created["cases"] = ["idx_cases_id_unique", "idx_cases_case_id_unique", "idx_cases_owner_user_id", "idx_cases_assigned_advocate_id", "idx_cases_status"]

    # 4. case_board_heads: case_id unique
    board_heads = db["case_board_heads"]
    board_heads.create_index([("id", ASCENDING)], unique=True, name="idx_board_heads_id_unique")
    created["case_board_heads"] = ["idx_board_heads_id_unique"]

    # 5. case_board_snapshots: snapshot id unique, case_id and version lookup
    board_snapshots = db["case_board_snapshots"]
    board_snapshots.create_index([("id", ASCENDING)], unique=True, name="idx_board_snapshots_id_unique")
    board_snapshots.create_index([("case_id", ASCENDING), ("version", ASCENDING)], name="idx_board_snapshots_case_version")
    created["case_board_snapshots"] = ["idx_board_snapshots_id_unique", "idx_board_snapshots_case_version"]

    # 6. documents: document_id unique, case_id, sha256
    documents = db["documents"]
    documents.create_index([("id", ASCENDING)], unique=True, name="idx_documents_id_unique")
    documents.create_index([("case_id", ASCENDING)], name="idx_documents_case_id")
    documents.create_index([("sha256", ASCENDING)], sparse=True, name="idx_documents_sha256")
    created["documents"] = ["idx_documents_id_unique", "idx_documents_case_id", "idx_documents_sha256"]

    # 7. legal_authority_heads: source_id unique
    auth_heads = db["legal_authority_heads"]
    auth_heads.create_index([("id", ASCENDING)], unique=True, name="idx_auth_heads_id_unique")
    created["legal_authority_heads"] = ["idx_auth_heads_id_unique"]

    # 8. legal_authority_versions: version_id unique
    auth_versions = db["legal_authority_versions"]
    auth_versions.create_index([("id", ASCENDING)], unique=True, name="idx_auth_versions_id_unique")
    auth_versions.create_index([("source.source_id", ASCENDING)], name="idx_auth_versions_source_id")
    created["legal_authority_versions"] = ["idx_auth_versions_id_unique", "idx_auth_versions_source_id"]

    # 9. legal_authority_reviews: review_id unique
    auth_reviews = db["legal_authority_reviews"]
    auth_reviews.create_index([("id", ASCENDING)], unique=True, name="idx_auth_reviews_id_unique")
    auth_reviews.create_index([("source_id", ASCENDING)], name="idx_auth_reviews_source_id")
    created["legal_authority_reviews"] = ["idx_auth_reviews_id_unique", "idx_auth_reviews_source_id"]

    # 10. legal_review_submissions
    submissions = db["legal_review_submissions"]
    submissions.create_index([("id", ASCENDING)], unique=True, name="idx_submissions_id_unique")
    submissions.create_index([("source_id", ASCENDING)], name="idx_submissions_source_id")
    created["legal_review_submissions"] = ["idx_submissions_id_unique", "idx_submissions_source_id"]

    # 11. legal_ingestion_requests
    ingestions = db["legal_ingestion_requests"]
    ingestions.create_index([("id", ASCENDING)], unique=True, name="idx_ingestions_id_unique")
    ingestions.create_index([("registry_id", ASCENDING)], name="idx_ingestions_registry_id")
    created["legal_ingestion_requests"] = ["idx_ingestions_id_unique", "idx_ingestions_registry_id"]

    # 12. audit_events
    audit_events = db["audit_events"]
    audit_events.create_index([("id", ASCENDING)], unique=True, sparse=True, name="idx_audit_events_id_unique")
    audit_events.create_index([("case_id", ASCENDING), ("created_at", DESCENDING)], name="idx_audit_case_created")
    created["audit_events"] = ["idx_audit_events_id_unique", "idx_audit_case_created"]

    # 13. review_admin_bootstrap
    bootstrap = db["review_admin_bootstrap"]
    bootstrap.create_index([("id", ASCENDING)], unique=True, name="idx_bootstrap_id_unique")
    created["review_admin_bootstrap"] = ["idx_bootstrap_id_unique"]

    # 14. review_admin_provisioning
    provisioning = db["review_admin_provisioning"]
    provisioning.create_index([("id", ASCENDING)], unique=True, name="idx_provisioning_id_unique")
    created["review_admin_provisioning"] = ["idx_provisioning_id_unique"]

    # 15. reviewer_identities
    reviewers = db["reviewer_identities"]
    reviewers.create_index([("id", ASCENDING)], unique=True, name="idx_reviewer_id_unique")
    reviewers.create_index([("email", ASCENDING)], unique=True, name="idx_reviewer_email_unique")
    created["reviewer_identities"] = ["idx_reviewer_id_unique", "idx_reviewer_email_unique"]

    return created
