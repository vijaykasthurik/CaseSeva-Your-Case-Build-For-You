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
    if case["status"] not in {"NEEDS_DOCUMENT", "REVIEW_REQUIRED", "LEGAL_CORPUS_NOT_READY", "CASE_UNDERSTANDING_READY", "LEGAL_FOUNDATION_REVIEW_REQUIRED"}:
        raise HTTPException(409, "Input reprocessing is unavailable in this state.")
    request.app.state.adapters.database.update("cases", case_id, {"status": "ENGINE1_RUNNING", "engine2_stale": bool(case.get("engine2")), "core_retry_requested": True, "legal_retry_requested": True, "legal_case_file_current": False})
    try:
        dispatch(request.app, 1, case_id)
    except Exception:
        request.app.state.adapters.database.update("cases", case_id, {"status": "REVIEW_REQUIRED", "processing_error": {"engine": 1, "stage": "DISPATCH", "message": "Could not start input reprocessing."}})
        raise HTTPException(503, "Input reprocessing could not be started.")
    return {"status": "ENGINE1_RUNNING"}


@router.post("/{case_id}/core-understanding")
def start_core(case_id: str, request: Request, user=Depends(get_current_user)):
    case = get_case_or_error(request, case_id, user)
    from ..services.core_workflow import CORE_VERSION
    from .cases import validate_complete
    def reserve(current):
        if current.get("workflow_version") != 2 or current.get("case_file") or current.get('legal_foundation_requested') or current["status"] not in {"DRAFT", "SUBMITTED", "REVIEW_REQUIRED", "NEEDS_DOCUMENT", "CASE_UNDERSTANDING_READY"} or current.get("pending_uploads"):
            raise HTTPException(409, "This case cannot switch processing paths in its current state.")
        if validate_complete(current):
            raise HTTPException(422, "Please provide the case stage and a story or narration before starting.")
        return {"engine1_execution": CORE_VERSION, "status": "ENGINE1_RUNNING", "analysis_requested_by": user["id"], "core_retry_requested": True}
    request.app.state.adapters.database.mutate("cases", case_id, reserve)
    try:
        dispatch(request.app, 1, case_id)
    except Exception:
        request.app.state.adapters.database.update("cases", case_id, {"status": "REVIEW_REQUIRED", "processing_error": {"engine": 1, "message": "Saved case needs processing retry."}})
        raise HTTPException(503, "Your case is saved. Please retry processing later.")
    return {"status": "ENGINE1_RUNNING"}


@router.post('/{case_id}/legal-foundation')
def start_legal_foundation(case_id: str, request: Request, user=Depends(get_current_user)):
    get_case_or_error(request, case_id, user)
    from ..services.core_workflow import enabled
    db = request.app.state.adapters.database
    def reserve(current):
        if not enabled(current) or current.get('pending_uploads') or current['status'] not in {
                'CASE_UNDERSTANDING_READY', 'REVIEW_REQUIRED', 'LEGAL_CORPUS_NOT_READY', 'LEGAL_FOUNDATION_REVIEW_REQUIRED', 'ENGINE1_CASE_FILE_READY'}:
            raise HTTPException(409, 'Complete case understanding before starting legal verification.')
        if current.get('case_file') and current['case_file'].get('kind') != 'SOURCE_VERIFIED_ENGINE1':
            raise HTTPException(409, 'This case uses a different processing workflow.')
        return {'status': 'LEGAL_FOUNDATION_IN_PROGRESS', 'legal_foundation_status': 'IN_PROGRESS',
                'legal_foundation_requested': True, 'legal_retry_requested': True, 'core_retry_requested': True,
                'legal_case_file_current': False, 'analysis_requested_by': user['id']}
    db.mutate('cases', case_id, reserve)
    try:
        dispatch(request.app, 1, case_id)
    except Exception:
        db.update('cases', case_id, {'status': 'LEGAL_FOUNDATION_REVIEW_REQUIRED', 'legal_foundation_status': 'REVIEW_REQUIRED',
            'processing_error': {'engine': 1, 'message': 'Legal verification needs a processing retry.'}})
        raise HTTPException(503, 'Your case is saved. Please retry processing later.')
    return {'status': 'LEGAL_FOUNDATION_IN_PROGRESS'}


@router.get("/{case_id}/client-case-overview")
def overview(case_id: str, request: Request, user=Depends(get_current_user)):
    from ..services.overview import client_overview
    return {"overview": client_overview(get_case_or_error(request, case_id, user), request.app.state.adapters.database)}


@router.post("/{case_id}/engine2")
def choose_engine2(case_id: str, body: Engine2Choice, request: Request, user=Depends(get_current_user)):
    case = get_case_or_error(request, case_id, user)
    if case.get('legal_foundation_requested'):
        raise HTTPException(409, 'Deeper analysis is not yet available for this legal-foundation workflow.')
    if not case.get("case_file") or case["status"] not in {"ENGINE1_DONE", "LEGAL_CORPUS_NOT_READY", "REVIEW_REQUIRED", "ENGINE2_DONE"} or case.get("processing_error"):
        raise HTTPException(409, "Complete the case explanation or resolve the processing problem first.")
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
        from ..services.blackboard import engine_state
        engine_state(request.app.state.adapters.database, case_id, 2, "SKIPPED")
    return {"status": updated["status"], "engine2_choice": updated.get("engine2_choice")}
