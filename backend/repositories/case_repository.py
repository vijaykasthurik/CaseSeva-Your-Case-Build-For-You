"""Case repository contracts and MongoDB implementations."""
from abc import ABC, abstractmethod
import copy
import time
from typing import Any, Callable
import pymongo


class CaseRepository(ABC):
    @abstractmethod
    def get_case(self, case_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def create_case(self, case_data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def update_case(self, case_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def mutate_case(self, case_id: str, transform: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_cases_for_owner(self, owner_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_cases_for_advocate(self, advocate_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def delete_case(self, case_id: str) -> bool:
        raise NotImplementedError


class MongoCaseRepository(CaseRepository):
    def __init__(self, db: pymongo.database.Database):
        self.db = db
        self.cases = db["cases"]

    def _clean(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if not doc:
            return None
        res = dict(doc)
        if "_id" in res:
            if "id" not in res:
                res["id"] = str(res["_id"])
            res.pop("_id", None)
        return res

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        target = str(case_id)
        doc = self.cases.find_one({"$or": [{"_id": target}, {"id": target}, {"case_id": target}]})
        return self._clean(doc)

    def create_case(self, case_data: dict[str, Any]) -> dict[str, Any]:
        doc = dict(case_data)
        cid = str(doc.get("id") or doc.get("case_id"))
        doc["_id"] = cid
        doc.setdefault("id", cid)
        doc.setdefault("case_id", cid)
        doc.setdefault("_revision", 1)
        self.cases.insert_one(doc)
        return self._clean(doc) or dict(case_data)

    def update_case(self, case_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        return self.mutate_case(case_id, lambda current: updates)

    def mutate_case(self, case_id: str, transform: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        target = str(case_id)
        for attempt in range(50):
            current = self.cases.find_one({"$or": [{"_id": target}, {"id": target}, {"case_id": target}]})
            if current is None:
                raise KeyError(case_id)
            cleaned = self._clean(current) or {}
            revision = current.get("_revision", 0)

            modifications = transform(copy.deepcopy(cleaned))
            cleaned.update(modifications)
            cleaned["_revision"] = revision + 1
            cleaned["_id"] = target
            cleaned.setdefault("id", target)
            cleaned.setdefault("case_id", target)

            res = self.cases.replace_one(
                {"_id": target, "_revision": revision},
                cleaned,
                upsert=False
            )
            if res.matched_count > 0:
                return cleaned
            time.sleep(0.01)

        raise RuntimeError(f"Concurrent updates to case {case_id} could not be resolved.")

    def list_cases_for_owner(self, owner_id: str) -> list[dict[str, Any]]:
        return [self._clean(d) for d in self.cases.find({"owner_user_id": str(owner_id)})]

    def list_cases_for_advocate(self, advocate_id: str) -> list[dict[str, Any]]:
        return [self._clean(d) for d in self.cases.find({"assigned_advocate_id": str(advocate_id)})]

    def delete_case(self, case_id: str) -> bool:
        target = str(case_id)
        res = self.cases.delete_one({"$or": [{"_id": target}, {"id": target}, {"case_id": target}]})
        return res.deleted_count > 0
