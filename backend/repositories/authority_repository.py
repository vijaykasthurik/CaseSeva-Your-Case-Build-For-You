"""Legal authority and review repository contracts and MongoDB implementations."""
from abc import ABC, abstractmethod
from typing import Any
import pymongo


class AuthorityRepository(ABC):
    @abstractmethod
    def get_head(self, source_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def set_head(self, source_id: str, version_id: str, expected_version: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def save_version(self, version_id: str, source: dict[str, Any], reason: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_version(self, version_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def list_heads(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_versions_for_source(self, source_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError


class MongoAuthorityRepository(AuthorityRepository):
    def __init__(self, db: pymongo.database.Database):
        self.db = db
        self.heads = db["legal_authority_heads"]
        self.versions = db["legal_authority_versions"]

    def _clean(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if not doc:
            return None
        res = dict(doc)
        if "_id" in res:
            if "id" not in res:
                res["id"] = str(res["_id"])
            res.pop("_id", None)
        return res

    def get_head(self, source_id: str) -> dict[str, Any] | None:
        target = str(source_id)
        doc = self.heads.find_one({"$or": [{"_id": target}, {"id": target}]})
        return self._clean(doc)

    def set_head(self, source_id: str, version_id: str, expected_version: str | None = None) -> dict[str, Any]:
        target = str(source_id)
        current = self.heads.find_one({"$or": [{"_id": target}, {"id": target}]})
        if current and expected_version is not None and current.get("version") != expected_version:
            raise ValueError("Authority changed during review")
        head_doc = {
            "_id": target,
            "id": target,
            "version": str(version_id)
        }
        self.heads.replace_one({"_id": target}, head_doc, upsert=True)
        return self._clean(head_doc) or head_doc

    def save_version(self, version_id: str, source: dict[str, Any], reason: str) -> dict[str, Any]:
        vid = str(version_id)
        doc = {
            "_id": vid,
            "id": vid,
            "source": dict(source),
            "reason": reason
        }
        self.versions.replace_one({"_id": vid}, doc, upsert=True)
        return self._clean(doc) or doc

    def get_version(self, version_id: str) -> dict[str, Any] | None:
        vid = str(version_id)
        doc = self.versions.find_one({"$or": [{"_id": vid}, {"id": vid}]})
        return self._clean(doc)

    def list_heads(self) -> list[dict[str, Any]]:
        return [self._clean(d) for d in self.heads.find({})]

    def list_versions_for_source(self, source_id: str) -> list[dict[str, Any]]:
        target = str(source_id)
        return [self._clean(d) for d in self.versions.find({"source.source_id": target})]


class ReviewRepository(ABC):
    @abstractmethod
    def save_review(self, review: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_review(self, review_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def list_reviews_for_source(self, source_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def save_submission(self, submission: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_submissions_for_source(self, source_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def save_ingestion_request(self, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_ingestion_request(self, request_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def update_ingestion_request(self, request_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class MongoReviewRepository(ReviewRepository):
    def __init__(self, db: pymongo.database.Database):
        self.db = db
        self.reviews = db["legal_authority_reviews"]
        self.submissions = db["legal_review_submissions"]
        self.ingestions = db["legal_ingestion_requests"]

    def _clean(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if not doc:
            return None
        res = dict(doc)
        if "_id" in res:
            if "id" not in res:
                res["id"] = str(res["_id"])
            res.pop("_id", None)
        return res

    def save_review(self, review: dict[str, Any]) -> dict[str, Any]:
        doc = dict(review)
        rid = str(doc["id"])
        doc["_id"] = rid
        self.reviews.replace_one({"_id": rid}, doc, upsert=True)
        return self._clean(doc) or doc

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        target = str(review_id)
        return self._clean(self.reviews.find_one({"$or": [{"_id": target}, {"id": target}]}))

    def list_reviews_for_source(self, source_id: str) -> list[dict[str, Any]]:
        target = str(source_id)
        return [self._clean(d) for d in self.reviews.find({"source_id": target})]

    def save_submission(self, submission: dict[str, Any]) -> dict[str, Any]:
        doc = dict(submission)
        sid = str(doc["id"])
        doc["_id"] = sid
        self.submissions.replace_one({"_id": sid}, doc, upsert=True)
        return self._clean(doc) or doc

    def list_submissions_for_source(self, source_id: str) -> list[dict[str, Any]]:
        target = str(source_id)
        return [self._clean(d) for d in self.submissions.find({"source_id": target})]

    def save_ingestion_request(self, request: dict[str, Any]) -> dict[str, Any]:
        doc = dict(request)
        rid = str(doc["id"])
        doc["_id"] = rid
        self.ingestions.replace_one({"_id": rid}, doc, upsert=True)
        return self._clean(doc) or doc

    def get_ingestion_request(self, request_id: str) -> dict[str, Any] | None:
        target = str(request_id)
        return self._clean(self.ingestions.find_one({"$or": [{"_id": target}, {"id": target}]}))

    def update_ingestion_request(self, request_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        target = str(request_id)
        self.ingestions.update_one({"$or": [{"_id": target}, {"id": target}]}, {"$set": updates})
        return self.get_ingestion_request(target) or {}
