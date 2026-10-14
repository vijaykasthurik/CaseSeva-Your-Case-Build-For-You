import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from .dependencies import get_current_user
from ..models.case import utc_now
from ..services.blackboard import write

router = APIRouter(prefix="/api/guest-claims")


class ClaimStart(BaseModel):
    case_id: str


class ClaimConfirm(BaseModel):
    claim_id: str
    code: str = Field(min_length=6, max_length=6)


@router.post("")
def start(body: ClaimStart, request: Request, user=Depends(get_current_user)):
    if user.get("role") != "client": raise HTTPException(403, "Client account required.")
    db = request.app.state.adapters.database
    case = db.get("cases", body.case_id)
    if not case:
        case = next((item for item in db.list("cases") if item.get("public_case_id") == body.case_id.strip().upper()), None)
    guest = db.get("guest_clients", (case or {}).get("guest_client_id", ""))
    email = user.get("email", "").lower()
    if not case or case.get("guest_claimed_at") or not guest or not guest.get("email") or guest["email"] != email:
        raise HTTPException(404, "No unclaimed case matches your account email. Ask the advocate to check the client contact details.")
    recent = [item for item in db.list("guest_claims") if item["user_id"] == user["id"] and datetime.fromisoformat(item["created_at"]) > datetime.now(timezone.utc) - timedelta(hours=1)]
    if len(recent) >= 3: raise HTTPException(429, "Please wait before requesting another code.")
    claim_id, code = uuid4().hex, f"{secrets.randbelow(1000000):06d}"
    email_provider = getattr(request.app.state.adapters, "email_provider", "disabled")
    if email_provider not in {"mock", "ses"} or (email_provider == "mock" and os.getenv("APP_ENV", "development").lower() in {"prod", "production"}):
        raise HTTPException(503, "Secure email verification is not configured. The case remains unclaimed.")
    if email_provider == "ses":
        sender = os.getenv("OTP_FROM_EMAIL", "")
        if not sender: raise HTTPException(503, "Secure email verification is not configured. The case remains unclaimed.")
        try:
            import boto3
            boto3.client("ses", region_name=os.getenv("CASESEVA_AWS_REGION", "ap-southeast-2")).send_email(Source=sender, Destination={"ToAddresses": [email]}, Message={"Subject": {"Data": "CaseSeva case access verification"}, "Body": {"Text": {"Data": f"Your CaseSeva verification code is {code}. It expires in 10 minutes. Do not share it."}}})
        except Exception: raise HTTPException(503, "The verification email could not be sent. Please try later.")
    db.create("guest_claims", {"id": claim_id, "user_id": user["id"], "case_id": case["case_id"], "code_hash": hashlib.sha256((claim_id + code).encode()).hexdigest(), "attempts": 0, "used_at": None, "created_at": utc_now(), "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()})
    response = {"claim_id": claim_id, "message": "Enter the code sent to your account email."}
    if email_provider == "mock": response.update({"development_only": True, "development_code": code, "message": "Development-only code; no email was sent."})
    return response


@router.post("/confirm")
def confirm(body: ClaimConfirm, request: Request, user=Depends(get_current_user)):
    db = request.app.state.adapters.database
    valid = False
    def check(item):
        nonlocal valid
        if item["user_id"] != user["id"] or item.get("used_at") or item["attempts"] >= 5 or datetime.fromisoformat(item["expires_at"]) <= datetime.now(timezone.utc):
            raise HTTPException(403, "This verification attempt is unavailable or expired.")
        valid = hmac.compare_digest(item["code_hash"], hashlib.sha256((body.claim_id + body.code).encode()).hexdigest())
        return {"attempts": item["attempts"] + 1, "used_at": utc_now() if valid else None}
    if not db.get("guest_claims", body.claim_id): raise HTTPException(404, "Verification attempt not found.")
    claim = db.mutate("guest_claims", body.claim_id, check)
    if not valid: raise HTTPException(422, "The verification code is incorrect.")
    case = db.get("cases", claim["case_id"])
    if case.get("guest_claimed_at"): raise HTTPException(409, "This case was already linked.")
    write(db, case["case_id"], {"owner_user_id": user["id"], "guest_claimed_at": utc_now(), "status": "AWAITING_ADVOCATE"}, user["id"], "guest_case_claimed")
    return {"case_id": case["case_id"], "message": "The existing case is linked to your account. Review and grant advocate access to continue sharing."}
