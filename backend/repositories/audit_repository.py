"""Audit and citation repository contracts and MongoDB implementations."""
from abc import ABC, abstractmethod
from typing import Any
from uuid import uuid4
import pymongo

from ..models.case import utc_now


class AuditRepository(ABC):
    @abstractmethod
    def record_event(self, case_id: str, event_type: str, actor: str, detail: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_events_for_case(self, case_id: str, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError


class MongoAuditRepository(AuditRepository):
    def __init__(self, db: pymongo.database.Database):
        self.db = db
        self.events = db["audit_events"]

    def _clean(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if not doc:
            return None
        res = dict(doc)
        if "_id" in res:
            if "id" not in res:
                res["id"] = str(res["_id"])
            res.pop("_id", None)
        return res

    def record_event(self, case_id: str, event_type: str, actor: str, detail: dict[str, Any]) -> dict[str, Any]:
        eid = uuid4().hex
        doc = {
            "_id": eid,
            "id": eid,
            "case_id": str(case_id),
            "event_type": event_type,
            "actor": actor,
            "created_at": utc_now(),
            "detail": detail
        }
        self.events.insert_one(doc)
        return self._clean(doc) or doc

    def list_events_for_case(self, case_id: str, limit: int = 100) -> list[dict[str, Any]]:
        target = str(case_id)
        cursor = self.events.find({"case_id": target}).sort("created_at", pymongo.DESCENDING).limit(limit)
        return [self._clean(d) for d in cursor]


class CitationRepository(ABC):
    @abstractmethod
    def record_citation(self, citation_id: str, source_id: str, text: str, metadata: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_citation(self, citation_id: str) -> dict[str, Any] | None:
        raise NotImplementedError


class MongoCitationRepository(CitationRepository):
    def __init__(self, db: pymongo.database.Database):
        self.db = db
        self.citations = db["citations"]

    def _clean(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if not doc:
            return None
        res = dict(doc)
        if "_id" in res:
            if "id" not in res:
                res["id"] = str(res["_id"])
            res.pop("_id", None)
        return res

    def record_citation(self, citation_id: str, source_id: str, text: str, metadata: dict[str, Any]) -> dict[str, Any]:
        doc = {
            "_id": str(citation_id),
            "id": str(citation_id),
            "source_id": str(source_id),
            "text": text,
            "metadata": metadata,
            "created_at": utc_now()
        }
        self.citations.replace_one({"_id": str(citation_id)}, doc, upsert=True)
        return self._clean(doc) or doc

    def get_citation(self, citation_id: str) -> dict[str, Any] | None:
        return self._clean(self.citations.find_one({"$or": [{"_id": str(citation_id)}, {"id": str(citation_id)}]}))
