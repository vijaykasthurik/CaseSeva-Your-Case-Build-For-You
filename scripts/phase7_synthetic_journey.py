"""Phase 7 - End-to-End Synthetic Citizen Journey Script.

Exercises the complete citizen journey:
1. Citizen signup / login
2. Create case
3. Provide citizen-friendly narrative (no legal categories or jargon required)
4. Upload synthetic evidence document
5. Run Engine 1 processing
6. Verify Case Overview (facts, timeline, parties, issues, honest legal foundation status)
7. Strengthen My Case (Engine 2 challenge analysis)
8. Inspect challenge summary (opposing arguments, evidence gaps, risks, no win probability)
9. Open Get Legal Help
10. Browse verified advocate directory
11. Send connection request
12. Advocate accepts connection
13. Verify case remains completely inaccessible before explicit citizen consent
14. Citizen grants explicit consent
15. Verify advocate can access structured handoff contract bound to exact Case File version
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import copy
import hashlib
import json
import tempfile
from types import SimpleNamespace
from uuid import uuid4

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
from backend.routes.sharing import router as sharing_router
from backend.services.engine1 import run_engine1
from backend.services.engine2 import run_engine2


def run_journey():
    print("=" * 60)
    print("STARTING PHASE 7 SYNTHETIC CITIZEN JOURNEY")
    print("=" * 60)

    # Isolated temporary environment
    with tempfile.TemporaryDirectory() as tmpdir:
        db = MockDatabaseAdapter(tmpdir + "/database.json")
        storage = MockStorageAdapter(tmpdir + "/uploads")
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
        for r in (cases_router, auth_router, analysis_router, engines_router, advocates_router, sharing_router, clarification_router):
            app.include_router(r)
        client = TestClient(app)

        # Step 1: Citizen signup/login
        print("\n[Step 1] Citizen signup & login...")
        citizen_payload = {
            "full_name": "Meera Sundaram",
            "email": "meera.citizen@example.in",
            "password": "SecurePassword123!",
            "mobile_number": "9840112233",
            "preferred_language": "English",
            "state": "Tamil Nadu",
            "district_city": "Chennai",
            "role": "client",
        }
        res = client.post("/api/auth/signup", json=citizen_payload)
        assert res.status_code in (200, 201), f"Signup failed: {res.text}"
        citizen_data = res.json()
        citizen_token = citizen_data["session_token"]
        citizen_id = citizen_data["user"]["id"]
        c_headers = {"Authorization": f"Bearer {citizen_token}"}
        print(f" -> Citizen created: {citizen_id} ({citizen_data['user']['full_name']})")

        # Step 1b: Create a synthetic verified advocate
        print("\n[Step 1b] Setting up verified advocate in test environment...")
        adv_payload = {
            "full_name": "Adv. K. Swaminathan",
            "email": "swaminathan.adv@example.in",
            "password": "AdvocatePass123!",
            "mobile_number": "9840998877",
            "preferred_language": "English",
            "state": "Tamil Nadu",
            "district_city": "Chennai",
            "role": "advocate",
            "bar_council": "Bar Council of Tamil Nadu and Puducherry",
            "enrolment_number": "MS/9876/2015",
            "enrolment_year": 2015,
            "place_of_practice": "Chennai",
            "practice_domains": ["CONSUMER", "CONTRACT"],
            "languages": ["English", "Tamil"],
            "court_region": "Madras High Court / Chennai District Consumer Forum",
        }
        res_adv = client.post("/api/auth/signup", json=adv_payload)
        assert res_adv.status_code in (200, 201), f"Advocate signup failed: {res_adv.text}"
        adv_data = res_adv.json()
        adv_token = adv_data["session_token"]
        adv_id = adv_data["user"]["id"]
        a_headers = {"Authorization": f"Bearer {adv_token}"}
        # Mark advocate as verified in isolated test database
        db.update("users", adv_id, {
            "verification_status": "VERIFIED",
            "verification_documents": [{"filename": "bar_enrolment_cert.pdf", "storage_key": "private/adv_cert.pdf"}],
        })
        print(f" -> Verified advocate created: {adv_id} (MS/9876/2015)")

        # Step 2: Citizen creates a case
        print("\n[Step 2] Citizen creates a new case...")
        res_case = client.post("/api/cases", headers=c_headers)
        assert res_case.status_code == 200, f"Case creation failed: {res_case.text}"
        case = res_case.json()["case"]
        case_id = case["case_id"]
        print(f" -> Case created: {case_id}, status: {case['status']}")

        # Step 3: Citizen tells CaseSeva what happened (plain narrative without legal categories)
        print("\n[Step 3] Citizen provides factual narrative (no legal jargon)...")
        narrative = (
            "I ordered a high-end refrigerator from SuperTech Retail on 15 July 2026 for Rs. 62,000. "
            "It was delivered on 20 July 2026. Within 3 days the cooling stopped working completely. "
            "I contacted customer care four times and their technician visited on 28 July 2026 and confirmed "
            "a compressor failure, promising replacement in 7 days. Despite multiple follow-ups, they refused "
            "either replacement or refund."
        )
        patch_res = client.patch(
            f"/api/cases/{case_id}",
            headers=c_headers,
            json={"stage": "NEW_CONSULTATION", "client_story": narrative},
        )
        assert patch_res.status_code == 200, f"Update story failed: {patch_res.text}"
        print(" -> Narrative submitted and preserved immutably.")

        # Step 4: Upload synthetic evidence
        print("\n[Step 4] Citizen uploads evidence...")
        sample_invoice = (
            b"INVOICE\n"
            b"Vendor: SuperTech Retail Chennai\n"
            b"Customer: Meera Sundaram\n"
            b"Item: 450L Frost Free Refrigerator\n"
            b"Amount Paid: INR 62,000\n"
            b"Date: 15-07-2026\n"
            b"Invoice Number: STR-2026-8819\n"
        )
        invoice_hash = hashlib.sha256(sample_invoice).hexdigest()
        up_res = client.post(
            f"/api/cases/{case_id}/evidence",
            headers=c_headers,
            files={"file": ("supertech_invoice.txt", sample_invoice, "text/plain")},
        )
        assert up_res.status_code == 200, f"Upload failed: {up_res.text}"
        evidence_info = up_res.json()["evidence"]
        print(f" -> Evidence uploaded: {evidence_info['filename']} (evidence_id: {evidence_info['evidence_id']})")
        assert "storage_key" not in evidence_info, "Private storage key must not leak to citizen projection!"

        # Step 5: Engine 1 processing
        print("\n[Step 5] Running Engine 1 processing...")
        run_engine1(app, case_id)
        print(" -> Engine 1 completed. Canonical Case File constructed.")

        # Step 6: Case Overview
        print("\n[Step 6] Inspecting citizen Case Overview...")
        ov_res = client.get(f"/api/cases/{case_id}", headers=c_headers)
        assert ov_res.status_code == 200
        case_data = ov_res.json()["case"]
        overview = case_data.get("overview")
        assert overview is not None
        assert overview["case_file_version"] == 1
        print(f" -> Case File version: {overview['case_file_version']}")
        print(f" -> Facts extracted: {len(overview.get('key_facts', []))}")
        print(f" -> Legal foundation status: {overview.get('legal_foundation_status')}")
        print(f" -> Honest guidance next step: '{overview.get('next_step')}'")
        # Ensure no win prediction
        ov_text = json.dumps(overview).lower()
        for forbidden in ("win probability", "success percentage", "victory chance", "win_percentage", "win_rate", "case_score", "likely winner"):
            assert forbidden not in ov_text, f"Forbidden prediction term '{forbidden}' present in overview!"

        # Step 7 & 8: Strengthen My Case (Engine 2)
        print("\n[Step 7 & 8] Citizen triggers 'Strengthen My Case' (Engine 2)...")
        run_engine2(app, case_id)
        ov2_res = client.get(f"/api/cases/{case_id}", headers=c_headers)
        ov2 = ov2_res.json()["case"]["overview"]
        assert ov2["argument_analysis_run"] is True
        print(f" -> Argument analysis run: {ov2['argument_analysis_run']}")
        print(f" -> Argument analysis note: {ov2['argument_analysis_note']}")
        print(f" -> Key challenges count: {len(ov2.get('key_challenges', []))}")
        print(f" -> Unresolved contradictions: {len(ov2.get('unresolved_contradictions', []))}")
        print(f" -> Preparation actions count: {len(ov2.get('preparation_actions', []))}")
        # Verify no outcome prediction in E2 report
        e2_text = json.dumps(ov2).lower()
        for forbidden in ("win probability", "success percentage", "victory chance", "win_percentage", "win_rate", "case_score", "likely winner"):
            assert forbidden not in e2_text, f"Forbidden prediction term '{forbidden}' present after E2!"

        # Step 9: Get Legal Help - browse advocates
        print("\n[Step 9] Citizen opens 'Get Legal Help' and browses verified advocates...")
        adv_list_res = client.get("/api/advocates", headers=c_headers)
        assert adv_list_res.status_code == 200
        advocates = adv_list_res.json()["advocates"]
        print(f" -> Available verified advocates: {len(advocates)}")
        matched_adv = next((a for a in advocates if a["id"] == adv_id), None)
        assert matched_adv is not None, "Verified advocate must appear in public directory!"
        assert "verification_documents" not in matched_adv, "Advocate verification documents must not leak!"
        assert matched_adv["verification_status"] == "VERIFIED"
        print(f" -> Selected advocate: {matched_adv['full_name']} ({matched_adv['court_region']})")

        # Step 10 & 11: Send connection request
        print("\n[Step 10 & 11] Citizen sends connection request...")
        req_res = client.post(
            f"/api/cases/{case_id}/request-advocate",
            headers=c_headers,
            json={"advocate_id": adv_id},
        )
        assert req_res.status_code == 200
        case_after_req = req_res.json()["case"]
        assert case_after_req["status"] == "AWAITING_ADVOCATE"
        print(" -> Request sent. Case status: AWAITING_ADVOCATE")

        # Step 12: Advocate accepts connection request
        print("\n[Step 12] Advocate accepts connection request...")
        acc_res = client.post(f"/api/advocate/requests/{case_id}/accept", headers=a_headers)
        assert acc_res.status_code == 200
        print(" -> Advocate accepted the connection request.")

        # Step 13: Verify case remains INACCESSIBLE before explicit consent
        print("\n[Step 13] Verifying case is NOT accessible before citizen consent...")
        unconsented_view = client.get(f"/api/advocate/cases/{case_id}", headers=a_headers)
        assert unconsented_view.status_code == 403, f"Expected 403 Forbidden without consent, got {unconsented_view.status_code}"
        token_attempt = client.post(f"/api/advocate/cases/{case_id}/access-token", headers=a_headers)
        assert token_attempt.status_code == 403, f"Expected 403 Forbidden without consent, got {token_attempt.status_code}"
        print(" -> Access strictly blocked (HTTP 403). Advocate acceptance does NOT equal case sharing consent.")

        # Step 14: Citizen grants explicit consent
        print("\n[Step 14] Citizen grants explicit consent...")
        consent_res = client.post(
            f"/api/cases/{case_id}/sharing",
            headers=c_headers,
            json={
                "scopes": ["story", "case_file", "evidence"],
                "evidence_ids": [evidence_info["evidence_id"]],
                "expires_in_hours": 72,
            },
        )
        assert consent_res.status_code == 200
        grant = consent_res.json()["grant"]
        print(f" -> Consent grant recorded: {grant['id']}")
        print(f" -> Grant bound Case File version: {grant.get('engine1_case_file_version')}")

        # Step 15: Advocate accesses structured handoff contract
        print("\n[Step 15] Advocate exchanges access token and accesses structured handoff contract...")
        tok_res = client.post(f"/api/advocate/cases/{case_id}/access-token", headers=a_headers)
        assert tok_res.status_code == 200
        access_token = tok_res.json()["access_token"]

        handoff_res = client.get(
            f"/api/advocate/cases/{case_id}/handoff",
            headers={**a_headers, "X-Case-Access": access_token},
        )
        assert handoff_res.status_code == 200
        handoff = handoff_res.json()["handoff"]
        assert handoff["case_id"] == case_id
        assert handoff["engine1_case_file_version"] == 1
        assert handoff["engine2_skipped"] is False
        assert "Case File" in handoff["engine2_disclosure"]
        assert handoff["consent_id"] == grant["id"]
        assert handoff["consent_scopes"] == grant["scopes"]
        assert handoff["provenance"]["origin"] is not None
        print(f" -> Handoff contract verified: Case File v{handoff['engine1_case_file_version']}, E2 v{handoff['engine2_version']}")

        # Verify evidence integrity
        case_final = db.get("cases", case_id)
        ev_item = next(e for e in case_final["evidence"] if e["evidence_id"] == evidence_info["evidence_id"])
        ev_hash = ev_item.get("content_hash") or ev_item.get("extraction", {}).get("content_hash")
        assert ev_hash == invoice_hash, "Original evidence content hash was mutated!"
        print(f" -> Evidence hash verified immutable: {ev_hash[:16]}...")

        # Verify no Engine 3 invocation
        assert "draft_document" not in case_final, "Engine 3 must not run automatically!"
        assert "engine3" not in case_final
        print(" -> Confirmed no automatic Engine 3 invocation.")

    print("\n" + "=" * 60)
    print("PHASE 7 SYNTHETIC CITIZEN JOURNEY: SUCCESSFUL")
    print("=" * 60)


if __name__ == "__main__":
    run_journey()
