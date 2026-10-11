import copy
import multiprocessing
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.models.orchestration import AgentContract
from backend.services.agent_registry import AgentRegistry
from backend.services.case_blackboard import CaseBlackboard, VersionConflict


def increment_file(path, count):
    db = MockDatabaseAdapter(path)
    for _ in range(count):
        db.mutate("counter", "one", lambda r: {"n": r["n"] + 1})


class BlackboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "db.json")
        self.db = MockDatabaseAdapter(self.path)
        self.db.create("cases", {"id": "c", "case_id": "c", "owner_user_id": "u", "status": "DRAFT"})
        self.store = CaseBlackboard(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_initialize_old_case_is_idempotent_and_non_destructive(self):
        before = self.db.get("cases", "c")
        first = self.store.read_board("c")
        self.assertEqual(first, self.store.read_board("c"))
        self.assertEqual(before, self.db.get("cases", "c"))
        self.assertEqual(first["data"]["facts"], {})

    def test_versions_immutable_history_and_pagination(self):
        first = self.store.read_board("c")
        head = self.db.get("case_board_heads", "c")
        old = self.db.get("case_board_snapshots", head["snapshot_id"])
        self.store.append_change("c", {"facts.F001": "human statement"}, actor="u", reason="correction")
        self.assertEqual(self.store.read_board("c")["version"], 2)
        self.assertEqual(old, self.db.get("case_board_snapshots", head["snapshot_id"]))
        page = self.store.history("c", 1)
        self.assertEqual(page["events"][0]["before"], {"facts.F001": None})
        self.assertEqual(self.store.history("c", 1, page["cursor"])["events"][0]["version"], 1)
        self.assertEqual(first, old["board"])

    def test_optimistic_collision_and_parallel_rebase(self):
        first = self.store.read_board("c")
        def write(i):
            return self.store.append_change("c", {f"facts.F{i}": i}, actor="u", reason="parallel")
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(write, range(8)))
        self.assertEqual(len(self.store.read_board("c")["data"]["facts"]), 8)
        with self.assertRaises(VersionConflict):
            self.store.append_change("c", {"facts.bad": True}, actor="u", reason="old", expected_version=first["version"])

    def test_local_adapter_serializes_processes(self):
        self.db.create("counter", {"id": "one", "n": 0})
        ctx = multiprocessing.get_context("spawn")
        workers = [ctx.Process(target=increment_file, args=(self.path, 12)) for _ in range(3)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(20)
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual(self.db.get("counter", "one")["n"], 36)

    def test_raw_references_all_origins_no_content_duplication(self):
        for origin in ("CITIZEN_SELF_SERVICE", "CITIZEN_DIRECT_ADVOCATE", "ADVOCATE_WALK_IN"):
            self.db.update("cases", "c", {"origin": origin, "input_version": 2, "raw_package": {
                "version": 1, "input_version": 2, "canonical_narrative": "PRIVATE_RAW", "pending": [],
                "provenance": [{"source_id": "STORY", "original_text": "PRIVATE_RAW"}], "unknown_details": [{"label": "PRIVATE_RAW"}]}})
            board = self.store.sync_input("c")
            self.assertEqual(board["data"]["identity"]["origin"], origin)
            self.assertTrue(board["data"]["input"]["ready"])
            self.assertNotIn("PRIVATE_RAW", str(board))

    def test_conflict_decisions_and_protection(self):
        for decision, expected in (("KEEP", "human"), ("REPLACE", "machine"), ("MERGE", "reviewed")):
            self.store.apply_human_override("c", "facts.F001", "human", actor="advocate", reason="verified statement")
            board = self.store.record_conflict("c", "facts.F001", ["human", "machine"], ["advocate", decision])
            cid = next(k for k, c in board["conflicts"].items() if not c["resolution"])
            board = self.store.resolve_conflict("c", cid, decision, actor="advocate", reason="reviewed", merged_value="reviewed")
            self.assertEqual(board["data"]["facts"]["F001"], expected)
            with self.assertRaises(ValueError):
                self.store.append_change("c", {"facts": {}}, actor="agent", reason="overwrite")

    def test_crash_before_head_advance_does_not_publish_orphan_snapshot(self):
        first = self.store.read_board("c")
        with patch.object(self.db, "mutate", side_effect=RuntimeError("simulated worker interruption")):
            with self.assertRaises(RuntimeError):
                self.store.append_change("c", {"facts.F1": "uncommitted"}, actor="u", reason="interrupted")
        self.assertEqual(self.store.read_board("c"), first)
        self.assertEqual(len(self.store.history("c")["events"]), 1)
        self.store.append_change("c", {"facts.F1": "committed"}, actor="u", reason="resume")
        self.assertEqual(self.store.read_board("c")["version"], 2)

    def test_large_output_fails_closed_without_overwriting_history(self):
        before = self.store.read_board("c")
        with self.assertRaisesRegex(ValueError, "capacity"):
            self.store.append_change("c", {"facts.large": "x" * 310_000}, actor="u", reason="too large")
        self.assertEqual(self.store.read_board("c"), before)


class RegistryTests(unittest.TestCase):
    def contract(self, name, **kwargs):
        return AgentContract(agent_type=name, version="1.0.0", engine=1, purpose="nonlegal test", **kwargs)

    def test_validation_duplicate_missing_and_truthful_availability(self):
        registry = AgentRegistry().register(self.contract("FUTURE"))
        self.assertFalse(registry.describe()[0]["implemented"])
        with self.assertRaises(ValueError):
            registry.register(self.contract("FUTURE"))
        with self.assertRaises(ValueError):
            registry.graph(["MISSING"])
        with self.assertRaises(ValueError):
            AgentContract(agent_type="A", version="latest", engine=1, purpose="bad")
        with self.assertRaises(ValueError):
            registry.register(self.contract("OUTPUT", writes=("facts",)), lambda c: {})

    def test_graph_branch_cycle_and_packs(self):
        registry = AgentRegistry()
        for name, deps in (("A", ()), ("B", ("A",)), ("C", ("A",)), ("D", ("B", "C"))):
            registry.register(self.contract(name, dependencies=deps, pack="GENERIC"))
        self.assertEqual(registry.graph(["D"])["D"], ["B", "C"])
        self.assertEqual(len(registry.select_pack("GENERIC")), 4)
        cyclic = AgentRegistry().register(self.contract("A", dependencies=("B",))).register(self.contract("B", dependencies=("A",)))
        with self.assertRaises(ValueError):
            cyclic.graph(["A"])
