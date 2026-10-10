import copy
import hashlib
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from ..models.case import utc_now
from ..models.engines import ENGINE1_STAGES, ENGINE2_STAGES
from ..services.sharing import require_access
from ..services.jobs import dispatch
from .dependencies import get_current_user
from .advocates import accepted_case

router = APIRouter(prefix="/api/advocate/cases")
DEPENDENCIES = {"fact": "FACT_EXTRACTION", "incident": "FACT_EXTRACTION", "timeline": "TIMELINE_CONSTRUCTION", "party": "PARTY_IDENTIFICATION", "issue": "LEGAL_ISSUE_IDENTIFICATION", "provision": "CITATION_VERIFICATION", "temporal_law": "TEMPORAL_LAW_CHECK", "forum": "JURISDICTION_FORUM", "limitation": "LIMITATION_CHECK", "mapping": "EVIDENCE_ISSUE_MAPPING"}


class ReviewBody(BaseModel):
    kind: str
    target_id: str
    action: str
    value: dict = Field(default_factory=dict)
    reason: str = Field(min_length=1)


class RerunBody(BaseModel):
    engine: int
    start_stage: str | None = None


@router.post("/{case_id}/review")
def review(case_id: str, body: ReviewBody, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    if case["status"] in {"ENGINE1_RUNNING", "ENGINE2_RUNNING", "GENERATING_DOCUMENTS"}:
        raise HTTPException(409, "Wait for the active engine to finish.")
    if body.kind not in {*DEPENDENCIES, "argument", "pending", "evidence"} or body.action not in {"approve", "edit", "remove", "verify"}:
        raise HTTPException(422, "Invalid review operation.")
    if body.kind == "argument":
        require_access(request, case_id, user, "engine2")
    file = copy.deepcopy(case.get("case_file", {}))
    previous = None
    target = None
    collections = {"fact": ("facts", "fact_id"), "timeline": ("timeline", "event_id"), "provision": ("applicable_law", "provision_id"), "mapping": ("evidence_issue_mapping", "issue_id"), "pending": ("pending_advocate_verification", "provision_id")}
    collections.update({"issue": ("legal_issues", "issue_id"), "incident": ("incidents", "incident_id")})
    if body.kind in collections:
        collection, key = collections[body.kind]
        target = next((item for item in file.get(collection, []) if item.get(key) == body.target_id), None)
    elif body.kind in {"forum", "limitation", "temporal_law"}:
        target = file.get(body.kind)
    elif body.kind == "party":
        target = file.get("parties")
    elif body.kind == "argument":
        target = case.get("engine2", {}).get("opponent_counsel", {}).get("objections", [])
        target = next((item for item in target if item["objection_id"] == body.target_id), None)
    elif body.kind == "evidence":
        grant = require_access(request, case_id, user, "evidence")
        if body.target_id not in grant["evidence_ids"]:
            raise HTTPException(403, "Evidence was not shared.")
        target = next((item for item in case.get("evidence", []) if item["evidence_id"] == body.target_id), None)
    if target is None:
        if body.kind == "pending" and body.action == "verify" and body.value.get("title") and body.target_id and not any(item.get("provision_id") == body.target_id for item in file.get("applicable_law", [])):
            target = {"provision_id": body.target_id, "title": body.value["title"], "explanation": body.value.get("explanation", "")}
            file.setdefault("pending_advocate_verification", []).append(target)
        else:
            raise HTTPException(404, "Review item not found.")
    previous = copy.deepcopy(target)
    if body.action == "verify":
        if body.kind not in {"pending", "forum", "limitation", "temporal_law"}:
            raise HTTPException(422, "Explicit verification applies to pending law, forum, or limitation.")
        proof = body.value
        required = {"source_url", "retrieved_at", "official_text", "quote"}
        if not required.issubset(proof) or not all(proof[key] for key in required) or proof["quote"] not in proof["official_text"]:
            raise HTTPException(422, "Provide current official source URL, retrieval date, official text and an exact supporting quote.")
        from datetime import datetime, timezone
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(proof["retrieved_at"].replace("Z", "+00:00"))).total_seconds()
            if age < -300 or age > 30 * 86400:
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(422, "Use a timezone-aware retrieval date from the last 30 days.")
        from ..services.legal_knowledge import LegalKnowledge
        hosts = {host for source in LegalKnowledge().sources.values() for host in source["hosts"]}
        url = urlparse(proof["source_url"])
        if url.scheme != "https" or url.hostname not in hosts or url.username or url.password:
            raise HTTPException(422, "Register this official source before using it as verified authority.")
        protected = {"provision_id", "fact_id", "event_id", "issue_id", "removed", "advocate_approved"}
        if protected.intersection(proof):
            raise HTTPException(422, "Verification must preserve item identity and approval state.")
        target.update({**proof, "verification_status": "VERIFIED", "verification_method": "ADVOCATE_MANUAL_REVIEW", "verified_by": user["id"], "verified_at": utc_now(), "content_hash": hashlib.sha256(proof["official_text"].encode()).hexdigest()})
        if body.kind == "pending":
            file["pending_advocate_verification"].remove(target)
            file.setdefault("applicable_law", []).append(target)
    elif body.action == "edit":
        forbidden = {"verification_status", "verified_by", "verified_at", "source_url", "official_text", "content_hash", "retrieved_at", "provision_id", "fact_id", "event_id", "issue_id"}
        if forbidden.intersection(body.value):
            raise HTTPException(422, "Identity and verification metadata cannot be changed through ordinary edits.")
        target.update(body.value)
        target["human_corrected"] = True
        if body.kind in {"provision", "forum", "limitation", "temporal_law"}:
            target["verification_status"] = "PENDING_ADVOCATE_VERIFICATION"
            if body.kind == "provision":
                file["applicable_law"].remove(target)
                file.setdefault("pending_advocate_verification", []).append(target)
    elif body.action == "remove":
        target["removed"] = True
    elif body.action == "approve":
        if body.kind in {"provision", "pending", "forum", "limitation", "temporal_law"} and target.get("verification_status") != "VERIFIED":
            raise HTTPException(409, "Verify the official legal basis explicitly before approving this item.")
        target["advocate_approved"] = True
        if body.kind == "fact":
            target["human_corrected"] = True
    approved = set(case.get("advocate_approved_items", []))
    removed = set(case.get("advocate_removed_items", []))
    label = f"{body.kind}:{body.target_id}"
    if body.action == "approve": approved.add(label)
    if body.action == "remove": removed.add(label); approved.discard(label)
    if body.action in {"edit", "verify"}: approved.discard(label)
    changed_foundation = body.kind != "argument" and body.action != "approve"
    if changed_foundation:
        file["version"] = file.get("version", 0) + 1
    entry = {"advocate_id": user["id"], "action": body.action, "target": label, "previous": previous, "new": copy.deepcopy(target), "reason": body.reason, "timestamp": utc_now()}
    changes = {"case_file": file, "advocate_approved_items": sorted(approved), "advocate_removed_items": sorted(removed), "advocate_audit": case.get("advocate_audit", []) + [entry], "documents_outdated": bool(case.get("document_version")), "status": "ADVOCATE_REVIEW"}
    if body.kind == "argument":
        changes["engine2"] = case["engine2"]
    if body.kind == "evidence": changes["evidence"] = case["evidence"]
    if body.action != "approve":
        changes["professional_overrides"] = case.get("professional_overrides", []) + [entry]
    if changed_foundation:
        changes["engine2_stale"] = True
        changes["recommended_engine1_start"] = DEPENDENCIES.get(body.kind, "CITATION_VERIFICATION")
    for key in ("facts", "timeline", "parties", "forum", "limitation", "evidence_issue_mapping"):
        changes[key] = file.get(key, case.get(key))
    changes["verified_legal_sections"] = file.get("applicable_law", [])
    from ..services.blackboard import write, engine_state
    write(request.app.state.adapters.database, case_id, changes, user["id"], "professional_review")
    if changed_foundation and case.get("engine2"): engine_state(request.app.state.adapters.database, case_id, 2, "STALE", reason=body.reason)
    if case.get("document_version"): engine_state(request.app.state.adapters.database, case_id, 3, "STALE", outcome="OUTDATED", reason=body.reason)
    return {"status": "saved", "recommended_engine1_start": changes.get("recommended_engine1_start"), "engine2_stale": changed_foundation}


@router.post("/{case_id}/rerun")
def rerun(case_id: str, body: RerunBody, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    if body.engine not in {1, 2}:
        raise HTTPException(422, "Choose Engine 1 or Engine 2.")
    if case["status"] in {"ENGINE1_RUNNING", "ENGINE2_RUNNING", "GENERATING_DOCUMENTS"}:
        raise HTTPException(409, "A processing job is already running.")
    stages = ENGINE1_STAGES if body.engine == 1 else ENGINE2_STAGES
    if body.start_stage and body.start_stage not in stages:
        raise HTTPException(422, "The requested stage does not belong to this engine.")
    if body.engine == 1:
        grant = require_access(request, case_id, user, "story")
        require_access(request, case_id, user, "evidence")
        if not {item["evidence_id"] for item in case.get("evidence", [])}.issubset(grant["evidence_ids"]):
            raise HTTPException(403, "Engine 1 reruns require consent for every source input used by the case.")
    else:
        require_access(request, case_id, user, "engine2")
    entry = {"advocate_id": user["id"], "action": "rerun", "target": f"engine{body.engine}", "previous": case["status"], "new": body.start_stage or "ALL", "timestamp": utc_now()}
    if body.engine == 2 and not case.get("case_file"):
        raise HTTPException(409, "Complete the case foundation before running Case Challenge.")
    request.app.state.adapters.database.update("cases", case_id, {"status": f"ENGINE{body.engine}_RUNNING", "analysis_requested_by": user["id"], "documents_outdated": bool(case.get("document_version")), "advocate_audit": case.get("advocate_audit", []) + [entry]})
    try:
        dispatch(request.app, body.engine, case_id, start_stage=body.start_stage)
    except Exception:
        request.app.state.adapters.database.update("cases", case_id, {"status": "REVIEW_REQUIRED", "processing_error": {"engine": body.engine, "stage": "DISPATCH", "message": "The rerun could not be started."}})
        raise HTTPException(503, "Rerun could not be started.")
    return {"status": "started"}


@router.post("/{case_id}/approve")
def approve(case_id: str, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    if case["status"] != "ADVOCATE_REVIEW" or case.get("processing_error"):
        raise HTTPException(409, "Complete review and resolve processing errors first.")
    if case.get("engine2") and case.get("engine2_stale"):
        raise HTTPException(409, "Rerun Engine 2 after foundation changes before final approval.")
    file = case.get("case_file", {})
    if case.get("engines", {}).get("1", {}).get("status") == "STALE":
        raise HTTPException(409, "Update the case foundation after new client information before approval.")
    if not file.get("version"):
        raise HTTPException(409, "Run and review the case foundation before final approval.")
    required = {f"fact:{item['fact_id']}" for item in file.get("facts", []) if not item.get("removed")}
    required |= {f"provision:{item['provision_id']}" for item in file.get("applicable_law", []) if not item.get("removed")}
    missing = required - set(case.get("advocate_approved_items", []))
    if missing:
        raise HTTPException(409, {"message": "Review all facts and verified provisions first.", "outstanding": sorted(missing)})
    entry = {"advocate_id": user["id"], "action": "final_approval", "target": "case", "previous": case["status"], "new": "ADVOCATE_APPROVED", "timestamp": utc_now()}
    request.app.state.adapters.database.update("cases", case_id, {"status": "ADVOCATE_APPROVED", "advocate_approved_case_file_version": file.get("version"), "advocate_audit": case.get("advocate_audit", []) + [entry]})
    return {"status": "ADVOCATE_APPROVED"}
