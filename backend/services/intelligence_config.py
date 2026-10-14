"""Data-only capability configuration. Registration never establishes legal readiness."""
import json
from pathlib import Path

CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'registries/intelligence.json').read_text(encoding='utf-8'))


def jurisdiction_matches(source, target):
    if not source or not target:
        return False
    if source == target:
        return True
    return any(target.startswith(prefix) and source == parent
               for prefix, parent in CONFIG['jurisdiction_prefix_parents'].items())
