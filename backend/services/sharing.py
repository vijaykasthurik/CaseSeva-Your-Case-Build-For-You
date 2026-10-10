from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import uuid4
from fastapi import HTTPException
from ..models.case import utc_now


def active_grant(db, case_id, advocate_id):
    case = db.get("cases", case_id)
    if case and case.get("origin") == "ADVOCATE_WALK_IN" and case.get("assigned_advocate_id") == advocate_id and not case.get("guest_claimed_at"):
        consent = db.get("walkin_consents", case_id)
        if consent and not consent.get("revoked_at"):
            return {**consent, "id": "walkin:" + case_id, "scopes": ["story", "raw_package", "case_file", "engine2", "evidence"], "evidence_ids": [item["evidence_id"] for item in case.get("evidence", [])], "expires_at": None, "permission_type": "WALK_IN_CONSENT"}
    now = datetime.now(timezone.utc)
    for grant in db.list("case_grants"):
        if grant["case_id"] == case_id and grant["advocate_id"] == advocate_id and not grant.get("revoked_at") and datetime.fromisoformat(grant["expires_at"]) > now:
            return grant
    return None


def require_access(request, case_id, user, scope="case_file"):
    if user.get("role") != "advocate" or user.get("verification_status") != "VERIFIED":
        raise HTTPException(403, "A verified advocate account is required.")
    walkin = active_grant(request.app.state.adapters.database, case_id, user["id"])
    if walkin and walkin.get("permission_type") == "WALK_IN_CONSENT":
        return walkin
    token = request.headers.get("X-Case-Access", "")
    if not token:
        raise HTTPException(403, "A scoped case access token is required.")
    digest = hashlib.sha256(token.encode()).hexdigest()
    session = request.app.state.adapters.database.get("case_access_tokens", digest)
    if not session or session["case_id"] != case_id or session["advocate_id"] != user["id"]:
        raise HTTPException(403, "Invalid case access token.")
    grant = request.app.state.adapters.database.get("case_grants", session["grant_id"])
    if not grant or grant.get("revoked_at") or datetime.fromisoformat(grant["expires_at"]) <= datetime.now(timezone.utc):
        raise HTTPException(403, "Case access has expired or been revoked.")
    if scope and scope not in grant["scopes"]:
        raise HTTPException(403, f"The client did not share {scope}.")
    return grant


def issue_token(db, grant):
    token = secrets.token_urlsafe(40)
    digest = hashlib.sha256(token.encode()).hexdigest()
    db.create("case_access_tokens", {"id": digest, "case_id": grant["case_id"], "advocate_id": grant["advocate_id"], "grant_id": grant["id"], "created_at": utc_now()})
    return token


def grant_access(db, case, user, scopes, evidence_ids, hours):
    allowed = {item["evidence_id"] for item in case.get("evidence", [])}
    if not set(evidence_ids).issubset(allowed):
        raise HTTPException(422, "Unknown evidence ID in sharing selection.")
    if not scopes or not set(scopes).issubset({"story", "raw_package", "case_file", "engine2", "evidence"}):
        raise HTTPException(422, "Choose valid sharing scopes.")
    if evidence_ids and "evidence" not in scopes:
        raise HTTPException(422, "Evidence sharing scope is required.")
    grant = {"id": uuid4().hex, "case_id": case["case_id"], "owner_user_id": user["id"], "advocate_id": case["assigned_advocate_id"], "scopes": scopes, "evidence_ids": evidence_ids, "created_at": utc_now(), "expires_at": (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(), "revoked_at": None}
    db.create("case_grants", grant)
    db.create("consent_audit", {"id": uuid4().hex, "action": "GRANT", "actor_id": user["id"], **grant})
    return grant


def shared_case(case, grant):
    keys = ("case_id", "status", "stage", "created_at", "version", "workflow_version", "documents_outdated", "document_version", "advocate_approved_items", "advocate_removed_items", "advocate_review_note", "advocate_document_requests", "stage_statuses", "processing_error", "engine2_stale")
    result = {key: case.get(key) for key in keys if key in case}
    from .overview import public_processing_error, public_evidence
    result["processing_error"] = public_processing_error(case.get("processing_error"))
    # Audit entries can contain previous private argument/evidence values.
    def allowed_entry(entry):
        target = entry.get("target", "")
        if target.startswith("argument:") or target == "engine2": return "engine2" in grant["scopes"]
        if target.startswith("evidence:"): return "evidence" in grant["scopes"] and target.split(":", 1)[1] in grant["evidence_ids"]
        return "case_file" in grant["scopes"]
    result["advocate_audit"] = [entry for entry in case.get("advocate_audit", []) if allowed_entry(entry)]
    if "story" in grant["scopes"]:
        result["client_story"] = case.get("client_story", "")
    if "raw_package" in grant["scopes"]:
        source = case.get("raw_package", {})
        # Combined translations/normalizations have no per-source provenance.
        # Deny them by default, including future nested fields.
        raw = {key: source[key] for key in ("version", "input_version", "origin", "preferred_language", "created_at", "case_stage", "processing_mode") if key in source}
        raw["language"] = {key: source.get("language", {})[key] for key in ("language", "status", "review_required") if key in source.get("language", {})}
        raw["evidence"] = [public_evidence(item) for item in source.get("evidence", []) if "evidence" in grant["scopes"] and item["evidence_id"] in grant["evidence_ids"]]
        if "story" in grant["scopes"]:
            raw["original_story"] = source.get("original_story", "")
            raw["optional_fields"] = source.get("optional_fields", {})
        result["raw_package"] = raw
    if "case_file" in grant["scopes"]:
        result["case_file"] = case.get("case_file", {})
        result["clarification"] = (case.get("clarification_rounds") or [None])[-1]
        result["engines"] = case.get("engines", {})
        result["professional_notes"] = case.get("professional_notes", [])
        result["information_requests"] = case.get("information_requests", [])
        result["filing_update"] = case.get("filing_update")
        result["origin"] = case.get("origin", "CITIZEN_SELF_SERVICE")
        result["public_case_id"] = case.get("public_case_id", case["case_id"])
        for key in ("facts", "timeline", "parties", "legal_issues", "verified_legal_sections", "forum", "limitation", "evidence_issue_mapping"):
            result[key] = case.get(key)
    if "engine2" in grant["scopes"]:
        result["engine2"] = case.get("engine2", {})
    if "evidence" in grant["scopes"]:
        result["evidence"] = [public_evidence(item) for item in case.get("evidence", []) if item["evidence_id"] in grant["evidence_ids"]]
    result["grant"] = grant
    return result
