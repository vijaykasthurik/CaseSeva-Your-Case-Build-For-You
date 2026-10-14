"""Media and multilingual provider abstractions for CaseSeva common input processing.

Decouples speech-to-text, OCR, language detection, and translation from
specific cloud vendors and language assumptions.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TranscriptionResult:
    transcript: str
    detected_languages: list[str] = field(default_factory=list)
    primary_language: str = "und"
    confidence: float | None = None
    uncertainties: list[str] = field(default_factory=list)
    timestamps: list[dict[str, Any]] = field(default_factory=list)
    status: str = "COMPLETED"  # COMPLETED, PENDING, FAILED, CAPABILITY_UNAVAILABLE
    reason: str | None = None
    provider: str = "mock"
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class OCRResult:
    text: str
    status: str = "COMPLETED"  # COMPLETED, PENDING, FAILED, CAPABILITY_UNAVAILABLE
    confidence: float | None = None
    reason: str | None = None
    provider: str = "mock"
    language_hint: str | None = None
    review_required: bool = True


@dataclass
class LanguageDetectionResult:
    primary_language: str = "und"
    detected_languages: list[str] = field(default_factory=list)
    script_hint: str = ""
    is_mixed: bool = False
    confidence: float | None = None
    uncertainties: list[str] = field(default_factory=list)
    review_required: bool = False
    status: str = "COMPLETED"  # COMPLETED, PENDING, DEVELOPMENT_ONLY, CAPABILITY_UNAVAILABLE
    provider: str = "mock"
    reason: str | None = None


@dataclass
class TranslationResult:
    original_text: str
    translated_text: str
    source_language: str = "und"
    target_language: str = "en"
    status: str = "COMPLETED"  # COMPLETED, PENDING, DEVELOPMENT_ONLY, CAPABILITY_UNAVAILABLE, FAILED
    fidelity: str | None = None
    uncertainties: list[str] = field(default_factory=list)
    review_required: bool = True
    provider: str = "mock"
    reason: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


class SpeechToTextProvider(ABC):
    @abstractmethod
    def transcribe(self, content: bytes, extension: str, metadata: dict[str, Any] | None = None) -> TranscriptionResult:
        raise NotImplementedError

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        raise NotImplementedError


class OCRProvider(ABC):
    @abstractmethod
    def ocr_image(self, content: bytes, metadata: dict[str, Any] | None = None) -> OCRResult:
        raise NotImplementedError

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        raise NotImplementedError


class LanguageDetectionProvider(ABC):
    @abstractmethod
    def detect_language(self, text: str, metadata: dict[str, Any] | None = None) -> LanguageDetectionResult:
        raise NotImplementedError

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        raise NotImplementedError


class TranslationProvider(ABC):
    @abstractmethod
    def translate(self, text: str, source_language: str = "und", target_language: str = "en", metadata: dict[str, Any] | None = None) -> TranslationResult:
        raise NotImplementedError

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        raise NotImplementedError


class MediaAdapter(ABC):
    speech_to_text: SpeechToTextProvider
    ocr: OCRProvider
    language_detection: LanguageDetectionProvider
    translation: TranslationProvider

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        raise NotImplementedError
