"""Conservative registry: a URL or an LLM decision is not evidence of verified law."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1] / "legal_corpus"
REGISTRY = Path(__file__).resolve().parents[1] / "registries"


def source_record(item: dict, source_registry: dict) -> tuple[bool, str]:
    source = source_registry.get(item.get("source_id"))
    if not source or source.get("tier") != "PRIMARY" or not source.get("enabled"):
        return False, "No enabled official source record."
    url = urlparse(item.get("source_url", ""))
    if url.scheme != "https" or url.hostname not in source.get("hosts", []) or url.username or url.password:
        return False, "Source URL is not registered as an official HTTPS source."
    text = item.get("official_text", "")
    quote = item.get("quote", "")
    if not text or not quote or quote not in text:
        return False, "Official source text and exact supporting quotation are required."
    if hashlib.sha256(text.encode()).hexdigest() != item.get("content_hash"):
        return False, "Source content hash does not match the stored text."
    if not item.get("reviewed_by") or not item.get("source_reviewed"):
        return False, "Source identification and section boundaries require ingestion review."
    try:
        retrieved = datetime.fromisoformat(item["retrieved_at"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - retrieved).total_seconds()
        if age < -300 or age > source.get("refresh_days", 30) * 86400:
            return False, "Official source freshness must be checked again."
    except (KeyError, ValueError, TypeError):
        return False, "A valid retrieval timestamp is required."
    return True, "Matched to reviewed official text."


class LegalKnowledge:
    def __init__(self, root=ROOT, registry=REGISTRY):
        self.root = Path(root)
        self.registry = Path(registry)
        self.sources = json.loads((self.registry / "sources.json").read_text(encoding="utf-8"))
        self.domains = json.loads((self.registry / "domains.json").read_text(encoding="utf-8"))

    def candidates(self, domain: str) -> list[dict]:
        definition = self.domains.get(domain.lower(), {})
        if not definition.get("ready"):
            return []
        path = (self.root / definition.get("corpus", "missing.json")).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():
            return []
        return [item for item in json.loads(path.read_text(encoding="utf-8")) if item.get("domain") == domain.lower() and item.get("source_id") in definition.get("source_ids", []) and source_record(item, self.sources)[0]]

    def ready(self, domain: str) -> bool:
        return bool(self.candidates(domain))

    def search(self, domains: list[str], query: str, limit=10) -> list[dict]:
        terms = set(query.lower().split())
        entries = {item["provision_id"]: item for domain in domains for item in self.candidates(domain)}
        return sorted(entries.values(), key=lambda item: sum(term in (item.get("title", "") + item.get("quote", "")).lower() for term in terms), reverse=True)[:limit]
