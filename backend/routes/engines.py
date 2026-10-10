from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from .dependencies import get_current_user, get_case_or_error
from ..services.jobs import dispatch

router = APIRouter(prefix="/api/cases")


class Engine2Choice(BaseModel):
    run: bool


@router.post("/{case_id}/migrate-workflow")
def migrate(case_id: str, request: Request, user=Depends(get_current_user)):
    case = get_case_or_error(request, case_id, user)
    if case.get("workflow_version") == 2:
        raise HTTPException(409, "This case already uses the new workflow.")
    if case["status"] in {"ANALYZING", "LEGAL_ANALYSIS_RUNNING", "GENERATING_DOCUMENTS"}:
        raise HTTPException(409, "Wait for the current job to finish before upgrading.")
    from uuid import uuid4
    from ..models.case import utc_now
    db = request.app.state.adapters.database
    db.create("case_migration_snapshots", {"id": uuid4().hex, "case_id": case_id, "snapshot": case, "created_at": utc_now(), "actor_id": user["id"]})
    db.update("cases", case_id, {"workflow_version": 2, "status": "DRAFT" if case["status"] == "DRAFT" else "SUBMITTED", "documents_outdated": bool(case.get("document_version")), "engine2_stale": False})
    if case["status"] != "DRAFT":
        try:
            dispatch(request.app, 1, case_id)
        except Exception:
            db.update("cases", case_id, {"status": "REVIEW_REQUIRED", "processing_error": {"engine": 1, "stage": "DISPATCH", "message": "Upgrade was saved, but processing could not start."}})
            raise HTTPException(503, "Upgrade was saved, but processing could not start.")
    return {"status": "migrated"}


@router.post("/{case_id}/reprocess-input")
def reprocess(case_id: str, request: Request, user=Depends(get_current_user)):
    case = get_case_or_error(request, case_id, user)
    if case["status"] not in {"NEEDS_DOCUMENT", "REVIEW_REQUIRED", "LEGAL_CORPUS_NOT_READY"}:
        raise HTTPException(409, "Input reprocessing is unavailable in this state.")
    request.app.state.adapters.database.update("cases", case_id, {"status": "ENGINE1_RUNNING", "engine2_stale": bool(case.get("engine2"))})
    try:
        dispatch(request.app, 1, case_id)
    except Exception:
        request.app.state.adapters.database.update("cases", case_id, {"status": "REVIEW_REQUIRED", "processing_error": {"engine": 1, "stage": "DISPATCH", "message": "Could not start input reprocessing."}})
        raise HTTPException(503, "Input reprocessing could not be started.")
    return {"status": "ENGINE1_RUNNING"}


@router.get("/{case_id}/client-case-overview")
def overview(case_id: str, request: Request, user=Depends(get_current_user)):
    from ..services.overview import client_overview
    return {"overview": client_overview(get_case_or_error(request, case_id, user))}


@router.post("/{case_id}/engine2")
def choose_engine2(case_id: str, body: Engine2Choice, request: Request, user=Depends(get_current_user)):
    case = get_case_or_error(request, case_id, user)
    if not case.get("case_file") or case["status"] not in {"ENGINE1_DONE", "LEGAL_CORPUS_NOT_READY", "REVIEW_REQUIRED", "ENGINE2_DONE"} or case.get("processing_error"):
        raise HTTPException(409, "Complete Engine 1 or resolve its processing error first.")
    if body.run:
        updated = request.app.state.adapters.database.update("cases", case_id, {"status": "ENGINE2_RUNNING", "engine2_choice": "RUN"})
        try:
            dispatch(request.app, 2, case_id)
        except Exception:
            request.app.state.adapters.database.update("cases", case_id, {"status": "REVIEW_REQUIRED", "processing_error": {"engine": 2, "stage": "DISPATCH", "message": "Could not start Engine 2."}})
            raise HTTPException(503, "Engine 2 could not be started.")
    else:
        if case.get("engine2"):
            raise HTTPException(409, "Argument analysis already exists; it cannot be relabelled as not run.")
        updated = request.app.state.adapters.database.update("cases", case_id, {"engine2_choice": "DECLINED"})
    return {"status": updated["status"], "engine2_choice": updated.get("engine2_choice")}
