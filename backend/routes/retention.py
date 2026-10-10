import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from .dependencies import get_current_user, get_case_or_error
from ..models.case import utc_now
from ..services.blackboard import write

router = APIRouter(prefix="/api/cases")


@router.post("/{case_id}/deletion-request")
def deletion_request(case_id: str, request: Request, user=Depends(get_current_user)):
    case = get_case_or_error(request, case_id, user)
    if user.get("role") != "client": raise HTTPException(403, "Client account required.")
    days = max(0, int(os.getenv("CASE_RETENTION_DAYS", "365")))
    due = datetime.fromisoformat(case["created_at"].replace("Z", "+00:00")) + timedelta(days=days)
    audit_days = max(days, int(os.getenv("AUDIT_RETENTION_DAYS", "2555")))
    db = request.app.state.adapters.database
    record = {"id": uuid4().hex, "case_id": case_id, "requested_by": user["id"], "requested_at": utc_now(), "delete_after": due.isoformat(), "audit_retention_days": audit_days, "status": "PENDING_RETENTION"}
    db.create("deletion_requests", record)
    for grant in db.list("case_grants"):
        if grant["case_id"] == case_id and not grant.get("revoked_at"):
            db.update("case_grants", grant["id"], {"revoked_at": utc_now()})
    consent = db.get("walkin_consents", case_id)
    if consent:
        db.update("walkin_consents", case_id, {"revoked_at": utc_now()})
    if case["status"] in {"ENGINE1_RUNNING", "ENGINE2_RUNNING", "GENERATING_DOCUMENTS", "SUBMITTED"}:
        record["explanation"] = "Your request is recorded. Active processing must finish before deletion; advocate access is revoked now."
    elif case.get("legal_hold"):
        record["status"] = "LEGAL_HOLD"
        record["explanation"] = "Deletion is paused because this case has a recorded retention hold. Audit and version history are retained."
    elif due > datetime.now(timezone.utc):
        record["explanation"] = "Your deletion request is recorded. Case content remains until the configured retention date; advocate access is revoked now."
    else:
        keys = [item["storage_key"] for item in case.get("evidence", [])]
        documents = [doc for doc in db.list("documents") if doc.get("case_id") == case_id]
        keys += [doc["storage_key"] for doc in documents if doc.get("storage_key")]
        try:
            for key in keys: request.app.state.adapters.storage.delete(key)
            for doc in documents: db.delete("documents", doc["id"])
        except Exception:
            db.update("deletion_requests", record["id"], {"status": "FAILED_RETRY_REQUIRED"})
            raise HTTPException(503, "Deletion could not finish. Your request is recorded and advocate access is revoked; retry is required.")
        # Keep a restricted audit archive according to policy, never returned by citizen APIs.
        db.create("retained_case_audit", {"id": uuid4().hex, "case_id": case_id, "retained_until": (datetime.now(timezone.utc) + timedelta(days=audit_days)).isoformat(), "audit": {key: case.get(key) for key in ("board_history", "advocate_audit", "professional_overrides", "filing_history")}, "document_metadata": [{key: doc.get(key) for key in ("id", "type", "version", "created_at", "case_file_version")} for doc in documents]})
        write(db, case_id, {"client_story": "", "evidence": [], "case_file": {}, "raw_package": {}, "facts": [], "timeline": [], "parties": {}, "engine2": {}, "professional_notes": [], "clarification_rounds": [], "information_requests": [], "engine1_checkpoint": None, "advocate_audit": [], "professional_overrides": [], "verified_legal_sections": [], "legal_sections": [], "arguments": {}, "status": "DELETED", "deleted_at": utc_now()}, user["id"], "case_content_deleted")
        record.update({"status": "DELETED", "explanation": "Active story, evidence and generated documents were deleted. Restricted audit/version history is retained under the configured policy."})
    db.update("deletion_requests", record["id"], record)
    return {"request": record}
