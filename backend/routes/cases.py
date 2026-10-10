import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from typing import Literal
from starlette.concurrency import run_in_threadpool
from ..services.blackboard import initial_board, write, engine_state
from ..services.input_layer import extract_content

from ..models.case import utc_now
from ..services.overview import client_case, public_evidence
from .dependencies import get_case_or_error, get_current_user

router = APIRouter(prefix="/api/cases")
MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".doc", ".docx",
    ".txt", ".rtf", ".xls", ".xlsx", ".csv", ".mp4", ".mov", ".avi", ".webm",
    ".mp3", ".wav", ".m4a", ".ogg", ".flac",
}
STAGES = {"NEW_CONSULTATION", "COMPLAINT_FIR", "EXISTING_OLD_CASE"}


class CaseUpdateBody(BaseModel):
    stage: str | None = None
    stage_details: dict[str, Any] | None = None
    client_story: str | None = None


class EvidenceUpdateBody(BaseModel):
    description: str = ""


class CreateBody(BaseModel):
    origin: Literal["CITIZEN_SELF_SERVICE", "CITIZEN_DIRECT_ADVOCATE", "ADVOCATE_WALK_IN"] = "CITIZEN_SELF_SERVICE"
    client_name: str = ""
    client_email: str = ""
    client_mobile: str = ""
    preferred_language: str = "English"
    consent: bool = False


class SubmitBody(BaseModel):
    path: Literal["understand", "legal_help"] = "understand"


def field_error(fields: dict[str, str]) -> HTTPException:
    return HTTPException(status_code=422, detail={"message": "Please complete the highlighted fields.", "fields": fields})


def validate_stage(stage: str | None, details: dict[str, Any] | None) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not stage:
        errors["stage"] = "Choose a case stage."
        return errors
    if stage not in STAGES:
        errors["stage"] = "Choose a valid case stage."
        return errors
    details = details or {}
    required = []  # Stage details are optional; unknown values must not be invented.
    for key in required:
        value = details.get(key)
        if value is None or not str(value).strip():
            errors[key] = "This field is required for the selected stage."
    return errors


def validate_complete(case: dict[str, Any]) -> dict[str, str]:
    errors = validate_stage(case.get("stage"), case.get("stage_details"))
    media = any(item.get("content_type", "").startswith(("audio/", "video/")) or item.get("filename", "").lower().endswith((".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".mov", ".avi", ".webm")) for item in case.get("evidence", []))
    if not case.get("client_story", "").strip() and not media:
        errors["client_story"] = "Tell your story by typing, recording, or uploading audio/video narration. Supporting documents alone are not a story."
    if case.get("pending_uploads"):
        errors["evidence"] = "Wait for evidence uploads to finish before submitting."
    return errors


def next_evidence_id(evidence: list[dict[str, Any]]) -> str:
    numbers = [int(match.group(1)) for item in evidence if (match := re.fullmatch(r"E(\d+)", item["evidence_id"]))]
    return f"E{(max(numbers) + 1 if numbers else 1):03d}"


def get_owned_case(request: Request, case_id: str, user: dict) -> dict:
    return get_case_or_error(request, case_id, user)


@router.post("")
def create_case(request: Request, body: CreateBody | None = None, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    body = body or CreateBody()
    if user.get("role") == "advocate":
        if user.get("verification_status") != "VERIFIED":
            raise HTTPException(403, "Credential verification is required before creating a professional case.")
        if body.origin != "ADVOCATE_WALK_IN" or not body.consent or not body.client_name.strip():
            raise HTTPException(422, "Provide a client name and record consent for this walk-in case.")
    elif user.get("role") != "client" or body.origin == "ADVOCATE_WALK_IN":
        raise HTTPException(403, "Only a verified advocate can create a walk-in case.")
    case = {
        "id": uuid4().hex,
        "case_id": uuid4().hex,
        "owner_user_id": user["id"],
        "status": "DRAFT",
        "created_at": utc_now(),
        "stage": None,
        "stage_details": {},
        "client_story": "",
        "evidence": [],
        "facts": [],
        "timeline": [],
        "legal_issues": [],
        "legal_sections": [],
        "arguments": {},
        "advocate_id": None,
        "stage_statuses": {},
        "version": 1,
        "next_evidence_number": 1,
        "workflow_version": 2,
    }
    case["id"] = case["case_id"]
    case.update(initial_board(case["case_id"], body.origin, user["id"], body.preferred_language if body.origin == "ADVOCATE_WALK_IN" else user.get("preferred_language", "English")))
    if body.origin == "ADVOCATE_WALK_IN":
        guest_id = uuid4().hex
        request.app.state.adapters.database.create("guest_clients", {"id": guest_id, "name": body.client_name.strip(), "email": body.client_email.strip().lower(), "mobile": body.client_mobile.strip(), "preferred_language": body.preferred_language, "created_by": user["id"], "created_at": utc_now()})
        case.update({"owner_user_id": guest_id, "guest_client_id": guest_id, "created_by_advocate_id": user["id"], "assigned_advocate_id": user["id"]})
        request.app.state.adapters.database.create("walkin_consents", {"id": case["case_id"], "case_id": case["case_id"], "advocate_id": user["id"], "client_id": guest_id, "type": "ADVOCATE_DECLARATION", "recorded_by": user["id"], "created_at": utc_now(), "revoked_at": None})
    request.app.state.adapters.database.create("cases", case)
    return {"case": case}


@router.get("")
def list_cases(request: Request, user: dict = Depends(get_current_user)) -> dict[str, list[dict[str, Any]]]:
    cases = [
        {
            "case_id": case["case_id"],
            "status": case["status"],
            "created_at": case["created_at"],
            "stage": case.get("stage"),
            "title": (case.get("client_story", "").strip() or "Untitled case")[:80],
            "preview": case.get("client_story", "").strip()[:140],
        }
        for case in request.app.state.adapters.database.list("cases")
        if case["owner_user_id"] == user["id"]
    ]
    cases.sort(key=lambda item: item["created_at"], reverse=True)
    return {"cases": cases}


@router.get("/{case_id}")
def get_case(case_id: str, request: Request, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    return {"case": client_case(get_owned_case(request, case_id, user))}


@router.patch("/{case_id}")
def update_case(case_id: str, body: CaseUpdateBody, request: Request, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    case = get_owned_case(request, case_id, user)
    if case["status"] != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft cases can be edited")
    changes = body.model_dump(exclude_none=True)
    merged_stage = changes.get("stage", case.get("stage"))
    merged_details = changes.get("stage_details", case.get("stage_details", {}))
    if "stage" in changes and changes["stage"] != case.get("stage"):
        merged_details = changes.get("stage_details", {})
    errors = validate_stage(merged_stage, merged_details)
    if errors:
        raise field_error(errors)
    changes["stage"] = merged_stage
    changes["stage_details"] = merged_details
    changes["version"] = case.get("version", 1) + 1
    changes["input_version"] = case.get("input_version", 1) + 1
    updated = write(request.app.state.adapters.database, case_id, changes, user["id"], "intake_updated")
    return {"case": client_case(updated)}


@router.post("/{case_id}/submit")
def submit_case(case_id: str, request: Request, body: SubmitBody | None = None, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    body = body or SubmitBody()
    case = get_owned_case(request, case_id, user)
    if case["status"] != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft cases can be submitted")
    errors = validate_complete(case)
    if errors:
        raise field_error(errors)
    state = "SUBMITTED" if case.get("workflow_version") == 2 else "READY_FOR_ANALYSIS"
    origin = case.get("origin", "CITIZEN_SELF_SERVICE")
    if body.path == "legal_help" and origin != "ADVOCATE_WALK_IN":
        origin = "CITIZEN_DIRECT_ADVOCATE"
    updated = write(request.app.state.adapters.database, case_id, {"status": state, "origin": origin, "journey_stage": "SUBMITTED", "version": case.get("version", 1) + 1}, user["id"], "intake_submitted")
    if case.get("workflow_version") == 2:
        from ..services.jobs import dispatch
        try:
            if origin == "ADVOCATE_WALK_IN":
                dispatch(request.app, 0, case_id, understand=True)
            elif body.path == "legal_help":
                dispatch(request.app, 0, case_id)
            else:
                dispatch(request.app, 1, case_id)
        except Exception:
            updated = request.app.state.adapters.database.update("cases", case_id, {"status": "REVIEW_REQUIRED", "processing_error": {"stage": "DISPATCH", "message": "Could not start the processing job. Retry is required."}})
    return {"case": client_case(updated)}


@router.delete("/{case_id}")
def delete_case(case_id: str, request: Request, user: dict = Depends(get_current_user)) -> dict[str, str]:
    case = get_owned_case(request, case_id, user)
    if case["status"] != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft cases can be deleted")
    for item in case.get("evidence", []):
        request.app.state.adapters.storage.delete(item["storage_key"])
    request.app.state.adapters.database.delete("cases", case_id)
    return {"status": "deleted"}


@router.post("/{case_id}/evidence")
async def upload_evidence(
    case_id: str,
    request: Request,
    file: UploadFile = File(...),
    description: str = Form(""),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    case = get_owned_case(request, case_id, user)
    if case["status"] not in {"DRAFT", "AWAITING_PREVIEW_1", "AWAITING_CLIENT_INFO", "NEEDS_DOCUMENT", "REVIEW_REQUIRED", "LEGAL_CORPUS_NOT_READY"}:
        raise HTTPException(status_code=409, detail="Evidence can only be added during draft or Preview 1")
    filename = (file.filename or "upload").replace("\\", "/").split("/")[-1]
    filename = re.sub(r'[\x00-\x1f<>:"|?*]', "_", filename)
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content = await file.read(MAX_FILE_SIZE + 1)
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported file type. Upload an image, PDF, document, or video.")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File is too large. Maximum size is 10 MB.")
    if not content:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    db = request.app.state.adapters.database
    def reserve(current):
        if current["status"] not in {"DRAFT", "AWAITING_PREVIEW_1", "AWAITING_CLIENT_INFO", "NEEDS_DOCUMENT", "REVIEW_REQUIRED", "LEGAL_CORPUS_NOT_READY"}:
            raise HTTPException(409, "The case state changed before upload; retry after processing.")
        number = max(current.get("next_evidence_number", 1), int(next_evidence_id(current.get("evidence", []))[1:]))
        return {"next_evidence_number": number + 1, "pending_uploads": current.get("pending_uploads", 0) + 1}
    reservation = db.mutate("cases", case_id, reserve)
    sequence = reservation["next_evidence_number"] - 1
    evidence_id = f"E{sequence:03d}"
    storage_key = f"cases/{case_id}/{evidence_id}-{filename}"
    try:
        url = request.app.state.adapters.storage.upload(storage_key, content, file.content_type or "application/octet-stream")
    except Exception:
        db.mutate("cases", case_id, lambda current: {"pending_uploads": max(0, current.get("pending_uploads", 1) - 1)})
        raise HTTPException(503, "Evidence storage failed. Please retry.")
    item = {
        "evidence_id": evidence_id,
        "filename": filename,
        "content_type": file.content_type or "application/octet-stream",
        "size": len(content),
        "storage_key": storage_key,
        "url": url,
        "description": description.strip(),
        "uploaded_at": utc_now(),
        "uploaded_by": user["id"],
        "source_type": "ADVOCATE_UPLOAD" if user.get("role") == "advocate" else "CLIENT_UPLOAD",
        "extraction": await run_in_threadpool(extract_content, content, filename, file.content_type or ""),
    }
    updated = db.mutate("cases", case_id, lambda current: {"evidence": current.get("evidence", []) + [item], "pending_uploads": max(0, current.get("pending_uploads", 1) - 1), "version": current.get("version", 1) + 1, "input_version": current.get("input_version", 1) + 1, "engine2_stale": bool(current.get("engine2")), "documents_outdated": bool(current.get("document_version"))})
    if case.get("case_file"):
        engine_state(db, case_id, 1, "STALE", reason="New uploaded information")
    return {"evidence": public_evidence(item), "case": client_case(updated)}


@router.get("/{case_id}/evidence/{evidence_id}")
def download_evidence(case_id: str, evidence_id: str, request: Request, user: dict = Depends(get_current_user)):
    case = get_owned_case(request, case_id, user)
    item = next((entry for entry in case.get("evidence", []) if entry["evidence_id"] == evidence_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    from fastapi.responses import Response
    return Response(
        content=request.app.state.adapters.storage.download(item["storage_key"]),
        media_type=item["content_type"],
        headers={"Content-Disposition": f'inline; filename="{item["filename"]}"'},
    )


@router.delete("/{case_id}/evidence/{evidence_id}")
def delete_evidence(case_id: str, evidence_id: str, request: Request, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    case = get_owned_case(request, case_id, user)
    if case["status"] != "DRAFT":
        raise HTTPException(status_code=409, detail="Evidence can only be deleted from draft cases")
    item = next((entry for entry in case.get("evidence", []) if entry["evidence_id"] == evidence_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    request.app.state.adapters.storage.delete(item["storage_key"])
    remaining = [entry for entry in case.get("evidence", []) if entry["evidence_id"] != evidence_id]
    updated = request.app.state.adapters.database.update("cases", case_id, {"evidence": remaining, "version": case.get("version", 1) + 1})
    return {"case": client_case(updated)}


@router.patch("/{case_id}/evidence/{evidence_id}")
def update_evidence(
    case_id: str,
    evidence_id: str,
    body: EvidenceUpdateBody,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    case = get_owned_case(request, case_id, user)
    if case["status"] != "DRAFT":
        raise HTTPException(status_code=409, detail="Evidence can only be edited in draft cases")
    updated_entry = None
    evidence = []
    for entry in case.get("evidence", []):
        if entry["evidence_id"] == evidence_id:
            updated_entry = {**entry, "description": body.description.strip()}
            evidence.append(updated_entry)
        else:
            evidence.append(entry)
    if updated_entry is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    updated = request.app.state.adapters.database.update("cases", case_id, {"evidence": evidence, "version": case.get("version", 1) + 1})
    return {"evidence": public_evidence(updated_entry), "case": client_case(updated)}
