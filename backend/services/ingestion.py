from .input_layer import build_raw_package
from .blackboard import write


def run_ingestion(app, case_id, understand=False):
    db, adapters = app.state.adapters.database, app.state.adapters
    case = db.get("cases", case_id)
    try:
        def progress(evidence_id, state):
            current = db.get("cases", case_id)
            write(db, case_id, {"input_statuses": {**current.get("input_statuses", {}), evidence_id: state}, "current_stage": "READING_INPUT"}, action="ingestion_progress")
        raw = build_raw_package(case, adapters, progress)
        changes = {"raw_package": raw, "evidence": raw["evidence"], "input_status": "PENDING" if raw["pending"] else "COMPLETE", "processing_error": None, "current_stage": None}
        if not understand:
            changes.update({"status": "READY_FOR_ADVOCATE", "journey_stage": "READY_FOR_ADVOCATE"})
        write(db, case_id, changes, action="input_prepared")
        if understand:
            from .engine1 import run_engine1
            run_engine1(app, case_id)
    except Exception:
        write(db, case_id, {"status": "REVIEW_REQUIRED", "input_status": "FAILED", "current_stage": None, "processing_error": {"engine": 0, "message": "Your information could not be prepared. Please retry or ask an advocate for help."}}, action="ingestion_failed")
