import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend.services.input_layer import build_raw_package, extract_content, working_text
from backend.services.input_canonical import canonicalize, detect_language
from backend.services.input_declarations import declarations
from backend.services.ingestion import run_ingestion
from backend.tests.helpers import test_app, client_account


class CommonInputTests(unittest.TestCase):
    def package(self, story="I have the receipt. I do not have the warranty card. I do not know the visit date.", **changes):
        case = {"case_id": "test", "client_story": story, "owner_user_id": "actor", "created_at": "2026-10-11T00:00:00+00:00", "evidence": [], **changes}
        return build_raw_package(case, SimpleNamespace(mode="mock", processing_mode="mock", llm_processing_mode="mock"))

    def test_typed_languages_and_original_provenance(self):
        for text, language in (("My story", "script:LATIN"), ("என் கதை", "script:TAMIL"), ("என் receipt 24,500", "script:LATIN+TAMIL")):
            raw = self.package(text)
            self.assertEqual(raw["original_story"], text)
            self.assertEqual(raw["canonical_narrative"], text)
            self.assertEqual(raw["provenance"][0]["language"], language)
            self.assertEqual(raw["provenance"][0]["actor_id"], "actor")
            self.assertEqual(raw["evidence_ids"], [])

    def test_repeated_story_transcript_and_document_keep_all_provenance(self):
        story = "I paid Rs. 24,500 on 3 Sep 2026 and asked the store for a replacement."
        items = [{"evidence_id": f"E00{i}", "filename": f"file{i}.txt", "uploaded_by": "actor", "input_source": source, "extraction": extract_content(story.encode(), "story.txt")} for i, source in ((1, "MICROPHONE"), (2, "FILE_UPLOAD"))]
        raw = self.package(story, evidence=items)
        self.assertEqual(raw["original_text"].count(story), 1)
        self.assertEqual(raw["canonical_narrative"], story)
        self.assertEqual(len(raw["provenance"]), 3)
        self.assertEqual(raw["canonical_segments"][0]["source_ids"], ["STORY", "E001", "E002"])
        self.assertEqual(raw["evidence"][1]["duplicate_of"], "E001")

    def test_overlap_is_exact_and_differing_amounts_are_not_merged(self):
        a = "One two three four five six seven eight nine ten eleven twelve"
        b = "three four five six seven eight nine ten eleven twelve then more"
        result = canonicalize([{"source_id": "a", "original_text": a}, {"source_id": "b", "original_text": b}])
        self.assertEqual(result["text"], a + " then more")
        result = canonicalize([{"source_id": "a", "original_text": "I paid 24500"}, {"source_id": "b", "original_text": "I paid 25000"}])
        self.assertEqual(len(result["segments"]), 2)

    def test_availability_is_not_an_upload(self):
        raw = self.package()
        self.assertEqual(raw["evidence"], [])
        self.assertEqual(len(raw["declared_evidence"]), 1)
        self.assertEqual(len(raw["unavailable_evidence"]), 1)
        self.assertEqual(len(raw["unknown_details"]), 1)
        self.assertNotIn("evidence_id", raw["declared_evidence"][0])
        self.assertEqual(raw["declaration_processing"]["status"], "DEVELOPMENT_ONLY")

    def test_live_declaration_references_are_resolved_by_server(self):
        source = [{"source_id": "STORY", "original_text": "I have a receipt. I do not know the date."}]
        llm = Mock()
        llm.generate.return_value = {"items": [{"source_id": "STORY", "quote_index": 0, "label": "Receipt", "state": "AVAILABLE_NOT_UPLOADED", "kind": "EVIDENCE"}]}
        result = declarations(source, SimpleNamespace(mode="real", processing_mode="live", llm_processing_mode="live", llm=llm))
        self.assertEqual(result["items"][0]["quote"], "I have a receipt.")
        self.assertTrue(any(i["state"] == "UNKNOWN" for i in result["items"]))
        llm.generate.return_value["items"][0]["quote_index"] = 99
        result = declarations(source, SimpleNamespace(mode="real", processing_mode="live", llm_processing_mode="live", llm=llm))
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["items"], [])

    def test_model_cannot_turn_known_amounts_into_unknown_or_available_evidence(self):
        llm = Mock()
        llm.generate.return_value = {"items": [{"source_id": "STORY", "quote_index": 0, "label": "Amount", "state": "UNKNOWN", "kind": "DETAIL"}, {"source_id": "STORY", "quote_index": 0, "label": "Payment date", "state": "AVAILABLE_NOT_UPLOADED", "kind": "DETAIL"}]}
        result = declarations([{"source_id": "STORY", "original_text": "I paid 24,500 on 3 Sep 2026."}], SimpleNamespace(mode="real", processing_mode="live", llm_processing_mode="live", llm=llm))
        self.assertEqual(result["items"], [])
        self.assertEqual(len(result["rejected_items"]), 2)
        self.assertTrue(result["review_required"])

    def test_translation_rejects_changed_amounts_and_keeps_original(self):
        llm = Mock()
        llm.generate.return_value = {"language": "Tamil", "english_text": "I paid 25000", "uncertainties": []}
        result = working_text("நான் 24,500 செலுத்தினேன்", SimpleNamespace(mode="real", processing_mode="live", llm_processing_mode="live", llm=llm))
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["english_text"], "")

    def test_all_origins_use_identical_package_contract(self):
        keys = []
        for origin in ("CITIZEN_SELF_SERVICE", "CITIZEN_DIRECT_ADVOCATE", "ADVOCATE_WALK_IN"):
            raw = self.package(origin=origin)
            keys.append(set(raw))
            self.assertEqual(raw["origin"], origin)
            self.assertEqual(raw["provenance"][0]["case_origin"], origin)
        self.assertEqual(keys[0], keys[1]); self.assertEqual(keys[1], keys[2])

    def test_media_uses_same_real_transcription_path_and_never_claims_visuals(self):
        for filename, mime in (("mic.webm", "audio/webm"), ("voice.wav", "audio/wav"), ("video.mp4", "video/mp4")):
            with patch("backend.services.input_layer.transcribe", return_value="Test transcript") as provider:
                result = extract_content(b"media", filename, mime)
            provider.assert_called_once()
            self.assertEqual(result["original_text"], "Test transcript")
            self.assertEqual(result["visual_analysis"], "NOT_PERFORMED")
            self.assertEqual(result["method"], "transcription")
        with patch.dict("os.environ", {"ENABLE_AWS_MEDIA": "false"}):
            result = extract_content(b"media", "recording.wav", "audio/wav")
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["original_text"], "")

    def test_partial_pdf_preserves_readable_pages_and_is_pending(self):
        import pymupdf as fitz
        with fitz.open() as pdf:
            page = pdf.new_page(); page.insert_text((50, 50), "Original amount 24,500")
            pdf.new_page()
            with patch("backend.services.input_layer.ocr_image", side_effect=RuntimeError("OCR unavailable")):
                result = extract_content(pdf.tobytes(), "mixed.pdf")
        self.assertEqual(result["status"], "PENDING")
        self.assertIn("24,500", result["original_text"])
        self.assertEqual([p["status"] for p in result["pages"]], ["COMPLETED", "PENDING"])

    def test_retry_recovers_failed_source_without_losing_other_sources(self):
        case = {"case_id": "case", "client_story": "Story", "evidence": [{"evidence_id": "E001", "filename": "receipt.txt", "storage_key": "one", "extraction": {"status": "PENDING", "original_text": "", "reason": "failure"}}, {"evidence_id": "E002", "filename": "other.txt", "extraction": extract_content(b"Other text", "other.txt")}]}
        storage = Mock(); storage.download.return_value = b"Recovered original text"
        raw = build_raw_package(case, SimpleNamespace(mode="mock", processing_mode="mock", llm_processing_mode="mock", storage=storage))
        storage.download.assert_called_once_with("one")
        self.assertEqual(raw["source_statuses"]["E001"], "COMPLETED")
        self.assertIn("Other text", raw["original_text"])
        storage.download.side_effect = RuntimeError("INTERNAL_STORAGE")
        raw = build_raw_package(case, SimpleNamespace(mode="mock", processing_mode="mock", llm_processing_mode="mock", storage=storage))
        self.assertEqual(raw["source_statuses"]["E001"], "PENDING")
        self.assertIn("Other text", raw["original_text"])

    def test_fictional_tamil_sample_retains_dates_amounts_without_fake_uploads(self):
        text = (Path(__file__).parent / "fixtures/tamil_refrigerator.txt").read_text(encoding="utf-8")
        raw = self.package(text, preferred_language="Tamil")
        self.assertEqual(raw["original_story"], text)
        for token in ("24,500", "செப்டம்பர் 3", "செப்டம்பர் 5", "செப்டம்பர் 9", "செப்டம்பர் 10", "செப்டம்பர் 20", "அக்டோபர் 1", "அக்டோபர் 10"):
            self.assertIn(token, raw["original_text"])
        self.assertEqual(raw["evidence_ids"], [])


class InputRouteTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app, self.client = test_app()
        self.user, self.headers = client_account(self.client, "input")
        self.id = self.client.post("/api/cases", headers=self.headers).json()["case"]["case_id"]
        self.client.patch(f"/api/cases/{self.id}", headers=self.headers, json={"stage": "NEW_CONSULTATION", "client_story": "Original story"})

    def tearDown(self): self.directory.cleanup()

    def test_same_file_twice_keeps_both_sources_without_reextracting(self):
        for index in range(2):
            with patch("backend.routes.cases.extract_content", wraps=extract_content) as extractor:
                response = self.client.post(f"/api/cases/{self.id}/evidence", headers=self.headers, files={"file": ("receipt.txt", b"Paid 24,500", "text/plain")})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(extractor.call_count, 1 if index == 0 else 0)
        items = response.json()["case"]["evidence"]
        self.assertEqual([i["evidence_id"] for i in items], ["E001", "E002"])
        self.assertEqual(items[1]["duplicate_of"], "E001")
        self.assertNotIn("storage_key", response.text)

    def test_microphone_and_audio_upload_defer_provider_to_worker(self):
        with patch("backend.services.input_layer.transcribe", side_effect=AssertionError("not in HTTP request")):
            response = self.client.post(f"/api/cases/{self.id}/evidence", headers=self.headers, data={"input_source": "MICROPHONE"}, files={"file": ("mic.webm", b"media", "audio/webm")})
        self.assertEqual(response.status_code, 200)
        item = response.json()["evidence"]
        self.assertEqual(item["input_source"], "MICROPHONE")
        self.assertEqual(item["extraction"]["status"], "PENDING")

    def test_input_retry_preserves_draft_and_cannot_run_legal_engine(self):
        with patch("backend.services.jobs.dispatch") as dispatch:
            response = self.client.post(f"/api/cases/{self.id}/input/retry", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        dispatch.assert_called_once_with(self.app, 0, self.id, preserve_status=True)
        with patch("backend.services.engine1.run_engine1", side_effect=AssertionError("no legal processing")):
            run_ingestion(self.app, self.id, preserve_status=True)
        saved = self.app.state.adapters.database.get("cases", self.id)
        self.assertEqual(saved["status"], "DRAFT")
        self.assertEqual(saved["raw_package"]["case_id"], self.id)
        self.assertNotIn("case_file", saved)

    def test_other_user_cannot_retry_and_running_retry_cannot_duplicate(self):
        _, other = client_account(self.client, "outsider")
        self.assertEqual(self.client.post(f"/api/cases/{self.id}/input/retry", headers=other).status_code, 403)
        self.app.state.adapters.database.update("cases", self.id, {"input_status": "RUNNING"})
        self.assertEqual(self.client.post(f"/api/cases/{self.id}/input/retry", headers=self.headers).status_code, 409)
