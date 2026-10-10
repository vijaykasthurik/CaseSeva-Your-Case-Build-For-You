from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from .dependencies import get_current_user, get_case_or_error
from .advocates import accepted_case
from ..models.case import utc_now
from ..services.blackboard import write, engine_state
from ..services.notifications import notify

router = APIRouter(prefix="/api")


@router.get("/notifications")
def notifications(request: Request, user=Depends(get_current_user)):
    return {"notifications": sorted([item for item in request.app.state.adapters.database.list("notifications") if item["user_id"] == user["id"]], key=lambda item: item["created_at"], reverse=True)}


class Note(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    visibility: Literal["ADVOCATE_INTERNAL", "SHARED_WITH_CLIENT"] = "ADVOCATE_INTERNAL"


@router.post("/advocate/cases/{case_id}/notes")
def note(case_id: str, body: Note, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    item = {"id": uuid4().hex, "text": body.text, "visibility": body.visibility, "advocate_id": user["id"], "created_at": utc_now()}
    db = request.app.state.adapters.database
    write(db, case_id, {"professional_notes": case.get("professional_notes", []) + [item]}, user["id"], "note_added")
    if body.visibility == "SHARED_WITH_CLIENT": notify(db, case["owner_user_id"], "Your advocate shared a message with you.", case_id)
    return {"note": item}


class InfoRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    kind: Literal["INFORMATION", "DOCUMENT"] = "INFORMATION"


@router.post("/advocate/cases/{case_id}/information-requests")
def request_information(case_id: str, body: InfoRequest, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    item = {"id": uuid4().hex, **body.model_dump(), "requested_by": user["id"], "created_at": utc_now(), "response": None}
    db = request.app.state.adapters.database
    write(db, case_id, {"information_requests": case.get("information_requests", []) + [item]}, user["id"], "information_requested")
    notify(db, case["owner_user_id"], "Your advocate needs more information: " + body.question, case_id)
    return {"request": item}


class InfoAnswer(BaseModel):
    response: str = Field(min_length=1, max_length=10000)
    evidence_ids: list[str] = Field(default_factory=list)


@router.post("/cases/{case_id}/information-requests/{request_id}/answer")
def information_answer(case_id: str, request_id: str, body: InfoAnswer, request: Request, user=Depends(get_current_user)):
    case = get_case_or_error(request, case_id, user)
    items = case.get("information_requests", [])
    item = next((item for item in items if item["id"] == request_id), None)
    if not item: raise HTTPException(404, "Information request not found.")
    if not set(body.evidence_ids).issubset({item["evidence_id"] for item in case.get("evidence", [])}): raise HTTPException(422, "Unknown evidence reference.")
    item.update({**body.model_dump(), "answered_by": user["id"], "answered_at": utc_now()})
    item["response"] = body.response
    db = request.app.state.adapters.database
    write(db, case_id, {"information_requests": items, "input_version": case.get("input_version", 1) + 1, "engine2_stale": bool(case.get("engine2")), "documents_outdated": bool(case.get("document_version"))}, user["id"], "information_answered")
    engine_state(db, case_id, 1, "STALE", reason="New client information")
    if case.get("engine2"): engine_state(db, case_id, 2, "STALE", reason="New client information")
    notify(db, case.get("assigned_advocate_id"), "The client responded to your information request.", case_id)
    return {"message": "Your response is saved for your advocate. Earlier analysis may need updating."}


FILING_STATUSES = {"READY_TO_FILE", "PREPARING_FOR_FILING", "FILED", "FILING_ACKNOWLEDGED", "DEFECT_CORRECTION_REQUIRED", "CORRECTED_REFILED", "REGISTERED", "PENDING", "HEARING_SCHEDULED", "ORDER_RECEIVED", "CLOSED"}


class FilingUpdate(BaseModel):
    status: str
    explanation: str = Field(min_length=1, max_length=3000)
    filing_date: str = ""
    forum: str = ""
    filing_number: str = ""
    diary_number: str = ""
    application_number: str = ""
    case_number: str = ""
    next_action: str = ""
    next_date: str = ""
    client_message: str = ""
    receipt_evidence_id: str | None = None


@router.post("/advocate/cases/{case_id}/filing")
def filing(case_id: str, body: FilingUpdate, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    if body.status not in FILING_STATUSES: raise HTTPException(422, "Choose a supported filing update.")
    if body.status == "READY_TO_FILE" and (case.get("status") != "DOCUMENTS_READY" or case.get("documents_outdated")):
        raise HTTPException(409, "Review current, unblocked documents before marking ready to file.")
    if body.status != "READY_TO_FILE" and case.get("status") not in FILING_STATUSES:
        raise HTTPException(409, "First review the documents and mark the matter ready to file.")
    if body.receipt_evidence_id and body.receipt_evidence_id not in {item["evidence_id"] for item in case.get("evidence", [])}: raise HTTPException(422, "Receipt evidence not found.")
    update = {"id": uuid4().hex, **body.model_dump(), "source_label": "Advocate Update", "updated_by": user["id"], "updated_at": utc_now()}
    db = request.app.state.adapters.database
    write(db, case_id, {"status": body.status, "journey_stage": body.status, "filing_update": update, "filing_history": case.get("filing_history", []) + [update]}, user["id"], "filing_updated")
    notify(db, case["owner_user_id"], "Your advocate added a case status update: " + body.explanation, case_id)
    return {"update": update}
