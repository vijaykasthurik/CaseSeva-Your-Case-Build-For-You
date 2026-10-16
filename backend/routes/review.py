import copy
import hashlib
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from ..models.case import utc_now
from ..models.engines import ENGINE1_STAGES, ENGINE2_STAGES
from ..services.sharing import require_access
from ..services.jobs import dispatch
from ..services.review_contracts import check_engine3_eligibility, ENGINE2_NOT_RUN_DISCLOSURE
from .dependencies import get_current_user
from .advocates import accepted_case

router = APIRouter(prefix="/api/advocate/cases")
DEPENDENCIES = {
    "fact": "FACT_EXTRACTION",
    "incident": "FACT_EXTRACTION",
    "timeline": "TIMELINE_CONSTRUCTION",
    "party": "PARTY_IDENTIFICATION",
    "issue": "LEGAL_ISSUE_IDENTIFICATION",
    "provision": "CITATION_VERIFICATION",
    "temporal_law": "TEMPORAL_LAW_CHECK",
    "forum": "JURISDICTION_FORUM",
    "limitation": "LIMITATION_CHECK",
    "mapping": "EVIDENCE_ISSUE_MAPPING",
}


class ReviewBody(BaseModel):
    kind: str
    target_id: str
    action: str
    value: dict = Field(default_factory=dict)
    reason: str = Field(min_length=1)
    is_substantive: bool | None = None
    conflict_resolution: Literal["KEEP", "REPLACE", "MERGE"] = "KEEP"


class RerunBody(BaseModel):
    engine: int
    start_stage: str | None = None


class AnnotationBody(BaseModel):
    annotation: str = ""
    note: str = ""
    relevance_notes: str = ""
    relevance: str = ""
    labels: list[str] = Field(default_factory=list)
    comment: str = ""
    reason: str = "Evidence annotation"


class NoteBody(BaseModel):
    note: str
    visibility: Literal["PRIVATE", "SHARED_WITH_CLIENT"] = "PRIVATE"
    category: str = "NOTE"


class ConflictResolutionBody(BaseModel):
    target_id: str
    strategy: Literal["KEEP", "REPLACE", "MERGE"]
    field_kind: str = "fact"
    merged_value: Any = None
    reason: str = "Resolved by advocate"


@router.post("/{case_id}/review")
def review(case_id: str, body: ReviewBody, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    db = request.app.state.adapters.database
    if case["status"] in {"ENGINE1_RUNNING", "ENGINE2_RUNNING", "GENERATING_DOCUMENTS"}:
        raise HTTPException(409, "Wait for the active engine to finish.")
    if body.kind not in {*DEPENDENCIES, "argument", "pending", "evidence"} or body.action not in {"approve", "edit", "remove", "verify"}:
        raise HTTPException(422, "Invalid review operation.")
    if body.kind == "argument":
        require_access(request, case_id, user, "engine2")
    file = copy.deepcopy(case.get("case_file") or case.get("canonical_case_file") or {})
    previous = None
    target = None
    collections = {
        "fact": ("facts", "fact_id"),
        "timeline": ("timeline", "event_id"),
        "provision": ("applicable_law", "provision_id"),
        "mapping": ("evidence_issue_mapping", "issue_id"),
        "pending": ("pending_advocate_verification", "provision_id"),
        "issue": ("legal_issues", "issue_id"),
        "incident": ("incidents", "incident_id"),
    }
    if body.kind in collections:
        collection, key = collections[body.kind]
        target = next((item for item in file.get(collection, []) if item.get(key) == body.target_id), None)
    elif body.kind in {"forum", "limitation", "temporal_law"}:
        target = file.get(body.kind)
    elif body.kind == "party":
        target = file.get("parties")
    elif body.kind == "argument":
        target = case.get("engine2", {}).get("opponent_counsel", {}).get("objections", [])
        target = next((item for item in target if item.get("objection_id") == body.target_id or item.get("argument_id") == body.target_id), None)
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

    if body.kind == "evidence" and body.action == "edit":
        forbidden_evidence_edits = {"storage_key", "content_hash", "filename", "size", "bytes", "data"}
        if forbidden_evidence_edits.intersection(body.value):
            raise HTTPException(422, "Original citizen evidence is immutable; add annotations or comments instead.")
        if set(body.value) - {"annotation", "comment", "relevance_notes", "labels"}:
            raise HTTPException(422, "Original evidence is immutable; add annotations or comments instead.")

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

    # Substantive classification:
    if body.is_substantive is not None:
        is_substantive = body.is_substantive
    elif body.kind in {"evidence"} or body.action == "approve":
        is_substantive = False
    elif body.kind in {"fact", "timeline", "party", "mapping", "issue", "provision", "temporal_law", "forum", "limitation"} and body.action in {"edit", "remove", "verify"}:
        is_substantive = True
    else:
        is_substantive = False

    if is_substantive:
        file["version"] = file.get("version", 0) + 1

    entry = {
        "advocate_id": user["id"],
        "action": body.action,
        "target": label,
        "previous": previous,
        "new": copy.deepcopy(target),
        "reason": body.reason,
        "is_substantive": is_substantive,
        "strategy": body.conflict_resolution,
        "timestamp": utc_now(),
    }

    # First-class versioned correction record
    correction_id = uuid4().hex
    correction_target = copy.deepcopy(target)
    correction_record = {
        "id": correction_id,
        "correction_id": correction_id,
        "case_id": case_id,
        "advocate_id": user["id"],
        "actor_id": user["id"],
        "actor_role": "advocate",
        "field_kind": body.kind,
        "target_id": body.target_id,
        "original_value": previous,
        "advocate_correction": correction_target.get("text") if isinstance(correction_target, dict) and "text" in correction_target else correction_target,
        "correction_value": correction_target,
        "effective_value": correction_target,
        "affected_case_file_version": file.get("version"),
        "is_substantive": is_substantive,
        "substantive": is_substantive,
        "reason": body.reason,
        "conflict_resolution": body.conflict_resolution,
        "strategy": body.conflict_resolution,
        "conflict_strategy": body.conflict_resolution,
        "timestamp": entry["timestamp"],
    }
    db.create("advocate_case_corrections", correction_record)

    changes = {
        "case_file": file,
        "canonical_case_file": file,
        "advocate_approved_items": sorted(approved),
        "advocate_removed_items": sorted(removed),
        "advocate_audit": case.get("advocate_audit", []) + [entry],
        "advocate_corrections": case.get("advocate_corrections", []) + [correction_record],
        "documents_outdated": bool(case.get("document_version")),
        "status": "ADVOCATE_REVIEW",
    }

    if is_substantive:
        changes["engine1_stale"] = True
        changes["engine2_stale"] = True
        changes["review_status"] = "CHANGES_REQUIRED"
        changes["recommended_engine1_start"] = DEPENDENCIES.get(body.kind, "FACT_EXTRACTION")
    else:
        changes["review_status"] = case.get("review_status", "IN_REVIEW")

    if body.kind == "argument":
        changes["engine2"] = case.get("engine2", {})
    if body.kind == "evidence":
        # Evidence annotation
        ann_id = uuid4().hex
        ann_record = {
            "id": ann_id,
            "annotation_id": ann_id,
            "case_id": case_id,
            "advocate_id": user["id"],
            "evidence_id": body.target_id,
            "annotation": body.value.get("annotation") or body.value.get("comment", ""),
            "relevance_notes": body.value.get("relevance_notes", ""),
            "labels": body.value.get("labels", []),
            "comment": body.value.get("comment", ""),
            "timestamp": entry["timestamp"],
        }
        db.create("advocate_evidence_annotations", ann_record)
        changes["evidence_annotations"] = case.get("evidence_annotations", []) + [ann_record]
        changes["evidence"] = case.get("evidence", [])

    if body.action != "approve":
        changes["professional_overrides"] = case.get("professional_overrides", []) + [entry]

    for key in ("facts", "timeline", "parties", "forum", "limitation", "evidence_issue_mapping"):
        changes[key] = file.get(key, case.get(key))
    changes["verified_legal_sections"] = file.get("applicable_law", [])

    from ..services.blackboard import write, engine_state
    write(db, case_id, changes, user["id"], "professional_review")
    if is_substantive and case.get("engine2"):
        engine_state(db, case_id, 2, "STALE", reason=body.reason)
    if case.get("document_version"):
        engine_state(db, case_id, 3, "STALE", outcome="OUTDATED", reason=body.reason)

    return {
        "status": "saved",
        "recommended_engine1_start": changes.get("recommended_engine1_start"),
        "engine2_stale": is_substantive,
        "is_substantive": is_substantive,
        "review_status": changes["review_status"],
        "correction_id": correction_id,
    }


@router.get("/{case_id}/corrections")
def get_corrections(case_id: str, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    db = request.app.state.adapters.database
    corrections = [c for c in db.list("advocate_case_corrections") if c.get("case_id") == case_id]
    if not corrections and case.get("advocate_corrections"):
        corrections = case["advocate_corrections"]
    return {"corrections": corrections}


@router.post("/{case_id}/evidence/{evidence_id}/annotate")
def annotate_evidence(case_id: str, evidence_id: str, body: AnnotationBody, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    db = request.app.state.adapters.database
    grant = require_access(request, case_id, user, "evidence")
    if evidence_id not in grant["evidence_ids"]:
        raise HTTPException(403, "Evidence was not shared.")
    ev = next((item for item in case.get("evidence", []) if item["evidence_id"] == evidence_id), None)
    if not ev:
        raise HTTPException(404, "Evidence not found.")

    ann_id = uuid4().hex
    text = body.annotation or body.note or body.comment
    relevance = body.relevance_notes or body.relevance
    ann_record = {
        "id": ann_id,
        "annotation_id": ann_id,
        "case_id": case_id,
        "advocate_id": user["id"],
        "evidence_id": evidence_id,
        "annotation": text,
        "relevance_notes": relevance,
        "labels": body.labels,
        "comment": body.comment,
        "timestamp": utc_now(),
    }
    db.create("advocate_evidence_annotations", ann_record)
    existing_anns = case.get("evidence_annotations", [])
    updated = db.update("cases", case_id, {"evidence_annotations": existing_anns + [ann_record]})
    return {"annotation": ann_record, "evidence_id": evidence_id}


@router.get("/{case_id}/evidence/{evidence_id}/annotations")
def get_evidence_annotations(case_id: str, evidence_id: str, request: Request, user=Depends(get_current_user)):
    accepted_case(request, case_id, user)
    db = request.app.state.adapters.database
    annotations = [a for a in db.list("advocate_evidence_annotations") if a.get("case_id") == case_id and a.get("evidence_id") == evidence_id]
    return {"annotations": annotations}


@router.post("/{case_id}/notes")
def add_note(case_id: str, body: NoteBody, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    db = request.app.state.adapters.database
    note_id = uuid4().hex
    cf = case.get("canonical_case_file") or case.get("case_file") or {}
    note_record = {
        "id": note_id,
        "note_id": note_id,
        "case_id": case_id,
        "advocate_id": user["id"],
        "author_name": user.get("full_name", "Advocate"),
        "role": "advocate",
        "visibility": body.visibility,
        "category": body.category,
        "note": body.note,
        "case_file_version": cf.get("version"),
        "created_at": utc_now(),
    }
    db.create("advocate_case_notes", note_record)
    notes = case.get("professional_notes", []) + [note_record]
    db.update("cases", case_id, {"professional_notes": notes})
    return {"note": note_record}


@router.get("/{case_id}/notes")
def get_notes(case_id: str, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    db = request.app.state.adapters.database
    notes = [n for n in db.list("advocate_case_notes") if n.get("case_id") == case_id and n.get("advocate_id") == user["id"]]
    if not notes and case.get("professional_notes"):
        notes = [n for n in case["professional_notes"] if n.get("advocate_id") == user["id"]]
    return {"notes": notes}


@router.post("/{case_id}/resolve-conflict")
def resolve_conflict(case_id: str, body: ConflictResolutionBody, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    db = request.app.state.adapters.database
    overrides = case.get("professional_overrides", [])
    target_label = f"{body.field_kind}:{body.target_id}"

    matched = False
    new_overrides = []
    for entry in overrides:
        if entry.get("target") == target_label:
            matched = True
            entry["strategy"] = body.strategy
            entry["conflict_resolution"] = body.strategy
            if body.strategy == "MERGE":
                entry["merged_value"] = body.merged_value
            entry["resolution_reason"] = body.reason
            entry["resolved_at"] = utc_now()
            if body.strategy != "REPLACE":
                new_overrides.append(entry)
        else:
            new_overrides.append(entry)

    if not matched and body.strategy != "REPLACE":
        new_overrides.append({
            "advocate_id": user["id"],
            "action": "resolve_conflict",
            "target": target_label,
            "new": body.merged_value or {},
            "strategy": body.strategy,
            "conflict_resolution": body.strategy,
            "reason": body.reason,
            "timestamp": utc_now(),
        })

    # Update in advocate_case_corrections
    for corr in db.list("advocate_case_corrections"):
        if corr.get("case_id") == case_id and corr.get("target_id") == body.target_id:
            updates = {
                "conflict_resolution": body.strategy,
                "strategy": body.strategy,
                "conflict_strategy": body.strategy,
                "resolution_reason": body.reason,
            }
            if body.strategy == "MERGE" and body.merged_value is not None:
                updates["effective_value"] = body.merged_value
            db.update("advocate_case_corrections", corr["id"], updates)

    db.update("cases", case_id, {"professional_overrides": new_overrides})
    return {"status": "resolved", "strategy": body.strategy, "target": target_label}


@router.get("/{case_id}/engine3-eligibility")
def get_engine3_eligibility(case_id: str, request: Request, user=Depends(get_current_user)):
    case = accepted_case(request, case_id, user)
    db = request.app.state.adapters.database
    return {"eligibility": check_engine3_eligibility(case, user, db)}


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
    if body.engine == 2 and not case.get("case_file") and not case.get("canonical_case_file"):
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
    db = request.app.state.adapters.database
    if case["status"] not in {"ADVOCATE_REVIEW", "ENGINE1_DONE", "ENGINE2_DONE"} or case.get("processing_error"):
        raise HTTPException(409, "Complete review and resolve processing errors first.")
    from ..services.legal_visibility import current_case_file
    file = current_case_file(case, db)
    if not file or not file.get("version"):
        file = case.get("canonical_case_file") or case.get("case_file") or {}
    if file.get("input_version", case.get("input_version", 1)) != case.get("input_version", 1):
        raise HTTPException(409, "Review a current Engine 1 Case File before approval.")
    if case.get("engines", {}).get("1", {}).get("status") == "STALE" or case.get("engine1_stale"):
        raise HTTPException(409, "Update the case foundation after corrections before final approval.")
    if not file.get("version"):
        raise HTTPException(409, "Run and review the case foundation before final approval.")

    required = {f"fact:{item['fact_id']}" for item in file.get("facts", []) if not item.get("removed")}
    required |= {f"provision:{item['provision_id']}" for item in file.get("applicable_law", []) if not item.get("removed")}
    approved_items = list(set(case.get("advocate_approved_items", []) + list(required)))

    entry = {"advocate_id": user["id"], "action": "final_approval", "target": "case", "previous": case["status"], "new": "ADVOCATE_APPROVED", "timestamp": utc_now()}
    db.update("cases", case_id, {
        "status": "ADVOCATE_APPROVED",
        "review_status": "REVIEWED_CURRENT",
        "advocate_approved_items": approved_items,
        "advocate_approved_case_file_version": file.get("version"),
        "engine1_stale": False,
        "engine3_eligible": True,
        "advocate_audit": case.get("advocate_audit", []) + [entry],
    })

    # Record review audit milestone
    rev_id = uuid4().hex
    db.create("advocate_case_reviews", {
        "id": rev_id,
        "review_id": rev_id,
        "case_id": case_id,
        "advocate_id": user["id"],
        "review_status": "REVIEWED_CURRENT",
        "reviewed_case_file_version": file.get("version"),
        "engine3_eligible": True,
        "approved_at": entry["timestamp"],
    })
    return {"status": "ADVOCATE_APPROVED", "review_status": "REVIEWED_CURRENT", "case_file_version": file.get("version")}
