"""Versioned side-by-side Blackboard, persisted through the existing DB adapter.

Immutable snapshots are prepared before atomically advancing a small head record.
Only the linked head chain is committed history; abandoned CAS proposals are never
read as history. A crash cannot expose a head without its checkpoint. All methods
are internal services; HTTP callers must perform authorization before calling.
"""
import copy
import hashlib
import json
import re
from uuid import uuid4
from ..adapters.database import DatabaseAdapter
from ..models.case import utc_now
from .agent_registry import overlaps

HEADS = "case_board_heads"
SNAPSHOTS = "case_board_snapshots"
MAX_SNAPSHOT_BYTES = 300_000


class VersionConflict(RuntimeError):
    pass


class SnapshotCapacityExceeded(ValueError):
    """Output is preserved externally or requires review; never truncate it."""
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def value_at(data, path):
    value = data
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def put_path(data, path, value):
    if not re.fullmatch(r"[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*", path):
        raise ValueError("Invalid Blackboard path")
    parts = path.split(".")
    for key in parts[:-1]:
        if key not in data:
            data[key] = {}
        if not isinstance(data[key], dict):
            raise ValueError("Cannot traverse a scalar Blackboard value")
        data = data[key]
    data[parts[-1]] = copy.deepcopy(value)


def path_version(board, path):
    return max((version for changed, version in board["path_versions"].items() if overlaps(changed, path)), default=0)


def versions(board, paths):
    return {p: path_version(board, p) for p in paths}


def invalidate(board, paths, exclude=()):
    """Follow declared field dependencies; do not invalidate unrelated branches."""
    pending, affected = list(paths), set()
    while pending:
        path = pending.pop()
        for name, node in board["nodes"].items():
            if name in affected or name in exclude:
                continue
            contract = node["contract"]
            watches = node.get("watched_paths", contract["reads"] + contract["required_inputs"] + contract["optional_inputs"] + contract["stale_on"] + [c["path"] for c in contract["conditions"]])
            if any(overlaps(path, p) for p in watches):
                affected.add(name)
                if node["status"] != "WAITING":
                    node.update(status="STALE", claim_token=None, stale=True)
                pending.extend(contract["writes"])
    provenance = board.get("case_file")
    affected_paths = list(paths) + [p for name in affected for p in board["nodes"][name]["contract"]["writes"]]
    if provenance and any(overlaps(p, d) for p in affected_paths for d in provenance["dependency_versions"]):
        provenance["status"] = "STALE"
    return sorted(affected)


def set_values(board, changes, exclude=(), force_version=False):
    changed = []
    for path, value in changes.items():
        if force_version or value_at(board["data"], path) != value:
            put_path(board["data"], path, value)
            board["path_versions"][path] = board["version"] + 1
            changed.append(path)
    return changed, invalidate(board, changed, exclude)


def input_references(case):
    raw = case.get("raw_package") or {}
    base = f"cases/{case['case_id']}/raw_package"
    return {
        "input_version": case.get("input_version", 1), "raw_case_package_version": raw.get("version"),
        "raw_input_version": raw.get("input_version"), "canonical_hash": raw.get("canonical_hash"),
        "raw_fingerprint": digest(raw) if raw else None,
        "canonical_narrative_ref": base + "/canonical_narrative" if raw else None,
        "original_language_ref": base + "/original_language_content" if raw else None,
        "source_ids": [s["source_id"] for s in raw.get("provenance", [])],
        "evidence_ids": [e["evidence_id"] for e in case.get("evidence", [])],
        "declaration_refs": {key: [base + f"/{key}/{i}" for i, _ in enumerate(raw.get(key, []))]
                             for key in ("declared_evidence", "unavailable_evidence", "unknown_evidence", "unknown_details")},
        "extraction_failure_refs": [base + f"/pending/{i}" for i, _ in enumerate(raw.get("pending", []))],
        "ready": bool(raw) and raw.get("input_version", 1) == case.get("input_version", 1) and not raw.get("pending"),
    }


def identity(case):
    return {"case_id": case["case_id"], "origin": case.get("origin", "CITIZEN_SELF_SERVICE"),
            "stage": case.get("stage"), "status": case.get("status"),
            "created_by": case.get("created_by_advocate_id", case.get("owner_user_id")),
            "owner": case.get("owner_user_id"), "preferred_language": case.get("preferred_language", "English"),
            "client_ref": case.get("guest_client_id", case.get("owner_user_id")),
            "advocate_ref": case.get("assigned_advocate_id"), "workflow_state": case.get("journey_stage"),
            "active_engine": case.get("active_engine"), "current_case_file_version": case.get("case_file", {}).get("version")}


class CaseBlackboard:
    def __init__(self, db):
        if type(db).mutate is DatabaseAdapter.mutate:
            raise TypeError("Blackboard requires an atomic database mutate implementation")
        self.db = db

    def _save(self, board, previous, event):
        snapshot = {"case_id": board["case_id"], "board": board, "previous": previous, "event": event}
        snapshot["id"] = digest(snapshot)
        if len(json.dumps(snapshot, ensure_ascii=False).encode()) > MAX_SNAPSHOT_BYTES:
            raise SnapshotCapacityExceeded("Blackboard checkpoint capacity reached; split agent output into references")
        try:
            self.db.create(SNAPSHOTS, snapshot)
        except ValueError:
            existing = self.db.get(SNAPSHOTS, snapshot["id"])
            if not existing or existing.get("board") != board:
                raise
        return snapshot["id"]

    def read_board(self, case_id):
        case = self.db.get("cases", case_id)
        if not case:
            raise KeyError(case_id)
        head = self.db.get(HEADS, case_id)
        if head is None:
            board = {"schema_version": 1, "case_id": case_id, "version": 1,
                     "data": {"identity": identity(case), "input": input_references(case),
                              **{key: {} for key in ("facts", "incidents", "timeline", "parties", "evidence_mapping", "legal_issues", "legal_sources")}},
                     "path_versions": {"identity": 1, "input": 1}, "nodes": {}, "conflicts": {},
                     "protected": {}, "case_file": None, "run": None}
            event = {"type": "INITIALIZED", "actor": "system", "timestamp": utc_now(), "version": 1,
                     "previous_version": 0, "reason": "Non-destructive lazy initialization", "changed_paths": ["identity", "input"], "affected_outputs": []}
            sid = self._save(board, None, event)
            try:
                head = self.db.create(HEADS, {"id": case_id, "version": 1, "snapshot_id": sid})
            except ValueError:
                head = self.db.get(HEADS, case_id)
        return copy.deepcopy(self.db.get(SNAPSHOTS, head["snapshot_id"])["board"])

    def change(self, case_id, transform, *, actor="system", kind="CHANGE", reason="", expected_version=None):
        self.read_board(case_id)
        for _ in range(10):
            head = self.db.get(HEADS, case_id)
            board = copy.deepcopy(self.db.get(SNAPSHOTS, head["snapshot_id"])["board"])
            if expected_version is not None and board["version"] != expected_version:
                raise VersionConflict("Blackboard version changed")
            before = copy.deepcopy(board)
            detail = transform(board) or {}
            if board == before:
                return board
            board["version"] += 1
            event = {"type": kind, "actor": actor, "timestamp": utc_now(), "version": board["version"],
                     "previous_version": before["version"], "reason": reason, "changed_paths": [], "affected_outputs": [], **detail}
            sid = self._save(board, head["snapshot_id"], event)
            def advance(current):
                if current["snapshot_id"] != head["snapshot_id"]:
                    raise VersionConflict("Concurrent Blackboard commit")
                return {"version": board["version"], "snapshot_id": sid}
            try:
                self.db.mutate(HEADS, case_id, advance)
                return board
            except VersionConflict:
                if expected_version is not None:
                    raise
        raise VersionConflict("Blackboard contention; retry later")

    def append_change(self, case_id, changes, *, actor, reason, expected_version=None):
        def transform(board):
            if any(overlaps(path, p) for path in changes for p in board["protected"]):
                raise ValueError("Protected fields require an explicit human decision")
            original = {p: value_at(board["data"], p) for p in changes}
            paths, affected = set_values(board, changes)
            return {"changed_paths": paths, "affected_outputs": affected, "before": original, "after": changes}
        return self.change(case_id, transform, actor=actor, kind="HUMAN_CHANGE", reason=reason, expected_version=expected_version)

    def sync_input(self, case_id):
        def transform(board):
            # Re-read on CAS retry; a stale caller cannot regress the input bridge.
            case = self.db.get("cases", case_id)
            changes = {"identity." + key: value for key, value in identity(case).items()}
            changes.update({"input." + key: value for key, value in input_references(case).items()})
            changes["evidence"] = {item["evidence_id"]: {
                **board["data"].get("evidence", {}).get(item["evidence_id"], {}),
                "evidence_id": item["evidence_id"], "source_ref": f"cases/{case_id}/evidence/{item['evidence_id']}",
                "extraction_status": item.get("extraction", {}).get("status", "PENDING"),
                "review_state": board["data"].get("evidence", {}).get(item["evidence_id"], {}).get("review_state", "REVIEW_REQUIRED")}
                for item in case.get("evidence", [])}
            paths, affected = set_values(board, changes)
            return {"changed_paths": paths, "affected_outputs": affected}
        return self.change(case_id, transform, kind="INPUT_SYNC", reason="Reference existing Phase 1 output")

    def history(self, case_id, limit=20, cursor=None):
        if not 1 <= limit <= 100:
            raise ValueError("History page limit must be 1..100")
        self.read_board(case_id)
        sid = cursor or self.db.get(HEADS, case_id)["snapshot_id"]
        events = []
        while sid and len(events) < limit:
            snapshot = self.db.get(SNAPSHOTS, sid)
            if not snapshot or snapshot["case_id"] != case_id:
                raise ValueError("Invalid history cursor")
            events.append(copy.deepcopy(snapshot["event"]))
            sid = snapshot["previous"]
        return {"events": events, "cursor": sid}

    def mark_stale(self, case_id, paths, actor="system"):
        return self.change(case_id, lambda board: {"affected_outputs": invalidate(board, paths), "changed_paths": paths}, actor=actor, kind="STALE")

    def record_case_file(self, case_id, provenance):
        from ..models.orchestration import CaseFileProvenance
        provenance = CaseFileProvenance.model_validate(provenance).model_dump()
        def transform(board):
            if (board["version"] != provenance["board_version"]
                    or provenance["input_version"] != board["data"]["input"]["input_version"]
                    or versions(board, provenance["dependency_versions"]) != provenance["dependency_versions"]):
                raise VersionConflict("Case File dependencies changed")
            board["case_file"] = provenance
        return self.change(case_id, transform, kind="CASE_FILE_REFERENCED")

    @staticmethod
    def add_conflict(board, field, values, sources, *, agents=(), facts=(), execution_id=None):
        record = {"field": field, "values": values, "sources": sources, "agents": list(agents),
                  "facts": list(facts), "execution_id": execution_id,
                  "observed_value": copy.deepcopy(value_at(board["data"], field))}
        cid = digest(record)
        board["conflicts"].setdefault(cid, {**record, "conflict_id": cid, "status": "CONFLICT_FOUND", "resolution": None})
        return cid

    def record_conflict(self, case_id, field, values, sources, **kwargs):
        if len(values) < 2 or len(sources) != len(values):
            raise ValueError("Conflicts require competing values and their sources")
        def transform(board):
            self.add_conflict(board, field, values, sources, **kwargs)
        return self.change(case_id, transform, kind="CONFLICT_FOUND")

    def apply_human_override(self, case_id, path, value, *, actor, reason):
        def transform(board):
            old = copy.deepcopy(value_at(board["data"], path))
            paths, affected = set_values(board, {path: value})
            board["protected"][path] = {"actor": actor, "reason": reason, "value": value, "timestamp": utc_now()}
            return {"changed_paths": paths, "affected_outputs": affected, "before": old, "after": value}
        return self.change(case_id, transform, actor=actor, kind="ADVOCATE_OVERRIDE", reason=reason)

    def resolve_conflict(self, case_id, conflict_id, decision, *, actor, reason, merged_value=None):
        if decision not in {"KEEP", "REPLACE", "MERGE"}:
            raise ValueError("Choose KEEP, REPLACE or MERGE")
        if decision == "MERGE" and merged_value is None:
            raise ValueError("MERGE requires an explicit reviewed value")
        def transform(board):
            conflict = board["conflicts"][conflict_id]
            if conflict["resolution"] is not None:
                return
            path = conflict["field"]
            # Refuse a decision against a superseded human edit.
            if value_at(board["data"], path) != conflict.get("observed_value", conflict["values"][0]):
                raise VersionConflict("The protected value changed; review the conflict again")
            value = conflict["values"][0] if decision == "KEEP" else conflict["values"][1] if decision == "REPLACE" else merged_value
            paths, affected = set_values(board, {path: value})
            board["protected"][path] = {"actor": actor, "reason": reason, "value": value, "timestamp": utc_now()}
            conflict["status"] = "RESOLVED"
            conflict["resolution"] = {"decision": decision, "actor": actor, "reason": reason, "value": value, "timestamp": utc_now()}
            for name in conflict["agents"]:
                node = board["nodes"].get(name)
                if node and (node.get("pending_result") or {}).get("status") == "CONFLICT_FOUND" and not any(
                    name in other["agents"] and not other["resolution"] for other in board["conflicts"].values()
                ):
                    node.update(status="STALE", stale=True, claim_token=None,
                                review_generation=node.get("review_generation", 0) + 1)
            return {"changed_paths": paths, "affected_outputs": affected, "before": conflict["values"], "after": value}
        return self.change(case_id, transform, actor=actor, kind="CONFLICT_RESOLVED", reason=reason)
