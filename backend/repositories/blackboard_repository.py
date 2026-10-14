"""Case Blackboard repository contracts and MongoDB implementations."""
from abc import ABC, abstractmethod
import copy
import time
from typing import Any
import pymongo


class BlackboardRepository(ABC):
    @abstractmethod
    def get_head(self, case_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def save_head(self, case_id: str, version: int, snapshot_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def advance_head(self, case_id: str, version: int, snapshot_id: str, expected_snapshot_id: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def save_snapshot(self, snapshot: dict[str, Any]) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def get_history(self, case_id: str, limit: int = 20, cursor: str | None = None) -> dict[str, Any]:
        raise NotImplementedError


class MongoBlackboardRepository(BlackboardRepository):
    def __init__(self, db: pymongo.database.Database):
        self.db = db
        self.heads = db["case_board_heads"]
        self.snapshots = db["case_board_snapshots"]

    def _clean(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if not doc:
            return None
        res = dict(doc)
        if "_id" in res:
            if "id" not in res:
                res["id"] = str(res["_id"])
            res.pop("_id", None)
        return res

    def get_head(self, case_id: str) -> dict[str, Any] | None:
        target = str(case_id)
        doc = self.heads.find_one({"$or": [{"_id": target}, {"id": target}]})
        return self._clean(doc)

    def save_head(self, case_id: str, version: int, snapshot_id: str) -> dict[str, Any]:
        target = str(case_id)
        head_doc = {
            "_id": target,
            "id": target,
            "version": version,
            "snapshot_id": str(snapshot_id),
            "_revision": 1
        }
        self.heads.replace_one({"_id": target}, head_doc, upsert=True)
        return self._clean(head_doc) or head_doc

    def advance_head(self, case_id: str, version: int, snapshot_id: str, expected_snapshot_id: str | None = None) -> dict[str, Any]:
        target = str(case_id)
        for attempt in range(50):
            current = self.heads.find_one({"$or": [{"_id": target}, {"id": target}]})
            if current is None:
                raise KeyError(case_id)
            if expected_snapshot_id is not None and current.get("snapshot_id") != expected_snapshot_id:
                from ..services.case_blackboard import VersionConflict
                raise VersionConflict("Concurrent Blackboard commit")

            revision = current.get("_revision", 0)
            updated = {
                "_id": target,
                "id": target,
                "version": version,
                "snapshot_id": str(snapshot_id),
                "_revision": revision + 1
            }
            res = self.heads.replace_one(
                {"_id": target, "_revision": revision},
                updated,
                upsert=False
            )
            if res.matched_count > 0:
                return self._clean(updated) or updated
            time.sleep(0.01)

        from ..services.case_blackboard import VersionConflict
        raise VersionConflict("Blackboard contention; retry later")

    def save_snapshot(self, snapshot: dict[str, Any]) -> str:
        doc = dict(snapshot)
        sid = str(doc["id"])
        doc["_id"] = sid
        self.snapshots.insert_one(doc)
        return sid

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        target = str(snapshot_id)
        doc = self.snapshots.find_one({"$or": [{"_id": target}, {"id": target}]})
        return self._clean(doc)

    def get_history(self, case_id: str, limit: int = 20, cursor: str | None = None) -> dict[str, Any]:
        target = str(case_id)
        head = self.get_head(target)
        if not head:
            return {"events": [], "cursor": None}

        sid = cursor or head.get("snapshot_id")
        events = []
        while sid and len(events) < limit:
            snap = self.get_snapshot(sid)
            if not snap or snap.get("case_id") != target:
                raise ValueError("Invalid history cursor")
            events.append(copy.deepcopy(snap.get("event")))
            sid = snap.get("previous")
        return {"events": events, "cursor": sid}
