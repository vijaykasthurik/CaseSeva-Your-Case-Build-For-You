import json
import logging
import os
import re
from pathlib import Path
from typing import Any
import requests
import PyPDF2

from ..legal_retrieval import LegalRetrievalAdapter, normalize_domain_to_corpus
from ..authorised_sources import validate_authorised_url, is_authorised_url

logger = logging.getLogger("caseseva.live_retrieval")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BASE_HOST = "https://www.indiacode.nic.in"


def normalize_section_num(sec_str: str) -> str:
    """Normalises section numbers: 'WAGES-45 ( 6 )', 'Section 45(6)', '45 (6)' -> '45(6)'"""
    cleaned = re.sub(r"^[A-Z0-9]+-", "", sec_str).strip()
    cleaned = re.sub(r"(?i)\b(?:Section|Sec|\.)\b", "", cleaned).strip()
    cleaned = re.sub(r"\s*\(\s*", "(", cleaned)
    cleaned = re.sub(r"\s*\)\s*", ")", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned


def extract_pdf_text_pypdf2(pdf_bytes: bytes) -> str:
    """Pure-Python PyPDF2 text extractor (Lambda safe, zero compiled C binary dependencies)."""
    import io
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text
    except Exception as err:
        logger.error(f"PyPDF2 extraction error: {err}")
        return ""


def extract_sections_from_pdf_text(full_text: str, domain_prefix: str = "SEC") -> list[dict[str, Any]]:
    sections = []
    seen = set()

    pattern1 = re.compile(
        r"(?:^|\n)\s*(\d+[A-Z]?(?:\([0-9a-z]+\))?)\.\s*([A-Z][^\n\r]{2,120}?)(?:\.|\s*[\-–—]|\n)",
        re.MULTILINE,
    )
    pattern2 = re.compile(
        r"(?:^|\n)\s*(?:Section|Sec\.)\s*(\d+[A-Z]?(?:\([0-9a-z]+\))?)\.?\s*[\-–—:]?\s*([A-Z][^\n\r]{2,120}?)(?:\.|\s*[\-–—]|\n)",
        re.MULTILINE,
    )

    for p in [pattern1, pattern2]:
        for match in p.finditer(full_text):
            sec_num = match.group(1).strip()
            sec_title = match.group(2).strip()
            sec_title = re.sub(r"[\-–—.]+$", "", sec_title).strip()

            if (
                len(sec_title) < 3
                or sec_title.isdigit()
                or sec_num in seen
                or any(keyword in sec_title.upper() for keyword in ["ACT NO", "ARRANGEMENT OF SECTIONS", "MINISTRY OF", "CHAPTER", "PART "])
            ):
                continue

            seen.add(sec_num)
            pid = f"{domain_prefix.upper()}-{sec_num}"
            sections.append({
                "provision_id": pid,
                "section_number": sec_num,
                "title": f"Section {sec_num} - {sec_title}",
                "raw_title": sec_title,
                "summary": f"Statutory provision extracted under Section {sec_num}: {sec_title}.",
                "text": full_text[match.start(): match.start() + 1500],
            })

    def sort_key(s):
        m = re.match(r"^(\d+)", s["section_number"])
        return int(m.group(1)) if m else 99999

    return sorted(sections, key=sort_key)


class LiveLegalRetrievalAdapter(LegalRetrievalAdapter):
    """Retrieves legal provisions from trusted static corpora or live allowlisted Indian government legal sources."""

    def __init__(self, corpus_root: str | Path = "backend/legal_corpus", cache_root: str | Path = "scratch/rag_cache"):
        self.corpus_root = Path(corpus_root)
        self.cache_root = Path(cache_root)
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def _search_static_corpus(self, norm_domain: str, query: str, limit: int) -> list[dict[str, Any]]:
        corpus_file = self.corpus_root / norm_domain / "provisions.json"
        if not corpus_file.exists():
            return []

        entries = json.loads(corpus_file.read_text(encoding="utf-8"))
        terms = {term.lower() for term in query.split() if len(term) > 2}
        ranked = sorted(
            entries,
            key=lambda entry: sum(
                term in (entry["title"] + " " + entry["summary"]).lower() for term in terms
            ),
            reverse=True,
        )
        return ranked[:limit]

    def _fetch_live_act(self, domain: str, query: str) -> tuple[list[dict[str, Any]], str]:
        validate_authorised_url(BASE_HOST)

        cache_key = re.sub(r"[^\w\s]", "", query).replace(" ", "_").lower()
        cache_path = self.cache_root / f"{cache_key}.json"

        if cache_path.exists():
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return data.get("sections", []), data.get("full_text", "")

        search_url = f"{BASE_HOST}/server/api/discover/search/objects?query={requests.utils.quote(query)}&dsoType=ITEM"
        validate_authorised_url(search_url)

        try:
            r = requests.get(search_url, headers=HEADERS, timeout=15, verify=True)
            if r.status_code != 200:
                return [], ""

            objs = r.json().get("_embedded", {}).get("searchResult", {}).get("_embedded", {}).get("objects", [])
            if not objs:
                return [], ""

            for obj in objs:
                indexable = obj.get("_embedded", {}).get("indexableObject", {})
                item_uuid = indexable.get("uuid")
                if not item_uuid:
                    continue

                bundles_url = f"{BASE_HOST}/server/api/core/items/{item_uuid}/bundles"
                r_b = requests.get(bundles_url, headers=HEADERS, timeout=10, verify=True)
                if r_b.status_code != 200:
                    continue

                bundles = r_b.json().get("_embedded", {}).get("bundles", [])
                for bundle in bundles:
                    if bundle.get("name") in {"ORIGINAL", "CONTENT"}:
                        bit_href = bundle.get("_links", {}).get("bitstreams", {}).get("href")
                        if bit_href:
                            r_bits = requests.get(bit_href, headers=HEADERS, timeout=10, verify=True)
                            if r_bits.status_code == 200:
                                bits = r_bits.json().get("_embedded", {}).get("bitstreams", [])
                                for bit in bits:
                                    name = bit.get("name", "")
                                    if name.endswith(".pdf") and not name.endswith(".jpg"):
                                        dl_url = bit.get("_links", {}).get("content", {}).get("href")
                                        validate_authorised_url(dl_url)
                                        r_dl = requests.get(dl_url, headers=HEADERS, timeout=30, verify=True)
                                        if r_dl.status_code == 200 and len(r_dl.content) > 200:
                                            full_text = extract_pdf_text_pypdf2(r_dl.content)
                                            prefix = domain.upper()[:5]
                                            sections = extract_sections_from_pdf_text(full_text, domain_prefix=prefix)
                                            for sec in sections:
                                                sec["source_url"] = dl_url
                                            
                                            cache_data = {"sections": sections, "full_text": full_text, "source_url": dl_url}
                                            cache_path.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
                                            return sections, full_text
        except Exception as exc:
            logger.error(f"Live retrieval failed for query '{query}': {exc}")

        return [], ""

    def search(self, query: str, limit: int = 10, domain: str = "") -> list[dict[str, Any]]:
        norm_domain = normalize_domain_to_corpus(domain)
        if not norm_domain:
            return []

        # L1: Static corpus first
        static_results = self._search_static_corpus(norm_domain, query, limit)
        if static_results:
            return static_results

        # L2: Live allowlisted RAG retrieval
        live_sections, _ = self._fetch_live_act(domain, query)
        if live_sections:
            terms = {term.lower() for term in query.split() if len(term) > 2}
            ranked = sorted(
                live_sections,
                key=lambda entry: sum(
                    term in (entry["title"] + " " + entry.get("summary", "")).lower() for term in terms
                ),
                reverse=True,
            )
            return ranked[:limit]

        return []
