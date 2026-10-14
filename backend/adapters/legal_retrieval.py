"""Generic legacy corpus lookup; configured aliases do not imply reviewed eligibility."""
import json
import re
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Any

REGISTRY = Path(__file__).resolve().parents[1] / 'registries'
CORPUS_ALIAS_MAP = json.loads((REGISTRY / 'corpus_aliases.json').read_text())


def normalize_domain_to_corpus(domain_str: str) -> str | None:
    if not domain_str:
        return None
    cleaned = ' '.join(re.sub(r'[^\w\s]', ' ', domain_str.lower()).split())
    if cleaned in CORPUS_ALIAS_MAP:
        return CORPUS_ALIAS_MAP[cleaned]
    # Only registered corpus keys; never arbitrary caller-derived filesystem paths.
    domains = json.loads((REGISTRY / 'domains.json').read_text())
    return cleaned if cleaned in domains else None


class LegalRetrievalAdapter(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 10, domain: str = '') -> list[dict[str, Any]]:
        raise NotImplementedError
