"""Routes for Engine 3 Professional Legal Drafting and Document Generation.

Provides advocate-only drafting endpoints, versioned draft persistence,
selective regeneration, conflict resolution, advocate approval, and PDF download.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from ..models.case import utc_now
from ..models.draft import ConflictResolutionStrategy, DraftMode, DraftType
from ..services.documents import build_documents
from ..services.engine3 import (
    approve_advocate_draft,
    edit_advocate_draft,
    generate_advocate_draft,
    get_advocate_draft,
    list_advocate_drafts,
    regenerate_draft_section,
    regenerate_full_draft,
    resolve_section_conflict,
)
from ..services.review_contracts import check_engine3_eligibility, reviewed_engine1_current
from ..services.sharing import require_access
from .dependencies import get_case_or_error, get_current_user, retired_workflow

router = APIRouter(prefix="/api/cases")


def accessible_case(request: Request, case_id: str, user: dict[str, Any]) -> dict[str, Any]:
    case = request.app.state.adapters.database.get("cases", case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.get("owner_user_id") == user.get("id"):
        return case
    if case.get("assigned_advocate_id") == user.get("id") and user.get("role") == "advocate":
        require_access(request, case_id, user, "case_file")
        return case
    raise HTTPException(status_code=403, detail="You do not have access to these documents")


def require_advocate_drafting_access(request: Request, case_id: str, user: dict[str, Any]) -> dict[str, Any]:
    if user.get("role") != "advocate":
        raise HTTPException(status_code=403, detail="Engine 3 is advocate-only. Citizens and administrators cannot initiate drafting.")
    if user.get("verification_status") != "VERIFIED":
        raise HTTPException(status_code=403, detail="Advocate must be verified to operate Engine 3.")

    case = request.app.state.adapters.database.get("cases", case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.get("assigned_advocate_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="This case is not assigned to the authenticated advocate.")

    require_access(request, case_id, user, "case_file")
    return case


def serialize(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        key: doc.get(key)
        for key in ("id", "case_id", "type", "title", "version", "created_at", "case_file_version", "consistency", "download_url")
    }


def require_document(request: Request, case: dict[str, Any], doc: dict[str, Any], user: dict[str, Any]) -> None:
    if user.get("role") != "advocate":
        if doc.get("type") != "client_case_overview":
            raise HTTPException(403, "Professional Legal Draft and internal reports are advocate-only.")
    else:
        require_access(request, case["case_id"], user, "case_file")
        if doc.get("type") != "client_case_overview" and case.get("engine2") and not case.get("engine2_stale"):
            require_access(request, case["case_id"], user, "engine2")


# -------------------------------------------------------------
# Phase 9: New Advocate-Only Drafting Endpoints
# -------------------------------------------------------------

class GenerateDraftBody(BaseModel):
    draft_type: str = DraftType.COMPLAINT_PETITION.value
    draft_mode: str = DraftMode.AUTHORITATIVE.value
    title: Optional[str] = None


class EditDraftBody(BaseModel):
    section_updates: Optional[list[dict[str, Any]]] = None
    title: Optional[str] = None
    professional_notes: Optional[str] = None


class RegenerateSectionBody(BaseModel):
    section_id: str


class ResolveConflictBody(BaseModel):
    section_id: str
    strategy: str = ConflictResolutionStrategy.KEEP_ADVOCATE.value
    custom_paragraphs: Optional[list[str]] = None


@router.post("/{case_id}/drafts/generate")
def create_draft(case_id: str, body: GenerateDraftBody, request: Request, user: dict = Depends(get_current_user)):
    case = require_advocate_drafting_access(request, case_id, user)
    db = request.app.state.adapters.database

    eligibility = check_engine3_eligibility(case, user, db)
    if not eligibility.get("eligible"):
        detail = "; ".join(eligibility.get("reasons", []))
        status_code = 409 if any(k in detail for k in ["stale", "reviewed", "approved", "conflict"]) else 403
        raise HTTPException(status_code=status_code, detail=detail)

    try:
        draft = generate_advocate_draft(
            adapters=request.app.state.adapters,
            case=case,
            user=user,
            draft_type=body.draft_type,
            draft_mode=body.draft_mode,
            title=body.title,
        )
        return {"draft": draft.model_dump()}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{case_id}/drafts")
def list_drafts(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = accessible_case(request, case_id, user)
    db = request.app.state.adapters.database
    drafts = list_advocate_drafts(db, case_id, user)
    return {"drafts": drafts}


@router.get("/{case_id}/drafts/{draft_id}")
def get_draft(case_id: str, draft_id: str, request: Request, version: Optional[int] = None, user: dict = Depends(get_current_user)):
    require_advocate_drafting_access(request, case_id, user)
    db = request.app.state.adapters.database
    draft = get_advocate_draft(db, case_id, draft_id, version=version)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"draft": draft.model_dump()}


@router.post("/{case_id}/drafts/{draft_id}/edit")
def edit_draft(case_id: str, draft_id: str, body: EditDraftBody, request: Request, user: dict = Depends(get_current_user)):
    require_advocate_drafting_access(request, case_id, user)
    db = request.app.state.adapters.database
    try:
        updated = edit_advocate_draft(
            db=db,
            case_id=case_id,
            draft_id=draft_id,
            user=user,
            section_updates=body.section_updates,
            title_update=body.title,
            professional_notes=body.professional_notes,
        )
        return {"draft": updated.model_dump()}
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 422, detail=str(exc))


@router.post("/{case_id}/drafts/{draft_id}/regenerate-section")
def regenerate_section(case_id: str, draft_id: str, body: RegenerateSectionBody, request: Request, user: dict = Depends(get_current_user)):
    require_advocate_drafting_access(request, case_id, user)
    db = request.app.state.adapters.database
    try:
        updated = regenerate_draft_section(
            db=db,
            case_id=case_id,
            draft_id=draft_id,
            user=user,
            section_id=body.section_id,
        )
        return {"draft": updated.model_dump()}
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 422, detail=str(exc))


@router.post("/{case_id}/drafts/{draft_id}/resolve-conflict")
def resolve_conflict(case_id: str, draft_id: str, body: ResolveConflictBody, request: Request, user: dict = Depends(get_current_user)):
    require_advocate_drafting_access(request, case_id, user)
    db = request.app.state.adapters.database
    try:
        updated = resolve_section_conflict(
            db=db,
            case_id=case_id,
            draft_id=draft_id,
            user=user,
            section_id=body.section_id,
            strategy=body.strategy,
            custom_paragraphs=body.custom_paragraphs,
        )
        return {"draft": updated.model_dump()}
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 422, detail=str(exc))


@router.post("/{case_id}/drafts/{draft_id}/regenerate-full")
def regenerate_full(case_id: str, draft_id: str, request: Request, user: dict = Depends(get_current_user)):
    require_advocate_drafting_access(request, case_id, user)
    db = request.app.state.adapters.database
    try:
        updated = regenerate_full_draft(
            db=db,
            case_id=case_id,
            draft_id=draft_id,
            user=user,
        )
        return {"draft": updated.model_dump()}
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 422, detail=str(exc))


@router.post("/{case_id}/drafts/{draft_id}/approve")
def approve_draft(case_id: str, draft_id: str, request: Request, user: dict = Depends(get_current_user)):
    if user.get("role") != "advocate":
        raise HTTPException(status_code=403, detail="AI or Administrator cannot approve a professional legal draft. Advocate only.")
    case = require_advocate_drafting_access(request, case_id, user)
    db = request.app.state.adapters.database
    storage = request.app.state.adapters.storage
    try:
        approved = approve_advocate_draft(
            db=db,
            storage=storage,
            case_id=case_id,
            draft_id=draft_id,
            user=user,
        )
        return {"draft": approved.model_dump()}
    except ValueError as exc:
        raise HTTPException(status_code=409 if "stale" in str(exc).lower() else 422, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{case_id}/drafts/{draft_id}/pdf")
def download_draft_pdf(case_id: str, draft_id: str, request: Request, version: Optional[int] = None, user: dict = Depends(get_current_user)):
    require_advocate_drafting_access(request, case_id, user)
    db = request.app.state.adapters.database
    draft = get_advocate_draft(db, case_id, draft_id, version=version)
    if not draft or not draft.pdf_artifact:
        raise HTTPException(status_code=404, detail="Approved PDF not found for this draft.")
    storage = request.app.state.adapters.storage
    pdf_bytes = storage.download(draft.pdf_artifact.storage_key)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{draft.pdf_artifact.filename}"'},
    )


# -------------------------------------------------------------
# Legacy Compatibility Endpoints
# -------------------------------------------------------------

def start_engine3(case_id: str, request: Request, user: dict[str, Any], regenerate: bool = False) -> dict[str, str]:
    from .advocates import accepted_case
    from ..services.jobs import dispatch
    case = accepted_case(request, case_id, user)
    if not reviewed_engine1_current(case, request.app.state.adapters.database):
        raise HTTPException(409, "The current Engine 1 Case File must be reviewed by an advocate first.")
    allowed = {"ADVOCATE_APPROVED", "DOCUMENTS_READY", "DOCUMENTS_BLOCKED"} if regenerate else {"ADVOCATE_APPROVED"}
    if not case.get("case_file", {}).get("version") or case["status"] not in allowed or case.get("advocate_approved_case_file_version") != case.get("case_file", {}).get("version"):
        raise HTTPException(409, "The current Case File must be approved by an advocate first.")
    if case.get("engine2") and not case.get("engine2_stale"):
        require_access(request, case_id, user, "engine2")
    grant = require_access(request, case_id, user, "evidence")
    approved_evidence = {item.split(":", 1)[1] for item in case.get("advocate_approved_items", []) if item.startswith("evidence:")}
    if not approved_evidence.issubset(grant["evidence_ids"]):
        raise HTTPException(403, "The client did not share all evidence selected for the documents.")
    request.app.state.adapters.database.update("cases", case_id, {
        "status": "GENERATING_DOCUMENTS",
        "document_generation_stage": "RUNNING",
        "engine3_advocate_id": user["id"],
        "engine3_grant_id": grant["id"],
    })
    try:
        dispatch(request.app, 3, case_id)
    except Exception:
        request.app.state.adapters.database.update("cases", case_id, {
            "status": "DOCUMENTS_BLOCKED",
            "processing_error": {"engine": 3, "message": "Document processing job could not be started."},
        })
        raise HTTPException(503, "Document processing job could not be started.")
    return {"status": "GENERATING_DOCUMENTS"}


@router.post("/{case_id}/documents/generate")
def generate(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    return start_engine3(case_id, request, user)


@router.post("/{case_id}/documents/regenerate")
def regenerate(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    return start_engine3(case_id, request, user, regenerate=True)


@router.get("/{case_id}/documents")
def list_documents(case_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = accessible_case(request, case_id, user)
    docs = []
    for doc in request.app.state.adapters.database.list("documents"):
        if doc.get("case_id") != case_id:
            continue
        if user.get("role") != "advocate" and doc.get("type") != "client_case_overview":
            continue
        require_document(request, case, doc, user)
        docs.append({**serialize(doc), "outdated": case.get("documents_outdated", False) or doc.get("case_file_version") != case.get("case_file", {}).get("version")})
    return {"documents": docs}


@router.get("/{case_id}/documents/{document_id}")
def get_document(case_id: str, document_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = accessible_case(request, case_id, user)
    doc = request.app.state.adapters.database.get("documents", document_id)
    if not doc or doc.get("case_id") != case_id:
        raise HTTPException(status_code=404, detail="Document not found")
    require_document(request, case, doc, user)
    return {"document": {key: doc.get(key) for key in ("id", "case_id", "type", "version", "created_at", "html", "text", "consistency")}}


@router.get("/{case_id}/documents/{document_id}/download")
def download_document(case_id: str, document_id: str, request: Request, format: str = "html", user: dict = Depends(get_current_user)):
    case = accessible_case(request, case_id, user)
    doc = request.app.state.adapters.database.get("documents", document_id)
    if not doc or doc.get("case_id") != case_id:
        raise HTTPException(status_code=404, detail="Document not found")
    require_document(request, case, doc, user)
    from ..services.exports import export
    try:
        content, media_type = export(doc["html"], format)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, "The document could not be exported. Please retry later.")
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{doc["type"]}-v{doc["version"]}.{format}"'})


@router.get("/{case_id}/documents/{document_id}/consistency")
def consistency_route(case_id: str, document_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = accessible_case(request, case_id, user)
    doc = request.app.state.adapters.database.get("documents", document_id)
    if not doc or doc.get("case_id") != case_id:
        raise HTTPException(status_code=404, detail="Document not found")
    require_document(request, case, doc, user)
    return {"findings": doc.get("consistency", [])}


class OverrideBody(BaseModel):
    reason: str


@router.post("/{case_id}/documents/{document_id}/override-consistency", dependencies=[Depends(retired_workflow)])
def override_consistency(case_id: str, document_id: str, body: OverrideBody, request: Request, user: dict = Depends(get_current_user)):
    if user.get("role") != "advocate":
        raise HTTPException(status_code=403, detail="Advocate access required")
    case = accessible_case(request, case_id, user)
    if case.get("workflow_version") == 2:
        raise HTTPException(409, "Correct failed consistency checks and regenerate a new document version.")
    doc = request.app.state.adapters.database.get("documents", document_id)
    if not doc or doc.get("case_id") != case_id:
        raise HTTPException(status_code=404, detail="Document not found")
    if not body.reason.strip():
        raise HTTPException(status_code=422, detail="Override reason is required")
    override = {"advocate_id": user["id"], "reason": body.reason.strip(), "at": utc_now()}
    updated = request.app.state.adapters.database.update("documents", document_id, {"consistency_override": override})
    documents = [item for item in request.app.state.adapters.database.list("documents") if item.get("case_id") == case_id]
    all_clear = all(
        not any(finding.get("result") == "FAIL" for finding in item.get("consistency", []))
        or item.get("consistency_override")
        or item["id"] == document_id
        for item in documents
    )
    request.app.state.adapters.database.update("cases", case_id, {"document_consistency_override": override, "status": "DOCUMENTS_READY" if all_clear else case.get("status")})
    return {"document": serialize(updated), "override": override}
