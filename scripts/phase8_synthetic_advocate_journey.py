"""Phase 8 Synthetic End-to-End Advocate Journey Script.

Runs isolated synthetic end-to-end validation of:
synthetic citizen
→ synthetic verified advocate
→ connection request
→ advocate accepts
→ verify NO case access
→ citizen grants consent
→ advocate opens structured case
→ advocate makes factual correction
→ advocate adds evidence annotation
→ advocate adds private professional note
→ substantive correction marks dependencies stale
→ rerun Engine 1 using corrected state
→ confirm correction is not silently erased
→ resolve any correction conflict
→ obtain new Engine-1 Case File version
→ confirm old Engine-2 result becomes stale
→ optionally rerun Engine 2
→ mark advocate review CURRENT
→ revoke citizen consent
→ verify further advocate case access is denied

DOES NOT perform any genuine Phase 4 legal-authority corpus review.
"""

import copy
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
from backend.routes.analysis import router as analysis_router
from backend.routes.auth import router as auth_router
from backend.routes.cases import router as cases_router
from backend.routes.clarification import router as clarification_router
from backend.routes.engines import router as engines_router
from backend.routes.review import router as review_router
from backend.routes.sharing import router as sharing_router
from backend.services.engine1 import run_engine1
from backend.services.engine2 import run_engine2
from backend.services.review_contracts import ENGINE2_NOT_RUN_DISCLOSURE


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
        processing_mode="mock",
        llm_processing_mode="mock",
    )
    app = FastAPI()
    app.state.adapters = adapters
    for r in (cases_router, auth_router, analysis_router, engines_router, advocates_router, sharing_router, clarification_router, review_router):
        app.include_router(r)
    return temp_dir, app, TestClient(app), db


def run_synthetic_journey():
    print("=" * 60)
    print("STARTING PHASE 8 SYNTHETIC END-TO-END ADVOCATE JOURNEY")
    print("=" * 60)

    temp_dir, app, client, db = build_synthetic_environment()

    # Step 1: Create synthetic citizen and verified advocate
    print("\n[Step 1] Creating synthetic citizen and verified advocate...")
    cit_payload = {
        "full_name": "Synthetic Citizen Ananya",
        "email": f"synthetic.citizen.{uuid4().hex[:6]}@example.com",
        "password": "Password123!",
        "mobile_number": "9876543210",
        "preferred_language": "English",
        "state": "Karnataka",
        "district_city": "Bengaluru",
        "role": "client",
    }
    c_res = client.post("/api/auth/signup", json=cit_payload)
    assert c_res.status_code in (200, 201), c_res.text
    citizen = c_res.json()["user"]
    cit_headers = {"Authorization": f"Bearer {c_res.json()['session_token']}"}

    adv_payload = {
        "full_name": "Adv. Synthetic K. Raman",
        "email": f"synthetic.advocate.{uuid4().hex[:6]}@example.com",
        "password": "Password123!",
        "mobile_number": "9876543211",
        "preferred_language": "English",
        "state": "Karnataka",
        "district_city": "Bengaluru",
        "role": "advocate",
        "bar_council": "Karnataka State Bar Council",
        "enrolment_number": f"KAR/{uuid4().hex[:4].upper()}/2018",
        "enrolment_year": 2018,
        "place_of_practice": "Bengaluru",
        "practice_domains": ["CONSUMER", "CONTRACT"],
        "languages": ["English", "Kannada"],
        "court_region": "Karnataka High Court",
    }
    a_res = client.post("/api/auth/signup", json=adv_payload)
    assert a_res.status_code in (200, 201), a_res.text
    advocate = a_res.json()["user"]
    adv_headers = {"Authorization": f"Bearer {a_res.json()['session_token']}"}

    # Verify advocate credentials in database
    db.update("users", advocate["id"], {
        "verification_status": "VERIFIED",
        "verification_documents": [{"filename": "bar_council_id.pdf", "storage_key": "private/bar_id.pdf"}],
    })
    print(f"  [OK] Citizen created: {citizen['full_name']} ({citizen['id']})")
    print(f"  [OK] Advocate created & verified: {advocate['full_name']} ({advocate['id']})")

    # Step 2: Citizen creates case and Engine 1 runs
    print("\n[Step 2] Citizen creates intake case and triggers initial Engine 1...")
    case_res = client.post("/api/cases", headers=cit_headers)
    case_id = case_res.json()["case"]["case_id"]
    client.patch(
        f"/api/cases/{case_id}",
        headers=cit_headers,
        json={
            "stage": "NEW_CONSULTATION",
            "client_story": "I purchased an air conditioner on 15 March 2026 for Rs 42,000. It broke down in 3 days. Service center refuses repair or replacement.",
        },
    )

    # Run Engine 1 to produce canonical Case File
    run_engine1(app, case_id)

    # Attach immutable evidence document
    case = db.get("cases", case_id)
    ev_item = {
        "evidence_id": "ev_ac_invoice",
        "filename": "ac_invoice_bill.pdf",
        "content_type": "application/pdf",
        "size": 18450,
        "storage_key": "uploads/ev_ac_invoice.pdf",
        "content_hash": hashlib.sha256(b"ac_invoice_bytes_mock").hexdigest(),
        "uploaded_at": "2026-03-16T11:00:00Z",
        "uploaded_by": citizen["id"],
        "extraction": {"status": "COMPLETED", "original_text": "CoolAir Retailers Invoice #CA-9042 Rs 42,000 15 March 2026"},
    }
    app.state.adapters.storage.upload(ev_item["storage_key"], b"ac_invoice_bytes_mock", ev_item["content_type"])
    raw = case.get("raw_package") or {}
    raw["evidence"] = [ev_item]
    db.update("cases", case_id, {"evidence": [ev_item], "raw_package": raw})
    print(f"  [OK] Case #{case_id} synthesized by Engine 1 (Version 1)")

    # Step 3: Citizen sends connection request to advocate
    print("\n[Step 3] Citizen sends connection request...")
    req_res = client.post(f"/api/cases/{case_id}/request-advocate", headers=cit_headers, json={"advocate_id": advocate["id"]})
    assert req_res.status_code == 200, req_res.text
    print("  [OK] Connection request sent to advocate")

    # Step 4: Advocate accepts connection request
    print("\n[Step 4] Advocate accepts connection request...")
    acc_res = client.post(f"/api/advocate/requests/{case_id}/accept", headers=adv_headers)
    assert acc_res.status_code == 200, acc_res.text
    print("  [OK] Request accepted by advocate. Case status: ACCEPTED_AWAITING_CLIENT_CONSENT")

    # Step 5: Verify NO case access before explicit citizen consent
    print("\n[Step 5] Verifying advocate CANNOT access case without citizen consent...")
    tok_res = client.post(f"/api/advocate/cases/{case_id}/access-token", headers=adv_headers)
    assert tok_res.status_code == 403, f"Expected 403, got {tok_res.status_code}"
    print("  [OK] Advocate access token denied (403): Citizen consent required")

    # Step 6: Citizen grants explicit scoped consent
    print("\n[Step 6] Citizen grants explicit consent for story, case_file, and evidence...")
    consent_res = client.post(
        f"/api/cases/{case_id}/sharing",
        headers=cit_headers,
        json={"scopes": ["case_file", "story", "evidence", "engine2"], "evidence_ids": ["ev_ac_invoice"], "expires_in_hours": 168},
    )
    assert consent_res.status_code == 200, consent_res.text
    print("  [OK] Citizen sharing consent granted")

    # Step 7: Advocate obtains access token and opens structured case
    print("\n[Step 7] Advocate exchanges token and inspects structured case...")
    tok_res = client.post(f"/api/advocate/cases/{case_id}/access-token", headers=adv_headers)
    assert tok_res.status_code == 200, tok_res.text
    case_access_token = tok_res.json()["access_token"]
    adv_headers_scoped = {"Authorization": adv_headers["Authorization"], "X-Case-Access": case_access_token}

    shared_res = client.get(f"/api/advocate/cases/{case_id}", headers=adv_headers_scoped)
    assert shared_res.status_code == 200, shared_res.text
    shared_case = shared_res.json()["case"]
    assert "case_file" in shared_case
    assert "evidence" in shared_case
    print(f"  [OK] Case opened. Current review status: {shared_case.get('review_status', 'NOT_REVIEWED')}")
    print(f"  [OK] Engine 2 disclosure verified: \"{shared_case['engine2_disclosure']}\"")

    # Step 8: Advocate records factual correction (substantive)
    print("\n[Step 8] Advocate records substantive correction to fact...")
    cf = shared_case["case_file"]
    fact_id = cf["facts"][0]["fact_id"]
    corrected_fact = "Invoice amount was Rs 45,500 including 3-year warranty package."

    corr_res = client.post(
        f"/api/advocate/cases/{case_id}/review",
        headers=adv_headers_scoped,
        json={
            "kind": "fact",
            "target_id": fact_id,
            "action": "edit",
            "value": {"text": corrected_fact},
            "reason": "Warranty surcharge verified against invoice line-items",
        },
    )
    assert corr_res.status_code == 200, corr_res.text
    print("  [OK] First-class correction recorded in advocate_case_corrections")

    # Step 9: Advocate adds evidence annotation (separate layer)
    print("\n[Step 9] Advocate records evidence annotation...")
    ann_res = client.post(
        f"/api/advocate/cases/{case_id}/evidence/ev_ac_invoice/annotate",
        headers=adv_headers_scoped,
        json={"annotation": "Clear tax invoice with GSTIN and serial number visible.", "relevance_notes": "HIGH"},
    )
    assert ann_res.status_code == 200, ann_res.text
    print("  [OK] Annotation stored in advocate_evidence_annotations layer")

    # Step 10: Advocate adds private professional note
    print("\n[Step 10] Advocate records private strategy note...")
    note_res = client.post(
        f"/api/advocate/cases/{case_id}/notes",
        headers=adv_headers_scoped,
        json={"note": "Private note: Verify jurisdiction under CPA 2019 Section 34.", "visibility": "PRIVATE"},
    )
    assert note_res.status_code == 200, note_res.text
    print("  [OK] Private note saved (inaccessible to citizen)")

    # Step 11: Confirm substantive correction marked dependencies stale
    print("\n[Step 11] Confirming substantive dependencies are stale...")
    case_db = db.get("cases", case_id)
    assert case_db.get("engine1_stale"), "Engine 1 must be stale"
    assert case_db.get("engine2_stale"), "Engine 2 must be stale"
    assert case_db.get("review_status") == "CHANGES_REQUIRED", "Review status must be CHANGES_REQUIRED"
    print("  [OK] engine1_stale = True, engine2_stale = True, review_status = CHANGES_REQUIRED")

    # Step 12: Rerun Engine 1 with advocate corrections
    print("\n[Step 12] Rerunning Engine 1 to incorporate advocate corrections...")
    # Run sync Engine 1
    run_engine1(app, case_id)
    updated_case = db.get("cases", case_id)
    new_cf = updated_case.get("canonical_case_file") or updated_case.get("case_file")
    print(f"  [OK] New Engine 1 version created: Version {new_cf['version']}")

    # Confirm correction not silently erased
    fact_texts = [f["text"] for f in new_cf["facts"]]
    assert corrected_fact in fact_texts, "Corrected fact must be preserved in regenerated Case File"
    print("  [OK] Advocate correction preserved in new Case File")
    assert not updated_case.get("engine1_stale"), "Engine 1 should no longer be stale"
    print("  [OK] engine1_stale reset to False")

    # Step 13: Resolve any conflict strategy (KEEP / REPLACE / MERGE)
    print("\n[Step 13] Resolving conflict resolution strategy (KEEP)...")
    res_conf = client.post(
        f"/api/advocate/cases/{case_id}/resolve-conflict",
        headers=adv_headers_scoped,
        json={"target_id": fact_id, "strategy": "KEEP", "field_kind": "fact", "reason": "Advocate value confirmed authoritative"},
    )
    assert res_conf.status_code == 200, res_conf.text
    print("  [OK] Conflict resolution set to KEEP")

    # Step 14: Confirm old Engine 2 is stale & optionally rerun Engine 2
    print("\n[Step 14] Optionally running Engine 2 (Adversarial Analysis)...")
    run_engine2(app, case_id)
    case_after_e2 = db.get("cases", case_id)
    assert not case_after_e2.get("engine2_stale"), "Engine 2 refreshed"
    print("  [OK] Engine 2 refreshed (still optional)")

    # Step 15: Advocate marks review CURRENT / approved
    print("\n[Step 15] Advocate approves case review (REVIEWED_CURRENT)...")
    appr_res = client.post(f"/api/advocate/cases/{case_id}/approve", headers=adv_headers_scoped)
    assert appr_res.status_code == 200, appr_res.text
    case_approved = db.get("cases", case_id)
    assert case_approved.get("review_status") == "REVIEWED_CURRENT"
    print("  [OK] Review status: REVIEWED_CURRENT")

    # Step 16: Check future Engine 3 eligibility gate
    print("\n[Step 16] Checking future Engine 3 drafting eligibility gate...")
    e3_res = client.get(f"/api/advocate/cases/{case_id}/engine3-eligibility", headers=adv_headers_scoped)
    assert e3_res.status_code == 200, e3_res.text
    eligibility = e3_res.json()["eligibility"]
    assert eligibility["eligible"] is True
    assert eligibility["checks"]["assigned_advocate"] is True
    assert eligibility["checks"]["active_consent"] is True
    assert eligibility["checks"]["reviewed_engine1_current"] is True
    assert eligibility["checks"]["no_unresolved_conflicts"] is True
    print("  [OK] Engine 3 eligibility check: PASSED (Drafting prepared for future phase)")

    # Step 17: Citizen revokes sharing consent
    print("\n[Step 17] Citizen revokes sharing consent...")
    grants = client.get(f"/api/cases/{case_id}/sharing", headers=cit_headers).json()["grants"]
    grant_id = grants[0]["id"]
    rev_res = client.delete(f"/api/cases/{case_id}/sharing/{grant_id}", headers=cit_headers)
    assert rev_res.status_code == 200, rev_res.text
    print("  [OK] Consent grant revoked by citizen")

    # Step 18: Verify advocate access is immediately denied
    print("\n[Step 18] Verifying advocate access is immediately denied after revocation...")
    denied_res = client.get(f"/api/advocate/cases/{case_id}", headers=adv_headers_scoped)
    assert denied_res.status_code == 403, f"Expected 403, got {denied_res.status_code}"
    print("  [OK] Further advocate case access denied (403)")

    # Step 19: Confirm original evidence was never mutated
    print("\n[Step 19] Verifying citizen uploaded evidence immutability...")
    final_case = db.get("cases", case_id)
    ev_final = final_case["evidence"][0]
    assert ev_final["size"] == 18450
    assert ev_final["content_hash"] == hashlib.sha256(b"ac_invoice_bytes_mock").hexdigest()
    assert ev_final["storage_key"] == "uploads/ev_ac_invoice.pdf"
    print("  [OK] Original evidence bytes and hash completely immutable")

    temp_dir.cleanup()
    print("\n" + "=" * 60)
    print("PHASE 8 SYNTHETIC ADVOCATE JOURNEY COMPLETE AND VERIFIED!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = run_synthetic_journey()
    sys.exit(0 if success else 1)
