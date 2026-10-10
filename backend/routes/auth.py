import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, File, UploadFile
from pydantic import BaseModel, Field

from .dependencies import get_current_user

router = APIRouter(prefix="/api/auth")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MOBILE_RE = re.compile(r"^[6-9]\d{9}$")


@router.post("/advocate-verification-documents")
async def verification_document(request: Request, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if user.get("role") != "advocate":
        raise HTTPException(403, "Advocate account required.")
    from pathlib import Path
    from uuid import uuid4
    name = (file.filename or "document").replace("\\", "/").split("/")[-1]
    if Path(name).suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(415, "Upload a PDF or enrolment document image.")
    content = await file.read(10 * 1024 * 1024 + 1)
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Document must be nonempty and at most 10 MB.")
    key = f"verification/{user['id']}/{uuid4().hex}"
    request.app.state.adapters.storage.upload(key, content, file.content_type or "application/octet-stream")
    documents = user.get("verification_documents", []) + [{"filename": name, "storage_key": key, "content_type": file.content_type}]
    request.app.state.adapters.database.update("users", user["id"], {"verification_documents": documents, "verification_status": "VERIFICATION_PENDING"})
    return {"status": "VERIFICATION_PENDING"}


class SignupBody(BaseModel):
    full_name: str = Field(min_length=1)
    email: str
    mobile_number: str
    password: str
    preferred_language: str = Field(min_length=1)
    state: str = Field(min_length=1)
    district_city: str = Field(min_length=1)
    role: str = "client"
    bar_council: str | None = None
    enrolment_number: str | None = None
    enrolment_year: int | None = None
    place_of_practice: str | None = None
    court_region: str | None = None
    practice_domains: list[str] = []
    languages: list[str] = []


class LoginBody(BaseModel):
    email: str
    password: str


class ProfileUpdateBody(BaseModel):
    full_name: str | None = None
    mobile_number: str | None = None
    preferred_language: str | None = None
    state: str | None = None
    district_city: str | None = None


def validate_signup(body: SignupBody) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not EMAIL_RE.match(body.email.strip()):
        errors["email"] = "Enter a valid email address."
    if not MOBILE_RE.match(body.mobile_number.strip()):
        errors["mobile_number"] = "Enter a valid 10-digit Indian mobile number."
    if len(body.password) < 8:
        errors["password"] = "Password must be at least 8 characters."
    if body.role not in {"client", "advocate"}:
        errors["role"] = "Choose a valid account role."
    if body.role == "advocate":
        for name in ("bar_council", "enrolment_number", "place_of_practice", "court_region"):
            if not getattr(body, name):
                errors[name] = "This field is required for advocate accounts."
        if not body.enrolment_year:
            errors["enrolment_year"] = "Enrolment year is required for advocate accounts."
        if not body.practice_domains:
            errors["practice_domains"] = "Select at least one practice domain."
        if not body.languages:
            errors["languages"] = "Select at least one language."
    return errors


def validate_profile(body: ProfileUpdateBody) -> dict[str, str]:
    errors: dict[str, str] = {}
    if body.mobile_number is not None and not MOBILE_RE.match(body.mobile_number.strip()):
        errors["mobile_number"] = "Enter a valid 10-digit Indian mobile number."
    for field in ("full_name", "preferred_language", "state", "district_city"):
        value = getattr(body, field)
        if value is not None and not value.strip():
            errors[field] = "This field cannot be empty."
    return errors


def field_error(errors: dict[str, str]) -> HTTPException:
    return HTTPException(status_code=422, detail={"message": "Please fix the highlighted fields.", "fields": errors})


@router.post("/signup", status_code=201)
def signup(body: SignupBody, request: Request) -> dict[str, Any]:
    errors = validate_signup(body)
    if errors:
        raise field_error(errors)
    profile = body.model_dump(exclude={"password"})
    try:
        return request.app.state.adapters.auth.signup(profile, body.password)
    except ValueError as exc:
        if str(exc) == "User already exists":
            raise HTTPException(status_code=409, detail={"message": "An account with this email already exists.", "fields": {"email": "Email is already registered."}})
        raise HTTPException(status_code=422, detail={"message": str(exc)})


@router.post("/login")
def login(body: LoginBody, request: Request) -> dict[str, Any]:
    if not EMAIL_RE.match(body.email.strip()):
        raise field_error({"email": "Enter a valid email address."})
    try:
        return request.app.state.adapters.auth.login(body.email, body.password)
    except ValueError:
        raise HTTPException(status_code=401, detail={"message": "Invalid email or password."})


@router.post("/logout")
def logout(request: Request, user: dict = Depends(get_current_user)) -> dict[str, str]:
    credentials = request.headers.get("Authorization", "")
    token = credentials.removeprefix("Bearer ").strip()
    request.app.state.adapters.auth.logout(token)
    return {"status": "ok"}


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    return {"user": user}


@router.patch("/me")
def update_me(
    body: ProfileUpdateBody,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    errors = validate_profile(body)
    if errors:
        raise field_error(errors)
    changes = {
        key: value.strip()
        for key, value in body.model_dump(exclude_none=True).items()
    }
    updated = request.app.state.adapters.auth.update_profile(user["id"], changes)
    return {"user": updated}
