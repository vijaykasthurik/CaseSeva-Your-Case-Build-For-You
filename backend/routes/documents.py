from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from ..models.case import utc_now
from ..services.documents import build_documents
from .dependencies import get_current_user, get_case_or_error, retired_workflow
from ..services.sharing import require_access

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


def serialize(doc: dict[str, Any]) -> dict[str, Any]:
    return {key: doc.get(key) for key in ("id", "case_id", "type", "title", "version", "created_at", "case_file_version", "consistency", "download_url")}


def require_document(request, case, doc, user):
    if user.get("role") != "advocate":
        if doc.get("type") != "client_case_overview":
            raise HTTPException(403, "Professional Legal Draft and internal reports are advocate-only.")
    else:
        require_access(request, case["case_id"], user, "case_file")
        if doc.get("type") != "client_case_overview" and case.get("engine2"):
            require_access(request, case["case_id"], user, "engine2")


def start_engine3(case_id, request, user, regenerate=False):
    from .advocates import accepted_case
    from ..services.jobs import dispatch
    case = accepted_case(request, case_id, user)
    if case.get("engines", {}).get("1", {}).get("status") == "STALE":
        raise HTTPException(409, "Update and review the foundation after new client information first.")
    allowed = {"ADVOCATE_APPROVED", "DOCUMENTS_READY", "DOCUMENTS_BLOCKED"} if regenerate else {"ADVOCATE_APPROVED"}
    if not case.get("case_file", {}).get("version") or case["status"] not in allowed or case.get("advocate_approved_case_file_version") != case.get("case_file", {}).get("version"):
        raise HTTPException(409, "The current Case File must be approved by an advocate first.")
    if case.get("engine2") and case.get("engine2_stale"):
        raise HTTPException(409, "Rerun stale argument analysis before generating documents.")
    if case.get("engine2"):
        require_access(request, case_id, user, "engine2")
    grant = require_access(request, case_id, user, "evidence")
    approved_evidence = {item.split(":", 1)[1] for item in case.get("advocate_approved_items", []) if item.startswith("evidence:")}
    if not approved_evidence.issubset(grant["evidence_ids"]):
        raise HTTPException(403, "The client did not share all evidence selected for the documents.")
    request.app.state.adapters.database.update("cases", case_id, {"status": "GENERATING_DOCUMENTS", "document_generation_stage": "RUNNING", "engine3_advocate_id": user["id"], "engine3_grant_id": grant["id"]})
    try:
        dispatch(request.app, 3, case_id)
    except Exception:
        request.app.state.adapters.database.update("cases", case_id, {"status": "DOCUMENTS_BLOCKED", "processing_error": {"engine": 3, "message": "Document processing job could not be started."}})
        raise HTTPException(503, "Document processing job could not be started.")
    return {"status": "GENERATING_DOCUMENTS"}


def run_generation(request: Request, case: dict[str, Any]) -> list[dict[str, Any]]:
    generated = build_documents(case)
    db = request.app.state.adapters.database
    version = generated["version"]
    stored = []
    for kind in ("report", "draft"):
        content = generated[kind]
        key = f"cases/{case['case_id']}/documents/v{version}/{kind}.html"
        text_key = f"cases/{case['case_id']}/documents/v{version}/{kind}.txt"
        request.app.state.adapters.storage.upload(key, content["html"].encode(), "text/html")
        request.app.state.adapters.storage.upload(text_key, content["text"].encode(), "text/plain")
        item = {
            "id": f"{generated['id']}-{kind}", "case_id": case["case_id"], "type": kind,
            "version": version, "created_at": generated["created_at"], "html": content["html"],
            "text": content["text"], "storage_key": key, "text_storage_key": text_key,
            "consistency": generated["consistency"], "download_url": f"/api/cases/{case['case_id']}/documents/{generated['id']}-{kind}/download",
        }
        db.create("documents", item)
        stored.append(item)
    has_failures = any(item.get("result") == "FAIL" for item in generated["consistency"])
    db.update("cases", case["case_id"], {
        "status": "DOCUMENTS_BLOCKED" if has_failures else "DOCUMENTS_READY",
        "document_version": version,
        "document_consistency": generated["consistency"],
        "document_generation_stage": "COMPLETED",
        "version": case.get("version", 1) + 1,
    })
    return stored


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
def consistency(case_id: str, document_id: str, request: Request, user: dict = Depends(get_current_user)):
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
