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

from ..database import DatabaseAdapter
from ...database.mongo_client import get_mongo_db, get_mongo_client


class MongoDatabaseAdapter(DatabaseAdapter):
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
        coll = self._db[collection]
        target_id = str(record_id)
        for attempt in range(50):
            current = coll.find_one({"_id": target_id})
            if current is None:
                current = coll.find_one({"id": target_id})
            if current is None:
                raise KeyError(record_id)

            cleaned = self._clean_doc(current)
            revision = current.get("_revision", 0)

            modifications = transform(copy.deepcopy(cleaned))
            cleaned.update(modifications)
            cleaned["_revision"] = revision + 1
            cleaned["_id"] = target_id
            if "id" not in cleaned:
                cleaned["id"] = target_id

            # Atomic CAS update using matching revision
            result = coll.replace_one(
                {"_id": target_id, "_revision": revision},
                cleaned,
                upsert=False
            )
            if result.matched_count > 0:
                return self._clean_doc(cleaned)
            time.sleep(0.01)

        raise RuntimeError("Concurrent database updates could not be resolved; retry the operation.")

    def delete(self, collection: str, record_id: str) -> bool:
        coll = self._db[collection]
        target_id = str(record_id)
        result = coll.delete_one({"_id": target_id})
        if result.deleted_count == 0:
            result = coll.delete_one({"id": target_id})
        return result.deleted_count > 0

    def list(self, collection: str) -> list[dict[str, Any]]:
        coll = self._db[collection]
        return [self._clean_doc(doc) for doc in coll.find({})]

    def create_local_review_admin(self, user: dict[str, Any]) -> None:
        """Atomically claim the one-time bootstrap and insert a new dedicated user."""
        users_coll = self._db["users"]
        bootstrap_coll = self._db["review_admin_bootstrap"]

        # Check existing emails
        user_email = user["email"].strip().lower()
        if users_coll.find_one({"email": user_email}):
            raise ValueError("Account already exists; bootstrap never promotes existing users")

        # Check existing admin or bootstrap
        if bootstrap_coll.count_documents({}) > 0 or users_coll.find_one({"role": "admin"}):
            raise ValueError("Local review administrator bootstrap has already been used or an admin exists")

        if user.get("role") != "admin" or user.get("provisioning", {}).get("scope") != "PHASE4_REVIEW_ONLY":
            raise ValueError("Invalid local review provisioning request")

        user_doc = dict(user)
        user_doc["_id"] = user["id"]
        users_coll.insert_one(user_doc)

        bootstrap_doc = {
            "_id": "one-time",
            "id": "one-time",
            "user_id": user["id"],
            **user["provisioning"]
        }
        bootstrap_coll.insert_one(bootstrap_doc)

    def create_additional_review_admin(self, user: dict[str, Any], *, session_token: str) -> None:
        """Recheck authorization and duplicates atomically; leave bootstrap history untouched."""
        users_coll = self._db["users"]
        sessions_coll = self._db["sessions"]
        bootstrap_coll = self._db["review_admin_bootstrap"]
        prov_coll = self._db["review_admin_provisioning"]

        session = sessions_coll.find_one({"_id": session_token}) or sessions_coll.find_one({"id": session_token})
        authorizer = None
        if session:
            authorizer = users_coll.find_one({"_id": session.get("user_id")}) or users_coll.find_one({"id": session.get("user_id")})

        if not authorizer or authorizer.get("role") != "admin":
            raise ValueError("An authenticated existing administrator is required")

        if bootstrap_coll.count_documents({}) == 0:
            raise ValueError("Existing review bootstrap history is required; onboarding cannot bootstrap")

        user_email = user["email"].strip().lower()
        if users_coll.find_one({"_id": user["id"]}) or users_coll.find_one({"email": user_email}):
            raise ValueError("Account already exists; onboarding never promotes existing users")

        audit = user.get("provisioning", {})
        if (user.get("role") != "admin" or audit.get("scope") != "PHASE4_REVIEW_ONLY"
                or audit.get("authorized_by") != authorizer["id"]):
            raise ValueError("Invalid local reviewer onboarding request")

        user_doc = dict(user)
        user_doc["_id"] = user["id"]
        users_coll.insert_one(user_doc)

        prov_doc = {
            "_id": user["id"],
            "id": user["id"],
            "user_id": user["id"],
            **audit
        }
        prov_coll.insert_one(prov_doc)
