"""Durable dependency scheduler. No legal agents, prompts or engine routing here."""
import copy
import time
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from uuid import uuid4
from ..models.case import utc_now
from ..models.orchestration import AgentContract, AgentResult
from .case_blackboard import CaseBlackboard, digest, value_at, versions, set_values, overlaps


class TransientAgentError(RuntimeError):
    """Only explicitly classified provider failures are eligible for retry."""


# Bound actual provider calls even if a timed-out Python handler ignores its
# timeout. Its slot remains occupied until it exits; later ticks can retry.
_worker_slots = threading.BoundedSemaphore(8)


class MasterLegalOrchestrator:
    def __init__(self, db, registry, *, max_workers=4, capabilities=(), clock=time.time):
        if not 1 <= max_workers <= 8:
            raise ValueError("Concurrency must be 1..8")
        self.store, self.registry = CaseBlackboard(db), registry
        self.max_workers, self.capabilities, self.clock = max_workers, set(capabilities), clock

    def start(self, case_id, selected, *, action="understand", parent_run=None):
        """Trusted internal entry point. Does not dispatch a legacy engine."""
        graph = self.registry.graph(selected)
        self.store.sync_input(case_id)
        def initialize(board):
            if board["run"] and board["run"]["action"] != action:
                raise ValueError("A Blackboard run cannot silently change its requested action")
            if not board["run"]:
                board["run"] = {"run_id": uuid4().hex, "parent_run": parent_run, "action": action,
                                "created_at": utc_now(), "graph": {}, "checkpoint_version": board["version"] + 1}
            for name, deps in graph.items():
                contract = self.registry.get(name).contract.model_dump(mode="json")
                prior = board["nodes"].get(name)
                if prior and prior["contract"] != contract:
                    raise ValueError("Agent contract changed; explicit version migration is required")
                if not prior:
                    board["nodes"][name] = {"agent_type": name, "agent_instance_id": name, "contract": contract,
                                            "status": "WAITING", "attempts": 0, "retry_count": 0,
                                            "claim_token": None, "stale": False,
                                            "watched_paths": list(self.registry.watched_paths(name))}
                board["run"]["graph"][name] = deps
        return self.store.change(case_id, initialize, kind="PLAN_CREATED")

    def _eligible_status(self, board, name):
        node = board["nodes"][name]
        registration = self.registry.get(name)
        c = registration.contract
        if c.model_dump(mode="json") != node["contract"]:
            return "BLOCKED", "AGENT_VERSION_CHANGED"
        if not registration.enabled:
            return "BLOCKED", "AGENT_DISABLED"
        if registration.handler is None:
            return "NOT_IMPLEMENTED", "AGENT_NOT_IMPLEMENTED"
        if not set(c.required_capabilities).issubset(self.capabilities):
            return "BLOCKED", "CAPABILITY_UNAVAILABLE"
        language = board["data"]["identity"].get("preferred_language")
        if c.supported_languages and language not in c.supported_languages:
            return "BLOCKED", "LANGUAGE_UNSUPPORTED"
        for dependency in c.dependencies:
            upstream = board["nodes"][dependency]["status"]
            if upstream not in {"COMPLETED", "SKIPPED"}:
                return ("BLOCKED" if upstream in {"FAILED", "BLOCKED", "NOT_IMPLEMENTED", "NEEDS_DOCUMENT", "NEEDS_USER_INPUT", "REVIEW_REQUIRED", "CONFLICT_FOUND"} else "WAITING"), "DEPENDENCY_" + upstream
        for condition in c.conditions:
            value = value_at(board["data"], condition.path)
            active = value is not None if condition.operator == "exists" else value == condition.value
            if not active:
                return "SKIPPED", "CONDITION_NOT_APPLICABLE"
        if any(value_at(board["data"], path) is None for path in c.required_inputs):
            return "BLOCKED", "REQUIRED_INPUT_MISSING"
        return "READY", None

    def refresh(self, case_id):
        now = self.clock()
        def transform(board):
            for name, node in board["nodes"].items():
                if node["status"] == "RUNNING":
                    if now >= node["lease_until"]:
                        node.update(status="FAILED", claim_token=None, failure_reason="WORKER_LEASE_EXPIRED",
                                    transient=True, finished_at=utc_now(), next_retry_at=now)
                    else:
                        continue
                if node["status"] in {"COMPLETED", "NEEDS_USER_INPUT", "NEEDS_DOCUMENT", "REVIEW_REQUIRED", "CONFLICT_FOUND"}:
                    continue
                if node["status"] == "FAILED":
                    c = self.registry.get(name).contract
                    if not node.get("transient") or c.retry_policy == "never" or node["attempts"] >= c.max_retries + 1 or now < node.get("next_retry_at", 0):
                        continue
                status, reason = self._eligible_status(board, name)
                node.update(status=status, blocking_reason=reason)
            if board["run"]:
                states = [n["status"] for n in board["nodes"].values()]
                board["run"]["status"] = ("NO_AGENTS_AVAILABLE" if not states else "COMPLETED" if all(s in {"COMPLETED", "SKIPPED"} for s in states) else "RUNNING" if "RUNNING" in states else "READY" if "READY" in states else "PAUSED")
        return self.store.change(case_id, transform, kind="ELIGIBILITY_CHECK")

    def claim(self, case_id, name):
        token, now = uuid4().hex, self.clock()
        def transform(board):
            node = board["nodes"][name]
            if node["status"] != "READY" or self._eligible_status(board, name)[0] != "READY":
                return
            running = [n for n, item in board["nodes"].items() if item["status"] == "RUNNING"]
            if len(running) >= self.max_workers or any(not self.registry.compatible(name, other) for other in running):
                return
            c = self.registry.get(name).contract
            inputs = versions(board, self.registry.watched_paths(name))
            key = digest([case_id, name, c.version, inputs, board["run"]["action"]])
            attempts = node.get("attempts", 0) if node.get("idempotency_key") == key else 0
            if attempts >= c.max_retries + 1:
                node.update(status="FAILED", failure_reason="RETRY_EXHAUSTED")
                return
            node.update(status="RUNNING", execution_id=key, idempotency_key=key,
                        run_id=board["run"]["run_id"], parent_run=board["run"]["parent_run"], engine=c.engine,
                        attempts=attempts + 1, retry_count=attempts, dependency_versions=inputs,
                        input_version=board["data"]["input"]["input_version"], input_board_version=board["version"],
                        claim_token=token, lease_until=now + c.timeout_seconds,
                        started_at=utc_now(), finished_at=None, stale=False, failure_reason=None,
                        blocking_reason=None, pending_result=None, requests=[])
        board = self.store.change(case_id, transform, kind="AGENT_CLAIMED")
        node = board["nodes"][name]
        if node.get("claim_token") != token:
            return None
        # Handlers receive only declared inputs, never a DB or mutable shared board.
        c = self.registry.get(name).contract
        return {"case_id": case_id, "agent_type": name, "claim_token": token,
                "execution_id": node["execution_id"], "idempotency_key": node["idempotency_key"],
                "dependency_versions": node["dependency_versions"], "board_version": board["version"],
                "inputs": {path: copy.deepcopy(value_at(board["data"], path)) for path in self.registry.watched_paths(name)}}

    def fail(self, claim, exc):
        name, case_id = claim["agent_type"], claim["case_id"]
        c = self.registry.get(name).contract
        def transform(board):
            node = board["nodes"][name]
            if node["status"] != "RUNNING" or node.get("claim_token") != claim["claim_token"]:
                return
            node.update(status="FAILED", claim_token=None, finished_at=utc_now(),
                        transient=isinstance(exc, TransientAgentError), failure_reason=type(exc).__name__,
                        next_retry_at=self.clock() + c.retry_delay_seconds * (2 ** (node["attempts"] - 1)))
        return self.store.change(case_id, transform, kind="AGENT_FAILED")

    def _validate(self, name, result):
        result = AgentResult.model_validate(result)
        r = self.registry.get(name)
        if result.status == "COMPLETED":
            if set(result.outputs) != set(r.contract.writes) or result.conflicts or result.requests:
                raise ValueError("Completion requires exactly the validated outputs and no open requests")
        elif result.outputs:
            raise ValueError("A paused agent cannot publish partial outputs as completed")
        if result.status in {"NEEDS_DOCUMENT", "NEEDS_USER_INPUT"} and not result.requests:
            raise ValueError("A human pause requires a concrete request")
        for path, value in result.outputs.items():
            validator = r.validators[path]
            validated = validator(value)
            if validated is False:
                raise ValueError("Agent output failed validation")
        for conflict in result.conflicts:
            if not {"field", "values", "sources"}.issubset(conflict) or len(conflict["values"]) < 2 or len(conflict["values"]) != len(conflict["sources"]):
                raise ValueError("Invalid conflict provenance")
        if result.status == "CONFLICT_FOUND" and not result.conflicts:
            raise ValueError("A conflict status requires competing sources")
        return result

    def write_agent_output(self, claim, result, *, reviewed=False, actor="system"):
        name, case_id = claim["agent_type"], claim["case_id"]
        result = self._validate(name, result)
        c = self.registry.get(name).contract
        def transform(board):
            node = board["nodes"][name]
            allowed = {"REVIEW_REQUIRED", "CONFLICT_FOUND"} if reviewed else {"RUNNING"}
            if node["status"] not in allowed or node.get("claim_token") != claim["claim_token"]:
                return
            if versions(board, self.registry.watched_paths(name)) != claim["dependency_versions"]:
                node.update(status="STALE", stale=True, claim_token=None)
                return
            if not reviewed and self.clock() >= node["lease_until"]:
                node.update(status="FAILED", claim_token=None, failure_reason="TIMEOUT", transient=True,
                            finished_at=utc_now(), next_retry_at=self.clock() + c.retry_delay_seconds)
                return
            outputs = copy.deepcopy(result.outputs)
            unresolved = False
            for path, protection in board["protected"].items():
                for target in outputs:
                    if not overlaps(path, target):
                        continue
                    if path == target:
                        proposed = outputs[target]
                    elif path.startswith(target + "."):
                        proposed = value_at(outputs[target], path[len(target) + 1:])
                    else:
                        proposed = copy.deepcopy(value_at(board["data"], path))
                        from .case_blackboard import put_path
                        put_path(proposed, target[len(path) + 1:], outputs[target])
                    current = value_at(board["data"], path)
                    if proposed == current:
                        continue
                    resolved = [conflict for conflict in board["conflicts"].values()
                                if conflict["field"] == path and conflict["execution_id"] == node["execution_id"] and conflict["resolution"]]
                    if reviewed and resolved:
                        from .case_blackboard import put_path
                        if path == target:
                            outputs[target] = copy.deepcopy(current)
                        elif path.startswith(target + "."):
                            put_path(outputs[target], path[len(target) + 1:], current)
                        else:
                            outputs[target] = copy.deepcopy(value_at(board["data"], target))
                    else:
                        self.store.add_conflict(board, path, [current, proposed],
                                                [protection["actor"], node["execution_id"]], agents=[name], execution_id=node["execution_id"])
                        unresolved = True
            for conflict in result.conflicts:
                self.store.add_conflict(board, conflict["field"], conflict["values"], conflict["sources"], agents=[name], facts=conflict.get("facts", []), execution_id=node["execution_id"])
            if unresolved or result.status == "CONFLICT_FOUND":
                node.update(status="CONFLICT_FOUND", pending_result=result.model_dump(mode="json"), finished_at=utc_now())
                return
            if result.status == "COMPLETED" and c.requires_human_review and not reviewed:
                node.update(status="REVIEW_REQUIRED", pending_result=result.model_dump(mode="json"), finished_at=utc_now())
                return
            if result.status != "COMPLETED":
                node.update(status=result.status, requests=result.requests, blocking_reason=result.reason, finished_at=utc_now())
                return
            # Explicit human decisions may change proposed values; validate again.
            self._validate(name, AgentResult(status="COMPLETED", outputs=outputs))
            paths, affected = set_values(board, outputs, exclude=(name,), force_version=True)
            node.update(status="COMPLETED", output_version=board["version"] + 1,
                        output_versions=versions(board, c.writes), finished_at=utc_now(),
                        claim_token=None, pending_result=None, requests=[], stale=False)
            board["run"]["checkpoint_version"] = board["version"] + 1
            return {"changed_paths": paths, "affected_outputs": affected, "execution_id": node["execution_id"]}
        return self.store.change(case_id, transform, actor=actor, kind="AGENT_RESULT")

    def resume_review(self, case_id, name, *, actor):
        board = self.store.read_board(case_id)
        node = board["nodes"][name]
        if node["status"] not in {"REVIEW_REQUIRED", "CONFLICT_FOUND"} or not node.get("pending_result"):
            raise ValueError("No reviewable output checkpoint")
        if any(c["execution_id"] == node["execution_id"] and not c["resolution"] for c in board["conflicts"].values()):
            raise ValueError("Resolve conflicts before approving the checkpoint")
        claim = {"case_id": case_id, "agent_type": name, "claim_token": node["claim_token"], "dependency_versions": node["dependency_versions"]}
        if node["pending_result"]["status"] != "COMPLETED":
            raise ValueError("This agent needs new input before rerunning")
        return self.write_agent_output(claim, node["pending_result"], reviewed=True, actor=actor)

    def tick(self, case_id):
        """Run one bounded eligible batch; a later tick resumes persisted state."""
        board = self.refresh(case_id)
        claims = []
        for name, node in board["nodes"].items():
            if node["status"] == "READY" and len(claims) < self.max_workers:
                if not _worker_slots.acquire(blocking=False):
                    break
                try:
                    claim = self.claim(case_id, name)
                except BaseException:
                    _worker_slots.release()
                    raise
                if claim:
                    claims.append(claim)
                else:
                    _worker_slots.release()
        if not claims:
            return self.refresh(case_id)
        pool = ThreadPoolExecutor(max_workers=self.max_workers)
        futures = {}
        for claim in claims:
            future = pool.submit(self.registry.get(claim["agent_type"]).handler, copy.deepcopy(claim))
            future.add_done_callback(lambda _: _worker_slots.release())
            futures[future] = claim
        try:
            while futures:
                remaining = min(self.store.read_board(case_id)["nodes"][c["agent_type"]]["lease_until"] - self.clock() for c in futures.values())
                done, _ = wait(futures, timeout=max(0, min(remaining, 0.1)))
                for future in done:
                    claim = futures.pop(future)
                    try:
                        self.write_agent_output(claim, future.result())
                    except Exception as exc:
                        self.fail(claim, exc)
                for future, claim in list(futures.items()):
                    node = self.store.read_board(case_id)["nodes"][claim["agent_type"]]
                    if self.clock() >= node["lease_until"]:
                        future.cancel()
                        self.fail(claim, TransientAgentError("Agent timeout"))
                        del futures[future]
        finally:
            # Python cannot terminate a running thread. It has no DB access and
            # cannot commit late results. Provider adapters must also set timeouts.
            pool.shutdown(wait=False, cancel_futures=True)
        return self.refresh(case_id)

    def diagnostics(self, case_id):
        board = self.store.read_board(case_id)
        nodes = board["nodes"]
        return {"board_version": board["version"], "input_version": board["data"]["input"]["input_version"],
                "registry": self.registry.describe(), "checkpoint": board["run"],
                "executions": copy.deepcopy(nodes), "conflicts": copy.deepcopy(board["conflicts"]),
                "active": [n for n, v in nodes.items() if v["status"] == "RUNNING"],
                "completed": [n for n, v in nodes.items() if v["status"] == "COMPLETED"],
                "failed": [n for n, v in nodes.items() if v["status"] == "FAILED"],
                "blocked": [n for n, v in nodes.items() if v["status"] == "BLOCKED"],
                "stale": [n for n, v in nodes.items() if v.get("stale")],
                "last_success": max((v["finished_at"] for v in nodes.values() if v["status"] == "COMPLETED"), default=None),
                "last_failure": max((v["finished_at"] for v in nodes.values() if v["status"] == "FAILED" and v.get("finished_at")), default=None)}
