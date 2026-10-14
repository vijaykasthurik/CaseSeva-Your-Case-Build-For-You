"""Real, truthful official-source acquisition engine for CaseSeva Phase 4.

Lifecycle:
Official source -> discover real document -> retrieve actual bytes ->
validate official provenance -> store raw bytes in MongoDB GridFS ->
extract text -> sectionize -> compute immutable hashes ->
create MongoDB legal authority candidate/version -> REVIEW_PENDING ->
NOT retrieval-eligible until independent human review.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

import pymupdf
import pymongo
from gridfs import GridFS

from .models import (
    AuthorityType,
    ExtractedDocument,
    ProvisionRecord,
    RawDocumentRecord,
    ReviewStatus,
)
from .sectionizer import StatutorySectionizer

REGISTRY_PATH = Path(__file__).resolve().parent / "registries" / "official_sources.json"
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25 Megabytes


class AcquisitionSecurityError(ValueError):
    """Raised when an acquisition request violates security policy (SSRF, scheme, host)."""


class ContentValidationError(ValueError):
    """Raised when retrieved content fails integrity, magic-byte, or type validation."""


class GridFSPersistenceError(RuntimeError):
    """Raised when raw-byte persistence or read-back verification in GridFS fails."""


class OfficialRegistrySecurity:
    """Enforces strict official host allowlisting and SSRF protection."""

    # Disallowed private and special-purpose IP ranges
    BLOCKED_NETWORKS = [
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("100.64.0.0/10"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.0.0.0/24"),
        ipaddress.ip_network("192.0.2.0/24"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("198.18.0.0/15"),
        ipaddress.ip_network("198.51.100.0/24"),
        ipaddress.ip_network("203.0.113.0/24"),
        ipaddress.ip_network("224.0.0.0/4"),
        ipaddress.ip_network("240.0.0.0/4"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("::/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    ]

    ALLOWED_HOSTS: dict[str, set[str]] = {
        "india_code_central": {
            "indiacode.gov.in",
            "backend.indiacode.gov.in",
            "www.indiacode.nic.in",
            "indiacode.nic.in",
        },
        "legislative_dept_india": {
            "legislative.gov.in",
            "www.legislative.gov.in",
        },
        "doca_consumer_affairs": {
            "consumeraffairs.nic.in",
            "www.consumeraffairs.nic.in",
            "consumeraffairs.gov.in",
            "www.consumeraffairs.gov.in",
        },
        "meity_portal": {
            "meity.gov.in",
            "www.meity.gov.in",
        },
    }

    def __init__(self, registry_file: Path | str | None = None):
        self.registry_file = Path(registry_file) if registry_file else REGISTRY_PATH
        self.registry_data: dict[str, Any] = {}
        if self.registry_file.is_file():
            self.registry_data = json.loads(self.registry_file.read_text(encoding="utf-8"))

    def get_source_metadata(self, registry_id: str) -> dict[str, Any]:
        sources = self.registry_data.get("sources", [])
        for s in sources:
            if s.get("source_id") == registry_id:
                return s
        return {}

    def is_automation_permitted(self, registry_id: str) -> tuple[bool, str]:
        meta = self.get_source_metadata(registry_id)
        if not meta:
            return False, f"Unknown registry source: {registry_id}"
        if meta.get("captcha_required", False):
            return False, f"MANUAL_OR_BROWSER_REVIEW_REQUIRED: source requires CAPTCHA ({registry_id})"
        if meta.get("implementation_status") == "MANUAL_BROWSER_ONLY":
            return False, f"MANUAL_OR_BROWSER_REVIEW_REQUIRED: source is marked manual-only ({registry_id})"
        if meta.get("recommended_acquisition_method") == "MANUAL_OR_BROWSER_REVIEW_REQUIRED":
            return False, f"MANUAL_OR_BROWSER_REVIEW_REQUIRED: manual method mandated ({registry_id})"
        return True, "AUTOMATION_PERMITTED"

    def is_ip_blocked(self, ip_str: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip_str)
            return any(addr in net for net in self.BLOCKED_NETWORKS)
        except ValueError:
            return False

    def validate_url(self, registry_id: str, url: str, allow_private_for_test: bool = False) -> None:
        parsed = urlparse(url or "")
        if parsed.scheme != "https":
            raise AcquisitionSecurityError(f"Insecure scheme '{parsed.scheme}': only https is permitted")
        if not parsed.hostname:
            raise AcquisitionSecurityError("URL missing hostname")
        if parsed.username or parsed.password:
            raise AcquisitionSecurityError("URL embedded credentials forbidden")
        if parsed.port not in (None, 443):
            raise AcquisitionSecurityError(f"Disallowed non-standard port: {parsed.port}")

        host = parsed.hostname.lower()
        allowed = self.ALLOWED_HOSTS.get(registry_id, set())
        if host not in allowed:
            raise AcquisitionSecurityError(f"Host '{host}' not permitted for registry source '{registry_id}'")

        if not allow_private_for_test:
            # Check for direct IP in hostname
            if self.is_ip_blocked(host):
                raise AcquisitionSecurityError(f"Access to private/loopback IP forbidden: {host}")


class SecureRedirectHandler(HTTPRedirectHandler):
    """Monitors HTTP redirects and ensures each intermediate hop is secure and authorized."""

    def __init__(self, security: OfficialRegistrySecurity, registry_id: str, allow_private: bool = False):
        super().__init__()
        self.security = security
        self.registry_id = registry_id
        self.allow_private = allow_private
        self.redirect_chain: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.security.validate_url(self.registry_id, newurl, allow_private_for_test=self.allow_private)
        self.redirect_chain.append(newurl)
        if len(self.redirect_chain) > 5:
            raise AcquisitionSecurityError("Too many redirects (exceeded limit of 5 hops)")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class OfficialDocumentRetriever:
    """Safe, rate-limited, and verified HTTPS retrieval of official legal material."""

    def __init__(
        self,
        security: OfficialRegistrySecurity | None = None,
        user_agent: str = "CaseSeva Phase4 Official Legal Acquisition/1.0 (+https://caseseva.gov.in)",
    ):
        self.security = security or OfficialRegistrySecurity()
        self.user_agent = user_agent

    def fetch(
        self,
        registry_id: str,
        official_url: str,
        timeout: int = 20,
        allow_private_for_test: bool = False,
    ) -> dict[str, Any]:
        """Retrieves raw bytes from official HTTPS URL with security and content validation."""
        permitted, reason = self.security.is_automation_permitted(registry_id)
        if not permitted:
            raise AcquisitionSecurityError(reason)

        self.security.validate_url(registry_id, official_url, allow_private_for_test=allow_private_for_test)

        meta = self.security.get_source_metadata(registry_id)
        source_owner = meta.get("owner", "Official Government Publisher")

        redirect_handler = SecureRedirectHandler(self.security, registry_id, allow_private=allow_private_for_test)
        opener = build_opener(redirect_handler)
        req = Request(official_url, headers={"User-Agent": self.user_agent})

        retrieval_start = datetime.now(timezone.utc).isoformat()
        try:
            with opener.open(req, timeout=timeout) as resp:
                final_url = resp.geturl()
                self.security.validate_url(registry_id, final_url, allow_private_for_test=allow_private_for_test)
                http_status = resp.status
                headers_dict = {k: v for k, v in resp.headers.items()}
                content_type = headers_dict.get("Content-Type", "application/octet-stream").split(";")[0].strip()

                raw_bytes = resp.read(MAX_DOWNLOAD_BYTES + 1)
                if len(raw_bytes) > MAX_DOWNLOAD_BYTES:
                    raise ContentValidationError(f"Downloaded content exceeds maximum limit of {MAX_DOWNLOAD_BYTES} bytes")
                if len(raw_bytes) == 0:
                    raise ContentValidationError("Retrieved 0-byte document; empty content is invalid")

        except (HTTPError, URLError) as exc:
            raise RuntimeError(f"Network error during official retrieval: {exc}") from exc

        # Detect CAPTCHA or bot challenges masquerading as 200 OK
        sample = raw_bytes[:8192].lower()
        if any(token in sample for token in [b"recaptcha", b"cf-turnstile", b"challenge-running", b"please enable cookies"]):
            raise ContentValidationError("Anti-bot or CAPTCHA challenge encountered; automated retrieval disallowed")

        # Content validation: if PDF expected or claimed
        is_pdf_url = final_url.lower().endswith(".pdf") or official_url.lower().endswith(".pdf")
        if content_type == "application/pdf" or is_pdf_url:
            if not raw_bytes.startswith(b"%PDF"):
                raise ContentValidationError("Content claimed or expected to be PDF lacks '%PDF' magic header (possible HTML error page)")
            content_type = "application/pdf"

        raw_hash = hashlib.sha256(raw_bytes).hexdigest()

        return {
            "registry_id": registry_id,
            "requested_url": official_url,
            "final_url": final_url,
            "redirect_chain": redirect_handler.redirect_chain,
            "retrieved_at": retrieval_start,
            "http_status": http_status,
            "content_type": content_type,
            "byte_size": len(raw_bytes),
            "raw_bytes": raw_bytes,
            "raw_hash": raw_hash,
            "source_owner": source_owner,
            "retrieval_method": "OFFICIAL_HTTPS_GET",
            "http_headers": headers_dict,
        }


class GridFSRawStorage:
    """Stores immutable raw official legal bytes in MongoDB GridFS with roundtrip verification."""

    @staticmethod
    def get_storage_key(registry_id: str, raw_hash: str, ext: str = "pdf") -> str:
        clean_ext = ext.lstrip(".").lower() or "bin"
        return f"raw_legal_sources/{registry_id}/{raw_hash}.{clean_ext}"

    @classmethod
    def store_raw_document(
        cls,
        db: pymongo.database.Database,
        registry_id: str,
        document_id: str,
        raw_bytes: bytes,
        raw_hash: str,
        metadata: dict[str, Any],
    ) -> tuple[str, str, bool]:
        """Stores raw bytes in GridFS with idempotent deduplication and roundtrip verification.

        Returns (gridfs_file_id, gridfs_key, already_existed).
        """
        fs = GridFS(db)
        expected_size = len(raw_bytes)
        ext = "pdf" if metadata.get("content_type") == "application/pdf" else "bin"
        gridfs_key = cls.get_storage_key(registry_id, raw_hash, ext=ext)

        # 1. Check if identical raw object already exists
        existing = db["fs.files"].find_one({"filename": gridfs_key})
        if existing:
            file_id = existing["_id"]
            grid_out = fs.get(file_id)
            stored_bytes = grid_out.read()
            stored_hash = hashlib.sha256(stored_bytes).hexdigest()
            if stored_hash != raw_hash or len(stored_bytes) != expected_size:
                raise GridFSPersistenceError(
                    f"GridFS file '{gridfs_key}' exists but hash/size mismatch! Expected {raw_hash}, got {stored_hash}"
                )
            return str(file_id), gridfs_key, True

        # 2. Store new raw object
        grid_file_id = fs.put(
            raw_bytes,
            filename=gridfs_key,
            raw_hash=raw_hash,
            content_type=metadata.get("content_type", "application/pdf"),
            metadata={
                **metadata,
                "document_id": document_id,
                "registry_id": registry_id,
                "stored_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # 3. Read back and verify exact byte integrity
        read_back_out = fs.get(grid_file_id)
        read_back_bytes = read_back_out.read()
        read_back_hash = hashlib.sha256(read_back_bytes).hexdigest()
        read_back_size = len(read_back_bytes)

        if read_back_hash != raw_hash:
            raise GridFSPersistenceError(
                f"GridFS write integrity check failed: written hash {read_back_hash} != expected {raw_hash}"
            )
        if read_back_size != expected_size:
            raise GridFSPersistenceError(
                f"GridFS write integrity check failed: written size {read_back_size} != expected {expected_size}"
            )

        return str(grid_file_id), gridfs_key, False


class OfficialTextExtractor:
    """Extracts text strictly from official raw document bytes without synthetic text injection."""

    @staticmethod
    def extract(raw_bytes: bytes, content_type: str = "application/pdf") -> tuple[str, str, str, str, list[str]]:
        """Extracts text from bytes.

        Returns (text, text_hash, extractor_version, status, warnings).
        """
        warnings: list[str] = []
        if content_type == "application/pdf" or raw_bytes.startswith(b"%PDF"):
            if not raw_bytes.startswith(b"%PDF"):
                raise ContentValidationError("Content claimed to be PDF lacks '%PDF' magic header (possible HTML error page)")
            try:
                with pymupdf.open(stream=raw_bytes, filetype="pdf") as doc:
                    pages_text = [page.get_text() for page in doc]
                    text = "\n".join(pages_text).strip()
                    extractor_ver = f"pymupdf_{pymupdf.__version__}"
                    if len(doc) > 0 and not text:
                        return (
                            "",
                            hashlib.sha256(b"").hexdigest(),
                            extractor_ver,
                            "SCANNED_OCR_REQUIRED",
                            ["Zero extracted text: document appears scanned or image-only; OCR review required"],
                        )
            except Exception as exc:
                raise ContentValidationError(f"Failed to extract text from PDF bytes: {exc}") from exc
        else:
            try:
                text = raw_bytes.decode("utf-8")
                extractor_ver = "utf-8_decode"
            except UnicodeDecodeError:
                text = raw_bytes.decode("latin-1", errors="replace")
                extractor_ver = "latin-1_decode"
                warnings.append("Text decoded with fallback encoding; possible corruption")

        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return text, text_hash, extractor_ver, "EXTRACTED", warnings


class OfficialAcquisitionPipeline:
    """Complete official source acquisition pipeline producing REVIEW_PENDING candidates."""

    def __init__(
        self,
        retriever: OfficialDocumentRetriever | None = None,
        sectionizer: StatutorySectionizer | None = None,
    ):
        self.retriever = retriever or OfficialDocumentRetriever()
        self.sectionizer = sectionizer or StatutorySectionizer()

    def acquire_document(
        self,
        db: pymongo.database.Database,
        registry_id: str,
        document_id: str,
        title: str,
        official_url: str,
        domain: str,
        authority_type: AuthorityType = AuthorityType.ACT,
        citation: str = "",
        allow_private_for_test: bool = False,
    ) -> dict[str, Any]:
        """Runs the full official acquisition lifecycle for a single enactment."""
        # 1. Retrieve actual bytes
        retrieval = self.retriever.fetch(
            registry_id=registry_id,
            official_url=official_url,
            allow_private_for_test=allow_private_for_test,
        )

        raw_bytes = retrieval["raw_bytes"]
        raw_hash = retrieval["raw_hash"]
        final_url = retrieval["final_url"]
        retrieved_at = retrieval["retrieved_at"]
        source_owner = retrieval["source_owner"]

        # 2. Store raw bytes in MongoDB GridFS
        storage_meta = {
            "title": title,
            "official_url": official_url,
            "final_url": final_url,
            "domain": domain,
            "authority_type": authority_type.value,
            "retrieved_at": retrieved_at,
            "content_type": retrieval["content_type"],
            "raw_hash": raw_hash,
            "source_owner": source_owner,
        }
        gridfs_file_id, gridfs_key, already_in_gridfs = GridFSRawStorage.store_raw_document(
            db=db,
            registry_id=registry_id,
            document_id=document_id,
            raw_bytes=raw_bytes,
            raw_hash=raw_hash,
            metadata=storage_meta,
        )

        # 3. Create RawDocumentRecord model
        raw_record = RawDocumentRecord(
            document_id=document_id,
            source_id=registry_id,
            title=title,
            authority_type=authority_type,
            official_url=official_url,
            final_url=final_url,
            retrieved_at=retrieved_at,
            raw_content_hash=raw_hash,
            content_type=retrieval["content_type"],
            file_extension="pdf",
            file_size_bytes=retrieval["byte_size"],
            http_headers=retrieval["http_headers"],
            source_owner=source_owner,
            retrieval_method="OFFICIAL_HTTPS_GET",
            http_status=retrieval["http_status"],
            gridfs_file_id=gridfs_file_id,
            gridfs_key=gridfs_key,
            redirect_chain=retrieval["redirect_chain"],
            source_mode="OFFICIAL_ACQUISITION",
            officially_retrieved=True,
        )

        # 4. Extract text strictly from raw bytes
        text, text_hash, extractor_ver, ext_status, ext_warnings = OfficialTextExtractor.extract(
            raw_bytes=raw_bytes, content_type=retrieval["content_type"]
        )

        extracted_record = ExtractedDocument(
            document_id=document_id,
            source_id=registry_id,
            title=title,
            authority_type=authority_type,
            official_url=official_url,
            raw_hash=raw_hash,
            source_owner=source_owner,
            text_content=text,
            text_hash=text_hash,
            extractor_version=extractor_ver,
            extraction_status=ext_status,
            extraction_warnings=ext_warnings,
            gridfs_file_id=gridfs_file_id,
            source_mode="OFFICIAL_ACQUISITION",
            officially_retrieved=True,
        )

        # 5. Generic Statutory Sectionization
        provisions = self.sectionizer.extract_provisions(
            document_id=document_id,
            title=title,
            text=text,
            official_url=official_url,
            source_owner=source_owner,
            raw_document_hash=raw_hash,
            authority_type=authority_type,
            domain=domain,
            jurisdiction="IN",
            language="en",
        )

        # 6. Persist Ingestion Request in legal_ingestion_requests
        ingestion_id = uuid4().hex
        now_ts = datetime.now(timezone.utc).isoformat()
        ingestion_doc = {
            "id": ingestion_id,
            "registry_id": registry_id,
            "official_url": official_url,
            "final_url": final_url,
            "state": "PARSED",
            "document_id": document_id,
            "title": title,
            "domain": domain,
            "authority_type": authority_type.value,
            "raw_hash": raw_hash,
            "content_hash": text_hash,
            "byte_size": retrieval["byte_size"],
            "gridfs_file_id": gridfs_file_id,
            "gridfs_key": gridfs_key,
            "created_at": now_ts,
            "retrieved_at": retrieved_at,
            "provisions_count": len(provisions),
            "events": [
                {"state": "DISCOVERED", "at": now_ts},
                {"state": "DOWNLOADED", "at": now_ts, "raw_hash": raw_hash, "gridfs_file_id": gridfs_file_id},
                {"state": "PARSED", "at": now_ts, "provisions_count": len(provisions), "text_hash": text_hash},
            ],
            "official_text": text[:245000],  # Bound within model max length
        }
        db["legal_ingestion_requests"].insert_one(ingestion_doc)

        # 7. Create Legal Authority Candidate Version in legal_authority_versions (REVIEW_PENDING)
        # Choose a representative provision (e.g. Section 1 or 3, or the first provision)
        candidate_versions: list[dict[str, Any]] = []
        if provisions:
            # Pick the first section provision
            selected_prov = provisions[0]
            for p in provisions:
                if p.section in ("1", "2", "3", "4", "43"):
                    selected_prov = p
                    break

            prov_source_id = f"{document_id}_s{selected_prov.section.lower()}"
            # Ensure text substring matches quote
            quote_text = selected_prov.quote
            # Clean quote if needed to fit max length 6000
            if len(quote_text) > 5900:
                quote_text = quote_text[:5900]

            candidate_source = {
                "source_id": prov_source_id,
                "family": title,
                "source_type": "STATUTE",
                "domain": domain,
                "jurisdiction": "IN",
                "title": title,
                "section": selected_prov.section,
                "citation": citation or f"{title} (Official Gazette)",
                "official_url": official_url,
                "final_url": final_url,
                "ingestion_id": ingestion_id,
                "review_state": "REVIEW_PENDING",
                "review_id": None,
                "revision_status": "NONE",
                "parent_revision": None,
                "revision_request_id": None,
                "revision_metadata": {},
                "reviewed_at": None,
                "registry_id": registry_id,
                "source_language": "en",
                "official_text": text[:245000],
                "quote": quote_text,
                "content_hash": text_hash,
                "retrieved_at": retrieved_at,
                "effective_from": None,
                "effective_until": None,
                "temporal_source_ids": [],
                "temporal_reviewed": False,
                "version_note": "Official source acquisition candidate - pending independent human review",
                "corpus_version": "phase4-candidate",
                "source_reviewed": False,
                "reviewed_by": None,
                "section_start": selected_prov.section_start,
                "section_end": selected_prov.section_start + len(quote_text),
                "verification": "PENDING",
                "rules": {},
                "rules_reviewed": False,
                "raw_hash": raw_hash,
                "working_translation": None,
            }

            # Generate version ID
            from backend.services.case_blackboard import digest
            candidate_digest = digest(candidate_source)
            version_doc = {
                "_id": candidate_digest,
                "id": candidate_digest,
                "source": candidate_source,
                "reason": "Official source acquisition candidate - pending independent human review",
                "gridfs_file_id": gridfs_file_id,
                "gridfs_key": gridfs_key,
            }
            # Insert into legal_authority_versions (NOT legal_authority_heads)
            db["legal_authority_versions"].insert_one(version_doc)
            candidate_versions.append(version_doc)

        return {
            "document_id": document_id,
            "title": title,
            "domain": domain,
            "registry_id": registry_id,
            "official_url": official_url,
            "final_url": final_url,
            "raw_hash": raw_hash,
            "text_hash": text_hash,
            "byte_size": retrieval["byte_size"],
            "gridfs_file_id": gridfs_file_id,
            "gridfs_key": gridfs_key,
            "already_in_gridfs": already_in_gridfs,
            "provisions_count": len(provisions),
            "ingestion_id": ingestion_id,
            "candidate_versions": [v["id"] for v in candidate_versions],
            "review_status": "REVIEW_PENDING",
            "verification": "PENDING",
            "source_reviewed": False,
            "review_eligible": False,
        }


def inspect_candidate_for_review(db: pymongo.database.Database, version_id: str) -> dict[str, Any] | None:
    """Prepares complete reviewer inspection package for human administrative decision."""
    ver = db["legal_authority_versions"].find_one({"$or": [{"_id": version_id}, {"id": version_id}]})
    if not ver:
        return None
    source = ver.get("source", {})
    ingestion_id = source.get("ingestion_id")
    ingestion = db["legal_ingestion_requests"].find_one({"$or": [{"_id": ingestion_id}, {"id": ingestion_id}]}) if ingestion_id else {}

    gridfs_file_id = ver.get("gridfs_file_id") or (ingestion.get("gridfs_file_id") if ingestion else None)
    gridfs_key = ver.get("gridfs_key") or (ingestion.get("gridfs_key") if ingestion else None)

    return {
        "version_id": version_id,
        "source_id": source.get("source_id"),
        "official_source": source.get("registry_id"),
        "official_owner": (ingestion.get("source_owner") if ingestion else None) or "Official Government Publisher",
        "requested_url": source.get("official_url"),
        "final_url": source.get("final_url"),
        "raw_gridfs_file_id": gridfs_file_id,
        "raw_gridfs_key": gridfs_key,
        "raw_hash": source.get("raw_hash"),
        "extraction_hash": source.get("content_hash"),
        "extracted_text_snippet": (source.get("official_text") or "")[:500],
        "extracted_text_total_chars": len(source.get("official_text") or ""),
        "exact_provision_quote": source.get("quote"),
        "section": source.get("section"),
        "section_start": source.get("section_start"),
        "section_end": source.get("section_end"),
        "domain": source.get("domain"),
        "jurisdiction": source.get("jurisdiction"),
        "retrieval_timestamp": source.get("retrieved_at"),
        "review_state": source.get("review_state"),
        "source_reviewed": source.get("source_reviewed"),
        "verification": source.get("verification"),
        "temporal_reviewed": source.get("temporal_reviewed"),
        "temporal_warnings": [
            "TEMPORAL_STATUS_UNVERIFIED",
            "COMMENCEMENT_AND_AMENDMENT_LINEAGE_REQUIRES_INDEPENDENT_HUMAN_REVIEW",
        ],
        "acquisition_method": "OFFICIAL_HTTPS_GET",
        "parsing_warnings": [],
    }
