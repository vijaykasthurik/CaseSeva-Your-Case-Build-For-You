from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from ..models.case import utc_now
from ..services.sharing import active_grant, grant_access, issue_token, require_access, build_handoff_contract
from .dependencies import get_current_user, get_case_or_error

router = APIRouter(prefix="/api")


class ConsentBody(BaseModel):
    scopes: list[str]
    evidence_ids: list[str] = Field(default_factory=list)
    expires_in_hours: int = Field(default=168, ge=1, le=720)


@router.post("/cases/{case_id}/sharing")
def consent(case_id: str, body: ConsentBody, request: Request, user=Depends(get_current_user)):
    case = get_case_or_error(request, case_id, user)
    db = request.app.state.adapters.database
    advocate = db.get("users", case.get("assigned_advocate_id", ""))
    if not advocate or advocate.get("verification_status") != "VERIFIED":
        raise HTTPException(409, "A verified advocate must first accept the request.")
    if case["status"] not in {"AWAITING_ADVOCATE", "ADVOCATE_REVIEW"}:
        raise HTTPException(409, "Sharing is unavailable in this case state.")
    if active_grant(db, case_id, advocate["id"]):
        raise HTTPException(409, "Revoke the current grant before changing its scope.")
    grant = grant_access(db, case, user, body.scopes, body.evidence_ids, body.expires_in_hours)
    db.update("cases", case_id, {"status": "ADVOCATE_REVIEW"})
    return {"grant": grant}


@router.get("/cases/{case_id}/sharing")
def grants(case_id: str, request: Request, user=Depends(get_current_user)):
    get_case_or_error(request, case_id, user)
    return {"grants": [item for item in request.app.state.adapters.database.list("case_grants") if item["case_id"] == case_id]}


@router.delete("/cases/{case_id}/sharing/{grant_id}")
def revoke(case_id: str, grant_id: str, request: Request, user=Depends(get_current_user)):
    case = get_case_or_error(request, case_id, user)
    db = request.app.state.adapters.database
    grant = db.get("case_grants", grant_id)
    if not grant or grant["case_id"] != case_id:
        raise HTTPException(404, "Sharing grant not found.")
    now = utc_now()
    db.update("case_grants", grant_id, {"revoked_at": now})
    from uuid import uuid4
    db.create("consent_audit", {"id": uuid4().hex, "action": "REVOKE", "actor_id": user["id"], "grant_id": grant_id, "case_id": case_id, "created_at": now})
    if case["status"] in {"ADVOCATE_REVIEW", "ADVOCATE_APPROVED"}:
        db.update("cases", case_id, {"status": "AWAITING_ADVOCATE"})
    return {"status": "revoked"}


@router.post("/advocate/cases/{case_id}/access-token")
def exchange(case_id: str, request: Request, user=Depends(get_current_user)):
    if user.get("role") != "advocate" or user.get("verification_status") != "VERIFIED":
        raise HTTPException(403, "Verified advocate access required.")
    db = request.app.state.adapters.database
    grant = active_grant(db, case_id, user["id"])
    if not grant:
        raise HTTPException(403, "The client has not granted access, or access has expired or been revoked.")
    if grant.get("permission_type") == "WALK_IN_CONSENT":
        return {"access_token": None, "expires_at": None, "permission_type": "WALK_IN_CONSENT"}
    return {"access_token": issue_token(db, grant), "expires_at": grant["expires_at"]}


@router.get("/advocate/cases/{case_id}/evidence/{evidence_id}")
def evidence(case_id: str, evidence_id: str, request: Request, user=Depends(get_current_user)):
    from fastapi.responses import Response
    grant = require_access(request, case_id, user, "evidence")
    if evidence_id not in grant["evidence_ids"]:
        raise HTTPException(403, "This evidence was not shared.")
    case = request.app.state.adapters.database.get("cases", case_id)
    item = next((item for item in case.get("evidence", []) if item["evidence_id"] == evidence_id), None)
    if not item:
        raise HTTPException(404, "Evidence not found.")
    return Response(request.app.state.adapters.storage.download(item["storage_key"]), media_type=item["content_type"])


@router.get("/cases/{case_id}/handoff")
def client_handoff(case_id: str, request: Request, user=Depends(get_current_user)):
    case = get_case_or_error(request, case_id, user)
    db = request.app.state.adapters.database
    grant = active_grant(db, case_id, case.get("assigned_advocate_id", ""))
    return {"handoff": build_handoff_contract(case, grant, db)}


@router.get("/advocate/cases/{case_id}/handoff")
def advocate_handoff(case_id: str, request: Request, user=Depends(get_current_user)):
    if user.get("role") != "advocate" or user.get("verification_status") != "VERIFIED":
        raise HTTPException(403, "Verified advocate access required.")
    db = request.app.state.adapters.database
    case = db.get("cases", case_id)
    if not case:
        raise HTTPException(404, "Case not found.")
    if case.get("assigned_advocate_id") != user["id"]:
        raise HTTPException(403, "This case is not assigned to you.")
    grant = active_grant(db, case_id, user["id"])
    if not grant:
        raise HTTPException(403, "Explicit citizen consent required before accessing case handoff.")
    return {"handoff": build_handoff_contract(case, grant, db)}
