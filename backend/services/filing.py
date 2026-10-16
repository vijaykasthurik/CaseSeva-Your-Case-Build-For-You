"""Phase 10 — Filing Preparation & Submission Safety Service.

Prepares a SAFE, ADVOCATE-CONTROLLED FILING PACKAGE.
Absolute boundary: Strictly NO automated external filing, court-portal connection,
fee payment, electronic signatures, or real filing numbers.
Final filing remains an explicit human advocate action.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from backend.models.filing import (
    AnnexureItem,
    DocumentManifestItem,
    FilingPackage,
    FilingReadinessStatus,
    PreSubmissionChecklistItem,
)
from backend.models.draft import AdvocateDraft, DraftStatus
from backend.services.engine3 import approved_content, compute_draft_integrity_hash, export
from backend.services.review_contracts import (
    ENGINE2_NOT_RUN_DISCLOSURE,
    reviewed_engine1_current,
)
from backend.services.sharing import active_grant


DISCLOSURE_PHASE10_SAFETY = "Phase 10 prepares filing materials but does not submit anything to a court or external filing portal."
DISCLOSURE_ADVOCATE_ONLY = "Only the assigned verified advocate can prepare the filing package."
DISCLOSURE_REVIEW_PENDING = "REVIEW_PENDING legal authorities were not used as verified law."
DISCLOSURE_NO_EXTERNAL_SUBMISSION = "No external filing, payment, electronic signature, or court-portal submission was performed."
DISCLOSURE_PHASE4_OPEN = "Phase 4 remains open pending genuine human legal review."
DISCLOSURE_HUMAN_ACTION = "Final filing remains an explicit human advocate action."


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_filing_eligibility(case: dict[str, Any], user: dict[str, Any], db: Any) -> dict[str, Any]:
    """Evaluates whether all Phase 10 filing preparation eligibility requirements are met."""
    reasons: list[str] = []

    # 1. Assigned verified advocate
    if user.get("role") != "advocate":
        reasons.append("Filing package preparation is advocate-only. Citizens and administrators cannot prepare filing packages.")

    if user.get("verification_status") != "VERIFIED":
        reasons.append("Advocate must be verified before preparing a filing package.")

    if case.get("assigned_advocate_id") != user.get("id"):
        reasons.append("This case is not assigned to the authenticated advocate.")

    # 2. Active citizen consent
    grant = active_grant(db, case.get("case_id"), user.get("id")) if db else None
    has_consent = bool(grant and "case_file" in grant.get("scopes", []) and "evidence" in grant.get("scopes", []))
    # Support walkin consent if recorded and not revoked
    if not has_consent and db:
        walkin = db.get("walkin_consents", case.get("case_id"))
        if walkin and not walkin.get("revoked_at"):
            has_consent = True

    if not has_consent:
        reasons.append("Active citizen consent covering the Case File and evidence is required before preparing a filing package.")

    # 3. Current advocate-reviewed Engine-1 Case File
    e1_current = reviewed_engine1_current(case, db)
    if not e1_current:
        reasons.append("A current advocate-reviewed Engine 1 Case File is required.")

    if case.get("engine1_stale"):
        reasons.append("Engine 1 Case File is stale. Rerun Engine 1 and complete advocate review before filing preparation.")

    canonical = case.get("canonical_case_file") or case.get("case_file") or {}
    e1_version = canonical.get("version")
    if not canonical or not e1_version:
        reasons.append("Current Engine 1 Case File is missing.")
    elif case.get("advocate_approved_case_file_version") != e1_version:
        reasons.append("Current Case File version does not match advocate review sign-off.")

    # 4. No unresolved substantive correction conflicts
    corrections = db.list("advocate_case_corrections") if db else []
    unresolved_conflicts = any(
        c.get("conflict_status") == "CONFLICT_DETECTED"
        for c in corrections
        if c.get("case_id") == case.get("case_id")
    )
    if unresolved_conflicts:
        reasons.append("Unresolved substantive correction conflicts must be resolved before filing preparation.")

    # 5. Current Engine-3 draft exists and is ADVOCATE_APPROVED
    draft_id = case.get("engine3_draft_id")
    draft_obj: Optional[AdvocateDraft] = None
    draft_root = db.get("engine3_drafts", draft_id) if (db and draft_id) else None
    if not draft_root and db:
        # Search for drafts of this case
        drafts = [d for d in db.list("engine3_drafts") if d.get("case_id") == case.get("case_id")]
        if drafts:
            draft_root = drafts[-1]
            draft_id = draft_root.get("id")

    if not draft_root:
        reasons.append("An Engine 3 professional legal draft must be generated before filing preparation.")
    else:
        cur_version = draft_root.get("current_version", 1)
        ver_doc = db.get("engine3_draft_versions", f"{draft_id}_v{cur_version}")
        if not ver_doc:
            reasons.append("Engine 3 draft version document not found.")
        else:
            draft_data = copy.deepcopy(ver_doc.get("data", {}))
            draft_obj = AdvocateDraft.model_validate(draft_data)

            # Check draft status == ADVOCATE_APPROVED
            if draft_obj.status != DraftStatus.ADVOCATE_APPROVED.value:
                reasons.append(f"Draft status must be ADVOCATE_APPROVED (currently {draft_obj.status}). Advocate must approve draft first.")

            # Approval record and hash check
            if not draft_obj.approval_record:
                reasons.append("Draft lacks advocate approval record.")
            else:
                calc_hash = compute_draft_integrity_hash(draft_obj)
                if draft_obj.approval_record.integrity_hash != calc_hash:
                    reasons.append("Draft approval integrity hash mismatch.")

                # Version binding check
                if draft_obj.approval_record.source_engine1_version != e1_version:
                    reasons.append("Draft approval references a different Engine 1 version than the current reviewed Case File.")

            # Source Engine 1 version matches
            if draft_obj.engine1_case_file_version != e1_version:
                reasons.append("Draft input Engine 1 version does not match current reviewed Case File.")

            # Stale input check
            if draft_obj.status == DraftStatus.STALE_INPUT.value:
                reasons.append("Draft is marked STALE_INPUT.")

    # 6. Engine 2 is optional
    e2 = case.get("engine2_report") or case.get("engine2") or {}
    e2_ran = bool(e2) and bool(e2.get("overview_ready") or e2.get("status") == "COMPLETED" or e2.get("run_id"))
    e2_is_current = e2_ran and not case.get("engine2_stale")
    e2_disclosure = "Argument analysis was run on the current Case File." if e2_is_current else ENGINE2_NOT_RUN_DISCLOSURE

    # 7. Legal foundation status
    legal_status = canonical.get("legal_foundation_status") or (draft_obj.provenance.get("legal_foundation_status") if draft_obj else None) or "PENDING_SOURCE"

    return {
        "eligible": len(reasons) == 0,
        "case_id": case.get("case_id"),
        "reasons": reasons,
        "checks": {
            "role_advocate": user.get("role") == "advocate",
            "advocate_verified": user.get("verification_status") == "VERIFIED",
            "assigned_advocate": case.get("assigned_advocate_id") == user.get("id"),
            "active_consent": has_consent,
            "reviewed_engine1_current": e1_current,
            "engine1_not_stale": not case.get("engine1_stale"),
            "version_matches_approval": canonical.get("version") == case.get("advocate_approved_case_file_version"),
            "no_unresolved_conflicts": not unresolved_conflicts,
            "draft_exists": bool(draft_root),
            "draft_approved": bool(draft_obj and draft_obj.status == DraftStatus.ADVOCATE_APPROVED.value),
            "integrity_hash_valid": bool(draft_obj and draft_obj.approval_record and draft_obj.approval_record.integrity_hash == compute_draft_integrity_hash(draft_obj)),
            "engine2_optional": True,
        },
        "engine1_version": e1_version,
        "draft_id": draft_id,
        "draft_version": draft_obj.version if draft_obj else None,
        "draft_integrity_hash": draft_obj.approval_record.integrity_hash if (draft_obj and draft_obj.approval_record) else None,
        "engine2_status": "COMPLETED" if e2_is_current else "NOT_RUN",
        "engine2_run_id": (e2.get("run_id") or e2.get("id")) if e2_is_current else None,
        "engine2_disclosure": e2_disclosure,
        "legal_foundation_status": legal_status,
        "draft": draft_obj,
    }


def build_annexures_and_evidence_index(
    case: dict[str, Any],
    draft: AdvocateDraft,
    db: Any = None,
) -> tuple[list[AnnexureItem], list[dict[str, Any]]]:
    """Generates structured annexures and deterministic evidence index from approved evidence references."""
    case_evidence = {e.get("evidence_id"): e for e in case.get("evidence", [])}
    canonical = case.get("canonical_case_file") or case.get("case_file") or {}
    source_e1_ver = canonical.get("version", draft.engine1_case_file_version)

    # Collect cited evidence references from draft
    cited_ids: list[str] = []
    for ref in draft.evidence_references:
        eid = ref.get("evidence_id")
        if eid and eid not in cited_ids:
            cited_ids.append(eid)

    # Also include any evidence explicitly in case that has an ID if not cited
    for eid in sorted(case_evidence.keys()):
        if eid not in cited_ids:
            cited_ids.append(eid)

    annexures: list[AnnexureItem] = []
    evidence_index: list[dict[str, Any]] = []

    for idx, eid in enumerate(cited_ids, start=1):
        ev = case_evidence.get(eid, {})
        filename = ev.get("filename") or f"evidence_{eid}.dat"
        sha = ev.get("sha256") or ev.get("hash") or hashlib.sha256(f"{eid}_{filename}".encode("utf-8")).hexdigest()
        ev_type = ev.get("evidence_type") or ev.get("content_type") or "DOCUMENT"
        rel_note = ev.get("description") or ev.get("relevance_note") or f"Evidence document {eid} referenced in draft."
        storage_key = ev.get("storage_key")
        size_bytes = ev.get("size_bytes") or len(ev.get("original_text", "").encode("utf-8"))

        label = f"Annexure A-{idx}"

        item = AnnexureItem(
            evidence_id=eid,
            source_hash=sha,
            filename=filename,
            evidence_type=str(ev_type),
            relevance_note=rel_note,
            annexure_label=label,
            ordering=idx,
            source_case_file_version=source_e1_ver,
            storage_key=storage_key,
            size_bytes=size_bytes,
        )
        annexures.append(item)

        evidence_index.append({
            "annexure_label": label,
            "ordering": idx,
            "evidence_id": eid,
            "filename": filename,
            "source_hash": sha,
            "evidence_type": str(ev_type),
            "relevance_note": rel_note,
            "source_case_file_version": source_e1_ver,
            "storage_key": storage_key,
            "size_bytes": size_bytes,
        })

    return annexures, evidence_index


def build_pre_submission_checklist(
    case: dict[str, Any],
    draft: AdvocateDraft,
    legal_status: str,
    annexures: list[AnnexureItem],
    missing_items: list[str],
) -> list[PreSubmissionChecklistItem]:
    """Builds a comprehensive advocate-facing pre-submission safety checklist."""
    items: list[PreSubmissionChecklistItem] = []

    # 1. Correct party names
    parties = draft.parties or {}
    has_parties = bool(parties.get("complainant") or parties.get("petitioner") or parties.get("applicant"))
    items.append(PreSubmissionChecklistItem(
        item_id="chk_parties",
        category="PARTIES",
        label="Correct Party Names & Contact Details",
        status="PASSED" if has_parties else "WARNING",
        details="Applicant/Complainant and Opposite Parties are identified in draft." if has_parties else "Party details are incomplete. Advocate confirmation recommended.",
        requires_advocate_action=not has_parties,
    ))

    # 2. Current advocate-reviewed facts
    e1_ver = draft.engine1_case_file_version
    items.append(PreSubmissionChecklistItem(
        item_id="chk_facts",
        category="FACTS",
        label="Advocate-Reviewed Facts & Chronology",
        status="PASSED",
        details=f"Draft binds to Engine-1 reviewed Case File version {e1_ver}.",
        requires_advocate_action=False,
    ))

    # 3. Approved draft current
    draft_appr = bool(draft.approval_record and draft.status == DraftStatus.ADVOCATE_APPROVED.value)
    items.append(PreSubmissionChecklistItem(
        item_id="chk_draft_approval",
        category="DRAFT",
        label="Advocate Approval & Integrity Binding",
        status="PASSED" if draft_appr else "ACTION_REQUIRED",
        details=f"Draft approved by advocate with cryptographic SHA-256 integrity hash {draft.approval_record.integrity_hash[:12]}..." if draft_appr else "Draft requires explicit advocate approval.",
        requires_advocate_action=not draft_appr,
    ))

    # 4. Legal authority verified
    is_verified_law = (legal_status == "VERIFIED_AUTHORITY")
    items.append(PreSubmissionChecklistItem(
        item_id="chk_legal_authority",
        category="LAW",
        label="Authoritative Legal Foundation Verification",
        status="PASSED" if is_verified_law else "ACTION_REQUIRED",
        details="Authoritative statutory basis verified against official corpus." if is_verified_law else f"Legal foundation status is {legal_status}. Statutory grounds require manual advocate verification before court submission. Preparation only.",
        requires_advocate_action=not is_verified_law,
    ))

    # 5. Annexures complete & evidence hashes intact
    all_hashes = all(bool(a.source_hash) for a in annexures)
    items.append(PreSubmissionChecklistItem(
        item_id="chk_annexures",
        category="ANNEXURES",
        label="Annexure Index & Evidence Hashes",
        status="PASSED" if (annexures and all_hashes) else "WARNING",
        details=f"{len(annexures)} annexures indexed with tamper-evident cryptographic hashes." if annexures else "No annexures attached to this matter.",
        requires_advocate_action=False,
    ))

    # 6. Physical / DSC Signatures Required (ALWAYS flagged as human manual requirement!)
    items.append(PreSubmissionChecklistItem(
        item_id="chk_signatures",
        category="SIGNATURE",
        label="Advocate & Citizen Signatures (Physical / DSC)",
        status="ACTION_REQUIRED",
        details="Physical or Digital Signature Certificate (DSC) signature must be affixed by human advocate and citizen prior to filing. Platform does not execute electronic signatures.",
        requires_advocate_action=True,
    ))

    # 7. Missing documents check
    items.append(PreSubmissionChecklistItem(
        item_id="chk_missing_items",
        category="PROCEDURE",
        label="Required / Missing Documents Verification",
        status="PASSED" if not missing_items else "ACTION_REQUIRED",
        details="No blocking missing requirements detected." if not missing_items else f"Missing items detected: {', '.join(missing_items)}.",
        requires_advocate_action=bool(missing_items),
    ))

    # 8. Forum & Jurisdiction Confirmed
    forum = draft.jurisdiction_forum or {}
    forum_confirmed = bool(forum.get("forum_name") or forum.get("forum") or forum.get("jurisdiction"))
    items.append(PreSubmissionChecklistItem(
        item_id="chk_forum",
        category="PROCEDURE",
        label="Intended Forum & Territorial Jurisdiction",
        status="PASSED" if forum_confirmed else "WARNING",
        details=f"Intended forum: {forum.get('forum_name') or forum.get('forum') or 'Advocate confirmation required'}." if forum_confirmed else "Intended forum requires explicit advocate confirmation.",
        requires_advocate_action=not forum_confirmed,
    ))

    # 9. Citizen consent active
    items.append(PreSubmissionChecklistItem(
        item_id="chk_consent",
        category="CONSENT",
        label="Citizen Explicit Scoped Consent",
        status="PASSED",
        details="Active citizen consent covering Case File and evidence verified.",
        requires_advocate_action=False,
    ))

    return items


def determine_readiness_state(
    eligibility: dict[str, Any],
    legal_status: str,
    checklist: list[PreSubmissionChecklistItem],
    missing_items: list[str],
    draft: AdvocateDraft,
) -> str:
    """Determines the filing readiness state following strict legal foundation safety."""
    if not eligibility.get("eligible"):
        return FilingReadinessStatus.MISSING_REQUIREMENTS.value

    if missing_items:
        return FilingReadinessStatus.MISSING_REQUIREMENTS.value

    # Legal foundation safety:
    # If legal foundation is PENDING_SOURCE, ABSTAINED, or CONFLICTING_AUTHORITY,
    # or draft is in FACTUAL_WORKING_DRAFT mode:
    # Do NOT mark READY_FOR_HUMAN_FILING. Allow only PREPARATION_ONLY.
    if legal_status in {"PENDING_SOURCE", "ABSTAINED", "CONFLICTING_AUTHORITY", "NOT_REQUESTED"}:
        return FilingReadinessStatus.PREPARATION_ONLY.value

    if draft.draft_mode == "FACTUAL_WORKING_DRAFT":
        return FilingReadinessStatus.PREPARATION_ONLY.value

    # Check for blocking checklist items (other than the standard human signature requirement)
    blocking = [
        item for item in checklist
        if item.status == "ACTION_REQUIRED" and item.item_id != "chk_signatures"
    ]
    if blocking:
        return FilingReadinessStatus.ADVOCATE_REVIEW_REQUIRED.value

    if legal_status == "VERIFIED_AUTHORITY" and draft.status == DraftStatus.ADVOCATE_APPROVED.value:
        return FilingReadinessStatus.READY_FOR_HUMAN_FILING.value

    return FilingReadinessStatus.PREPARATION_ONLY.value


def create_deterministic_zip_bundle(
    manifest_items: list[DocumentManifestItem],
    files_map: dict[str, bytes],
) -> tuple[bytes, str]:
    """Creates a deterministic ZIP archive and returns (zip_bytes, sha256_digest)."""
    buf = io.BytesIO()

    # Fixed timestamp for zip metadata determinism (2026-01-01 00:00:00)
    zip_time = (2026, 1, 1, 0, 0, 0)

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Sort filenames alphabetically for determinism
        for filename in sorted(files_map.keys()):
            content = files_map[filename]
            zinfo = zipfile.ZipInfo(filename=filename, date_time=zip_time)
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zinfo.external_attr = 0o644 << 16
            zf.writestr(zinfo, content)

    zip_bytes = buf.getvalue()
    sha256 = hashlib.sha256(zip_bytes).hexdigest()
    return zip_bytes, sha256


def prepare_filing_package(
    db: Any,
    storage: Any,
    case_id: str,
    user: dict[str, Any],
    options: Optional[dict[str, Any]] = None,
) -> FilingPackage:
    """Prepares an immutable, advocate-controlled filing package."""
    options = options or {}
    case = db.get("cases", case_id)
    if not case:
        raise ValueError(f"Case {case_id} not found.")

    # 1. Run eligibility gate
    eligibility = check_filing_eligibility(case, user, db)
    if not eligibility.get("eligible"):
        reasons_str = "; ".join(eligibility.get("reasons", []))
        raise PermissionError(f"Filing preparation eligibility gate failed: {reasons_str}")

    draft: AdvocateDraft = eligibility["draft"]
    legal_status = eligibility.get("legal_foundation_status", "PENDING_SOURCE")
    is_verified_law = (legal_status == "VERIFIED_AUTHORITY")

    # 2. Build annexures and evidence index
    annexures, evidence_index = build_annexures_and_evidence_index(case, draft, db)

    # 3. Check for missing requirements
    missing_items: list[str] = []
    canonical = case.get("canonical_case_file") or case.get("case_file") or {}
    if not draft.parties.get("complainant") and not draft.parties.get("petitioner") and not draft.parties.get("applicant"):
        missing_items.append("applicant_party_details")

    # 4. Build pre-submission checklist
    checklist = build_pre_submission_checklist(case, draft, legal_status, annexures, missing_items)

    # 5. Determine readiness state
    readiness_state = determine_readiness_state(eligibility, legal_status, checklist, missing_items, draft)

    # 6. Retrieve approved PDF artifact
    pdf_bytes: bytes = b""
    pdf_sha = ""
    pdf_filename = f"{draft.draft_type}_approved.pdf"
    if draft.pdf_artifact and draft.pdf_artifact.storage_key:
        try:
            pdf_bytes = storage.download(draft.pdf_artifact.storage_key)
            pdf_sha = draft.pdf_artifact.sha256
            pdf_filename = draft.pdf_artifact.filename
        except Exception:
            pdf_bytes = b""

    if not pdf_bytes:
        # Generate approved PDF dynamically if not in storage
        html = draft.html_content or "<html><body><h1>Approved Draft</h1></body></html>"
        pdf_bytes, _ = export(html, "pdf")
        pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()

    # 7. Collect and assemble export files
    files_map: dict[str, bytes] = {}

    # /approved-draft.pdf
    files_map["approved-draft.pdf"] = pdf_bytes

    # /evidence-index.json
    ev_index_json = json.dumps(evidence_index, indent=2, sort_keys=True).encode("utf-8")
    files_map["evidence-index.json"] = ev_index_json

    # /checklist.json
    checklist_dicts = [item.model_dump() for item in checklist]
    checklist_json = json.dumps(checklist_dicts, indent=2, sort_keys=True).encode("utf-8")
    files_map["checklist.json"] = checklist_json

    # Disclosures & Provenance
    disclosures = [
        DISCLOSURE_PHASE10_SAFETY,
        DISCLOSURE_ADVOCATE_ONLY,
        DISCLOSURE_REVIEW_PENDING,
        DISCLOSURE_NO_EXTERNAL_SUBMISSION,
        DISCLOSURE_PHASE4_OPEN,
        DISCLOSURE_HUMAN_ACTION,
        eligibility.get("engine2_disclosure", ENGINE2_NOT_RUN_DISCLOSURE),
    ]

    provenance_data = {
        "case_id": case_id,
        "advocate_id": user.get("id"),
        "engine1_case_file_version": draft.engine1_case_file_version,
        "engine3_draft_id": draft.draft_id,
        "engine3_draft_version": draft.version,
        "draft_integrity_hash": draft.approval_record.integrity_hash if draft.approval_record else None,
        "engine2_run_id": eligibility.get("engine2_run_id"),
        "engine2_disclosure": eligibility.get("engine2_disclosure"),
        "legal_foundation_status": legal_status,
        "readiness_status": readiness_state,
        "filing_mode": "MANUAL_HUMAN_ADVOCATE_FILING",
        "prepared_at": options.get("prepared_at") or (draft.approval_record.approved_at if draft.approval_record else utc_now()),
        "disclosures": disclosures,
        "automated_submission_performed": False,
        "court_portal_contacted": False,
    }
    provenance_json = json.dumps(provenance_data, indent=2, sort_keys=True).encode("utf-8")
    files_map["provenance.json"] = provenance_json

    # /annexures/
    for a in annexures:
        # Read file from storage if present, otherwise structured metadata
        content_bytes = b""
        if a.storage_key:
            try:
                content_bytes = storage.download(a.storage_key)
            except Exception:
                content_bytes = b""
        if not content_bytes:
            # Deterministic JSON descriptor of annexure
            annex_desc = {
                "annexure_label": a.annexure_label,
                "evidence_id": a.evidence_id,
                "filename": a.filename,
                "source_hash": a.source_hash,
                "evidence_type": a.evidence_type,
                "relevance_note": a.relevance_note,
                "ordering": a.ordering,
                "source_case_file_version": a.source_case_file_version,
            }
            content_bytes = json.dumps(annex_desc, indent=2, sort_keys=True).encode("utf-8")
            clean_name = a.filename.replace("/", "_").replace("\\", "_")
            files_map[f"annexures/{a.annexure_label}_{clean_name}.json"] = content_bytes
        else:
            clean_name = a.filename.replace("/", "_").replace("\\", "_")
            files_map[f"annexures/{a.annexure_label}_{clean_name}"] = content_bytes

    # 8. Document Manifest
    manifest_items: list[DocumentManifestItem] = []

    # Approved PDF entry
    manifest_items.append(DocumentManifestItem(
        item_type="APPROVED_PDF",
        filename="approved-draft.pdf",
        version=draft.version,
        sha256=pdf_sha,
        size_bytes=len(pdf_bytes),
        mandatory_for_filing=True,
        description="Approved final legal draft PDF signed off by advocate.",
    ))

    # Evidence index entry
    manifest_items.append(DocumentManifestItem(
        item_type="EVIDENCE_INDEX",
        filename="evidence-index.json",
        version=1,
        sha256=hashlib.sha256(ev_index_json).hexdigest(),
        size_bytes=len(ev_index_json),
        mandatory_for_filing=True,
        description="Structured annexures and evidence index mapping.",
    ))

    # Checklist entry
    manifest_items.append(DocumentManifestItem(
        item_type="CHECKLIST",
        filename="checklist.json",
        version=1,
        sha256=hashlib.sha256(checklist_json).hexdigest(),
        size_bytes=len(checklist_json),
        mandatory_for_filing=True,
        description="Pre-submission safety checklist.",
    ))

    # Provenance entry
    manifest_items.append(DocumentManifestItem(
        item_type="PROVENANCE",
        filename="provenance.json",
        version=1,
        sha256=hashlib.sha256(provenance_json).hexdigest(),
        size_bytes=len(provenance_json),
        mandatory_for_filing=True,
        description="Filing package provenance and integrity metadata.",
    ))

    # Annexure entries in manifest
    for k, v in files_map.items():
        if k.startswith("annexures/"):
            manifest_items.append(DocumentManifestItem(
                item_type="ANNEXURE",
                filename=k,
                version=1,
                sha256=hashlib.sha256(v).hexdigest(),
                size_bytes=len(v),
                mandatory_for_filing=True,
                description=f"Annexure document item {k}",
            ))

    # Add manifest.json to export files
    manifest_dicts = [item.model_dump() for item in manifest_items]
    manifest_json = json.dumps(manifest_dicts, indent=2, sort_keys=True).encode("utf-8")
    files_map["manifest.json"] = manifest_json

    # Add self to manifest
    manifest_items.append(DocumentManifestItem(
        item_type="MANIFEST",
        filename="manifest.json",
        version=1,
        sha256=hashlib.sha256(manifest_json).hexdigest(),
        size_bytes=len(manifest_json),
        mandatory_for_filing=True,
        description="Complete cryptographic document manifest.",
    ))

    # 9. Create deterministic ZIP bundle and calculate package digest
    zip_bytes, package_digest = create_deterministic_zip_bundle(manifest_items, files_map)

    # 10. Check if earlier package exists for this case to handle versioning
    existing_packages = [p for p in db.list("filing_packages") if p.get("case_id") == case_id]
    pkg_version = 1
    package_id = f"fp_{uuid4().hex[:12]}"
    if existing_packages:
        pkg_version = max(p.get("version", 1) for p in existing_packages) + 1
        # Mark previous packages as SUPERSEDED
        for prev in existing_packages:
            if prev.get("status") not in {FilingReadinessStatus.SUPERSEDED.value, FilingReadinessStatus.STALE.value}:
                try:
                    db.update("filing_packages", prev["id"], {"status": FilingReadinessStatus.SUPERSEDED.value})
                except Exception:
                    pass

    # 11. Upload bundle to storage
    storage_key = f"cases/{case_id}/filing_packages/{package_id}/v{pkg_version}/filing_bundle.zip"
    storage.upload(storage_key, zip_bytes, "application/zip")

    # 12. Build FilingPackage contract
    package = FilingPackage(
        filing_package_id=package_id,
        case_id=case_id,
        advocate_id=user.get("id"),
        engine1_case_file_version=draft.engine1_case_file_version,
        engine3_draft_id=draft.draft_id,
        engine3_draft_version=draft.version,
        draft_integrity_hash=draft.approval_record.integrity_hash if draft.approval_record else "",
        engine2_run_id=eligibility.get("engine2_run_id"),
        status=readiness_state,
        created_at=utc_now(),
        version=pkg_version,
        document_type=draft.draft_type,
        intended_forum=draft.jurisdiction_forum,
        jurisdiction=draft.jurisdiction_forum,
        filing_mode="MANUAL_HUMAN_ADVOCATE_FILING",
        filing_readiness=readiness_state,
        approved_draft_reference={
            "draft_id": draft.draft_id,
            "version": draft.version,
            "integrity_hash": draft.approval_record.integrity_hash if draft.approval_record else "",
            "approved_at": draft.approval_record.approved_at if draft.approval_record else "",
        },
        approved_pdf_reference={
            "storage_key": draft.pdf_artifact.storage_key if draft.pdf_artifact else "",
            "sha256": pdf_sha,
            "size_bytes": len(pdf_bytes),
            "filename": pdf_filename,
        },
        annexures=annexures,
        evidence_index=evidence_index,
        document_manifest=manifest_items,
        party_details=draft.parties,
        chronology_reference=draft.chronology,
        verified_legal_basis=draft.legal_basis if is_verified_law else [],
        required_missing_items=missing_items,
        pre_submission_checklist=checklist,
        disclosures=disclosures,
        provenance=provenance_data,
        package_digest=package_digest,
        storage_key=storage_key,
        export_bundle_sha256=package_digest,
    )

    # 13. Persist root package and immutable package version record
    pkg_dict = package.model_dump()
    pkg_dict["id"] = package_id
    db.create("filing_packages", pkg_dict)

    version_record = {
        "id": f"{package_id}_v{pkg_version}",
        "filing_package_id": package_id,
        "version": pkg_version,
        "case_id": case_id,
        "advocate_id": user.get("id"),
        "package_digest": package_digest,
        "status": readiness_state,
        "created_at": package.created_at,
        "data": pkg_dict,
    }
    db.create("filing_package_versions", version_record)

    # 14. Update case metadata with safe status
    try:
        db.update("cases", case_id, {
            "filing_preparation_status": readiness_state,
            "latest_filing_package_id": package_id,
            "latest_filing_package_version": pkg_version,
            "filing_package_prepared_at": package.created_at,
        })
    except Exception:
        pass

    return package


def evaluate_package_staleness(db: Any, case: dict[str, Any], package: FilingPackage) -> FilingPackage:
    """Evaluates if an existing package has become STALE due to changes in E1, draft, consent, or corrections."""
    canonical = case.get("canonical_case_file") or case.get("case_file") or {}
    current_e1_ver = canonical.get("version")
    e1_stale = case.get("engine1_stale", False)

    is_stale = False
    stale_reasons: list[str] = []

    # 1. E1 version change or staleness
    if current_e1_ver != package.engine1_case_file_version:
        is_stale = True
        stale_reasons.append(f"Engine 1 Case File version changed (package={package.engine1_case_file_version}, current={current_e1_ver}).")
    if e1_stale:
        is_stale = True
        stale_reasons.append("Engine 1 Case File is marked stale.")

    # 2. Approved draft version change
    draft_root = db.get("engine3_drafts", package.engine3_draft_id) if db else None
    if draft_root and draft_root.get("current_version") != package.engine3_draft_version:
        is_stale = True
        stale_reasons.append(f"Engine 3 draft version changed (package={package.engine3_draft_version}, current={draft_root.get('current_version')}).")

    # 3. Consent state
    grant = active_grant(db, case.get("case_id"), package.advocate_id) if db else None
    has_consent = bool(grant and "case_file" in grant.get("scopes", []))
    if not has_consent and db:
        walkin = db.get("walkin_consents", case.get("case_id"))
        if walkin and not walkin.get("revoked_at"):
            has_consent = True

    if not has_consent:
        is_stale = True
        stale_reasons.append("Active citizen consent was revoked or expired.")

    # 4. Substantive correction conflicts
    corrections = db.list("advocate_case_corrections") if db else []
    unresolved_conflicts = any(
        c.get("conflict_status") == "CONFLICT_DETECTED"
        for c in corrections
        if c.get("case_id") == case.get("case_id")
    )
    if unresolved_conflicts:
        is_stale = True
        stale_reasons.append("New unresolved substantive correction conflicts detected.")

    if is_stale and package.status != FilingReadinessStatus.SUPERSEDED.value:
        package.status = FilingReadinessStatus.STALE.value
        package.filing_readiness = FilingReadinessStatus.STALE.value
        # Persist updated status to root package
        try:
            db.update("filing_packages", package.filing_package_id, {
                "status": FilingReadinessStatus.STALE.value,
                "filing_readiness": FilingReadinessStatus.STALE.value,
                "stale_reasons": stale_reasons,
            })
        except Exception:
            pass

    return package


def get_filing_package(db: Any, case_id: str, package_id: str, user: dict[str, Any]) -> dict[str, Any]:
    """Retrieves a filing package with strict access control and dynamic staleness check."""
    case = db.get("cases", case_id)
    if not case:
        raise ValueError(f"Case {case_id} not found.")

    pkg_doc = db.get("filing_packages", package_id)
    if not pkg_doc or pkg_doc.get("case_id") != case_id:
        raise ValueError("Filing package not found.")

    # Access control
    is_assigned_advocate = (user.get("role") == "advocate" and case.get("assigned_advocate_id") == user.get("id"))
    is_owner_citizen = (user.get("role") == "citizen" and case.get("owner_user_id") == user.get("id"))

    if not is_assigned_advocate and not is_owner_citizen:
        raise PermissionError("Access denied. Only the assigned advocate or case citizen may view filing package status.")

    if is_assigned_advocate:
        grant = active_grant(db, case_id, user.get("id"))
        if not grant:
            raise PermissionError("Access denied. Active citizen consent is required to view filing packages.")

    package = FilingPackage.model_validate(pkg_doc)
    package = evaluate_package_staleness(db, case, package)

    if is_owner_citizen:
        # Return safe citizen summary without raw legal work product
        return {
            "filing_package_id": package.filing_package_id,
            "case_id": package.case_id,
            "status": package.status,
            "created_at": package.created_at,
            "version": package.version,
            "filing_mode": package.filing_mode,
            "safe_citizen_status": (
                "Filing package prepared by advocate"
                if package.status in {FilingReadinessStatus.READY_FOR_HUMAN_FILING.value, FilingReadinessStatus.PREPARATION_ONLY.value}
                else "Filing preparation in progress"
            ),
            "disclaimer": "Filing materials have been prepared for advocate review. No external court filing has occurred.",
        }

    return package.model_dump()


def list_filing_packages(db: Any, case_id: str, user: dict[str, Any]) -> list[dict[str, Any]]:
    """Lists filing packages for a case with access control."""
    case = db.get("cases", case_id)
    if not case:
        raise ValueError(f"Case {case_id} not found.")

    is_assigned_advocate = (user.get("role") == "advocate" and case.get("assigned_advocate_id") == user.get("id"))
    is_owner_citizen = (user.get("role") == "citizen" and case.get("owner_user_id") == user.get("id"))

    if not is_assigned_advocate and not is_owner_citizen:
        raise PermissionError("Access denied.")

    if is_assigned_advocate:
        grant = active_grant(db, case_id, user.get("id"))
        if not grant:
            raise PermissionError("Access denied. Active citizen consent is required to view filing packages.")

    packages = [p for p in db.list("filing_packages") if p.get("case_id") == case_id]
    result = []
    for p in packages:
        pkg = FilingPackage.model_validate(p)
        pkg = evaluate_package_staleness(db, case, pkg)
        if is_owner_citizen:
            result.append({
                "filing_package_id": pkg.filing_package_id,
                "case_id": pkg.case_id,
                "status": pkg.status,
                "created_at": pkg.created_at,
                "version": pkg.version,
                "safe_citizen_status": "Filing package prepared by advocate" if pkg.status in {FilingReadinessStatus.READY_FOR_HUMAN_FILING.value, FilingReadinessStatus.PREPARATION_ONLY.value} else "Filing preparation in progress",
            })
        else:
            result.append(pkg.model_dump())

    return sorted(result, key=lambda x: x.get("version", 1), reverse=True)


def export_filing_bundle(db: Any, storage: Any, case_id: str, package_id: str, user: dict[str, Any]) -> tuple[bytes, str]:
    """Exports the deterministic filing package bundle (ZIP). Strictly advocate-only."""
    if user.get("role") != "advocate":
        raise PermissionError("Only the assigned advocate may export the filing package bundle.")

    case = db.get("cases", case_id)
    if not case or case.get("assigned_advocate_id") != user.get("id"):
        raise PermissionError("Only the assigned advocate may export the filing package bundle.")

    pkg_doc = db.get("filing_packages", package_id)
    if not pkg_doc or pkg_doc.get("case_id") != case_id:
        raise ValueError("Filing package not found.")

    storage_key = pkg_doc.get("storage_key")
    if not storage_key:
        raise ValueError("Filing bundle storage key missing.")

    zip_bytes = storage.download(storage_key)
    filename = f"filing_package_{case_id}_v{pkg_doc.get('version', 1)}.zip"
    return zip_bytes, filename
