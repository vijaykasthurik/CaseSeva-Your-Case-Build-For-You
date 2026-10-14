from ..adapters.capabilities import processing_mode
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..models.case import utc_now
from ..services.analysis import STAGES, start_async
from .dependencies import get_case_or_error, get_current_user, retired_workflow

router = APIRouter(prefix="/api/cases")


class FactUpdate(BaseModel):
    text: str | None = None
    removed: bool | None = None


class FactCreate(BaseModel):
    text: str
    evidence_ids: list[str] = []
    confidence: float = 1.0


class TimelineUpdate(BaseModel):
    date: str | None = None
    date_uncertain: bool | None = None
    description: str | None = None


class PartiesUpdate(BaseModel):
    client_role: str
    opposite_party: str
    relationship: str


def owned(request, case_id, user):
    return get_case_or_error(request, case_id, user)


@router.post("/{case_id}/analyze", dependencies=[Depends(retired_workflow)])
def analyze(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = owned(request, case_id, user)
    if case["status"] != "READY_FOR_ANALYSIS":
        raise HTTPException(status_code=409, detail="Analysis can only start after case submission")
    start_async(request.app, case_id)
    return {"status": "started"}


@router.post("/{case_id}/analyze/retry", dependencies=[Depends(retired_workflow)])
def retry_analysis(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = owned(request, case_id, user)
    if case["status"] != "ANALYSIS_FAILED":
        raise HTTPException(status_code=409, detail="There are no failed analysis stages to retry")
    start_async(request.app, case_id, retry_failed=True)
    return {"status": "retry_started"}


@router.post("/{case_id}/preview1/rerun", dependencies=[Depends(retired_workflow)])
def rerun_preview_stages(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = owned(request, case_id, user)
    if case["status"] != "AWAITING_PREVIEW_1":
        raise HTTPException(status_code=409, detail="Preview 1 reruns are only available while reviewing")
    statuses = dict(case.get("stage_statuses", {}))
    statuses["FACT_EXTRACTION"] = "WAITING"
    statuses["TIMELINE_CONSTRUCTION"] = "WAITING"
    request.app.state.adapters.database.update("cases", case_id, {
        "status": "ANALYZING",
        "stage_statuses": statuses,
        "version": case.get("version", 1) + 1,
    })
    start_async(request.app, case_id, requested_stages=["FACT_EXTRACTION", "TIMELINE_CONSTRUCTION"])
    return {"status": "rerun_started"}


@router.get("/{case_id}/status")
def analysis_status(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = owned(request, case_id, user)
    from ..services.overview import public_processing_error, public_statuses
    return {"status": case["status"], "stage_statuses": public_statuses(case.get("stage_statuses", {})), "input_statuses": public_statuses(case.get("input_statuses", {})), "active_engine": case.get("active_engine"), "current_stage": case.get("current_stage"), "processing_mode": processing_mode(request.app.state.adapters), "document_generation_stage": case.get("document_generation_stage"), "error": public_processing_error(case.get("processing_error") or case.get("analysis_error") or case.get("legal_analysis_error"))}


@router.get("/{case_id}/preview1", dependencies=[Depends(retired_workflow)])
def preview1(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    raise HTTPException(410, "Preview approval screens are retired. Use the Client Case Overview.")


@router.patch("/{case_id}/facts/{fact_id}", dependencies=[Depends(retired_workflow)])
def edit_fact(case_id: str, fact_id: str, body: FactUpdate, request: Request, user: dict = Depends(get_current_user)):
    case = owned(request, case_id, user)
    if case["status"] != "AWAITING_PREVIEW_1":
        raise HTTPException(status_code=409, detail="Facts can only be edited during Preview 1")
    found = None
    facts = []
    for fact in case.get("facts", []):
        if fact["fact_id"] == fact_id:
            found = {**fact, "human_corrected": True}
            if body.text is not None:
                found["text"] = body.text
            if body.removed is not None:
                found["removed"] = body.removed
            facts.append(found)
        else:
            facts.append(fact)
    if found is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    updated = request.app.state.adapters.database.update("cases", case_id, {"facts": facts, "version": case.get("version", 1) + 1})
    return {"fact": found, "case": updated}


@router.post("/{case_id}/facts", dependencies=[Depends(retired_workflow)])
def add_fact(case_id: str, body: FactCreate, request: Request, user: dict = Depends(get_current_user)):
    case = owned(request, case_id, user)
    if case["status"] != "AWAITING_PREVIEW_1":
        raise HTTPException(status_code=409, detail="Facts can only be added during Preview 1")
    numbers = [int(f["fact_id"][1:]) for f in case.get("facts", []) if f.get("fact_id", "").startswith("F") and f["fact_id"][1:].isdigit()]
    fact = {"fact_id": f"F{(max(numbers) + 1 if numbers else 1):03d}", "text": body.text, "confidence": body.confidence, "evidence_ids": body.evidence_ids, "human_corrected": True, "removed": False}
    updated = request.app.state.adapters.database.update("cases", case_id, {"facts": case.get("facts", []) + [fact], "version": case.get("version", 1) + 1})
    return {"fact": fact, "case": updated}


@router.patch("/{case_id}/timeline/{event_id}", dependencies=[Depends(retired_workflow)])
def edit_timeline(case_id: str, event_id: str, body: TimelineUpdate, request: Request, user: dict = Depends(get_current_user)):
    case = owned(request, case_id, user)
    if case["status"] != "AWAITING_PREVIEW_1":
        raise HTTPException(status_code=409, detail="Timeline can only be edited during Preview 1")
    events = []
    found = None
    for event in case.get("timeline", []):
        if event["event_id"] == event_id:
            found = {**event, **body.model_dump(exclude_none=True), "human_corrected": True}
            events.append(found)
        else:
            events.append(event)
    if found is None:
        raise HTTPException(status_code=404, detail="Timeline event not found")
    updated = request.app.state.adapters.database.update("cases", case_id, {"timeline": events, "version": case.get("version", 1) + 1})
    return {"event": found, "case": updated}


@router.patch("/{case_id}/parties", dependencies=[Depends(retired_workflow)])
def edit_parties(case_id: str, body: PartiesUpdate, request: Request, user: dict = Depends(get_current_user)):
    case = owned(request, case_id, user)
    if case["status"] != "AWAITING_PREVIEW_1":
        raise HTTPException(status_code=409, detail="Parties can only be edited during Preview 1")
    parties = {**body.model_dump(), "human_corrected": True}
    updated = request.app.state.adapters.database.update("cases", case_id, {"parties": parties, "version": case.get("version", 1) + 1})
    return {"parties": parties, "case": updated}


@router.post("/{case_id}/preview1/approve", dependencies=[Depends(retired_workflow)])
def approve_preview(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = owned(request, case_id, user)
    if case["status"] != "AWAITING_PREVIEW_1":
        raise HTTPException(status_code=409, detail="Preview 1 is not ready for approval")
    updated = request.app.state.adapters.database.update("cases", case_id, {
        "status": "PREVIEW_1_APPROVED",
        "preview1_approved_by": user["id"],
        "preview1_approved_at": utc_now(),
        "version": case.get("version", 1) + 1,
    })
    return {"case": updated}
