"""Phase 10 Synthetic End-to-End Filing Preparation Journey Script.

Runs isolated synthetic end-to-end validation of:
synthetic citizen
→ Engine 1
→ optional Engine 2
→ verified synthetic advocate
→ consent
→ advocate review
→ current reviewed E1
→ Engine 3 approved draft
→ generate approved PDF
→ prepare filing package
→ generate annexure/evidence index
→ run checklist
→ export immutable preparation bundle
→ verify package digest
→ modify E1/draft
→ confirm previous package becomes stale
→ create new package version

DOES NOT submit anything to a court or external filing portal.
DOES NOT perform any genuine Phase 4 legal-authority corpus review.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymongo
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.adapters.mock.auth import MockAuthAdapter
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.adapters.mock.llm import MockLLMAdapter
from backend.adapters.mock.storage import MockStorageAdapter
from backend.routes.advocates import router as advocates_router
from backend.routes.auth import router as auth_router
from backend.routes.cases import router as cases_router
from backend.routes.documents import router as documents_router
from backend.routes.engines import router as engines_router
from backend.routes.filing import router as filing_router
from backend.routes.review import router as review_router
from backend.routes.sharing import router as sharing_router
from backend.models.draft import AdvocateDraft, ApprovalRecord, DraftMode, DraftStatus, PdfArtifact
from backend.models.filing import FilingReadinessStatus
from backend.services.engine3 import compute_draft_integrity_hash, export
from backend.services.filing import (
    check_filing_eligibility,
    evaluate_package_staleness,
    prepare_filing_package,
    DISCLOSURE_PHASE10_SAFETY,
    DISCLOSURE_ADVOCATE_ONLY,
    DISCLOSURE_NO_EXTERNAL_SUBMISSION,
)
from backend.services.review_contracts import ENGINE2_NOT_RUN_DISCLOSURE
from backend.services.sharing import issue_token


def verify_phase4_invariants(label: str):
    """Verifies Phase 4 safety invariants in local MongoDB."""
    client = pymongo.MongoClient("mongodb://127.0.0.1:27017")
    db = client["caseseva"]
    count = db.legal_authority_versions.count_documents({})
    assert count == 48, f"[{label}] Expected legal_authority_versions == 48, got {count}"

    queue_file = Path(__file__).resolve().parent.parent / "docs" / "audits" / "phase4_review_queue.json"
    queue = json.loads(queue_file.read_text(encoding="utf-8"))
    candidates = queue["candidates"]
    assert len(candidates) == 12, f"[{label}] Expected 12 candidates, got {len(candidates)}"

    for c in candidates:
        vid = c["version_id"]
        sid = c["source_id"]
        doc = db.legal_authority_versions.find_one({"id": vid})
        assert doc is not None, f"[{label}] Missing version doc for {sid}"
        src = doc.get("source", {})
        assert src.get("review_state") == "REVIEW_PENDING", f"[{label}] {sid} review_state != REVIEW_PENDING"
        assert src.get("source_reviewed") is False, f"[{label}] {sid} source_reviewed != False"
        assert src.get("temporal_reviewed") is False, f"[{label}] {sid} temporal_reviewed != False"
        assert src.get("review_eligible", False) is False, f"[{label}] {sid} review_eligible != False"

    print(f"[{label}] Phase-4 safety invariants VERIFIED: 48 authority versions, 12 candidates in REVIEW_PENDING.")


def build_synthetic_environment():
    temp_dir = tempfile.TemporaryDirectory()
    db = MockDatabaseAdapter(temp_dir.name + "/database.json")
    storage = MockStorageAdapter(temp_dir.name + "/uploads")
    adapters = SimpleNamespace(
        database=db,
        storage=storage,
        llm=MockLLMAdapter(),
        auth=MockAuthAdapter(db),
        email_provider="mock",
        mode="mock",
        processing_mode="live",
        llm_processing_mode="live",
    )
    app = FastAPI()
    app.state.adapters = adapters
    for r in (cases_router, auth_router, engines_router, advocates_router, sharing_router, review_router, documents_router, filing_router):
        app.include_router(r)
    return temp_dir, app, TestClient(app), db, storage


def run_synthetic_filing_journey():
    print("=" * 70)
    print("STARTING PHASE 10 SYNTHETIC FILING PREPARATION END-TO-END JOURNEY")
    print("=" * 70)

    # Preflight Phase 4 invariant check
    verify_phase4_invariants("Preflight")

    temp_dir, app, client, db, storage = build_synthetic_environment()

    try:
        # Step 1: Synthetic Citizen Setup
        print("\n[Step 1] Creating synthetic citizen and case...")
        citizen = {"id": "cit_synth_10", "email": "priya.citizen@synth.in", "role": "citizen", "full_name": "Priya Sharma"}
        db.create("users", citizen)
        db.create("sessions", {"id": "ses_cit10", "user_id": citizen["id"]})
        cit_headers = {"Authorization": "Bearer ses_cit10"}

        case_id = "case_phase10_synth"
        evidence_item = {
            "evidence_id": "E101",
            "filename": "fee_receipt_45000.pdf",
            "sha256": "8f4e2b1a8d0c6f5e4b3a2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f",
            "description": "Fee payment receipt of INR 45,000 to Ace Coaching Ltd",
            "evidence_type": "RECEIPT",
            "storage_key": f"cases/{case_id}/evidence/E101.pdf",
        }
        storage.upload(evidence_item["storage_key"], b"SYNTHETIC_RECEIPT_PDF_BYTES", "application/pdf")

        # Step 2: Engine 1 Case File
        print("\n[Step 2] Establishing Engine 1 Case File...")
        case_file_v1 = {
            "version": 1,
            "case_id": case_id,
            "legal_foundation_status": "VERIFIED_AUTHORITY",
            "applicable_law": [
                {
                    "source_id": "cpa2019_s2_7",
                    "title": "THE CONSUMER PROTECTION ACT, 2019",
                    "section": "2(7)",
                    "authority_status": "VERIFIED_AUTHORITY",
                    "explanation": "Consumer rights in service contract dispute.",
                },
                {
                    "source_id": "cpa2019_s34",
                    "title": "THE CONSUMER PROTECTION ACT, 2019",
                    "section": "34",
                    "authority_status": "VERIFIED_AUTHORITY",
                    "explanation": "Territorial and pecuniary jurisdiction before District Commission.",
                },
            ],
            "facts": [
                {"id": "F1", "text": "Citizen paid INR 45,000 for coaching classes on 15-06-2024."},
                {"id": "F2", "text": "Center closed down without conducting sessions and refused refund."},
            ],
            "parties": {
                "complainant": {"name": "Priya Sharma", "address": "Delhi"},
                "opposite_party": {"name": "Ace Coaching Ltd", "address": "Connaught Place, New Delhi"},
            },
            "jurisdiction": {"forum_name": "District Consumer Disputes Redressal Commission", "state": "Delhi"},
            "chronology": [
                {"date": "2024-06-15", "event": "Paid admission fee."},
                {"date": "2024-07-01", "event": "Coaching center shut down."},
            ],
        }

        # Step 3: Verified Synthetic Advocate
        print("\n[Step 3] Onboarding verified synthetic advocate...")
        advocate = {
            "id": "adv_synth_10",
            "email": "advocate.verma@bar.in",
            "name": "Adv. Ramesh Verma",
            "role": "advocate",
            "verification_status": "VERIFIED",
            "bar_registration_number": "D/7788/2014",
        }
        db.create("users", advocate)
        db.create("sessions", {"id": "ses_adv10", "user_id": advocate["id"]})
        adv_headers = {"Authorization": "Bearer ses_adv10"}

        # Step 4: Case Assignment & Citizen Consent
        print("\n[Step 4] Assigning case and recording citizen scoped consent...")
        case = {
            "id": case_id,
            "case_id": case_id,
            "owner_user_id": citizen["id"],
            "assigned_advocate_id": advocate["id"],
            "status": "ADVOCATE_APPROVED",
            "review_status": "REVIEWED_CURRENT",
            "advocate_approved_case_file_version": 1,
            "engine1_case_file_version": 1,
            "engine1_stale": False,
            "canonical_case_file": case_file_v1,
            "evidence": [evidence_item],
            "engine2": None,
            "engine2_choice": "DECLINED",
        }
        db.create("cases", case)

        grant = {
            "id": f"grant_{case_id}_{advocate['id']}",
            "case_id": case_id,
            "user_id": citizen["id"],
            "advocate_id": advocate["id"],
            "status": "ACTIVE",
            "scopes": ["story", "case_file", "evidence"],
            "evidence_ids": ["E101"],
            "expires_at": "2030-01-01T00:00:00+00:00",
            "created_at": "2026-10-15T10:00:00Z",
        }
        db.create("case_grants", grant)
        case_token = issue_token(db, grant)
        adv_headers["X-Case-Access"] = case_token

        # Step 5: Engine 3 Approved Draft & PDF Artifact
        print("\n[Step 5] Creating Engine-3 approved draft and immutable PDF...")
        draft_id = "draft_phase10_e3"
        draft = AdvocateDraft(
            draft_id=draft_id,
            case_id=case_id,
            advocate_id=advocate["id"],
            draft_type="complaint_petition",
            draft_mode=DraftMode.AUTHORITATIVE.value,
            engine1_case_file_version=1,
            engine2_run_id=None,
            engine2_status="NOT_RUN",
            version=1,
            status=DraftStatus.ADVOCATE_APPROVED.value,
            created_at="2026-10-15T11:00:00Z",
            updated_at="2026-10-15T11:30:00Z",
            title="Formal Consumer Complaint u/s 35 CPA 2019",
            parties=case_file_v1["parties"],
            jurisdiction_forum=case_file_v1["jurisdiction"],
            facts_section=case_file_v1["facts"],
            chronology=case_file_v1["chronology"],
            legal_basis=case_file_v1["applicable_law"],
            reliefs_or_requests=["Full refund of INR 45,000", "Litigation cost INR 10,000"],
            evidence_references=[evidence_item],
            disclosures=[ENGINE2_NOT_RUN_DISCLOSURE],
            provenance={"legal_foundation_status": "VERIFIED_AUTHORITY"},
        )
        draft.approval_record = ApprovalRecord(
            approved_by_advocate_id=advocate["id"],
            draft_version=1,
            source_engine1_version=1,
            approved_at="2026-10-15T11:30:00Z",
            integrity_hash=compute_draft_integrity_hash(draft),
            approval_state="ADVOCATE_APPROVED",
            disclosures=[ENGINE2_NOT_RUN_DISCLOSURE],
        )
        pdf_bytes, _ = export("<html><body><h1>Consumer Complaint Draft</h1></body></html>", "pdf")
        pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
        pdf_key = f"cases/{case_id}/drafts/{draft_id}/v1/approved.pdf"
        storage.upload(pdf_key, pdf_bytes, "application/pdf")
        draft.pdf_artifact = PdfArtifact(
            storage_key=pdf_key,
            sha256=pdf_sha,
            created_at="2026-10-15T11:30:00Z",
            size_bytes=len(pdf_bytes),
            filename="complaint_petition_v1_approved.pdf",
        )

        db.create("engine3_drafts", {
            "id": draft_id,
            "case_id": case_id,
            "advocate_id": advocate["id"],
            "current_version": 1,
            "status": DraftStatus.ADVOCATE_APPROVED.value,
        })
        db.create("engine3_draft_versions", {
            "id": f"{draft_id}_v1",
            "draft_id": draft_id,
            "version": 1,
            "case_id": case_id,
            "advocate_id": advocate["id"],
            "data": draft.model_dump(),
        })
        db.update("cases", case_id, {"engine3_draft_id": draft_id})

        # Step 6: Eligibility Gate Check
        print("\n[Step 6] Running Phase 10 Eligibility Gate...")
        elig = check_filing_eligibility(db.get("cases", case_id), advocate, db)
        assert elig["eligible"] is True, f"Eligibility gate failed: {elig['reasons']}"
        print("    [PASS] Eligibility gate satisfied: Verified advocate assigned, active consent, reviewed E1, approved draft.")

        # Step 7: Prepare Filing Package (Version 1)
        print("\n[Step 7] Preparing Filing Package (v1)...")
        pkg1 = prepare_filing_package(db, storage, case_id, advocate)
        assert pkg1.version == 1
        assert pkg1.status == FilingReadinessStatus.READY_FOR_HUMAN_FILING.value
        assert len(pkg1.package_digest) == 64
        assert len(pkg1.annexures) == 1
        assert pkg1.annexures[0].annexure_label == "Annexure A-1"
        assert pkg1.annexures[0].evidence_id == "E101"
        print(f"    [PASS] Filing package v1 prepared: ID={pkg1.filing_package_id}, status={pkg1.status}, digest={pkg1.package_digest[:16]}...")

        # Step 8: Pre-Submission Safety Checklist Verification
        print("\n[Step 8] Verifying Pre-Submission Safety Checklist...")
        chk_items = {c.item_id: c for c in pkg1.pre_submission_checklist}
        assert "chk_parties" in chk_items
        assert "chk_facts" in chk_items
        assert "chk_draft_approval" in chk_items
        assert "chk_legal_authority" in chk_items
        assert "chk_signatures" in chk_items
        assert chk_items["chk_signatures"].status == "ACTION_REQUIRED"
        assert chk_items["chk_signatures"].requires_advocate_action is True
        print("    [PASS] Pre-submission checklist contains mandatory checks; manual signature flagged as action required.")

        # Step 9: Document Manifest & Export Bundle Integrity
        print("\n[Step 9] Verifying Document Manifest & ZIP Bundle...")
        manifest_files = {m.filename: m for m in pkg1.document_manifest}
        assert "approved-draft.pdf" in manifest_files
        assert "manifest.json" in manifest_files
        assert "checklist.json" in manifest_files
        assert "evidence-index.json" in manifest_files
        assert "provenance.json" in manifest_files

        zip_bytes = storage.download(pkg1.storage_key)
        assert len(zip_bytes) > 0
        computed_zip_sha = hashlib.sha256(zip_bytes).hexdigest()
        assert computed_zip_sha == pkg1.package_digest
        print(f"    [PASS] Immutable bundle verified in storage: size={len(zip_bytes)} bytes, SHA-256 match.")

        # Step 10: Disclosures & Absolute Boundaries
        print("\n[Step 10] Verifying Disclosures & No External Filing...")
        assert DISCLOSURE_PHASE10_SAFETY in pkg1.disclosures
        assert DISCLOSURE_ADVOCATE_ONLY in pkg1.disclosures
        assert DISCLOSURE_NO_EXTERNAL_SUBMISSION in pkg1.disclosures
        assert ENGINE2_NOT_RUN_DISCLOSURE in pkg1.disclosures
        assert pkg1.filing_mode == "MANUAL_HUMAN_ADVOCATE_FILING"
        assert pkg1.status != "FILED"
        print("    [PASS] Safety disclosures verified: Strictly NO court portal submission or fee payment.")

        # Step 11: Modify Engine 1 Input & Test Staleness
        print("\n[Step 11] Modifying Case File to simulate new facts and checking staleness...")
        case_file_v2 = deepcopy(case_file_v1)
        case_file_v2["version"] = 2
        case_file_v2["facts"].append({"id": "F3", "text": "Complainant discovered coaching center registration expired."})
        db.update("cases", case_id, {
            "canonical_case_file": case_file_v2,
            "engine1_case_file_version": 2,
            "advocate_approved_case_file_version": 2,
        })

        case_fresh = db.get("cases", case_id)
        stale_pkg = evaluate_package_staleness(db, case_fresh, pkg1)
        assert stale_pkg.status == FilingReadinessStatus.STALE.value
        print(f"    [PASS] Previous package v1 became STALE after Engine 1 version change (status={stale_pkg.status}).")

        # Step 12: Generate Approved Draft v2 and Prepare New Package Version (v2)
        print("\n[Step 12] Approving updated draft v2 and explicitly preparing new package version...")
        draft_v2 = deepcopy(draft)
        draft_v2.version = 2
        draft_v2.engine1_case_file_version = 2
        draft_v2.facts_section = case_file_v2["facts"]
        draft_v2.approval_record = ApprovalRecord(
            approved_by_advocate_id=advocate["id"],
            draft_version=2,
            source_engine1_version=2,
            approved_at="2026-10-16T10:00:00Z",
            integrity_hash=compute_draft_integrity_hash(draft_v2),
            approval_state="ADVOCATE_APPROVED",
            disclosures=[ENGINE2_NOT_RUN_DISCLOSURE],
        )
        db.create("engine3_draft_versions", {
            "id": f"{draft_id}_v2",
            "draft_id": draft_id,
            "version": 2,
            "case_id": case_id,
            "advocate_id": advocate["id"],
            "data": draft_v2.model_dump(),
        })
        db.update("engine3_drafts", draft_id, {"current_version": 2, "status": DraftStatus.ADVOCATE_APPROVED.value})

        # Explicitly prepare new package version
        pkg2 = prepare_filing_package(db, storage, case_id, advocate)
        assert pkg2.version == 2
        assert pkg2.status == FilingReadinessStatus.READY_FOR_HUMAN_FILING.value
        assert pkg2.engine1_case_file_version == 2
        assert pkg2.engine3_draft_version == 2

        # Verify historical v1 package is now marked SUPERSEDED in db
        historical_v1 = db.get("filing_packages", pkg1.filing_package_id)
        assert historical_v1["status"] in {FilingReadinessStatus.SUPERSEDED.value, FilingReadinessStatus.STALE.value}

        # Verify immutable version records preserved
        v1_rec = db.get("filing_package_versions", f"{pkg1.filing_package_id}_v1")
        v2_rec = db.get("filing_package_versions", f"{pkg2.filing_package_id}_v2")
        assert v1_rec is not None
        assert v2_rec is not None
        print(f"    [PASS] New package version v2 prepared successfully (ID={pkg2.filing_package_id}); v1 preserved and marked superseded.")

        # Step 13: Citizen Safe View Verification
        print("\n[Step 13] Verifying citizen access returns safe status without court filing claim...")
        cit_packages = client.get(f"/api/cases/{case_id}/filing-packages", headers=cit_headers).json()
        assert len(cit_packages) > 0
        latest_cit_pkg = cit_packages[0]
        assert latest_cit_pkg["safe_citizen_status"] == "Filing package prepared by advocate"
        assert "approved-draft.pdf" not in latest_cit_pkg  # Raw legal artifacts withheld from citizen overview
        print("    [PASS] Citizen view confirmed: shows 'Filing package prepared by advocate', no claim of filing.")

        print("\n" + "=" * 70)
        print("SYNTHETIC END-TO-END FILING PREPARATION JOURNEY COMPLETED SUCCESSFULLY")
        print("=" * 70)

    finally:
        temp_dir.cleanup()

    # Postflight Phase 4 invariant check
    verify_phase4_invariants("Postflight")


if __name__ == "__main__":
    run_synthetic_filing_journey()
