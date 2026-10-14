"""Deterministic mock media and multilingual providers for offline testing.

Zero AWS imports, zero external network calls.
Preserves fail-closed behavior for unavailable capabilities.
"""
import hashlib
import unicodedata
from typing import Any

from ..media import (
    SpeechToTextProvider,
    OCRProvider,
    LanguageDetectionProvider,
    TranslationProvider,
    MediaAdapter,
    TranscriptionResult,
    OCRResult,
    LanguageDetectionResult,
    TranslationResult,
)


def _compute_script_hint(text: str) -> str:
    scripts = sorted({unicodedata.name(c, "").split(" ")[0] for c in text if c.isalpha()})
    return "script:" + "+".join(scripts) if scripts else "unknown"


class MockSpeechToTextProvider(SpeechToTextProvider):
    def __init__(self, available: bool = True, mock_transcript: str | None = None, detected_languages: list[str] | None = None):
        self.available = available
        self.mock_transcript = mock_transcript
        self.detected_languages = detected_languages or []

    def transcribe(self, content: bytes, extension: str, metadata: dict[str, Any] | None = None) -> TranscriptionResult:
        if not self.available:
            return TranscriptionResult(
                transcript="",
                status="CAPABILITY_UNAVAILABLE",
                reason="Speech-to-text capability is unavailable; original recording is preserved.",
                provider="mock",
                provenance={"content_hash": hashlib.sha256(content).hexdigest() if content else ""},
            )
        transcript = self.mock_transcript if self.mock_transcript is not None else "Mock speech transcript"
        languages = list(self.detected_languages) if self.detected_languages else ["und"]
        return TranscriptionResult(
            transcript=transcript,
            detected_languages=languages,
            primary_language=languages[0] if languages else "und",
            status="COMPLETED",
            provider="mock",
            provenance={"content_hash": hashlib.sha256(content).hexdigest() if content else ""},
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "readiness": "mock" if self.available else "unavailable",
            "provider": "mock",
            "available": self.available,
            "supported_languages": ["*"],
        }


class MockOCRProvider(OCRProvider):
    def __init__(self, available: bool = True, mock_text: str | None = None):
        self.available = available
        self.mock_text = mock_text

    def ocr_image(self, content: bytes, metadata: dict[str, Any] | None = None) -> OCRResult:
        if not self.available:
            return OCRResult(
                text="",
                status="CAPABILITY_UNAVAILABLE",
                reason="OCR capability is unavailable; original document is preserved.",
                provider="mock",
            )
        return OCRResult(
            text=self.mock_text if self.mock_text is not None else "Mock OCR extracted text",
            status="COMPLETED",
            provider="mock",
            review_required=True,
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "readiness": "mock" if self.available else "unavailable",
            "provider": "mock",
            "available": self.available,
        }


class MockLanguageDetectionProvider(LanguageDetectionProvider):
    def __init__(self, available: bool = True, custom_mappings: dict[str, Any] | None = None):
        self.available = available
        self.custom_mappings = custom_mappings or {}

    def detect_language(self, text: str, metadata: dict[str, Any] | None = None) -> LanguageDetectionResult:
        if not self.available:
            return LanguageDetectionResult(
                primary_language="und",
                status="CAPABILITY_UNAVAILABLE",
                reason="Language detection capability is unavailable.",
                provider="mock",
            )
        if not text.strip():
            return LanguageDetectionResult(
                primary_language="unknown",
                status="COMPLETED",
                provider="mock",
            )
        # Check custom mappings first
        if text in self.custom_mappings:
            mapping = self.custom_mappings[text]
            if isinstance(mapping, dict):
                return LanguageDetectionResult(**mapping)
            return LanguageDetectionResult(primary_language=str(mapping), status="COMPLETED", provider="mock")

        # Heuristic detection for tests
        script_hint = _compute_script_hint(text)
        scripts = {unicodedata.name(c, "").split(" ")[0] for c in text if c.isalpha()}

        # Script alone is never definitive language proof:
        # Latin can be English, Tanglish, Hinglish, or any Latin-script language.
        is_latin = "LATIN" in scripts
        is_tamil = "TAMIL" in scripts
        is_devanagari = "DEVANAGARI" in scripts
        is_telugu = "TELUGU" in scripts

        # Check for mixed script / multilingual text
        is_mixed = len(scripts) > 1
        detected = []

        if is_tamil:
            detected.append("ta")
        if is_devanagari:
            detected.append("hi")
        if is_telugu:
            detected.append("te")
        if is_latin:
            # Check for Romanized patterns or default to en candidate
            lower = text.lower()
            if any(term in lower for term in ("kaasu", "panam", "illa", "theriyathu", "romba", "vanakkam")):
                detected.append("ta-Latn")
            elif any(term in lower for term in ("paisa", "rupaye", "nahi", "malum", "namaste")):
                detected.append("hi-Latn")
            else:
                detected.append("en")

        primary = "mixed" if len(detected) > 1 else (detected[0] if detected else "und")

        return LanguageDetectionResult(
            primary_language=primary,
            detected_languages=detected,
            script_hint=script_hint,
            is_mixed=is_mixed or len(detected) > 1,
            review_required=is_mixed or len(detected) > 1 or any(d.endswith("-Latn") for d in detected),
            status="COMPLETED",
            provider="mock",
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "readiness": "mock" if self.available else "unavailable",
            "provider": "mock",
            "available": self.available,
        }


class MockTranslationProvider(TranslationProvider):
    def __init__(self, available: bool = False, translations: dict[str, str] | None = None):
        # By default in mock mode, translation fails closed unless explicitly enabled/configured
        self.available = available
        self.translations = translations or {}

    def translate(self, text: str, source_language: str = "und", target_language: str = "en", metadata: dict[str, Any] | None = None) -> TranslationResult:
        if not text.strip():
            return TranslationResult(
                original_text="",
                translated_text="",
                status="COMPLETED",
                provider="mock",
            )
        if not self.available:
            return TranslationResult(
                original_text=text,
                translated_text="",
                source_language=source_language,
                target_language=target_language,
                status="CAPABILITY_UNAVAILABLE",
                reason="Translation capability is unavailable; original text is preserved.",
                provider="mock",
            )
        translated = self.translations.get(text, f"[Mock translation of: {text}]")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return TranslationResult(
            original_text=text,
            translated_text=translated,
            source_language=source_language,
            target_language=target_language,
            status="COMPLETED",
            provider="mock",
            review_required=True,
            provenance={"original_text_hash": digest, "source_id": (metadata or {}).get("source_id")},
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "readiness": "mock" if self.available else "unavailable",
            "provider": "mock",
            "available": self.available,
        }


class MockMediaAdapter(MediaAdapter):
    def __init__(
        self,
        speech_to_text: SpeechToTextProvider | None = None,
        ocr: OCRProvider | None = None,
        language_detection: LanguageDetectionProvider | None = None,
        translation: TranslationProvider | None = None,
    ):
        self.speech_to_text = speech_to_text or MockSpeechToTextProvider()
        self.ocr = ocr or MockOCRProvider()
        self.language_detection = language_detection or MockLanguageDetectionProvider()
        self.translation = translation or MockTranslationProvider()

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "speech_to_text": self.speech_to_text.get_capabilities(),
            "ocr": self.ocr.get_capabilities(),
            "language_detection": self.language_detection.get_capabilities(),
            "translation": self.translation.get_capabilities(),
        }
