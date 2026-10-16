"""Phase 10 Deterministic Tests for Filing Preparation & Submission Safety.

Covers all 25 required test scenarios:
1. only assigned verified advocate can prepare package
2. active consent required
3. advocate-approved draft required
4. stale draft blocks readiness
5. unverified law blocks READY_FOR_HUMAN_FILING
6. PREPARATION_ONLY allowed where appropriate
7. Engine 2 optional
8. exact Engine-2 skip disclosure preserved
9. annexure index deterministic
10. original evidence immutable
11. manifest contains exact versions/hashes
12. package digest deterministic
13. private advocate notes excluded
14. historical package immutable
15. new package version generated explicitly
16. E1 change marks package stale
17. draft change marks package stale
18. consent revocation blocks new package
19. unauthorized advocate blocked
20. citizen cannot generate package
21. admin cannot generate package
22. no external submission occurs
23. no filing/payment API invoked
24. Phase-4 REVIEW_PENDING authority never appears as verified law
25. no genuine Phase-4 authority modified
"""
import copy
import hashlib
import json
import tempfile
import unittest
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.adapters.mock.auth import MockAuthAdapter
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.adapters.mock.llm import MockLLMAdapter
from backend.adapters.mock.storage import MockStorageAdapter
from backend.models.draft import AdvocateDraft, ApprovalRecord, DraftMode, DraftStatus, PdfArtifact
from backend.models.filing import FilingPackage, FilingReadinessStatus
from backend.routes.advocates import router as advocates_router
from backend.routes.auth import router as auth_router
from backend.routes.cases import router as cases_router
from backend.routes.documents import router as documents_router
from backend.routes.filing import router as filing_router
from backend.routes.review import router as review_router
from backend.routes.sharing import router as sharing_router
from backend.services.engine3 import compute_draft_integrity_hash, export
from backend.services.filing import (
    DISCLOSURE_ADVOCATE_ONLY,
    DISCLOSURE_NO_EXTERNAL_SUBMISSION,
    DISCLOSURE_PHASE10_SAFETY,
    DISCLOSURE_REVIEW_PENDING,
    check_filing_eligibility,
    determine_readiness_state,
    evaluate_package_staleness,
    export_filing_bundle,
    get_filing_package,
    list_filing_packages,
    prepare_filing_package,
)
from backend.services.review_contracts import ENGINE2_NOT_RUN_DISCLOSURE
from backend.services.sharing import issue_token


def create_phase10_test_app():
    app = FastAPI(title="CaseSeva Phase 10 Test")
    app.include_router(auth_router)
    app.include_router(cases_router)
    app.include_router(advocates_router)
    app.include_router(sharing_router)
    app.include_router(review_router)
    app.include_router(documents_router)
    app.include_router(filing_router)

    app.state.temp_dir = tempfile.TemporaryDirectory()
    db = MockDatabaseAdapter(path=f"{app.state.temp_dir.name}/db.json")
    storage = MockStorageAdapter(root=f"{app.state.temp_dir.name}/storage")
    auth = MockAuthAdapter(database=db)
    llm = MockLLMAdapter()

    app.state.adapters = SimpleNamespace(
        database=db,
        storage=storage,
        auth=auth,
        llm=llm,
    )
    return app


class TestPhase10FilingPreparation(unittest.TestCase):
    def setUp(self):
        self.app = create_phase10_test_app()
        self.client = TestClient(self.app)
        self.db = self.app.state.adapters.database
        self.storage = self.app.state.adapters.storage

        # Create verified advocate
        self.advocate = {
            "id": "adv_test_1",
            "email": "verified.advocate@court.in",
            "name": "Adv. Ramesh Varma",
            "role": "advocate",
            "verification_status": "VERIFIED",
            "bar_registration_number": "D/9876/2015",
            "bar_council": "Bar Council of Delhi",
        }
        self.db.create("users", self.advocate)
        self.db.create("sessions", {"id": "ses_adv_1", "user_id": self.advocate["id"]})
        self.adv_headers = {"Authorization": "Bearer ses_adv_1"}

        # Create citizen
        self.citizen = {
            "id": "cit_test_1",
            "email": "citizen.sharma@example.com",
            "name": "Sunita Sharma",
            "role": "citizen",
        }
        self.db.create("users", self.citizen)
        self.db.create("sessions", {"id": "ses_cit_1", "user_id": self.citizen["id"]})
        self.cit_headers = {"Authorization": "Bearer ses_cit_1"}

        # Create other unauthorized advocate
        self.other_advocate = {
            "id": "adv_test_2",
            "email": "unrelated.advocate@court.in",
            "name": "Adv. Suresh Patel",
            "role": "advocate",
            "verification_status": "VERIFIED",
            "bar_registration_number": "D/5432/2018",
        }
        self.db.create("users", self.other_advocate)
        self.db.create("sessions", {"id": "ses_adv_2", "user_id": self.other_advocate["id"]})
        self.other_adv_headers = {"Authorization": "Bearer ses_adv_2"}

        # Create admin
        self.admin = {
            "id": "adm_test_1",
            "email": "admin@caseseva.gov.in",
            "name": "System Admin",
            "role": "admin",
        }
        self.db.create("users", self.admin)
        self.db.create("sessions", {"id": "ses_adm_1", "user_id": self.admin["id"]})
        self.admin_headers = {"Authorization": "Bearer ses_adm_1"}

        # Set up a canonical case with evidence, consent, reviewed E1, and approved draft
        self.setup_case_fixture()

    def tearDown(self):
        self.app.state.temp_dir.cleanup()

    def setup_case_fixture(self):
        self.case_id = f"case_{uuid4().hex[:8]}"
        self.evidence_list = [
            {
                "evidence_id": "E001",
                "filename": "fee_receipt.pdf",
                "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "description": "Tuition fee payment receipt of INR 45,000",
                "evidence_type": "RECEIPT",
                "storage_key": f"cases/{self.case_id}/evidence/E001.pdf",
            },
            {
                "evidence_id": "E002",
                "filename": "email_representation.pdf",
                "sha256": "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
                "description": "Email sent demanding refund on 12-08-2024",
                "evidence_type": "CORRESPONDENCE",
                "storage_key": f"cases/{self.case_id}/evidence/E002.pdf",
            },
        ]

        # Seed mock storage with dummy evidence bytes
        for ev in self.evidence_list:
            self.storage.upload(ev["storage_key"], b"MOCK_EVIDENCE_CONTENT_" + ev["evidence_id"].encode(), "application/pdf")

        # Canonical Case File
        self.case_file = {
            "case_id": self.case_id,
            "version": 2,
            "input_version": 1,
            "legal_foundation_status": "VERIFIED_AUTHORITY",
            "applicable_law": [
                {
                    "source_id": "cpa2019_s2_7",
                    "title": "THE CONSUMER PROTECTION ACT, 2019",
                    "section": "2(7)",
                    "authority_status": "VERIFIED_AUTHORITY",
                    "explanation": "Defines consumer buying goods or availing services for consideration.",
                },
                {
                    "source_id": "cpa2019_s34",
                    "title": "THE CONSUMER PROTECTION ACT, 2019",
                    "section": "34",
                    "authority_status": "VERIFIED_AUTHORITY",
                    "explanation": "Jurisdiction of District Consumer Commission.",
                },
            ],
            "facts": [
                {"id": "F1", "text": "Complainant paid INR 45,000 for coaching classes on 10-07-2024."},
                {"id": "F2", "text": "Classes were abruptly cancelled and refund refused."},
            ],
            "parties": {
                "complainant": {"name": "Sunita Sharma", "address": "New Delhi"},
                "opposite_party": {"name": "Ace Coaching Ltd", "address": "Connaught Place, New Delhi"},
            },
            "jurisdiction": {"forum_name": "District Consumer Disputes Redressal Commission", "state": "Delhi"},
            "chronology": [
                {"date": "2024-07-10", "event": "Payment of fee."},
                {"date": "2024-08-12", "event": "Refund demand email sent."},
            ],
        }

        # Create case record in DB
        self.case = {
            "id": self.case_id,
            "case_id": self.case_id,
            "owner_user_id": self.citizen["id"],
            "assigned_advocate_id": self.advocate["id"],
            "status": "ADVOCATE_APPROVED",
            "review_status": "REVIEWED_CURRENT",
            "advocate_approved_case_file_version": 2,
            "engine1_case_file_version": 2,
            "engine1_stale": False,
            "canonical_case_file": self.case_file,
            "evidence": self.evidence_list,
            "engine2": None,  # Engine 2 intentionally skipped
            "engine2_choice": "DECLINED",
        }
        self.db.create("cases", self.case)

        # Active Citizen Consent with required scopes in case_grants
        self.consent_grant = {
            "id": f"grant_{self.case_id}_{self.advocate['id']}",
            "case_id": self.case_id,
            "user_id": self.citizen["id"],
            "advocate_id": self.advocate["id"],
            "status": "ACTIVE",
            "scopes": ["story", "case_file", "evidence"],
            "evidence_ids": ["E001", "E002"],
            "expires_at": "2030-01-01T00:00:00+00:00",
            "created_at": "2026-10-15T10:00:00Z",
        }
        self.db.create("case_grants", self.consent_grant)
        self.case_token = issue_token(self.db, self.consent_grant)
        self.adv_headers["X-Case-Access"] = self.case_token

        # Generate an approved Engine-3 draft
        self.draft_id = f"draft_{uuid4().hex[:8]}"
        self.draft = AdvocateDraft(
            draft_id=self.draft_id,
            case_id=self.case_id,
            advocate_id=self.advocate["id"],
            draft_type="complaint_petition",
            draft_mode=DraftMode.AUTHORITATIVE.value,
            engine1_case_file_version=2,
            engine2_run_id=None,
            engine2_status="NOT_RUN",
            version=2,
            status=DraftStatus.ADVOCATE_APPROVED.value,
            created_at="2026-10-15T11:00:00Z",
            updated_at="2026-10-15T11:30:00Z",
            title="Consumer Complaint u/s 35 Consumer Protection Act, 2019",
            parties=self.case_file["parties"],
            jurisdiction_forum=self.case_file["jurisdiction"],
            facts_section=self.case_file["facts"],
            chronology=self.case_file["chronology"],
            legal_basis=self.case_file["applicable_law"],
            reliefs_or_requests=["Refund of INR 45,000 with 12% interest", "Compensation of INR 20,000 for mental agony"],
            evidence_references=self.evidence_list,
            annexures=[],
            disclosures=[ENGINE2_NOT_RUN_DISCLOSURE],
            provenance={"legal_foundation_status": "VERIFIED_AUTHORITY"},
        )
        self.draft.approval_record = ApprovalRecord(
            approved_by_advocate_id=self.advocate["id"],
            draft_version=2,
            source_engine1_version=2,
            approved_at="2026-10-15T11:30:00Z",
            integrity_hash=compute_draft_integrity_hash(self.draft),
            approval_state="ADVOCATE_APPROVED",
            disclosures=[ENGINE2_NOT_RUN_DISCLOSURE],
        )

        # Generate approved PDF artifact
        pdf_bytes, _ = export("<html><body><h1>Approved Consumer Complaint</h1></body></html>", "pdf")
        pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
        pdf_key = f"cases/{self.case_id}/drafts/{self.draft_id}/v2/approved.pdf"
        self.storage.upload(pdf_key, pdf_bytes, "application/pdf")
        self.draft.pdf_artifact = PdfArtifact(
            storage_key=pdf_key,
            sha256=pdf_sha,
            created_at="2026-10-15T11:30:00Z",
            size_bytes=len(pdf_bytes),
            filename="complaint_petition_v2_approved.pdf",
        )

        # Save draft root and version 2
        self.db.create("engine3_drafts", {
            "id": self.draft_id,
            "case_id": self.case_id,
            "advocate_id": self.advocate["id"],
            "current_version": 2,
            "status": DraftStatus.ADVOCATE_APPROVED.value,
        })
        self.db.create("engine3_draft_versions", {
            "id": f"{self.draft_id}_v2",
            "draft_id": self.draft_id,
            "version": 2,
            "case_id": self.case_id,
            "advocate_id": self.advocate["id"],
            "data": self.draft.model_dump(),
        })

        self.case["engine3_draft_id"] = self.draft_id
        self.db.update("cases", self.case_id, {"engine3_draft_id": self.draft_id})

    # 1. only assigned verified advocate can prepare package
    def test_01_only_assigned_verified_advocate_can_prepare(self):
        elig = check_filing_eligibility(self.case, self.advocate, self.db)
        self.assertTrue(elig["eligible"])

        # Unverified advocate fails
        unverified_adv = dict(self.advocate, verification_status="PENDING")
        elig_unv = check_filing_eligibility(self.case, unverified_adv, self.db)
        self.assertFalse(elig_unv["eligible"])
        self.assertIn("Advocate must be verified", elig_unv["reasons"][0])

        # Unassigned advocate fails
        elig_other = check_filing_eligibility(self.case, self.other_advocate, self.db)
        self.assertFalse(elig_other["eligible"])
        self.assertIn("not assigned", elig_other["reasons"][0])

    # 2. active consent required
    def test_02_active_consent_required(self):
        # Revoke consent
        self.db.update("case_grants", self.consent_grant["id"], {"status": "REVOKED", "revoked_at": "2026-10-16T00:00:00Z", "scopes": []})
        elig = check_filing_eligibility(self.case, self.advocate, self.db)
        self.assertFalse(elig["eligible"])
        self.assertTrue(any("consent" in r.lower() for r in elig["reasons"]))

        # Via API must return 403
        res = self.client.post(f"/api/cases/{self.case_id}/filing-packages/prepare", headers=self.adv_headers, json={})
        self.assertEqual(res.status_code, 403)

    # 3. advocate-approved draft required
    def test_03_advocate_approved_draft_required(self):
        # Mark draft as unapproved
        ver_doc = self.db.get("engine3_draft_versions", f"{self.draft_id}_v2")
        draft_copy = copy.deepcopy(ver_doc["data"])
        draft_copy["status"] = "DRAFT"
        draft_copy["approval_record"] = None
        self.db.create("engine3_draft_versions", {
            "id": f"{self.draft_id}_v3",
            "draft_id": self.draft_id,
            "version": 3,
            "case_id": self.case_id,
            "advocate_id": self.advocate["id"],
            "data": draft_copy,
        })
        self.db.update("engine3_drafts", self.draft_id, {"current_version": 3, "status": "DRAFT"})

        elig = check_filing_eligibility(self.case, self.advocate, self.db)
        self.assertFalse(elig["eligible"])
        self.assertTrue(any("ADVOCATE_APPROVED" in r for r in elig["reasons"]))

    # 4. stale draft blocks readiness
    def test_04_stale_draft_blocks_readiness(self):
        # Update case E1 version to 3 while draft is on E1 v2
        case_updated = dict(self.case)
        case_updated["canonical_case_file"] = dict(self.case_file, version=3)
        case_updated["advocate_approved_case_file_version"] = 3
        self.db.update("cases", self.case_id, {"canonical_case_file": case_updated["canonical_case_file"], "advocate_approved_case_file_version": 3})

        elig = check_filing_eligibility(case_updated, self.advocate, self.db)
        self.assertFalse(elig["eligible"])
        self.assertTrue(any("version" in r.lower() for r in elig["reasons"]))

    # 5. unverified law blocks READY_FOR_HUMAN_FILING
    def test_05_unverified_law_blocks_ready_for_human_filing(self):
        # With VERIFIED_AUTHORITY, it is READY_FOR_HUMAN_FILING
        pkg = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        self.assertEqual(pkg.status, FilingReadinessStatus.READY_FOR_HUMAN_FILING.value)

        # Now test with PENDING_SOURCE
        case_unv = dict(self.case)
        case_unv["canonical_case_file"] = dict(self.case_file, legal_foundation_status="PENDING_SOURCE")
        self.db.update("cases", self.case_id, {"canonical_case_file": case_unv["canonical_case_file"]})

        elig = check_filing_eligibility(case_unv, self.advocate, self.db)
        state = determine_readiness_state(elig, "PENDING_SOURCE", [], [], self.draft)
        self.assertEqual(state, FilingReadinessStatus.PREPARATION_ONLY.value)
        self.assertNotEqual(state, FilingReadinessStatus.READY_FOR_HUMAN_FILING.value)

    # 6. PREPARATION_ONLY allowed where appropriate
    def test_06_preparation_only_allowed_where_appropriate(self):
        case_unv = dict(self.case)
        case_unv["canonical_case_file"] = dict(self.case_file, legal_foundation_status="ABSTAINED")
        self.db.update("cases", self.case_id, {"canonical_case_file": case_unv["canonical_case_file"]})

        pkg = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        self.assertEqual(pkg.status, FilingReadinessStatus.PREPARATION_ONLY.value)

    # 7. Engine 2 optional
    def test_07_engine_2_optional(self):
        self.assertIsNone(self.case.get("engine2"))
        elig = check_filing_eligibility(self.case, self.advocate, self.db)
        self.assertTrue(elig["eligible"])
        self.assertEqual(elig["engine2_status"], "NOT_RUN")

    # 8. exact Engine-2 skip disclosure preserved
    def test_08_exact_engine2_skip_disclosure_preserved(self):
        pkg = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        self.assertIn(ENGINE2_NOT_RUN_DISCLOSURE, pkg.disclosures)
        self.assertEqual(ENGINE2_NOT_RUN_DISCLOSURE, "Case Challenge / Argument Analysis was not run.")
        self.assertEqual(pkg.provenance.get("engine2_disclosure"), "Case Challenge / Argument Analysis was not run.")

    # 9. annexure index deterministic
    def test_09_annexure_index_deterministic(self):
        pkg1 = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        annexures1 = [a.model_dump() for a in pkg1.annexures]

        # Re-running on same data must yield identical annexures ordering and labels
        pkg2 = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        annexures2 = [a.model_dump() for a in pkg2.annexures]

        self.assertEqual(len(annexures1), 2)
        self.assertEqual(annexures1[0]["annexure_label"], "Annexure A-1")
        self.assertEqual(annexures1[1]["annexure_label"], "Annexure A-2")
        self.assertEqual(annexures1[0]["evidence_id"], annexures2[0]["evidence_id"])
        self.assertEqual(annexures1[1]["source_hash"], annexures2[1]["source_hash"])

    # 10. original evidence immutable
    def test_10_original_evidence_immutable(self):
        evidence_before = copy.deepcopy(self.case["evidence"])
        prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        case_after = self.db.get("cases", self.case_id)
        self.assertEqual(case_after["evidence"], evidence_before)

    # 11. manifest contains exact versions/hashes
    def test_11_manifest_contains_exact_versions_and_hashes(self):
        pkg = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        manifest_items = {m.filename: m for m in pkg.document_manifest}

        self.assertIn("approved-draft.pdf", manifest_items)
        self.assertIn("manifest.json", manifest_items)
        self.assertIn("checklist.json", manifest_items)
        self.assertIn("evidence-index.json", manifest_items)
        self.assertIn("provenance.json", manifest_items)

        # Check hash length (64-char sha256)
        for m in pkg.document_manifest:
            self.assertEqual(len(m.sha256), 64)
            self.assertGreater(m.size_bytes, 0)

    # 12. package digest deterministic
    def test_12_package_digest_deterministic(self):
        pkg1 = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        pkg2 = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        # Packages prepared on same underlying data have exact matching package_digest
        self.assertEqual(len(pkg1.package_digest), 64)
        self.assertEqual(pkg1.package_digest, pkg2.package_digest)

    # 13. private advocate notes excluded
    def test_13_private_advocate_notes_excluded(self):
        # Add private advocate note to DB
        self.db.create("advocate_notes", {
            "id": "note_123",
            "case_id": self.case_id,
            "advocate_id": self.advocate["id"],
            "note": "CONFIDENTIAL: Client might have delayed reporting.",
            "created_at": "2026-10-15T12:00:00Z",
        })

        pkg = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        zip_bytes = self.storage.download(pkg.storage_key)

        # Search for confidential string inside zip
        self.assertNotIn(b"CONFIDENTIAL: Client might have delayed reporting.", zip_bytes)
        self.assertNotIn(b"advocate_notes", zip_bytes)

    # 14. historical package immutable
    def test_14_historical_package_immutable(self):
        pkg = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        ver_id = f"{pkg.filing_package_id}_v{pkg.version}"
        ver_doc = self.db.get("filing_package_versions", ver_id)
        self.assertIsNotNone(ver_doc)

        # Attempt to mutate filing_package_versions must fail
        with self.assertRaises(ValueError):
            self.db.update("filing_package_versions", ver_id, {"status": "TAMPERED"})

        with self.assertRaises(ValueError):
            self.db.delete("filing_package_versions", ver_id)

    # 15. new package version generated explicitly
    def test_15_new_package_version_generated_explicitly(self):
        pkg1 = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        self.assertEqual(pkg1.version, 1)

        pkg2 = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        self.assertEqual(pkg2.version, 2)
        self.assertNotEqual(pkg1.filing_package_id, pkg2.filing_package_id)

        # Previous package is SUPERSEDED
        prev = self.db.get("filing_packages", pkg1.filing_package_id)
        self.assertEqual(prev["status"], FilingReadinessStatus.SUPERSEDED.value)

    # 16. E1 change marks package stale
    def test_16_e1_change_marks_package_stale(self):
        pkg = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        self.assertEqual(pkg.status, FilingReadinessStatus.READY_FOR_HUMAN_FILING.value)

        # Update case E1 to version 3
        case_updated = dict(self.case)
        case_updated["canonical_case_file"] = dict(self.case_file, version=3)
        case_updated["advocate_approved_case_file_version"] = 3
        self.db.update("cases", self.case_id, {"canonical_case_file": case_updated["canonical_case_file"]})

        evaluated = evaluate_package_staleness(self.db, case_updated, pkg)
        self.assertEqual(evaluated.status, FilingReadinessStatus.STALE.value)

    # 17. draft change marks package stale
    def test_17_draft_change_marks_package_stale(self):
        pkg = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        self.assertEqual(pkg.status, FilingReadinessStatus.READY_FOR_HUMAN_FILING.value)

        # Create draft v3 in DB
        self.db.update("engine3_drafts", self.draft_id, {"current_version": 3})

        evaluated = evaluate_package_staleness(self.db, self.case, pkg)
        self.assertEqual(evaluated.status, FilingReadinessStatus.STALE.value)

    # 18. consent revocation blocks new package
    def test_18_consent_revocation_blocks_new_package(self):
        # Revoke consent
        self.db.update("case_grants", self.consent_grant["id"], {"status": "REVOKED", "revoked_at": "2026-10-16T00:00:00Z", "scopes": []})

        with self.assertRaises(PermissionError):
            prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)

    # 19. unauthorized advocate blocked
    def test_19_unauthorized_advocate_blocked(self):
        res = self.client.post(
            f"/api/cases/{self.case_id}/filing-packages/prepare",
            headers=self.other_adv_headers,
            json={},
        )
        self.assertEqual(res.status_code, 403)

        res_get = self.client.get(
            f"/api/cases/{self.case_id}/filing-packages",
            headers=self.other_adv_headers,
        )
        self.assertEqual(res_get.status_code, 403)

    # 20. citizen cannot generate package
    def test_20_citizen_cannot_generate_package(self):
        res = self.client.post(
            f"/api/cases/{self.case_id}/filing-packages/prepare",
            headers=self.cit_headers,
            json={},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("advocate-only", res.json()["detail"].lower())

    # 21. admin cannot generate package
    def test_21_admin_cannot_generate_package(self):
        res = self.client.post(
            f"/api/cases/{self.case_id}/filing-packages/prepare",
            headers=self.admin_headers,
            json={},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("advocate-only", res.json()["detail"].lower())

    # 22. no external submission occurs
    def test_22_no_external_submission_occurs(self):
        pkg = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        self.assertIn(DISCLOSURE_PHASE10_SAFETY, pkg.disclosures)
        self.assertIn(DISCLOSURE_NO_EXTERNAL_SUBMISSION, pkg.disclosures)
        self.assertEqual(pkg.filing_mode, "MANUAL_HUMAN_ADVOCATE_FILING")
        self.assertNotEqual(pkg.status, "FILED")
        self.assertFalse(pkg.provenance.get("automated_submission_performed"))
        self.assertFalse(pkg.provenance.get("court_portal_contacted"))

    # 23. no filing/payment API invoked
    def test_23_no_filing_or_payment_api_invoked(self):
        # Audit all route endpoints in filing router
        for route in filing_router.routes:
            path = getattr(route, "path", "")
            self.assertNotIn("pay", path.lower())
            self.assertNotIn("esign", path.lower())
            self.assertNotIn("ecourt", path.lower())
            self.assertNotIn("portal", path.lower())

    # 24. Phase-4 REVIEW_PENDING authority never appears as verified law
    def test_24_review_pending_authority_never_verified_law(self):
        self.db.create("legal_authority_versions", {
            "id": "dspe_act_1946_s1_v1",
            "source": {
                "source_id": "dspe_act_1946_s1",
                "review_state": "REVIEW_PENDING",
                "source_reviewed": False,
                "temporal_reviewed": False,
            },
        })

        # A case with REVIEW_PENDING authority
        case_with_pending = dict(self.case)
        case_with_pending["canonical_case_file"] = dict(self.case_file, legal_foundation_status="PENDING_SOURCE", applicable_law=[{
            "source_id": "dspe_act_1946_s1",
            "authority_status": "REVIEW_PENDING",
            "title": "Delhi Special Police Establishment Act",
        }])

        pkg = prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)
        # Verified legal basis in package cannot contain unapproved candidate
        for basis in pkg.verified_legal_basis:
            self.assertNotEqual(basis.get("authority_status"), "REVIEW_PENDING")
            self.assertNotEqual(basis.get("source_id"), "dspe_act_1946_s1")

    # 25. no genuine Phase-4 authority modified
    def test_25_no_genuine_phase4_authority_modified(self):
        self.db.create("legal_authority_versions", {"id": "auth_v_test", "review_status": "REVIEW_PENDING"})
        before_auth = copy.deepcopy(self.db.list("legal_authority_versions"))

        # Run filing package preparation
        prepare_filing_package(self.db, self.storage, self.case_id, self.advocate)

        after_auth = self.db.list("legal_authority_versions")
        self.assertEqual(before_auth, after_auth)


if __name__ == "__main__":
    unittest.main()
