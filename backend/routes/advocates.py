import os
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..models.case import utc_now
from ..services.advocate_review import DEPENDENCY_MAP, append_audit, audit, outstanding_items
from ..services.legal_analysis import run_legal_pipeline
from ..services.sharing import require_access, shared_case
from .dependencies import get_case_or_error, get_current_user

router = APIRouter(prefix="/api")


def require_advocate(user: dict[str, Any]) -> None:
    if user.get("role") != "advocate":
        raise HTTPException(status_code=403, detail="Advocate access required")
    if user.get("verification_status") != "VERIFIED":
        raise HTTPException(status_code=403, detail="Advocate verification is required")


def accepted_case(request: Request, case_id: str, user: dict[str, Any]) -> dict[str, Any]:
    require_advocate(user)
    require_access(request, case_id, user, "case_file")
    case = request.app.state.adapters.database.get("cases", case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.get("assigned_advocate_id") != user["id"] or case.get("status") not in {"ADVOCATE_REVIEW", "ADVOCATE_APPROVED", "DOCUMENTS_READY", "DOCUMENTS_BLOCKED", "GENERATING_DOCUMENTS", "REVIEW_REQUIRED", "ENGINE1_RUNNING", "ENGINE2_RUNNING", "NEEDS_DOCUMENT"}:
        raise HTTPException(status_code=403, detail="This case is not assigned to you")
    return case


class VerificationBody(BaseModel):
    status: str
    reason: str = ""


class AdvocateRequestBody(BaseModel):
    advocate_id: str


class ProvisionUpdate(BaseModel):
    explanation: str | None = None
    removed: bool | None = None


class ForumUpdate(BaseModel):
    commission_level: str
    territorial_basis: str


class LimitationUpdate(BaseModel):
    result: str
    reasoning: str


class ArgumentUpdate(BaseModel):
    resolution: str | None = None
    note: str | None = None


class DocumentRequestBody(BaseModel):
    description: str
    affected_stages: list[str] = ["EVIDENCE_ISSUE_MAPPING", "EVIDENCE_CHALLENGER", "REBUTTAL", "NEUTRAL_EVALUATION"]


class ReviewNoteBody(BaseModel):
    note: str


@router.post("/advocate/cases/{case_id}/evidence/{evidence_id}/approve")
def approve_evidence(case_id: str, evidence_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    if case.get("workflow_version") == 2:
        raise HTTPException(410, "Use the versioned advocate review endpoint for this case.")
    if not any(item.get("evidence_id") == evidence_id for item in case.get("evidence", [])):
        raise HTTPException(status_code=404, detail="Evidence not found")
    entry = audit(case, user["id"], "approve", f"evidence:{evidence_id}", None, {"approved": True})
    updated = request.app.state.adapters.database.update("cases", case_id, {
        "advocate_approved_items": list(set(case.get("advocate_approved_items", []) + [f"evidence:{evidence_id}"])),
        "advocate_audit": append_audit(case, entry),
        "version": case.get("version", 1) + 1,
    })
    return {"case": updated}


@router.post("/advocate/cases/{case_id}/evidence/{evidence_id}/remove")
def remove_evidence(case_id: str, evidence_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    if case.get("workflow_version") == 2:
        raise HTTPException(410, "Use the versioned advocate review endpoint for this case.")
    if not any(item.get("evidence_id") == evidence_id for item in case.get("evidence", [])):
        raise HTTPException(status_code=404, detail="Evidence not found")
    entry = audit(case, user["id"], "remove", f"evidence:{evidence_id}", None, {"removed": True})
    updated = request.app.state.adapters.database.update("cases", case_id, {
        "advocate_removed_items": list(set(case.get("advocate_removed_items", []) + [f"evidence:{evidence_id}"])),
        "advocate_audit": append_audit(case, entry),
        "version": case.get("version", 1) + 1,
    })
    return {"case": updated}


@router.get("/advocates")
def directory(request: Request, domain: str | None = None, state: str | None = None, language: str | None = None, user: dict = Depends(get_current_user)):
    result = []
    for advocate in request.app.state.adapters.database.list("users"):
        if advocate.get("role") != "advocate" or advocate.get("verification_status") != "VERIFIED":
            continue
        if domain and domain.lower() not in [item.lower() for item in advocate.get("practice_domains", [])]:
            continue
        if state and advocate.get("state", "").lower() != state.lower():
            continue
        if language and language.lower() not in [item.lower() for item in advocate.get("languages", [])]:
            continue
        result.append({key: advocate.get(key) for key in ("id", "full_name", "bar_council", "enrolment_year", "place_of_practice", "practice_domains", "languages", "state", "court_region")})
    return {"advocates": result}


@router.post("/admin/advocates/{advocate_id}/verification")
def verify_advocate(advocate_id: str, body: VerificationBody, request: Request, user: dict = Depends(get_current_user)):
    admin_token = request.headers.get("X-Admin-Token")
    configured = os.getenv("ADMIN_TOKEN", "")
    if not configured or not admin_token or not secrets.compare_digest(admin_token, configured):
        raise HTTPException(status_code=403, detail="Admin verification token required")
    if body.status not in {"VERIFIED", "UNVERIFIED", "VERIFICATION_PENDING"}:
        raise HTTPException(status_code=422, detail="Invalid verification status")
    advocate = request.app.state.adapters.database.get("users", advocate_id)
    if not advocate or advocate.get("role") != "advocate":
        raise HTTPException(status_code=404, detail="Advocate not found")
    if not body.reason.strip():
        raise HTTPException(422, "A verification review reason is required.")
    if body.status == "VERIFIED" and not advocate.get("verification_documents"):
        raise HTTPException(409, "Review supporting enrolment documents before verification.")
    from uuid import uuid4
    db = request.app.state.adapters.database
    db.create("verification_audit", {"id": uuid4().hex, "advocate_id": advocate_id, "reviewer_id": user["id"], "previous": advocate.get("verification_status"), "new": body.status, "reason": body.reason, "created_at": utc_now()})
    updated = db.update("users", advocate_id, {"verification_status": body.status, "verification_reason": body.reason})
    return {"user": {key: value for key, value in updated.items() if key != "password_hash"}}


@router.get("/admin/advocates")
def admin_advocates(request: Request, user: dict = Depends(get_current_user)):
    token = request.headers.get("X-Admin-Token", "")
    configured = os.getenv("ADMIN_TOKEN", "")
    if not configured or not token or not secrets.compare_digest(token, configured):
        raise HTTPException(status_code=403, detail="Admin verification token required")
    return {"advocates": [{key: value for key, value in item.items() if key != "password_hash"} for item in request.app.state.adapters.database.list("users") if item.get("role") == "advocate"]}


@router.get("/admin/advocates/{advocate_id}/documents/{index}")
def verification_material(advocate_id: str, index: int, request: Request, user: dict = Depends(get_current_user)):
    token = request.headers.get("X-Admin-Token", "")
    configured = os.getenv("ADMIN_TOKEN", "")
    if not configured or not token or not secrets.compare_digest(token, configured):
        raise HTTPException(403, "Admin verification token required.")
    advocate = request.app.state.adapters.database.get("users", advocate_id)
    documents = (advocate or {}).get("verification_documents", [])
    if index < 0 or index >= len(documents):
        raise HTTPException(404, "Verification document not found.")
    from fastapi.responses import Response
    item = documents[index]
    return Response(request.app.state.adapters.storage.download(item["storage_key"]), media_type=item.get("content_type") or "application/octet-stream")


@router.post("/cases/{case_id}/request-advocate")
def request_advocate(case_id: str, request: Request, body: AdvocateRequestBody | None = None, advocate_id: str | None = None, user: dict = Depends(get_current_user)):
    advocate_id = body.advocate_id if body else advocate_id
    if not advocate_id:
        raise HTTPException(status_code=422, detail="advocate_id is required")
    case = get_case_or_error(request, case_id, user)
    if user.get("role") != "client" or case["status"] not in {"PREVIEW_2_APPROVED", "ENGINE1_DONE", "ENGINE2_DONE", "LEGAL_CORPUS_NOT_READY", "REVIEW_REQUIRED"} or case.get("processing_error"):
        raise HTTPException(status_code=409, detail="Only approved client cases can request an advocate")
    advocate = request.app.state.adapters.database.get("users", advocate_id)
    if not advocate or advocate.get("role") != "advocate" or advocate.get("verification_status") != "VERIFIED":
        raise HTTPException(status_code=400, detail="Selected advocate is not verified")
    existing = next((item for item in request.app.state.adapters.database.list("advocate_requests") if item["case_id"] == case_id and item["status"] == "PENDING"), None)
    if existing:
        raise HTTPException(status_code=409, detail="A request is already pending")
    request.app.state.adapters.database.create("advocate_requests", {"id": f"{case_id}-{advocate_id}", "case_id": case_id, "advocate_id": advocate_id, "client_id": user["id"], "status": "PENDING", "created_at": utc_now()})
    updated = request.app.state.adapters.database.update("cases", case_id, {"status": "AWAITING_ADVOCATE", "requested_advocate_id": advocate_id, "version": case.get("version", 1) + 1})
    from ..services.overview import client_case
    return {"case": client_case(updated)}


@router.post("/cases/{case_id}/cancel-advocate-request")
def cancel_request(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = get_case_or_error(request, case_id, user)
    pending = next((item for item in request.app.state.adapters.database.list("advocate_requests") if item["case_id"] == case_id and item["client_id"] == user["id"] and item["status"] == "PENDING"), None)
    if not pending:
        raise HTTPException(status_code=404, detail="Pending advocate request not found")
    request.app.state.adapters.database.update("advocate_requests", pending["id"], {"status": "CANCELLED"})
    restored_status = "ENGINE2_DONE" if case.get("engine2") else "ENGINE1_DONE"
    updated = request.app.state.adapters.database.update("cases", case_id, {"status": restored_status if case.get("workflow_version") == 2 else "PREVIEW_2_APPROVED", "requested_advocate_id": None, "version": case.get("version", 1) + 1})
    from ..services.overview import client_case
    return {"case": client_case(updated)}


@router.get("/advocate/requests")
def advocate_requests(request: Request, user: dict = Depends(get_current_user)):
    require_advocate(user)
    result = []
    for item in request.app.state.adapters.database.list("advocate_requests"):
        if item["advocate_id"] != user["id"] or item["status"] != "PENDING":
            continue
        case = request.app.state.adapters.database.get("cases", item["case_id"])
        result.append({"case_id": item["case_id"], "status": item["status"], "domain": case.get("legal_domain", {}).get("domain"), "sub_domain": case.get("legal_domain", {}).get("sub_domain"), "forum_level": case.get("forum", {}).get("commission_level"), "evidence_count": len(case.get("evidence", [])), "unresolved_risks_count": len(case.get("neutral_evaluation", {}).get("unresolved_risks", []))})
    return {"requests": result}


@router.post("/advocate/requests/{case_id}/accept")
def accept_request(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    require_advocate(user)
    item = next((item for item in request.app.state.adapters.database.list("advocate_requests") if item["case_id"] == case_id and item["advocate_id"] == user["id"] and item["status"] == "PENDING"), None)
    if not item:
        raise HTTPException(status_code=403, detail="No pending request for this advocate")
    request.app.state.adapters.database.update("advocate_requests", item["id"], {"status": "ACCEPTED"})
    request.app.state.adapters.database.update("cases", case_id, {"status": "AWAITING_ADVOCATE", "assigned_advocate_id": user["id"]})
    return {"status": "ACCEPTED_AWAITING_CLIENT_CONSENT", "case_id": case_id}


@router.post("/advocate/requests/{case_id}/decline")
def decline_request(case_id: str, request: Request, reason: str | None = None, user: dict = Depends(get_current_user)):
    require_advocate(user)
    item = next((item for item in request.app.state.adapters.database.list("advocate_requests") if item["case_id"] == case_id and item["advocate_id"] == user["id"] and item["status"] == "PENDING"), None)
    if not item:
        raise HTTPException(status_code=403, detail="No pending request for this advocate")
    request.app.state.adapters.database.update("advocate_requests", item["id"], {"status": "DECLINED", "reason": reason or ""})
    case = request.app.state.adapters.database.get("cases", case_id)
    restored_status = "ENGINE2_DONE" if case.get("engine2") else "ENGINE1_DONE"
    updated = request.app.state.adapters.database.update("cases", case_id, {"status": restored_status if case.get("workflow_version") == 2 else "PREVIEW_2_APPROVED", "requested_advocate_id": None})
    return {"status": updated["status"], "case_id": case_id}


@router.get("/advocate/cases")
def list_advocate_cases(request: Request, user: dict = Depends(get_current_user)):
    require_advocate(user)
    advocate_id = user["id"]
    
    requests_list = [
        item for item in request.app.state.adapters.database.list("advocate_requests")
        if item.get("advocate_id") == advocate_id
    ]
    pending_request_case_ids = {
        item["case_id"] for item in requests_list if item.get("status") == "PENDING"
    }

    pending_requests = []
    under_review = []
    finalised = []
    
    all_cases = request.app.state.adapters.database.list("cases")
    for case in all_cases:
        case_id = case.get("case_id") or case.get("id")
        assigned_id = case.get("assigned_advocate_id") or case.get("advocate_id")
        requested_id = case.get("requested_advocate_id")
        status = case.get("status")

        if assigned_id != advocate_id and requested_id != advocate_id and case_id not in pending_request_case_ids:
            continue

        summary = {
            "case_id": case_id,
            "status": status,
            "created_at": case.get("created_at"),
            "stage": case.get("stage"),
            "domain": case.get("legal_domain", {}).get("domain") or case.get("domain"),
            "sub_domain": case.get("legal_domain", {}).get("sub_domain"),
            "forum_level": case.get("forum", {}).get("commission_level"),
            "evidence_count": len(case.get("evidence", [])),
            "unresolved_risks_count": len(case.get("neutral_evaluation", {}).get("unresolved_risks", [])),
            "outstanding_items_count": len(outstanding_items(case)),
            "outstanding_doc_requests_count": len([req for req in case.get("advocate_document_requests", []) if not req.get("resolved")]),
            "title": (case.get("client_story", "").strip() or "Untitled case")[:80],
            "preview": case.get("client_story", "").strip()[:140],
        }
        summary.pop("title", None)
        summary.pop("preview", None)
        if status == "AWAITING_ADVOCATE":
            summary.pop("title", None)
            summary.pop("preview", None)
            summary["client_consent_pending"] = bool(case.get("assigned_advocate_id"))

        if status == "AWAITING_ADVOCATE" or (case_id in pending_request_case_ids and status not in {"ADVOCATE_REVIEW", "ADVOCATE_APPROVED"}):
            pending_requests.append(summary)
        elif status == "ADVOCATE_REVIEW":
            under_review.append(summary)
        elif status in {"ADVOCATE_APPROVED", "DOCUMENTS_READY", "DOCUMENTS_BLOCKED"}:
            finalised.append(summary)

    return {
        "pending_requests": pending_requests,
        "under_review": under_review,
        "finalised": finalised,
        "cases": under_review + finalised,
    }


@router.get("/advocate/cases/{case_id}")
def advocate_case(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    grant = require_access(request, case_id, user, "case_file")
    return {"case": shared_case(case, grant)}


def change_review_item(case_id: str, kind: str, target_id: str, new_value: Any, request: Request, user: dict, action: str):
    case = accepted_case(request, case_id, user)
    if case.get("workflow_version") == 2:
        raise HTTPException(410, "Use the versioned advocate review endpoint for this case.")
    if action == "approve" and kind == "fact":
        new_value = {"human_corrected": True, "advocate_approved": True}
    if action == "approve" and kind in {"forum", "limitation"}:
        new_value = case.get(kind) or {}
    previous = None
    changes: dict[str, Any] = {}
    if kind == "fact":
        facts = []
        for item in case.get("facts", []):
            if item["fact_id"] == target_id:
                previous = item
                item = {**item, **new_value}
                facts.append(item)
            else:
                facts.append(item)
        changes["facts"] = facts
    elif kind == "provision":
        sections = []
        for item in case.get("verified_legal_sections", []):
            if item["provision_id"] == target_id:
                previous = item
                item = {**item, **new_value}
                sections.append(item)
            else:
                sections.append(item)
        changes["verified_legal_sections"] = sections
    elif kind == "argument":
        args = dict(case.get("arguments", {}))
        opponent = dict(args.get("opponent", {}))
        objections = []
        for item in opponent.get("objections", []):
            if item.get("objection_id") == target_id or item.get("id") == target_id:
                previous = item
                item = {**item, **new_value}
            objections.append(item)
        if previous is not None:
            opponent["objections"] = objections
            args["opponent"] = opponent
        else:
            rebuttals = []
            for item in args.get("rebuttal", {}).get("rebuttals", []):
                if item.get("objection_id") == target_id or item.get("id") == target_id:
                    previous = item
                    item = {**item, **new_value}
                rebuttals.append(item)
            args.setdefault("rebuttal", {})["rebuttals"] = rebuttals
        changes["arguments"] = args
    elif kind == "forum":
        previous = case.get("forum")
        changes["forum"] = new_value
    elif kind == "limitation":
        previous = case.get("limitation")
        changes["limitation"] = new_value
    if previous is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    rerun = DEPENDENCY_MAP[kind]
    entry = audit(case, user["id"], action, f"{kind}:{target_id}", previous, new_value)
    changes["advocate_audit"] = append_audit(case, entry)
    changes["advocate_reruns"] = case.get("advocate_reruns", []) + [{"stages": rerun, "reason": f"{action} on {kind}:{target_id}", "timestamp": entry["timestamp"]}]
    changes["version"] = case.get("version", 1) + 1
    if action == "approve":
        changes["advocate_approved_items"] = list(set(case.get("advocate_approved_items", []) + [f"{kind}:{target_id}"]))
    updated = request.app.state.adapters.database.update("cases", case_id, changes)
    if action != "approve":
        run_legal_pipeline(request.app, case_id, requested_stages=rerun)
    return {"case": updated, "rerun_stages": rerun}


@router.patch("/advocate/cases/{case_id}/facts/{fact_id}")
def edit_fact(case_id: str, fact_id: str, body: dict[str, Any], request: Request, user: dict = Depends(get_current_user)):
    body = {**body, "human_corrected": True}
    return change_review_item(case_id, "fact", fact_id, body, request, user, "edit")


@router.post("/advocate/cases/{case_id}/facts/{fact_id}/approve")
def approve_fact(case_id: str, fact_id: str, request: Request, user: dict = Depends(get_current_user)):
    return change_review_item(case_id, "fact", fact_id, {}, request, user, "approve")


@router.patch("/advocate/cases/{case_id}/provisions/{provision_id}")
def edit_provision(case_id: str, provision_id: str, body: ProvisionUpdate, request: Request, user: dict = Depends(get_current_user)):
    return change_review_item(case_id, "provision", provision_id, body.model_dump(exclude_none=True), request, user, "edit")


@router.post("/advocate/cases/{case_id}/provisions/{provision_id}/remove")
def remove_provision(case_id: str, provision_id: str, request: Request, user: dict = Depends(get_current_user)):
    result = change_review_item(case_id, "provision", provision_id, {"removed": True}, request, user, "remove")
    case = result["case"]
    result["case"] = request.app.state.adapters.database.update("cases", case_id, {"advocate_removed_items": case.get("advocate_removed_items", []) + [f"provision:{provision_id}"]})
    return result


@router.post("/advocate/cases/{case_id}/provisions/{provision_id}/approve")
def approve_provision(case_id: str, provision_id: str, request: Request, user: dict = Depends(get_current_user)):
    return change_review_item(case_id, "provision", provision_id, {}, request, user, "approve")


@router.patch("/advocate/cases/{case_id}/forum")
def edit_forum(case_id: str, body: ForumUpdate, request: Request, user: dict = Depends(get_current_user)):
    return change_review_item(case_id, "forum", "forum", body.model_dump(), request, user, "edit")


@router.post("/advocate/cases/{case_id}/forum/approve")
def approve_forum(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    return change_review_item(case_id, "forum", "forum", {}, request, user, "approve")


@router.patch("/advocate/cases/{case_id}/limitation")
def edit_limitation(case_id: str, body: LimitationUpdate, request: Request, user: dict = Depends(get_current_user)):
    return change_review_item(case_id, "limitation", "limitation", body.model_dump(), request, user, "edit")


@router.post("/advocate/cases/{case_id}/limitation/approve")
def approve_limitation(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    return change_review_item(case_id, "limitation", "limitation", {}, request, user, "approve")


@router.patch("/advocate/cases/{case_id}/arguments/{objection_id}")
def edit_argument(case_id: str, objection_id: str, body: ArgumentUpdate, request: Request, user: dict = Depends(get_current_user)):
    return change_review_item(case_id, "argument", objection_id, body.model_dump(exclude_none=True), request, user, "edit")


@router.post("/advocate/cases/{case_id}/arguments/{objection_id}/approve")
def approve_argument(case_id: str, objection_id: str, request: Request, user: dict = Depends(get_current_user)):
    return change_review_item(case_id, "argument", objection_id, {}, request, user, "approve")


@router.post("/advocate/cases/{case_id}/document-requests")
def create_document_request(case_id: str, body: DocumentRequestBody, request: Request, user: dict = Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    item = {"request_id": f"ADR{len(case.get('advocate_document_requests', [])) + 1:03d}", "description": body.description, "affected_stages": body.affected_stages, "resolved": False, "raised_by": user["id"]}
    updated = request.app.state.adapters.database.update("cases", case_id, {"advocate_document_requests": case.get("advocate_document_requests", []) + [item], "version": case.get("version", 1) + 1})
    return {"request": item, "case": shared_case(updated, require_access(request, case_id, user, "case_file"))}


@router.post("/advocate/cases/{case_id}/review-note")
def review_note(case_id: str, body: ReviewNoteBody, request: Request, user: dict = Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    entry = audit(case, user["id"], "review_note", "review_note", case.get("advocate_review_note"), body.note)
    updated = request.app.state.adapters.database.update("cases", case_id, {"advocate_review_note": body.note, "advocate_audit": append_audit(case, entry), "version": case.get("version", 1) + 1})
    return {"case": shared_case(updated, require_access(request, case_id, user, "case_file"))}


@router.post("/cases/{case_id}/advocate/finalize")
def finalize(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    if case.get("workflow_version") == 2:
        raise HTTPException(410, "Use the versioned advocate approval endpoint.")
    pending = outstanding_items(case)
    docs = [item for item in case.get("advocate_document_requests", []) if not item.get("resolved")]
    if pending or docs:
        raise HTTPException(status_code=409, detail={"message": "Review is incomplete.", "outstanding_items": pending, "outstanding_document_requests": docs})
    updated = request.app.state.adapters.database.update("cases", case_id, {"status": "ADVOCATE_APPROVED", "advocate_finalized_by": user["id"], "advocate_finalized_at": utc_now(), "version": case.get("version", 1) + 1})
    return {"case": updated}
