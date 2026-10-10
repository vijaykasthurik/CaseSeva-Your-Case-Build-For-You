from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ..models.case import utc_now
from ..services.legal_analysis import LEGAL_STAGES, start_legal_async
from .dependencies import get_case_or_error, get_current_user

router = APIRouter(prefix="/api/cases")


class Preview2Approval(BaseModel):
    proceed_without_documents: bool = False


class Preview2FactUpdate(BaseModel):
    text: str


def owned(request: Request, case_id: str, user: dict[str, Any]) -> dict[str, Any]:
    return get_case_or_error(request, case_id, user)


@router.post("/{case_id}/legal-analysis")
def start_legal_analysis(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = owned(request, case_id, user)
    if case["status"] != "PREVIEW_1_APPROVED":
        raise HTTPException(status_code=409, detail="Legal analysis can only start after Preview 1 approval")
    start_legal_async(request.app, case_id)
    return {"status": "started"}


@router.get("/{case_id}/preview2")
def get_preview2(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    raise HTTPException(410, "Preview approval screens are retired. Use the Client Case Overview.")


@router.post("/{case_id}/evidence-request/{request_id}/resolve")
async def resolve_document_request(
    case_id: str,
    request_id: str,
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    case = owned(request, case_id, user)
    pending = next((item for item in case.get("document_requests", []) if item["request_id"] == request_id and not item.get("resolved")), None)
    if pending is None:
        raise HTTPException(status_code=404, detail="Document request not found")
    content = await file.read()
    key = f"cases/{case_id}/requested-{request_id}-{file.filename or 'document'}"
    url = request.app.state.adapters.storage.upload(key, content, file.content_type or "application/octet-stream")
    evidence = list(case.get("evidence", []))
    evidence.append({
        "evidence_id": f"ER{len(evidence) + 1:03d}",
        "filename": file.filename or "document",
        "content_type": file.content_type or "application/octet-stream",
        "size": len(content),
        "storage_key": key,
        "url": url,
        "description": f"Response to {request_id}",
        "uploaded_at": utc_now(),
    })
    requests = [{**item, "resolved": True} if item["request_id"] == request_id else item for item in case["document_requests"]]
    updated = request.app.state.adapters.database.update("cases", case_id, {
        "evidence": evidence,
        "document_requests": requests,
        "status": "LEGAL_ANALYSIS_RUNNING",
        "version": case.get("version", 1) + 1,
    })
    affected = pending.get("affected_stages") or LEGAL_STAGES[6:]
    start_legal_async(request.app, case_id, requested_stages=affected)
    return {"status": "rerun_started", "case": updated}


@router.post("/{case_id}/preview2/approve")
def approve_preview2(case_id: str, body: Preview2Approval, request: Request, user: dict = Depends(get_current_user)):
    case = owned(request, case_id, user)
    if case["status"] not in {"AWAITING_PREVIEW_2", "NEEDS_DOCUMENT"}:
        raise HTTPException(status_code=409, detail="Preview 2 is not ready for approval")
    outstanding = [item for item in case.get("document_requests", []) if not item.get("resolved")]
    if outstanding and not body.proceed_without_documents:
        raise HTTPException(status_code=409, detail={"message": "Resolve or explicitly waive outstanding document requests.", "requests": outstanding})
    updated = request.app.state.adapters.database.update("cases", case_id, {
        "status": "PREVIEW_2_APPROVED",
        "preview2_approved_by": user["id"],
        "preview2_approved_at": utc_now(),
        "preview2_waived_document_requests": [item["request_id"] for item in outstanding] if outstanding else [],
        "version": case.get("version", 1) + 1,
    })
    return {"case": updated}


@router.patch("/{case_id}/preview2/facts/{fact_id}")
def correct_preview2_fact(case_id: str, fact_id: str, body: Preview2FactUpdate, request: Request, user: dict = Depends(get_current_user)):
    case = owned(request, case_id, user)
    if case["status"] not in {"AWAITING_PREVIEW_2", "NEEDS_DOCUMENT"}:
        raise HTTPException(status_code=409, detail="Facts can only be corrected during Preview 2")
    facts = []
    found = False
    for fact in case.get("facts", []):
        if fact["fact_id"] == fact_id:
            facts.append({**fact, "text": body.text, "human_corrected": True})
            found = True
        else:
            facts.append(fact)
    if not found:
        raise HTTPException(status_code=404, detail="Fact not found")
    updated = request.app.state.adapters.database.update("cases", case_id, {
        "facts": facts,
        "status": "LEGAL_ANALYSIS_RUNNING",
        "version": case.get("version", 1) + 1,
    })
    start_legal_async(request.app, case_id, requested_stages=LEGAL_STAGES)
    return {"status": "rerun_started", "case": updated}
