from .input_layer import build_raw_package
from .blackboard import write, engine_state


def run_ingestion(app, case_id, understand=False, preserve_status=False):
    db, adapters = app.state.adapters.database, app.state.adapters
    case = db.get("cases", case_id)
    try:
        def progress(evidence_id, state):
            current = db.get("cases", case_id)
            write(db, case_id, {"input_statuses": {**current.get("input_statuses", {}), evidence_id: state}, "current_stage": "READING_INPUT"}, action="ingestion_progress")
        raw = build_raw_package(case, adapters, progress)
        changes = {"raw_package": raw, "evidence": raw["evidence"], "input_status": "PENDING" if raw["pending"] else "COMPLETE", "processing_error": None, "current_stage": None}
        changed_content = bool(case.get("case_file")) and raw.get("canonical_hash") != case.get("raw_package", {}).get("canonical_hash")
        if changed_content:
            changes.update({"engine2_stale": bool(case.get("engine2")), "documents_outdated": bool(case.get("document_version"))})
        if not understand and not preserve_status:
            changes.update({"status": "READY_FOR_ADVOCATE", "journey_stage": "READY_FOR_ADVOCATE"})
        def commit(current):
            if current.get("input_version", 1) != case.get("input_version", 1):
                return {"input_status": "PENDING", "current_stage": None, "processing_error": {"engine": 0, "message": "Input changed while processing; retry the latest saved version."}}
            return changes
        updated = db.mutate("cases", case_id, commit)
        if updated.get("input_status") == "PENDING" and updated.get("processing_error"):
            return
        from .blackboard import sync_control_board
        sync_control_board(db, case_id)
        if changed_content:
            engine_state(db, case_id, 1, "STALE", reason="Input extraction changed after retry")
        if understand:
            from .core_workflow import run_selected_engine1
            run_selected_engine1(app, case_id)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("Input preparation failed")
        write(db, case_id, {"status": case["status"] if preserve_status else "REVIEW_REQUIRED", "input_status": "FAILED", "current_stage": None, "processing_error": {"engine": 0, "message": str(exc)}}, action="ingestion_failed")
