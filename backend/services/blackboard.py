"""Shared case state for every entry route."""
from ..models.case import utc_now


def sync_control_board(db, case_id):
    """Side-by-side Phase 2 bridge; a failure must not break accepted engines.

    No legal work is dispatched. Diagnostics can retry synchronization on demand.
    """
    from .case_blackboard import CaseBlackboard
    try:
        return CaseBlackboard(db).sync_input(case_id)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Phase 2 Blackboard synchronization pending for case %s", case_id)
        return None


def initial_board(case_id, origin, actor_id, language):
    return {"origin": origin, "public_case_id": "CS-" + utc_now()[:4] + "-" + case_id[:10].upper(), "preferred_language": language,
            "input_version": 1, "board_version": 1, "journey_stage": "DRAFT",
            "engines": {str(n): {"status": "NOT_RUN"} for n in (1, 2, 3)},
            "board_history": [{"version": 1, "actor_id": actor_id, "timestamp": utc_now(), "action": "case_created"}]}


def write(db, case_id, changes, actor_id="system", action="update"):
    def update(current):
        version = current.get("board_version", 0) + 1
        event = {"version": version, "actor_id": actor_id, "timestamp": utc_now(), "action": action, "changed_fields": sorted(changes)}
        journey = {"journey_stage": changes["status"]} if "status" in changes else {}
        return {**journey, **changes, "board_version": version, "board_history": current.get("board_history", []) + [event], "last_activity_at": event["timestamp"]}
    return db.mutate("cases", case_id, update)


def engine_state(db, case_id, engine, status, **details):
    def update(case):
        engines = dict(case.get("engines", {}))
        engines[str(engine)] = {**engines.get(str(engine), {}), "status": status, "updated_at": utc_now(), **details}
        version = case.get("board_version", 0) + 1
        event = {"version": version, "actor_id": "system", "timestamp": utc_now(), "action": f"engine{engine}_{status.lower()}", "changed_fields": ["engines"]}
        return {"engines": engines, "board_version": version, "board_history": case.get("board_history", []) + [event]}
    return db.mutate("cases", case_id, update)
