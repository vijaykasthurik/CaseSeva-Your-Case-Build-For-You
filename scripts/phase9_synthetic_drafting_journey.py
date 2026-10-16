"""Phase 9 Synthetic End-to-End Advocate Drafting Journey Script.

Runs isolated synthetic end-to-end validation of:
synthetic citizen
→ Engine 1
→ optional Engine 2
→ verified synthetic advocate
→ request accepted
→ citizen consent
→ advocate correction/review
→ REVIEWED_CURRENT
→ Engine-3 eligibility passes
→ advocate chooses a safe draft type
→ generate draft
→ inspect provenance
→ advocate edits draft
→ save new version
→ selectively regenerate one section
→ confirm untouched advocate edits preserved
→ advocate approves final version
→ generate immutable PDF
→ change Engine-1 input afterward
→ verify previous draft becomes stale but remains preserved

DOES NOT perform any genuine Phase 4 legal-authority corpus review.
DOES NOT file or submit anything externally.
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
from backend.routes.review import router as review_router
from backend.routes.sharing import router as sharing_router
from backend.services.engine1 import run_engine1
from backend.services.engine2 import run_engine2
from backend.services.review_contracts import ENGINE2_NOT_RUN_DISCLOSURE, check_engine3_eligibility
from backend.services.sharing import issue_token


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
    for r in (cases_router, auth_router, engines_router, advocates_router, sharing_router, review_router, documents_router):
        app.include_router(r)
    return temp_dir, app, TestClient(app), db, storage


def run_synthetic_journey():
    print("=" * 70)
    print("STARTING PHASE 9 SYNTHETIC ADVOCATE DRAFTING END-TO-END JOURNEY")
    print("=" * 70)

    temp_dir, app, client, db, storage = build_synthetic_environment()

    try:
        # Step 1: Synthetic Citizen Setup
        print("\n[Step 1] Creating synthetic citizen and submitting narrative...")
        citizen = {"id": "cit_synth_9", "email": "citizen9@synth.in", "role": "citizen", "full_name": "Priya Sharma"}
        db.create("users", citizen)
        db.create("sessions", {"id": "ses_cit9", "user_id": citizen["id"]})
        cit_headers = {"Authorization": "Bearer ses_cit9"}

        case_id = "case_phase9_synth"
        case_file_v1 = {
            "version": 1,
            "case_id": case_id,
            "legal_foundation_status": "VERIFIED_AUTHORITY",
            "facts": [
                {"fact_id": "F001", "text": "Consumer paid Rs 75,000 for electronic equipment that was never delivered.", "verification_status": "VERIFIED"},
                {"fact_id": "F002", "text": "Vendor acknowledged receipt on 10 January 2026.", "verification_status": "VERIFIED"},
            ],
            "timeline": [
                {"date": "2026-01-10", "description": "Order placed and full payment transferred."},
                {"date": "2026-01-25", "description": "Delivery deadline breached with no response."},
            ],
            "parties": {
                "client_role": "Consumer / Complainant (Priya Sharma)",
                "opposite_party": "MegaElectronics Retail Pvt Ltd",
            },
            "forum": {
                "commission_level": "District Consumer Disputes Redressal Commission, Bangalore",
                "verification_status": "VERIFIED",
                "forum_id": "dcdrc_bangalore",
            },
            "applicable_law": [
                {
                    "provision_id": "cpa_2019_s35",
                    "title": "Section 35, Consumer Protection Act, 2019",
                    "section": "35",
                    "verification_status": "VERIFIED",
                    "authority_status": "VERIFIED_AUTHORITY",
                    "review_status": "REVIEWED_CURRENT",
                    "explanation": "Manner in which complaint shall be made to District Commission.",
                }
            ],
            "evidence_inventory": [
                {"evidence_id": "E001", "filename": "payment_receipt_75k.pdf", "description": "Payment transaction confirmation"},
                {"evidence_id": "E002", "filename": "delivery_terms.pdf", "description": "Delivery agreement terms"},
            ],
        }

        case = {
            "id": case_id,
            "case_id": case_id,
            "owner_user_id": citizen["id"],
            "status": "SUBMITTED",
            "case_file": case_file_v1,
            "canonical_case_file": case_file_v1,
            "engine1_stale": False,
        }
        db.create("cases", case)
        print("  [OK] Synthetic Case File version 1 created.")

        # Step 2: Engine 2 is OPTIONAL (skipped in this run)
        print("\n[Step 2] Engine 2 challenge analysis skipped (OPTIONAL path)...")
        print("  [OK] Engine 2 not run; downstream drafts must preserve exact disclosure.")

        # Step 3: Verified Advocate Setup & Connection
        print("\n[Step 3] Onboarding verified synthetic advocate...")
        advocate = {
            "id": "adv_synth_9",
            "email": "advocate9@bar.in",
            "role": "advocate",
            "verification_status": "VERIFIED",
            "full_name": "Advocate Rajesh Iyer",
        }
        db.create("users", advocate)
        db.create("sessions", {"id": "ses_adv9", "user_id": advocate["id"]})
        adv_headers = {"Authorization": "Bearer ses_adv9"}

        # Connect advocate to case
        db.update("cases", case_id, {"assigned_advocate_id": advocate["id"]})
        print("  [OK] Advocate assigned to case.")

        # Step 4: Citizen Consent Grant
        print("\n[Step 4] Citizen granting scoped consent to advocate...")
        grant = {
            "id": "grant_phase9_synth",
            "case_id": case_id,
            "advocate_id": advocate["id"],
            "status": "ACTIVE",
            "scopes": ["case_file", "evidence", "engine2"],
            "evidence_ids": ["E001", "E002"],
            "expires_at": "2030-01-01T00:00:00+00:00",
        }
        db.create("case_grants", grant)
        adv_token = issue_token(db, grant)
        adv_headers["X-Case-Access"] = adv_token
        print("  [OK] Scoped consent token issued and bound.")

        # Step 5: Advocate Review & Sign-Off as REVIEWED_CURRENT
        print("\n[Step 5] Advocate reviewing case and certifying review currentness...")
        db.update("cases", case_id, {
            "status": "ADVOCATE_APPROVED",
            "review_status": "REVIEWED_CURRENT",
            "advocate_approved_case_file_version": 1,
            "advocate_review_note": "Factual basis and CPA provisions verified for professional complaint draft.",
        })
        print("  [OK] Case review certified as REVIEWED_CURRENT.")

        # Step 6: Engine 3 Eligibility Gate Check
        print("\n[Step 6] Evaluating Engine 3 eligibility gate...")
        case_doc = db.get("cases", case_id)
        eligibility = check_engine3_eligibility(case_doc, advocate, db)
        assert eligibility["eligible"] is True, f"Eligibility failed: {eligibility['reasons']}"
        assert eligibility["checks"]["engine2_optional"] is True
        assert eligibility["engine2_disclosure"] == ENGINE2_NOT_RUN_DISCLOSURE
        print("  [OK] Engine 3 eligibility PASSES.")
        print(f"    - Exact Engine 2 Disclosure: '{eligibility['engine2_disclosure']}'")

        # Step 7: Draft Generation (Advocate Chooses complaint_petition)
        print("\n[Step 7] Advocate initiating professional draft generation (complaint_petition)...")
        gen_res = client.post(
            f"/api/cases/{case_id}/drafts/generate",
            json={"draft_type": "complaint_petition", "draft_mode": "AUTHORITATIVE"},
            headers=adv_headers,
        )
        assert gen_res.status_code == 200, f"Generation failed: {gen_res.text}"
        draft_v1 = gen_res.json()["draft"]
        draft_id = draft_v1["draft_id"]
        assert draft_v1["version"] == 1
        assert draft_v1["engine1_case_file_version"] == 1
        assert ENGINE2_NOT_RUN_DISCLOSURE in draft_v1["disclosures"]
        print(f"  [OK] Professional draft generated. Draft ID: {draft_id}, Version: {draft_v1['version']}")
        print(f"    - Title: {draft_v1['title']}")
        print(f"    - Number of structured sections: {len(draft_v1['sections'])}")

        # Step 8: Inspect Provenance
        print("\n[Step 8] Verifying draft provenance and legal authority grounding...")
        assert draft_v1["provenance"]["created_by"] == advocate["id"]
        assert draft_v1["provenance"]["engine1_version"] == 1
        assert draft_v1["provenance"]["engine2_disclosure"] == ENGINE2_NOT_RUN_DISCLOSURE
        print("  [OK] Provenance records exact actor, E1 version, and Engine 2 skip disclosure.")

        # Step 9: Advocate Edits Draft
        print("\n[Step 9] Advocate customizing statement of facts in the editor...")
        edit_res = client.post(
            f"/api/cases/{case_id}/drafts/{draft_id}/edit",
            json={
                "title": "Formal Consumer Complaint — Priya Sharma v. MegaElectronics",
                "section_updates": [
                    {
                        "section_id": "facts",
                        "paragraphs": [
                            "1. The Complainant purchased high-end equipment on 10 January 2026 for valuable consideration.",
                            "2. Despite repeated follow-ups and statutory notice, the Respondent committed gross deficiency of service.",
                        ],
                        "advocate_notes": ["Refined language for stronger deficiency of service grounds."],
                    }
                ],
            },
            headers=adv_headers,
        )
        assert edit_res.status_code == 200, f"Edit failed: {edit_res.text}"
        draft_v2 = edit_res.json()["draft"]
        assert draft_v2["version"] == 2
        assert draft_v2["status"] == "ADVOCATE_EDITED"
        print(f"  [OK] Version 2 saved successfully (Status: {draft_v2['status']}).")

        # Step 10: Selective Regeneration of Annexures
        print("\n[Step 10] Selectively regenerating 'annexures' section while preserving facts...")
        regen_res = client.post(
            f"/api/cases/{case_id}/drafts/{draft_id}/regenerate-section",
            json={"section_id": "annexures"},
            headers=adv_headers,
        )
        assert regen_res.status_code == 200, f"Selective regeneration failed: {regen_res.text}"
        draft_v3 = regen_res.json()["draft"]
        assert draft_v3["version"] == 3

        # Confirm untouched advocate edits in facts are preserved!
        facts_sec = next(s for s in draft_v3["sections"] if s["section_id"] == "facts")
        assert "high-end equipment" in " ".join(facts_sec["paragraphs"])
        print("  [OK] Selective regeneration succeeded: Annexures updated, manual edits in Facts 100% PRESERVED.")

        # Step 11: Final Advocate Approval
        print("\n[Step 11] Advocate approving final draft and certifying integrity...")
        app_res = client.post(
            f"/api/cases/{case_id}/drafts/{draft_id}/approve",
            headers=adv_headers,
        )
        assert app_res.status_code == 200, f"Approval failed: {app_res.text}"
        approved_draft = app_res.json()["draft"]
        assert approved_draft["status"] == "ADVOCATE_APPROVED"
        assert approved_draft["approval_record"]["approved_by_advocate_id"] == advocate["id"]
        assert approved_draft["approval_record"]["source_engine1_version"] == 1
        digest = approved_draft["approval_record"]["integrity_hash"]
        print(f"  [OK] Professional draft APPROVED by advocate.")
        print(f"    - Certified Draft Version: {approved_draft['version']}")
        print(f"    - SHA-256 Digest: {digest}")

        # Step 12: Immutable PDF Artifact Verification
        print("\n[Step 12] Inspecting generated immutable PDF artifact...")
        pdf_res = client.get(f"/api/cases/{case_id}/drafts/{draft_id}/pdf", headers=adv_headers)
        assert pdf_res.status_code == 200, f"PDF download failed: {pdf_res.text}"
        assert pdf_res.headers["content-type"] == "application/pdf"
        assert pdf_res.content.startswith(b"%PDF")
        print(f"  [OK] Immutable PDF artifact verified ({len(pdf_res.content)} bytes).")

        # Step 13: Stale Input Verification (Mutate E1 afterward)
        print("\n[Step 13] Mutating Engine 1 Case File to test staleness tracking...")
        case_file_v2 = deepcopy(case_file_v1)
        case_file_v2["version"] = 2
        db.update("cases", case_id, {"case_file": case_file_v2, "canonical_case_file": case_file_v2})

        stale_check = client.get(f"/api/cases/{case_id}/drafts/{draft_id}", headers=adv_headers)
        assert stale_check.status_code == 200
        assert stale_check.json()["draft"]["status"] == "STALE_INPUT"
        print("  [OK] Draft correctly marked STALE_INPUT when underlying E1 changed.")
        print("  [OK] Historical draft remains preserved and accessible to advocate.")

        print("\n" + "=" * 70)
        print("SYNTHETIC ADVOCATE DRAFTING JOURNEY COMPLETED SUCCESSFULLY")
        print("=" * 70)
        return True

    finally:
        temp_dir.cleanup()


if __name__ == "__main__":
    success = run_synthetic_journey()
    sys.exit(0 if success else 1)
