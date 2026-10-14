"""Document and evidence repository contracts and MongoDB implementations."""
from abc import ABC, abstractmethod
from typing import Any
import pymongo


class DocumentRepository(ABC):
    @abstractmethod
    def save_document(self, document: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_document(self, document_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def list_documents_for_case(self, case_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def update_document(self, document_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def delete_document(self, document_id: str) -> bool:
        raise NotImplementedError


class MongoDocumentRepository(DocumentRepository):
    def __init__(self, db: pymongo.database.Database):
        self.db = db
        self.documents = db["documents"]

    def _clean(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if not doc:
            return None
        res = dict(doc)
        if "_id" in res:
            if "id" not in res:
                res["id"] = str(res["_id"])
            res.pop("_id", None)
        return res

    def save_document(self, document: dict[str, Any]) -> dict[str, Any]:
        doc = dict(document)
        doc_id = str(doc["id"])
        doc["_id"] = doc_id
        self.documents.replace_one({"_id": doc_id}, doc, upsert=True)
        return self._clean(doc) or dict(document)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        target = str(document_id)
        doc = self.documents.find_one({"$or": [{"_id": target}, {"id": target}]})
        return self._clean(doc)

    def list_documents_for_case(self, case_id: str) -> list[dict[str, Any]]:
        target = str(case_id)
        return [self._clean(d) for d in self.documents.find({"case_id": target})]

    def update_document(self, document_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        target = str(document_id)
        self.documents.update_one({"$or": [{"_id": target}, {"id": target}]}, {"$set": updates})
        return self.get_document(target) or {}

    def delete_document(self, document_id: str) -> bool:
        target = str(document_id)
        res = self.documents.delete_one({"$or": [{"_id": target}, {"id": target}]})
        return res.deleted_count > 0


class EvidenceRepository(ABC):
    @abstractmethod
    def add_evidence(self, case_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_evidence(self, case_id: str, evidence_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def list_evidence(self, case_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError


class MongoEvidenceRepository(EvidenceRepository):
    def __init__(self, db: pymongo.database.Database):
        self.db = db
        self.cases = db["cases"]

    def add_evidence(self, case_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        target = str(case_id)
        self.cases.update_one(
            {"$or": [{"_id": target}, {"id": target}, {"case_id": target}]},
            {"$push": {"evidence": evidence}}
        )
        return evidence

    def get_evidence(self, case_id: str, evidence_id: str) -> dict[str, Any] | None:
        target = str(case_id)
        case = self.cases.find_one({"$or": [{"_id": target}, {"id": target}, {"case_id": target}]})
        if not case:
            return None
        for item in case.get("evidence", []):
            if item.get("evidence_id") == evidence_id:
                return item
        return None

    def list_evidence(self, case_id: str) -> list[dict[str, Any]]:
        target = str(case_id)
        case = self.cases.find_one({"$or": [{"_id": target}, {"id": target}, {"case_id": target}]})
        if not case:
            return []
        return case.get("evidence", [])
