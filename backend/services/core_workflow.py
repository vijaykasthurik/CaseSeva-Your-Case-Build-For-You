from ..adapters.capabilities import llm_is_live
"""Opt-in Phase 3 worker lifecycle, preserving the legacy Engine 1 boundary."""
import logging
import time
from uuid import uuid4
from .case_blackboard import CaseBlackboard, digest, versions, VersionConflict
from .agent_registry import production_registry
from .orchestrator import MasterLegalOrchestrator
from .understanding_sources import synchronized_raw, InputNotReady
from .input_layer import build_raw_package
from ..models.case import utc_now

CORE_VERSION = "ORCHESTRATED_CORE_V1"


def enabled(case):
    return case.get("workflow_version") == 2 and case.get("engine1_execution") == CORE_VERSION


def run_selected_engine1(app, case_id, **legacy_options):
    if (app.state.adapters.database.get('cases', case_id) or {}).get('legal_foundation_requested'):
        from .legal_workflow import run_legal_foundation
        return run_legal_foundation(app, case_id)
    if enabled(app.state.adapters.database.get("cases", case_id) or {}):
        return run_core(app, case_id)
    from .engine1 import run_engine1
    return run_engine1(app, case_id, **legacy_options)


def prepare(app, case_id):
    db, adapters = app.state.adapters.database, app.state.adapters
    case = db.get("cases", case_id)
    if not enabled(case):
        raise ValueError("Case has not opted into orchestrated understanding")
    raw = case.get("raw_package") or {}
    if raw.get("input_version") != case.get("input_version", 1) or set(raw.get("evidence_ids", [])) != {e["evidence_id"] for e in case.get("evidence", [])}:
        raw = build_raw_package(case, adapters, working_language_required=False, retry_pending_media=False)
        def save(current):
            if current.get("input_version", 1) != case.get("input_version", 1):
                raise VersionConflict("Inputs changed while preparing the core")
            return {"raw_package": raw, "evidence": raw["evidence"]}
        db.mutate("cases", case_id, save)
    return synchronized_raw(db, case_id)


def publish_status(db, case_id, board):
    states = {name: node["status"] for name, node in board["nodes"].items() if not node.get('inactive')}
    case = db.get("cases", case_id)
    changes = {"legal_foundation_status": "PENDING", "current_stage": None, "stage_statuses": {},
               "active_engine": None, "processing_error": None}
    waiting = board["nodes"].get("CLARIFICATION", {})
    if waiting.get("status") in {"NEEDS_USER_INPUT", "NEEDS_DOCUMENT"}:
        rounds = case.get("clarification_rounds", [])
        batch_id = waiting["execution_id"]
        if not any(b.get("batch_id") == batch_id for b in rounds):
            rounds = rounds + [{"round": len(rounds) + 1, "batch_id": batch_id, "core": True,
                "questions": waiting["requests"], "answers": [], "status": "WAITING", "created_at": utc_now(),
                "answering_user_id": case.get("analysis_requested_by") or case.get("created_by_advocate_id") or case["owner_user_id"]}]
        changes.update(status="AWAITING_CLIENT_INFO", case_understanding_status="NEEDS_INPUT", clarification_rounds=rounds)
    elif states and all(s == "COMPLETED" for s in states.values()):
        stage = board["data"]["case_understanding"]["stage"]
        domain = board["data"]["domain_classification"]
        review = stage.get("review_required") or domain.get("review_required")
        changes.update(status="REVIEW_REQUIRED" if review else "CASE_UNDERSTANDING_READY", case_understanding_status="REVIEW_REQUIRED" if review else "READY")
        from .case_file import assemble_canonical_case_file
        changes["canonical_case_file"] = assemble_canonical_case_file(db, case_id, board, pipeline_status=changes["status"])
        changes["understanding_snapshot"] = {"board_version": board["version"], "raw_package_version": board["data"]["input"]["raw_case_package_version"],
            "dependency_versions": versions(board, ("facts", "incidents", "timeline", "parties", "relationships", "evidence_mapping", "clarification", "reconciliation", "case_issues", "domain_classification")),
            "kind": "CASE_UNDERSTANDING_ONLY", "legal_foundation": "PENDING", "created_at": utc_now()}
        if case.get("understanding_snapshot", {}).get("board_version") == board["version"]:
            changes["understanding_snapshot"] = case["understanding_snapshot"]
    elif any(s in {"CONFLICT_FOUND", "REVIEW_REQUIRED", "FAILED", "BLOCKED"} for s in states.values()):
        changes.update(status="REVIEW_REQUIRED", case_understanding_status="REVIEW_REQUIRED")
        if any(s == "FAILED" for s in states.values()):
            changes["processing_error"] = {"engine": 1, "message": "Core processing needs review or retry."}
        if board.get("data", {}).get("facts"):
            try:
                from .case_file import assemble_canonical_case_file
                changes["canonical_case_file"] = assemble_canonical_case_file(db, case_id, board, pipeline_status=changes["status"])
            except Exception:
                pass
    else:
        # The bounded worker has stopped. Offer a retry instead of a permanent spinner.
        changes.update(status="REVIEW_REQUIRED", case_understanding_status="REVIEW_REQUIRED",
                       processing_error={"engine": 1, "message": "Saved case understanding needs a processing retry."})
    db.update("cases", case_id, changes)
    return changes


def run_core(app, case_id, *, max_ticks=24):
    """One bounded worker; no recursive Lambda calls or new infrastructure."""
    db = app.state.adapters.database
    token = uuid4().hex
    now = time.time()
    try:
        db.create("core_workers", {"id": case_id, "token": None, "lease_until": 0})
    except ValueError:
        pass
    def reserve(current):
        if current.get("token") and current["lease_until"] > now:
            return {}
        return {"token": token, "lease_until": now + 900}
    reservation = db.mutate("core_workers", case_id, reserve)
    if reservation.get("token") != token:
        return
    try:
        prepare(app, case_id)
        db.update("cases", case_id, {"status": "ENGINE1_RUNNING", "case_understanding_status": "BUILDING", "legal_foundation_status": "PENDING", "processing_error": None, "stage_statuses": {}, "current_stage": None})
        live_or_test = llm_is_live(app.state.adapters) or getattr(app.state.adapters, "phase3_test_double", False)
        controller = MasterLegalOrchestrator(db, production_registry(app.state.adapters), capabilities=("core_reasoning",) if live_or_test else ())
        controller.start(case_id, ["DOMAIN_ROUTER"], replace_plan=True)
        if db.get("cases", case_id).get("core_retry_requested"):
            def retry_failed(board):
                from .case_blackboard import invalidate
                for name, node in board["nodes"].items():
                    if node["status"] == "FAILED" or node.get("agent_blocked"):
                        invalidate(board, node["contract"]["writes"], exclude=(name,))
                        node.update(status="STALE", stale=True, agent_blocked=False, claim_token=None,
                                    review_generation=node.get("review_generation", 0) + 1)
            controller.store.change(case_id, retry_failed, kind="CORE_RETRY_REQUESTED")
            db.update("cases", case_id, {"core_retry_requested": False})
        for _ in range(max_ticks):
            board = controller.tick(case_id)
            if (board.get("run") or {}).get("status") == "COMPLETED":
                break
            retry = [n for n in board["nodes"].values() if n["status"] == "FAILED" and n.get("transient") and n["attempts"] <= n["contract"]["max_retries"]]
            if not any(n["status"] in {"READY", "RUNNING"} for n in board["nodes"].values()) and not retry:
                break
            if retry:
                time.sleep(min(2, max(0, min(n.get("next_retry_at", 0) for n in retry) - time.time())))
            if time.time() - now > 650:
                break
        return publish_status(db, case_id, board)
    except Exception:
        logging.getLogger(__name__).exception("Orchestrated case understanding needs retry: %s", case_id)
        db.update("cases", case_id, {"status": "REVIEW_REQUIRED", "case_understanding_status": "REVIEW_REQUIRED", "legal_foundation_status": "PENDING",
                  "current_stage": None, "stage_statuses": {}, "processing_error": {"engine": 1, "message": "Case understanding could not finish. Saved information is preserved."}})
    finally:
        db.mutate("core_workers", case_id, lambda current: {"token": None, "lease_until": 0} if current.get("token") == token else {})


def save_core_answers(db, case, batch, answers, actor):
    store = CaseBlackboard(db)
    questions = {q["question_id"]: q for q in batch["questions"]}
    def transform(board):
        from .case_blackboard import set_values
        additions = {}
        for answer in answers:
            q = questions[answer["question_id"]]
            record = {**answer, "topic": q["topic"], "batch_id": batch["batch_id"], "actor": actor,
                      "source_id": "ANSWER_" + answer["question_id"], "created_at": utc_now(), "fact_ids": q["fact_ids"],
                      "need": q.get("need", "OPTIONAL_DETAIL")}
            # An explicit unknown is recorded for clarification, not treated as
            # a changed factual claim that regenerates already-grounded records.
            affected_names = q["affected"] if answer['response'] == 'ANSWER' else []
            for name in set(affected_names + ["CLARIFICATION"]):
                path = "human." + name
                old = additions.get(path, board["data"].get("human", {}).get(name, []))
                if not any(a["source_id"] == record["source_id"] and a["batch_id"] == record["batch_id"] for a in old):
                    additions[path] = old + [record]
        paths, affected = set_values(board, additions)
        return {"changed_paths": paths, "affected_outputs": affected, "after": answers}
    store.change(case["case_id"], transform, actor=actor, kind="CORE_CLARIFICATION_ANSWERED", reason="Citizen/authorized advocate supplied sourced clarification")
