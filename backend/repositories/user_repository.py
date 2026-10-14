"""Repository contracts and MongoDB implementations for CaseSeva domain persistence."""
from abc import ABC, abstractmethod
from typing import Any, Callable
from uuid import uuid4
import pymongo

from ..models.case import utc_now


# 1. Base Repository
class BaseRepository(ABC):
    pass


# 2. UserRepository & IdentityRepository
class UserRepository(BaseRepository):
    @abstractmethod
    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def get_by_email(self, email: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def create_user(self, user: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def update_user(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_users(self, role: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def create_session(self, token: str, user_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_session(self, token: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def delete_session(self, token: str) -> bool:
        raise NotImplementedError


class MongoUserRepository(UserRepository):
    def __init__(self, db: pymongo.database.Database):
        self.db = db
        self.users = db["users"]
        self.sessions = db["sessions"]

    def _clean(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if not doc:
            return None
        res = dict(doc)
        if "_id" in res:
            if "id" not in res:
                res["id"] = str(res["_id"])
            res.pop("_id", None)
        return res

    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        return self._clean(self.users.find_one({"$or": [{"_id": str(user_id)}, {"id": str(user_id)}]}))

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        normalized = email.strip().lower()
        return self._clean(self.users.find_one({"email": normalized}))

    def create_user(self, user: dict[str, Any]) -> dict[str, Any]:
        doc = dict(user)
        user_id = str(doc["id"])
        doc["_id"] = user_id
        if "email" in doc:
            doc["email"] = doc["email"].strip().lower()
        self.users.insert_one(doc)
        return dict(user)

    def update_user(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        target = str(user_id)
        self.users.update_one({"$or": [{"_id": target}, {"id": target}]}, {"$set": updates})
        return self.get_by_id(target) or {}

    def list_users(self, role: str | None = None) -> list[dict[str, Any]]:
        query = {"role": role} if role else {}
        return [self._clean(doc) for doc in self.users.find(query)]

    def create_session(self, token: str, user_id: str) -> dict[str, Any]:
        doc = {"_id": token, "id": token, "user_id": str(user_id), "created_at": utc_now()}
        self.sessions.insert_one(doc)
        return doc

    def get_session(self, token: str) -> dict[str, Any] | None:
        return self._clean(self.sessions.find_one({"$or": [{"_id": token}, {"id": token}]}))

    def delete_session(self, token: str) -> bool:
        res = self.sessions.delete_one({"$or": [{"_id": token}, {"id": token}]})
        return res.deleted_count > 0


class IdentityRepository(BaseRepository):
    @abstractmethod
    def get_bootstrap_record(self) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def record_bootstrap(self, user_id: str, details: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def record_provisioning(self, user_id: str, details: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_provisioned_reviewers(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class MongoIdentityRepository(IdentityRepository):
    def __init__(self, db: pymongo.database.Database):
        self.db = db
        self.bootstrap = db["review_admin_bootstrap"]
        self.provisioning = db["review_admin_provisioning"]

    def _clean(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if not doc:
            return None
        res = dict(doc)
        res.pop("_id", None)
        return res

    def get_bootstrap_record(self) -> dict[str, Any] | None:
        return self._clean(self.bootstrap.find_one({}))

    def record_bootstrap(self, user_id: str, details: dict[str, Any]) -> None:
        doc = {"_id": "one-time", "id": "one-time", "user_id": user_id, **details}
        self.bootstrap.insert_one(doc)

    def record_provisioning(self, user_id: str, details: dict[str, Any]) -> None:
        doc = {"_id": user_id, "id": user_id, "user_id": user_id, **details}
        self.provisioning.insert_one(doc)

    def list_provisioned_reviewers(self) -> list[dict[str, Any]]:
        return [self._clean(d) for d in self.provisioning.find({})]
