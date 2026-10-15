"""MongoDB-backed DatabaseAdapter for CaseSeva local persistence.

Provides atomic mutations, optimistic concurrency, and collection isolation
using local MongoDB Community Server.
"""
import copy
import os
import time
from typing import Any, Callable
import pymongo
from pymongo.errors import DuplicateKeyError
from pymongo.write_concern import WriteConcern

from ..database import DatabaseAdapter
from ...database.mongo_client import get_mongo_db


class MongoDatabaseAdapter(DatabaseAdapter):
    IMMUTABLE_COLLECTIONS = frozenset({
        "legal_authority_versions", "legal_authority_reviews", "legal_review_submissions",
        "legal_revision_requests", "audit_events", "review_admin_bootstrap",
        "review_admin_provisioning", "review_admin_password_rotations",
        "authority_reviewer_grants", "admin_role_audit",
    })

    def __init__(self, db_name: str | None = None, uri: str | None = None):
        self.db_name = db_name or os.getenv("MONGODB_DATABASE", "caseseva").strip()
        self.uri = uri or os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017").strip()
        self._db = get_mongo_db(self.db_name, self.uri)

    @property
    def db(self) -> pymongo.database.Database:
        return self._db

    def _clean_doc(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if doc is None:
            return None
        res = dict(doc)
        if "_id" in res:
            if "id" not in res:
                res["id"] = str(res["_id"])
            res.pop("_id", None)
        return res

    def create(self, collection: str, record: dict[str, Any]) -> dict[str, Any]:
        record_id = str(record["id"])
        doc = dict(record)
        doc["_id"] = record_id
        doc.setdefault("_revision", 1)
        coll = self._db[collection]
        try:
            coll.insert_one(doc)
        except DuplicateKeyError as exc:
            raise ValueError(f"Record already exists: {record_id}") from exc
        return dict(record)

    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        coll = self._db[collection]
        doc = coll.find_one({"_id": str(record_id)})
        if doc is None:
            # Fallback search by 'id' attribute
            doc = coll.find_one({"id": str(record_id)})
        return self._clean_doc(doc)

    def update(self, collection: str, record_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return self.mutate(collection, record_id, lambda current: changes)

    def mutate(self, collection: str, record_id: str, transform: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        if collection in self.IMMUTABLE_COLLECTIONS:
            raise ValueError("Historical records are append-only")
        coll = self._db[collection]
        target_id = str(record_id)
        for attempt in range(50):
            current = coll.find_one({"_id": target_id})
            if current is None:
                current = coll.find_one({"id": target_id})
            if current is None:
                raise KeyError(record_id)

            cleaned = self._clean_doc(current)
            revision = current.get("_revision")
            if revision is not None and (not isinstance(revision, int) or isinstance(revision, bool) or revision < 0):
                raise ValueError("Invalid mutation revision; refusing update")

            modifications = transform(copy.deepcopy(cleaned))
            if not modifications:
                return cleaned
            cleaned.update(modifications)
            cleaned["_revision"] = (revision or 0) + 1
            cleaned["_id"] = current["_id"]
            if "id" not in cleaned:
                cleaned["id"] = target_id

            # Compare the entire observed BSON document, including absent/null
            # fields and the original _id. Repository writers may not increment
            # _revision, so revision alone cannot protect their changes either.
            # $literal prevents stored values from becoming query expressions.
            result = coll.replace_one(
                {"_id": current["_id"], "$expr": {"$eq": ["$$ROOT", {"$literal": current}]}},
                cleaned,
                upsert=False
            )
            if result.matched_count > 0:
                return self._clean_doc(cleaned)
            time.sleep(0.01)

        raise RuntimeError("Concurrent database updates could not be resolved; retry the operation.")

    def delete(self, collection: str, record_id: str) -> bool:
        if collection in self.IMMUTABLE_COLLECTIONS:
            raise ValueError("Historical records are append-only")
        coll = self._db[collection]
        target_id = str(record_id)
        result = coll.delete_one({"_id": target_id})
        if result.deleted_count == 0:
            result = coll.delete_one({"id": target_id})
        return result.deleted_count > 0

    def list(self, collection: str) -> list[dict[str, Any]]:
        coll = self._db[collection]
        return [self._clean_doc(doc) for doc in coll.find({})]

    def reserve_admin_role_intent(self, intent):
        claims = self._db.get_collection("admin_role_audit", write_concern=WriteConcern(w="majority", j=True))
        # Includes legacy random-ID intents. Duplicate history fails closed;
        # never repair or delete history to make this index succeed.
        claims.create_index("user_id", unique=True, name="idx_admin_role_user_unique")
        existing = claims.find_one({"user_id": intent["user_id"]})
        if existing:
            return self._clean_doc(existing)
        try:
            claims.insert_one({**intent, "_id": intent["id"], "_revision": 1})
        except DuplicateKeyError:
            existing = claims.find_one({"user_id": intent["user_id"]})
            if not existing:
                raise ValueError("Conflicting administrator audit identity")
            return self._clean_doc(existing)
        return intent

    def _provisioning_collections(self):
        # Provisioning must enforce constraints even when startup index setup was
        # omitted. Existing invalid data makes index creation fail closed.
        users = self._db.get_collection("users", write_concern=WriteConcern(w="majority", j=True))
        users.create_index("id", unique=True, sparse=True, name="idx_users_id_unique")
        users.create_index("email", unique=True, sparse=True, name="idx_users_email_unique")
        return users

    @staticmethod
    def _review_user(user):
        value = copy.deepcopy(user)
        audit = value.get("provisioning", {})
        if (value.get("role") != "admin" or audit.get("scope") != "PHASE4_REVIEW_ONLY"
                or not isinstance(value.get("id"), str) or not value["id"]):
            raise ValueError("Invalid local review provisioning request")
        if {"id", "_id", "user_id", "email", "protocol"} & set(audit):
            raise ValueError("Provisioning metadata cannot override identity bindings")
        value["email"] = value["email"].strip().lower()
        if not value["email"]:
            raise ValueError("Reviewer email is required")
        value["_id"] = value["id"]
        return value

    def _insert_reserved_reviewer(self, users, user, collection, claim_id):
        # The audit is the durable reservation; inserting the user is the commit
        # point. Never roll back a claim after an ambiguous network/write failure.
        # Orphan reservations are intentionally retained and require investigation.
        claims = self._db.get_collection(collection, write_concern=WriteConcern(w="majority", j=True))
        index_name = "idx_bootstrap_id_unique" if collection == "review_admin_bootstrap" else "idx_provisioning_id_unique"
        claims.create_index("id", unique=True, name=index_name)
        audit = copy.deepcopy(user["provisioning"])
        claim = {**audit, "_id": claim_id, "id": claim_id,
                 "user_id": user["id"], "email": user["email"],
                 "protocol": "AUDIT_BEFORE_IDENTITY_V1"}
        try:
            claims.insert_one(claim)
            users.insert_one(user)
        except DuplicateKeyError as exc:
            raise ValueError("Reviewer identity or provisioning claim already exists") from exc

    def create_local_review_admin(self, user: dict[str, Any]) -> None:
        """Fail closed on standalone Mongo: reserve once, then insert identity."""
        value = self._review_user(user)
        if value["provisioning"].get("method") != "LOCAL_INTERACTIVE_REVIEW_BOOTSTRAP":
            raise ValueError("Invalid bootstrap method")
        users = self._provisioning_collections()
        if users.find_one({"$or": [{"id": value["id"]}, {"email": value["email"]}]}):
            raise ValueError("Account already exists; bootstrap never promotes existing users")
        if self._db.review_admin_bootstrap.count_documents({}) or users.find_one({"role": "admin"}):
            raise ValueError("Local review administrator bootstrap has already been used or an admin exists")
        self._insert_reserved_reviewer(users, value, "review_admin_bootstrap", "one-time")

    def _has_review_audit(self, user):
        if not user or user.get("role") != "admin":
            return False
        audit = user.get("provisioning", {})
        if audit.get("scope") != "PHASE4_REVIEW_ONLY":
            return False
        method = audit.get("method")
        if method == "LOCAL_INTERACTIVE_REVIEW_BOOTSTRAP":
            collection, key = "review_admin_bootstrap", "one-time"
        elif method == "AUTHENTICATED_LOCAL_REVIEW_ONBOARDING":
            collection, key = "review_admin_provisioning", user["id"]
        else:
            return False
        claim = self._db[collection].find_one({"_id": key})
        return bool(claim and claim.get("user_id") == user["id"]
                    and all(claim.get(k) == v for k, v in audit.items())
                    and ("email" not in claim or claim["email"] == user["email"]))

    def create_additional_review_admin(self, user: dict[str, Any], *, session_token: str) -> None:
        """Validate authenticated reviewer provenance, reserve audit, insert identity."""
        value = self._review_user(user)
        users = self._provisioning_collections()
        session = self.get("sessions", session_token)
        authorizer = self.get("users", session["user_id"]) if session else None
        if not self._has_review_audit(authorizer):
            raise ValueError("An authenticated existing review administrator is required")
        bootstrap = self._db.review_admin_bootstrap.find_one({"_id": "one-time"})
        founder = self.get("users", bootstrap["user_id"]) if bootstrap else None
        if not self._has_review_audit(founder):
            raise ValueError("Completed review bootstrap history is required")
        audit = value["provisioning"]
        if (audit.get("method") != "AUTHENTICATED_LOCAL_REVIEW_ONBOARDING"
                or audit.get("authorized_by") != authorizer["id"]):
            raise ValueError("Invalid local reviewer onboarding request")
        if users.find_one({"$or": [{"id": value["id"]}, {"email": value["email"]}]}):
            raise ValueError("Account already exists; onboarding never promotes existing users")
        self._insert_reserved_reviewer(users, value, "review_admin_provisioning", value["id"])

    def reset_local_review_admin_password(
        self, email: str, new_password_hash: str, *, operator: str
    ) -> dict[str, Any]:
        """Atomically rotates the password of an existing review admin in MongoDB."""
        from ...models.case import utc_now
        from uuid import uuid4

        users = self._provisioning_collections()
        normalized = email.strip().lower()
        user = users.find_one({"email": normalized})
        if not user:
            raise ValueError(f"Review administrator account '{email}' not found")
        if user.get("role") != "admin":
            raise ValueError(f"Account '{email}' is not an administrator; role promotion/rotation refused")

        user_id = user.get("id") or str(user.get("_id"))
        now = utc_now()

        users.update_one(
            {"_id": user["_id"]},
            {"$set": {"password_hash": new_password_hash, "password_rotated_at": now}},
        )

        # Invalidate sessions for this user
        self._db.sessions.delete_many({"user_id": user_id})

        # Record immutable audit event
        rotation_id = uuid4().hex
        self._db.review_admin_password_rotations.insert_one({
            "_id": rotation_id,
            "id": rotation_id,
            "user_id": user_id,
            "email": user["email"],
            "local_operator": operator,
            "timestamp": now,
            "operation_type": "LOCAL_REVIEW_ADMIN_PASSWORD_ROTATION",
        })

        updated = users.find_one({"_id": user["_id"]})
        return self._clean_doc(updated)
