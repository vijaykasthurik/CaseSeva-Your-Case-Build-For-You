"""Non-legal test agents only. Never registered by the application."""
import copy
import multiprocessing
import tempfile
import threading
import time
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.models.orchestration import AgentContract, AgentResult, Condition
from backend.services.agent_registry import AgentRegistry
from backend.services.case_blackboard import CaseBlackboard
from backend.services.orchestrator import MasterLegalOrchestrator, TransientAgentError


def integer(value):
    if type(value) is not int:
        raise ValueError("Expected an integer")
    return True


def resume_in_new_process(path):
    db = MockDatabaseAdapter(path)
    board = CaseBlackboard(db).read_board("c")
    registry = AgentRegistry()
    for name, node in board["nodes"].items():
        contract = AgentContract.model_validate(node["contract"])
        registry.register(contract, lambda c, name=name: AgentResult(status="COMPLETED", outputs={"test." + name: 7}), {"test." + name: integer})
    controller = MasterLegalOrchestrator(db, registry)
    controller.tick("c")
    controller.tick("c")


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "db.json")
        self.db = MockDatabaseAdapter(self.path)
        self.db.create("cases", {"id": "c", "case_id": "c", "owner_user_id": "u"})
        self.store = CaseBlackboard(self.db)
        self.registry = AgentRegistry()
        self.calls = []
        self.now = 100.0

    def tearDown(self):
        self.temp.cleanup()

    def register(self, name, *, reads=(), deps=(), handler=None, enabled=True, implemented=True, **kwargs):
        def default(context):
            self.calls.append(name)
            return AgentResult(status="COMPLETED", outputs={"test." + name: len(context["inputs"]) + 1})
        c = AgentContract(agent_type=name, version="1.0.0", engine=0, purpose="Synthetic nonlegal test",
                          reads=reads, dependencies=deps, writes=("test." + name,), can_run_concurrently=True,
                          **kwargs)
        self.registry.register(c, (handler or default) if implemented else None, {"test." + name: integer} if implemented else None, enabled=enabled)

    def orchestrator(self, **kwargs):
        return MasterLegalOrchestrator(self.db, self.registry, clock=lambda: self.now, **kwargs)

    def graph(self, parallel=False):
        self.store.append_change("c", {"test.seed": 1, "test.b_input": 1}, actor="u", reason="synthetic input")
        self.register("A", reads=("test.seed",))
        barrier = threading.Barrier(2)
        def branch(name):
            def run(context):
                if parallel:
                    barrier.wait(timeout=3)
                self.calls.append(name)
                return AgentResult(status="COMPLETED", outputs={"test." + name: 7})
            return run
        self.register("B", deps=("A",), reads=("test.A", "test.b_input"), handler=branch("B"))
        self.register("C", deps=("A",), reads=("test.A",), handler=branch("C"))
        self.register("D", deps=("B", "C"), reads=("test.B", "test.C"))
        o = self.orchestrator()
        o.start("c", ["D"])
        return o

    def test_acceptance_dag_parallel_dependency_wait_and_targeted_staleness(self):
        o = self.graph(parallel=True)
        board = o.refresh("c")
        self.assertEqual(board["nodes"]["A"]["status"], "READY")
        self.assertEqual(board["nodes"]["D"]["status"], "WAITING")
        board = o.tick("c")
        self.assertEqual(board["nodes"]["A"]["status"], "COMPLETED")
        self.assertEqual(board["nodes"]["B"]["status"], "READY")
        board = o.tick("c")
        self.assertEqual(board["nodes"]["B"]["status"], "COMPLETED")
        self.assertEqual(board["nodes"]["C"]["status"], "COMPLETED")
        self.assertEqual(board["nodes"]["D"]["status"], "READY")
        board = o.tick("c")
        self.assertEqual(board["run"]["status"], "COMPLETED")
        board = self.store.append_change("c", {"test.b_input": 2}, actor="u", reason="B-only input")
        self.assertEqual([board["nodes"][n]["status"] for n in "ABCD"], ["COMPLETED", "STALE", "COMPLETED", "STALE"])

    def test_resume_after_b_with_new_adapter_instance_and_no_duplicates(self):
        o = self.graph()
        o.tick("c")
        claim = o.claim("c", "B")
        result = self.registry.get("B").handler(claim)
        o.write_agent_output(claim, result)
        checkpoint = self.store.read_board("c")
        other = MasterLegalOrchestrator(MockDatabaseAdapter(self.path), self.registry, clock=lambda: self.now)
        other.start("c", ["D"])
        other.tick("c")
        board = other.tick("c")
        for _ in range(3):
            other.tick("c")
        self.assertEqual(self.calls.count("A"), 1)
        self.assertEqual(self.calls.count("B"), 1)
        self.assertEqual(self.store.read_board("c")["version"], board["version"])
        self.assertEqual(board["nodes"]["B"]["execution_id"], checkpoint["nodes"]["B"]["execution_id"])

    def test_duplicate_workers_claim_once_and_late_result_no_history(self):
        self.register("A")
        o = self.orchestrator()
        o.start("c", ["A"])
        o.refresh("c")
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda _: o.claim("c", "A"), range(4)))
        self.assertEqual(sum(c is not None for c in claims), 1)
        claim = next(c for c in claims if c)
        result = self.registry.get("A").handler(claim)
        completed = o.write_agent_output(claim, result)
        self.assertEqual(o.write_agent_output(claim, result), completed)

    def test_worker_crash_lease_recovery_and_fencing(self):
        self.register("A", timeout_seconds=2)
        o = self.orchestrator()
        o.start("c", ["A"])
        o.refresh("c")
        old = o.claim("c", "A")
        self.now += 3
        o.refresh("c")
        new = o.claim("c", "A")
        self.assertEqual(old["execution_id"], new["execution_id"])
        self.assertNotEqual(old["claim_token"], new["claim_token"])
        result = AgentResult(status="COMPLETED", outputs={"test.A": 4})
        self.assertEqual(o.write_agent_output(old, result)["nodes"]["A"]["status"], "RUNNING")
        self.assertEqual(o.write_agent_output(new, result)["nodes"]["A"]["status"], "COMPLETED")

    def test_transient_retry_bounded_and_terminal_error_not_retried(self):
        def broken(c):
            raise TransientAgentError("provider unavailable")
        self.register("A", handler=broken, max_retries=1, retry_delay_seconds=0)
        o = self.orchestrator()
        o.start("c", ["A"])
        o.tick("c")
        board = o.tick("c")
        self.assertEqual(board["nodes"]["A"]["status"], "FAILED")
        self.assertEqual(board["nodes"]["A"]["retry_count"], 1)
        self.assertEqual(o.tick("c"), board)
        self.register("B", handler=lambda c: (_ for _ in ()).throw(ValueError("terminal")))
        o.start("c", ["B"])
        board = o.tick("c")
        self.assertEqual(board["nodes"]["B"]["attempts"], 1)
        self.assertEqual(o.tick("c"), board)

    def test_invalid_output_cannot_complete(self):
        self.register("A", handler=lambda c: AgentResult(status="COMPLETED", outputs={"test.A": "wrong"}))
        self.register("B", handler=lambda c: AgentResult(status="COMPLETED", outputs={}))
        o = self.orchestrator()
        o.start("c", ["A", "B"])
        board = o.tick("c")
        self.assertEqual([board["nodes"][n]["status"] for n in "AB"], ["FAILED", "FAILED"])
        self.assertNotIn("test", board["data"])

    def test_condition_skip_reactivation_disabled_and_unimplemented(self):
        self.register("A", conditions=(Condition(path="test.required", operator="equals", value=True),))
        self.register("B", enabled=False)
        self.register("C", implemented=False)
        o = self.orchestrator()
        o.start("c", ["A", "B", "C"])
        board = o.refresh("c")
        self.assertEqual([board["nodes"][n]["status"] for n in "ABC"], ["SKIPPED", "BLOCKED", "NOT_IMPLEMENTED"])
        self.store.append_change("c", {"test.required": True}, actor="u", reason="activate conditional work")
        self.assertEqual(o.tick("c")["nodes"]["A"]["status"], "COMPLETED")

    def test_human_pauses_continue_unrelated_then_resume_changed_input(self):
        for status in ("NEEDS_USER_INPUT", "NEEDS_DOCUMENT", "REVIEW_REQUIRED"):
            name = status.replace("_", "")
            def handler(context, status=status, name=name):
                if context["inputs"].get("answers." + name) is None:
                    return AgentResult(status=status, requests=[{"path": "answers." + name, "question": "Supply the missing input"}])
                return AgentResult(status="COMPLETED", outputs={"test." + name: 2})
            self.register(name, reads=("answers." + name,), handler=handler)
        self.register("INDEPENDENT")
        o = self.orchestrator()
        names = list(self.registry._agents)
        o.start("c", names)
        board = o.tick("c")
        self.assertEqual(board["nodes"]["INDEPENDENT"]["status"], "COMPLETED")
        for status in ("NEEDS_USER_INPUT", "NEEDS_DOCUMENT", "REVIEW_REQUIRED"):
            name = status.replace("_", "")
            self.assertEqual(board["nodes"][name]["status"], status)
            self.store.append_change("c", {"answers." + name: "answered"}, actor="u", reason="clarification")
        board = o.tick("c")
        self.assertTrue(all(n["status"] == "COMPLETED" for n in board["nodes"].values()))
        self.assertEqual(self.calls.count("INDEPENDENT"), 1)

    def test_review_checkpoint_requires_explicit_approval(self):
        self.register("A", requires_human_review=True)
        o = self.orchestrator()
        o.start("c", ["A"])
        board = o.tick("c")
        self.assertEqual(board["nodes"]["A"]["status"], "REVIEW_REQUIRED")
        self.assertNotIn("test", board["data"])
        self.assertEqual(o.resume_review("c", "A", actor="advocate")["nodes"]["A"]["status"], "COMPLETED")

    def test_protected_override_rerun_conflicts_and_reviewed_keep(self):
        self.store.append_change("c", {"test.seed": 1}, actor="u", reason="input")
        self.register("A", reads=("test.seed",))
        o = self.orchestrator()
        o.start("c", ["A"])
        o.tick("c")
        self.store.apply_human_override("c", "test.A", 99, actor="advocate", reason="human correction")
        self.store.append_change("c", {"test.seed": 2}, actor="u", reason="upstream rerun")
        board = o.tick("c")
        self.assertEqual(board["data"]["test"]["A"], 99)
        self.assertEqual(board["nodes"]["A"]["status"], "CONFLICT_FOUND")
        with self.assertRaises(ValueError):
            o.resume_review("c", "A", actor="advocate")
        cid = next(iter(board["conflicts"]))
        self.store.resolve_conflict("c", cid, "KEEP", actor="advocate", reason="retain correction")
        board = o.resume_review("c", "A", actor="advocate")
        self.assertEqual(board["data"]["test"]["A"], 99)
        self.assertEqual(board["nodes"]["A"]["status"], "COMPLETED")

    def test_input_change_during_worker_discards_result(self):
        self.store.append_change("c", {"test.seed": 1}, actor="u", reason="input")
        self.register("A", reads=("test.seed",))
        o = self.orchestrator()
        o.start("c", ["A"])
        o.refresh("c")
        claim = o.claim("c", "A")
        self.store.append_change("c", {"test.seed": 2}, actor="u", reason="changed during execution")
        board = o.write_agent_output(claim, AgentResult(status="COMPLETED", outputs={"test.A": 7}))
        self.assertEqual(board["nodes"]["A"]["status"], "STALE")
        self.assertNotIn("A", board["data"]["test"])

    def test_conflicting_write_ownership_serializes_workers(self):
        self.register("A")
        contract = AgentContract(agent_type="B", version="1.0.0", purpose="test", engine=0,
                                 writes=("test.A",), can_run_concurrently=True)
        self.registry.register(contract, lambda c: AgentResult(status="COMPLETED", outputs={"test.A": 5}), {"test.A": integer})
        o = self.orchestrator()
        o.start("c", ["A", "B"])
        o.refresh("c")
        self.assertIsNotNone(o.claim("c", "A"))
        self.assertIsNone(o.claim("c", "B"))

    def test_agent_reported_conflict_preserves_both_sources(self):
        def handler(c):
            return AgentResult(status="CONFLICT_FOUND", conflicts=[{"field": "test.A", "values": [12, 14], "sources": ["story", "uploaded-message"]}])
        self.register("A", handler=handler)
        o = self.orchestrator()
        o.start("c", ["A"])
        board = o.tick("c")
        self.assertEqual(board["nodes"]["A"]["status"], "CONFLICT_FOUND")
        conflict = next(iter(board["conflicts"].values()))
        self.assertEqual(conflict["values"], [12, 14])
        self.assertEqual(conflict["sources"], ["story", "uploaded-message"])
        self.assertNotIn("test", board["data"])

    def test_contract_dependency_without_explicit_reads_still_invalidates(self):
        self.register("A")
        self.register("B", deps=("A",))
        o = self.orchestrator()
        o.start("c", ["B"])
        o.tick("c")
        o.tick("c")
        board = self.store.append_change("c", {"test.A": 123}, actor="u", reason="upstream change")
        self.assertEqual(board["nodes"]["B"]["status"], "STALE")

    def test_multiple_same_output_reruns_have_new_dependency_versions(self):
        o = self.graph()
        for _ in range(3):
            o.tick("c")
        for i in range(2, 7):
            self.store.append_change("c", {"test.b_input": i}, actor="u", reason="changed input")
            o.tick("c")
            board = o.tick("c")
            self.assertEqual(board["nodes"]["D"]["status"], "COMPLETED")
            self.assertEqual(board["nodes"]["D"]["retry_count"], 0)
        self.assertEqual(self.calls.count("A"), 1)
        self.assertEqual(self.calls.count("C"), 1)

    def test_timeout_fences_late_handler_output(self):
        finished = threading.Event()
        def slow(c):
            time.sleep(0.08)
            finished.set()
            return AgentResult(status="COMPLETED", outputs={"test.A": 99})
        self.register("A", handler=slow, timeout_seconds=0.02, max_retries=0)
        o = MasterLegalOrchestrator(self.db, self.registry)
        o.start("c", ["A"])
        board = o.tick("c")
        self.assertEqual(board["nodes"]["A"]["status"], "FAILED")
        self.assertTrue(finished.wait(2))
        self.assertNotIn("test", self.store.read_board("c")["data"])

    def test_dependency_field_change_leaves_sibling_current(self):
        self.store.append_change("c", {"source.left": 1, "source.right": 1}, actor="u", reason="inputs")
        self.register("LEFT", reads=("source.left",))
        self.register("RIGHT", reads=("source.right",))
        o = self.orchestrator()
        o.start("c", ["LEFT", "RIGHT"])
        o.tick("c")
        board = self.store.append_change("c", {"source.left": 2}, actor="u", reason="one field changed")
        self.assertEqual(board["nodes"]["LEFT"]["status"], "STALE")
        self.assertEqual(board["nodes"]["RIGHT"]["status"], "COMPLETED")

    def test_capability_blocker_does_not_block_independent_understanding(self):
        self.register("LAW", required_capabilities=("verified_corpus",))
        self.register("UNDERSTAND")
        o = self.orchestrator()
        o.start("c", ["LAW", "UNDERSTAND"])
        board = o.tick("c")
        self.assertEqual(board["nodes"]["LAW"]["status"], "BLOCKED")
        self.assertEqual(board["nodes"]["UNDERSTAND"]["status"], "COMPLETED")

    def test_source_conflict_can_be_resolved_before_any_value_exists(self):
        def handler(c):
            if c["human_decisions"]:
                return AgentResult(status="COMPLETED", outputs={"test.A": c["human_decisions"][-1]["resolution"]["value"]})
            return AgentResult(status="CONFLICT_FOUND", conflicts=[{"field": "test.A", "values": [12, 14], "sources": ["story", "file"]}])
        self.register("A", handler=handler)
        o = self.orchestrator()
        o.start("c", ["A"])
        board = o.tick("c")
        cid = next(iter(board["conflicts"]))
        self.store.resolve_conflict("c", cid, "REPLACE", actor="advocate", reason="checked original source")
        board = o.tick("c")
        self.assertEqual(board["nodes"]["A"]["status"], "COMPLETED")
        self.assertEqual(board["data"]["test"]["A"], 14)

    def test_case_file_is_stale_without_regeneration_when_derived_work_changes(self):
        from backend.services.case_blackboard import versions
        o = self.graph()
        for _ in range(3):
            board = o.tick("c")
        paths = ("facts", "parties", "timeline", "legal_issues", "legal_sources", "evidence_mapping", "test.D")
        self.store.record_case_file("c", {"case_file_version": 1, "board_version": board["version"],
            "input_version": 1, "dependency_versions": versions(board, paths), "generated_at": "test"})
        board = self.store.append_change("c", {"test.b_input": 22}, actor="u", reason="updated B")
        self.assertEqual(board["case_file"]["status"], "STALE")
        self.assertEqual(board["case_file"]["case_file_version"], 1)

    def test_recorded_retry_failure_remains_observable_after_success(self):
        calls = []
        def handler(c):
            calls.append(c)
            if len(calls) == 1:
                raise TransientAgentError("retry")
            return AgentResult(status="COMPLETED", outputs={"test.A": 2})
        self.register("A", handler=handler, retry_delay_seconds=0)
        o = self.orchestrator()
        o.start("c", ["A"])
        o.tick("c")
        o.tick("c")
        diagnostics = o.diagnostics("c")
        self.assertEqual(diagnostics["last_failure"]["reason"], "TransientAgentError")
        self.assertEqual(diagnostics["last_success"]["agent"], "A")

    def test_real_case_input_change_fences_claim_without_prior_ui_read(self):
        self.register("A", reads=("input.input_version",))
        o = self.orchestrator()
        o.start("c", ["A"])
        o.refresh("c")
        claim = o.claim("c", "A")
        self.db.update("cases", "c", {"input_version": 2})
        board = o.write_agent_output(claim, AgentResult(status="COMPLETED", outputs={"test.A": 2}))
        self.assertEqual(board["nodes"]["A"]["status"], "STALE")

    def test_override_replace_and_merge_resume_with_validated_human_values(self):
        for name, decision, expected in (("REPLACE", "REPLACE", 1), ("MERGE", "MERGE", 8)):
            self.register(name)
            o = self.orchestrator()
            o.start("c", [name])
            self.store.apply_human_override("c", "test." + name, 99, actor="advocate", reason="correction")
            board = o.tick("c")
            cid = next(k for k, c in board["conflicts"].items() if c["field"] == "test." + name)
            self.store.resolve_conflict("c", cid, decision, actor="advocate", reason="review", merged_value=8)
            board = o.resume_review("c", name, actor="advocate")
            self.assertEqual(board["data"]["test"][name], expected)
            self.assertEqual(board["nodes"][name]["status"], "COMPLETED")

    def test_actual_new_process_resumes_only_unfinished_nodes(self):
        o = self.graph()
        o.tick("c")
        claim = o.claim("c", "B")
        before = o.write_agent_output(claim, self.registry.get("B").handler(claim))
        worker = multiprocessing.get_context("spawn").Process(target=resume_in_new_process, args=(self.path,))
        worker.start()
        worker.join(20)
        self.assertEqual(worker.exitcode, 0)
        after = self.store.read_board("c")
        for name in ("A", "B"):
            self.assertEqual(after["nodes"][name]["execution_id"], before["nodes"][name]["execution_id"])
            self.assertEqual(after["nodes"][name]["attempts"], 1)
        self.assertEqual(after["run"]["status"], "COMPLETED")

    def test_dynamic_pack_addition_preserves_completed_work(self):
        self.register("A")
        self.register("OPTIONAL", pack="SECONDARY", conditions=(Condition(path="test.missing_record", operator="equals", value=True),))
        o = self.orchestrator()
        o.start("c", ["A"])
        o.tick("c")
        self.store.append_change("c", {"test.missing_record": True}, actor="u", reason="secondary work required")
        o.start("c", self.registry.select_pack("SECONDARY"))
        after = o.tick("c")
        self.assertEqual(after["nodes"]["OPTIONAL"]["status"], "COMPLETED")
        self.assertEqual(self.calls.count("A"), 1)
