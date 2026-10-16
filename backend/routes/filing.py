"""Routes for Phase 10 — Filing Preparation & Submission Safety.

Provides advocate-controlled filing package preparation, deterministic manifest,
annexure/evidence index, pre-submission checklist, and export bundle (ZIP).

Strictly enforces:
- Assigned verified advocate only
- Active citizen consent
- Approved draft and Engine 1 version binding
- Fail-closed legal foundation safety
- ABSOLUTELY NO AUTOMATED EXTERNAL FILING, PAYMENT, OR COURT-PORTAL SUBMISSION.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from ..services.filing import (
    check_filing_eligibility,
    export_filing_bundle,
    get_filing_package,
    list_filing_packages,
    prepare_filing_package,
)
from ..services.sharing import require_access
from .dependencies import get_current_user

router = APIRouter(prefix="/api/cases")


class PrepareFilingPackageBody(BaseModel):
    intended_forum_override: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


def require_advocate_filing_access(request: Request, case_id: str, user: dict[str, Any]) -> dict[str, Any]:
    if user.get("role") != "advocate":
        raise HTTPException(
            status_code=403,
            detail="Filing package preparation is advocate-only. Citizens and administrators cannot prepare filing packages.",
        )
    if user.get("verification_status") != "VERIFIED":
        raise HTTPException(status_code=403, detail="Advocate must be verified to prepare a filing package.")

    db = request.app.state.adapters.database
    case = db.get("cases", case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if case.get("assigned_advocate_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="This case is not assigned to the authenticated advocate.")

    require_access(request, case_id, user, "case_file")
    return case


@router.get("/{case_id}/filing-eligibility")
def get_eligibility(case_id: str, request: Request, user=Depends(get_current_user)):
    """Checks whether the case is currently eligible to prepare a filing package."""
    case = require_advocate_filing_access(request, case_id, user)
    db = request.app.state.adapters.database
    res = check_filing_eligibility(case, user, db)
    # Remove raw draft object from response for JSON serialization
    res_copy = dict(res)
    res_copy.pop("draft", None)
    return res_copy


@router.post("/{case_id}/filing-packages/prepare")
def prepare_package(case_id: str, body: PrepareFilingPackageBody, request: Request, user=Depends(get_current_user)):
    """Prepares an immutable, advocate-controlled filing package."""
    case = require_advocate_filing_access(request, case_id, user)
    db = request.app.state.adapters.database
    storage = request.app.state.adapters.storage

    try:
        package = prepare_filing_package(
            db=db,
            storage=storage,
            case_id=case_id,
            user=user,
            options=body.model_dump(),
        )
        return package.model_dump()
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))


@router.get("/{case_id}/filing-packages")
def list_packages(case_id: str, request: Request, user=Depends(get_current_user)):
    """Lists filing packages for a case. Assigned advocate sees complete packages; citizen sees safe status summary."""
    db = request.app.state.adapters.database
    case = db.get("cases", case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    is_assigned_advocate = (user.get("role") == "advocate" and case.get("assigned_advocate_id") == user.get("id"))
    is_owner_citizen = (user.get("role") == "citizen" and case.get("owner_user_id") == user.get("id"))

    if not is_assigned_advocate and not is_owner_citizen:
        raise HTTPException(status_code=403, detail="Access denied.")

    try:
        return list_filing_packages(db, case_id, user)
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))


@router.get("/{case_id}/filing-packages/{package_id}")
def get_package(case_id: str, package_id: str, request: Request, user=Depends(get_current_user)):
    """Retrieves a filing package by ID."""
    db = request.app.state.adapters.database
    try:
        return get_filing_package(db, case_id, package_id, user)
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))


@router.get("/{case_id}/filing-packages/{package_id}/export")
def download_export_bundle(case_id: str, package_id: str, request: Request, user=Depends(get_current_user)):
    """Downloads the immutable filing preparation bundle ZIP. Advocate-only."""
    require_advocate_filing_access(request, case_id, user)
    db = request.app.state.adapters.database
    storage = request.app.state.adapters.storage

    try:
        zip_bytes, filename = export_filing_bundle(db, storage, case_id, package_id, user)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))


@router.get("/{case_id}/filing-packages/{package_id}/manifest")
def get_manifest(case_id: str, package_id: str, request: Request, user=Depends(get_current_user)):
    """Retrieves the document manifest for a package. Advocate-only."""
    require_advocate_filing_access(request, case_id, user)
    db = request.app.state.adapters.database
    try:
        pkg = get_filing_package(db, case_id, package_id, user)
        return {"manifest": pkg.get("document_manifest", []), "package_digest": pkg.get("package_digest")}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{case_id}/filing-packages/{package_id}/checklist")
def get_checklist(case_id: str, package_id: str, request: Request, user=Depends(get_current_user)):
    """Retrieves the pre-submission checklist for a package. Advocate-only."""
    require_advocate_filing_access(request, case_id, user)
    db = request.app.state.adapters.database
    try:
        pkg = get_filing_package(db, case_id, package_id, user)
        return {"checklist": pkg.get("pre_submission_checklist", []), "status": pkg.get("status")}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
