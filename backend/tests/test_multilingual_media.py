"""Deterministic test matrix for CaseSeva multilingual and media provider abstractions.

Covers all 18 test matrix requirements specified in Section 16:
- English, Tamil, Hindi, Telugu text processing
- Mixed-language (Tamil+English, Hindi+English) processing
- Unknown / unverified language handling
- Romanized non-English text detection and review requirement
- Multiple language candidates reported by provider
- Language detection fail-closed behavior when unavailable
- Translation fail-closed behavior when unavailable
- Speech-to-text fail-closed behavior when unavailable
- Mock speech-to-text provider deterministic success
- OCR fail-closed behavior when unavailable
- GridFS local runtime execution with zero boto3 imports
- Arbitrary future language identifier flowing through schemas
- Original citizen input preserved unconditionally after translation
- Translation provenance explicitly linking back to original
- Script detection treated as weak hint only, never definitive language proof
"""
import builtins
import hashlib
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from backend.adapters.media import (
    TranscriptionResult,
    OCRResult,
    LanguageDetectionResult,
    TranslationResult,
)
from backend.adapters.mock.media import (
    MockMediaAdapter,
    MockSpeechToTextProvider,
    MockOCRProvider,
    MockLanguageDetectionProvider,
    MockTranslationProvider,
)
from backend.models.input import RawCasePackage, SourceRecord, InputProcessingStatus
from backend.services.input_layer import build_raw_package, extract_content, working_text
from backend.services.input_canonical import detect_language, detect_script_hint, canonicalize


class MultilingualMediaMatrixTests(unittest.TestCase):
    def setUp(self):
        self.mock_media = MockMediaAdapter()
        self.adapters = SimpleNamespace(
            mode="mock",
            processing_mode="mock",
            llm_processing_mode="mock",
            media=self.mock_media,
            storage=Mock(),
            database=Mock(),
            llm=Mock(),
        )

    def _package_story(self, story: str, preferred_language: str = "English", **kwargs):
        case = {
            "case_id": "test-multilingual",
            "client_story": story,
            "owner_user_id": "citizen-1",
            "preferred_language": preferred_language,
            "evidence": [],
            **kwargs,
        }
        return build_raw_package(case, self.adapters)

    def test_english_text(self):
        text = "I purchased a refrigerator for Rs. 24,500 on 3 September 2026 and the cooling stopped working."
        raw = self._package_story(text, preferred_language="English")
        self.assertEqual(raw["original_story"], text)
        self.assertEqual(raw["original_text"], text)
        self.assertEqual(raw["canonical_narrative"], text)
        self.assertIn("script:LATIN", raw["provenance"][0]["language"])
        self.assertEqual(raw["provenance"][0]["detailed_status"], InputProcessingStatus.EXTRACTED)

    def test_tamil_text(self):
        text = "வாடிக்கையாளர் வாங்கிய குளிர்சாதனப் பெட்டி பழுதானது. கடைக்காரர் பணம் தர மறுத்துவிட்டார்."
        raw = self._package_story(text, preferred_language="Tamil")
        self.assertEqual(raw["original_story"], text)
        self.assertEqual(raw["original_text"], text)
        self.assertEqual(raw["provenance"][0]["language"], "script:TAMIL")
        # Language detection provider identifies ta
        det = self.mock_media.language_detection.detect_language(text)
        self.assertEqual(det.primary_language, "ta")
        self.assertEqual(det.status, "COMPLETED")

    def test_hindi_text(self):
        text = "उपभोक्ता ने 25,000 रुपये का भुगतान किया और रसीद प्राप्त की, लेकिन सामान नहीं मिला।"
        raw = self._package_story(text, preferred_language="Hindi")
        self.assertEqual(raw["original_story"], text)
        self.assertEqual(raw["original_text"], text)
        self.assertIn("script:DEVANAGARI", raw["provenance"][0]["language"])
        det = self.mock_media.language_detection.detect_language(text)
        self.assertEqual(det.primary_language, "hi")

    def test_telugu_text(self):
        text = "వినియోగదారుడు 20,000 రూపాయలు చెల్లించారు కానీ సరుకు ఇంకా డెలివరీ కాలేదు."
        raw = self._package_story(text, preferred_language="Telugu")
        self.assertEqual(raw["original_story"], text)
        self.assertEqual(raw["original_text"], text)
        self.assertIn("script:TELUGU", raw["provenance"][0]["language"])
        det = self.mock_media.language_detection.detect_language(text)
        self.assertEqual(det.primary_language, "te")

    def test_tamil_english_mixed(self):
        text = "Order ID #84931 பொருளுக்கான refund தொகை இன்னும் வரவில்லை. Store manager refused assistance."
        raw = self._package_story(text)
        self.assertEqual(raw["original_story"], text)
        det = self.mock_media.language_detection.detect_language(text)
        self.assertTrue(det.is_mixed)
        self.assertIn("ta", det.detected_languages)
        self.assertIn("en", det.detected_languages)
        self.assertTrue(det.review_required)

    def test_hindi_english_mixed(self):
        text = "Order #4829 mein payment 15000 kat gaya but confirmation nahi mila."
        raw = self._package_story(text)
        self.assertEqual(raw["original_story"], text)
        det = self.mock_media.language_detection.detect_language(text)
        self.assertTrue(det.review_required)

    def test_unknown_language(self):
        text = "12345 67890 !@#$%^&*()"
        det = self.mock_media.language_detection.detect_language(text)
        self.assertEqual(det.script_hint, "unknown")
        # Survives raw package build without failure
        raw = self._package_story(text)
        self.assertEqual(raw["original_story"], text)

    def test_romanized_non_english_input(self):
        # Romanized Tamil (Tanglish)
        text_ta_latn = "Naan panam kattiya piragu receipt tharavillai."
        det_ta = self.mock_media.language_detection.detect_language(text_ta_latn)
        self.assertIn("script:LATIN", det_ta.script_hint)
        self.assertTrue(det_ta.review_required)
        self.assertIn("ta-Latn", det_ta.detected_languages)

        # Romanized Hindi (Hinglish)
        text_hi_latn = "Mera paisa kat gaya aur koi update nahi hai."
        det_hi = self.mock_media.language_detection.detect_language(text_hi_latn)
        self.assertIn("script:LATIN", det_hi.script_hint)
        self.assertTrue(det_hi.review_required)
        self.assertIn("hi-Latn", det_hi.detected_languages)

    def test_provider_reports_multiple_languages(self):
        provider = MockLanguageDetectionProvider(
            custom_mappings={
                "Multilingual input": {
                    "primary_language": "mixed",
                    "detected_languages": ["ta", "hi", "en"],
                    "is_mixed": True,
                    "review_required": True,
                    "confidence": 0.85,
                    "status": "COMPLETED",
                    "provider": "custom_mock",
                }
            }
        )
        res = provider.detect_language("Multilingual input")
        self.assertEqual(res.primary_language, "mixed")
        self.assertEqual(res.detected_languages, ["ta", "hi", "en"])
        self.assertTrue(res.is_mixed)
        self.assertTrue(res.review_required)

    def test_language_detection_unavailable(self):
        self.mock_media.language_detection = MockLanguageDetectionProvider(available=False)
        res = self.mock_media.language_detection.detect_language("Some text")
        self.assertEqual(res.status, "CAPABILITY_UNAVAILABLE")
        self.assertEqual(res.primary_language, "und")

    def test_translation_unavailable(self):
        # Default mock translation provider is unavailable
        self.mock_media.translation = MockTranslationProvider(available=False)
        text = "வாடிக்கையாளர் வாங்கிய குளிர்சாதனப் பெட்டி பழுதானது."
        res = working_text(text, self.adapters)
        # Translation capability unavailable -> fails closed, preserves original
        self.assertIn(res["status"], {"CAPABILITY_UNAVAILABLE", "PENDING"})
        self.assertEqual(res["english_text"], "")
        # Original input remains unaffected
        raw = self._package_story(text)
        self.assertEqual(raw["original_story"], text)
        self.assertEqual(raw["original_text"], text)

    def test_speech_transcription_unavailable(self):
        self.mock_media.speech_to_text = MockSpeechToTextProvider(available=False)
        self.adapters.storage.download.return_value = b"RIFF fake audio bytes"
        case = {
            "case_id": "test-speech-unavail",
            "client_story": "Audio statement attached.",
            "owner_user_id": "citizen-1",
            "evidence": [
                {
                    "evidence_id": "E001",
                    "filename": "narration.wav",
                    "content_type": "audio/wav",
                    "storage_key": "narration.wav",
                }
            ],
        }
        raw = build_raw_package(case, self.adapters, retry_pending_media=True)
        evidence_item = raw["evidence"][0]
        extraction = evidence_item["extraction"]
        self.assertEqual(extraction["status"], "PENDING")
        self.assertEqual(extraction["detailed_status"], InputProcessingStatus.CAPABILITY_UNAVAILABLE)
        self.assertIn("Speech", extraction["reason"])
        self.assertTrue(any(p["kind"] == "EXTRACTION" for p in raw["pending"]))

    def test_mock_speech_provider_success(self):
        self.mock_media.speech_to_text = MockSpeechToTextProvider(
            available=True,
            mock_transcript="Citizen paid Rs. 30,000 for service on 5 October 2026.",
            detected_languages=["en"],
        )
        self.adapters.storage.download.return_value = b"RIFF fake audio bytes"
        case = {
            "case_id": "test-speech-success",
            "client_story": "",
            "owner_user_id": "citizen-1",
            "evidence": [
                {
                    "evidence_id": "E001",
                    "filename": "narration.wav",
                    "content_type": "audio/wav",
                    "storage_key": "narration.wav",
                }
            ],
        }
        raw = build_raw_package(case, self.adapters, retry_pending_media=True)
        evidence_item = raw["evidence"][0]
        extraction = evidence_item["extraction"]
        self.assertEqual(extraction["status"], "COMPLETED")
        self.assertEqual(extraction["detailed_status"], InputProcessingStatus.TRANSCRIBED)
        self.assertEqual(extraction["original_text"], "Citizen paid Rs. 30,000 for service on 5 October 2026.")
        self.assertIn("30,000", raw["original_text"])

    def test_ocr_provider_unavailable(self):
        self.mock_media.ocr = MockOCRProvider(available=False)
        self.adapters.storage.download.return_value = b"\x89PNG\r\n\x1a\n fake image"
        case = {
            "case_id": "test-ocr-unavail",
            "client_story": "Invoice attached.",
            "owner_user_id": "citizen-1",
            "evidence": [
                {
                    "evidence_id": "E001",
                    "filename": "bill.png",
                    "content_type": "image/png",
                    "storage_key": "bill.png",
                }
            ],
        }
        raw = build_raw_package(case, self.adapters)
        extraction = raw["evidence"][0]["extraction"]
        self.assertEqual(extraction["status"], "PENDING")
        self.assertEqual(extraction["detailed_status"], InputProcessingStatus.CAPABILITY_UNAVAILABLE)
        self.assertIn("OCR", extraction["reason"])

    def test_gridfs_local_runtime_with_no_boto3_import(self):
        # Strict guard asserting zero boto3 or botocore attempts
        original_import = builtins.__import__

        def no_aws_import(name, *args, **kwargs):
            if name.split(".")[0] in {"boto3", "botocore"}:
                raise AssertionError(f"AWS import attempted: {name}")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=no_aws_import):
            # Plain text case processing in local runtime
            case = {
                "case_id": "test-no-boto3",
                "client_story": "Purchased smartphone online. Battery defective.",
                "owner_user_id": "citizen-local",
                "preferred_language": "English",
                "evidence": [],
            }
            raw = build_raw_package(case, self.adapters)
            self.assertEqual(raw["original_story"], "Purchased smartphone online. Battery defective.")
            self.assertEqual(raw["source_statuses"], {"STORY": "COMPLETED"})

            # Document extraction also works locally with zero boto3
            doc_result = extract_content(b"Local file content with no AWS", "statement.txt", "text/plain")
            self.assertEqual(doc_result["status"], "COMPLETED")
            self.assertEqual(doc_result["original_text"], "Local file content with no AWS")

    def test_arbitrary_future_language_identifier_survives_schema(self):
        # Regional Indian languages and hypothetical future language codes
        test_languages = [
            "en", "ta", "hi", "te", "ml", "kn", "bn", "mr", "gu", "pa", "ur",
            "or", "as", "ks", "kok", "und", "mixed", "mul", "xyz-future-lang",
        ]
        for lang_code in test_languages:
            with self.subTest(lang_code=lang_code):
                record = SourceRecord(
                    source_id="TEST_SRC",
                    case_id="case-1",
                    case_origin="CITIZEN_SELF_SERVICE",
                    source_type="TYPED_STORY",
                    mime_type="text/plain",
                    extraction_method="typed",
                    extraction_status="COMPLETED",
                    language=lang_code,
                    content_hash="hash1",
                    text_hash="hash2",
                    derived_reference="raw_package.provenance:TEST_SRC",
                    processing_mode="mock",
                    original_text="Arbitrary language content",
                    detected_languages=[lang_code],
                )
                self.assertEqual(record.language, lang_code)
                self.assertEqual(record.detected_languages, [lang_code])

                # RawCasePackage model accepts arbitrary preferred_language
                pkg = RawCasePackage(
                    case_id="case-1",
                    origin="CITIZEN_SELF_SERVICE",
                    canonical_narrative="Story",
                    original_language_content="Story",
                    english_working_text="",
                    preferred_language=lang_code,
                    provenance=[record],
                    declared_evidence=[],
                    unavailable_evidence=[],
                    unknown_evidence=[],
                    unknown_details=[],
                    evidence=[],
                    pending=[],
                )
                self.assertEqual(pkg.preferred_language, lang_code)

    def test_original_input_remains_unchanged_after_translation(self):
        tamil_story = "நான் 12,000 ரூபாய் செலுத்தினேன். ரசீது கிடைக்கவில்லை."
        self.mock_media.translation = MockTranslationProvider(
            available=True,
            translations={tamil_story: "I paid 12,000 rupees. Receipt was not received."},
        )
        raw = self._package_story(tamil_story, preferred_language="Tamil")

        # The original citizen story and text are completely untouched
        self.assertEqual(raw["original_story"], tamil_story)
        self.assertEqual(raw["original_text"], tamil_story)
        self.assertEqual(raw["canonical_narrative"], tamil_story)
        self.assertEqual(raw["original_language_content"], tamil_story)
        self.assertEqual(raw["provenance"][0]["original_text"], tamil_story)

        # Translation is strictly auxiliary and derivative
        self.assertEqual(raw["english_working_text"], "I paid 12,000 rupees. Receipt was not received.")
        self.assertNotEqual(raw["original_text"], raw["english_working_text"])

    def test_translation_provenance_links_to_original(self):
        text = "வாடிக்கையாளர் புகார் எண் 99881."
        provider = MockTranslationProvider(
            available=True,
            translations={text: "Customer complaint number 99881."},
        )
        res = provider.translate(text, source_language="ta", target_language="en", metadata={"source_id": "STORY"})
        self.assertEqual(res.status, "COMPLETED")
        self.assertEqual(res.provenance["original_text_hash"], hashlib.sha256(text.encode("utf-8")).hexdigest())
        self.assertEqual(res.provenance["source_id"], "STORY")
        self.assertTrue(res.review_required)

    def test_script_detection_never_establishes_language_by_itself(self):
        # Latin script is NOT proof of English
        latin_tanglish = "kaasu kuduthaen receipt tharala"
        hint = detect_script_hint(latin_tanglish)
        self.assertEqual(hint, "script:LATIN")
        # Script hint is only a script category, not a verified English assertion
        self.assertNotEqual(hint, "en")
        self.assertNotEqual(hint, "English")

        # Devanagari is NOT proof of Hindi alone (could be Marathi, Nepali, Sanskrit, Konkani)
        devanagari_marathi = "मी पैसे भरले पण पावती मिळाली नाही."
        hint_deva = detect_script_hint(devanagari_marathi)
        self.assertEqual(hint_deva, "script:DEVANAGARI")
        self.assertNotEqual(hint_deva, "hi")
        self.assertNotEqual(hint_deva, "Hindi")


if __name__ == "__main__":
    unittest.main()
