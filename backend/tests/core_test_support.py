"""Deterministic model DOUBLE used only by Phase 3 tests; never application output."""
import copy
import json
from types import SimpleNamespace
from backend.services.input_layer import build_raw_package
from backend.services.core_workflow import CORE_VERSION

STORY = "I, Kavya, bought a refrigerator for Rs. 24,500 on 3 September 2026 from Sample Store. It stopped cooling. I have not filed a case."
LANGUAGE = {"detected_languages": ["en"], "supported": True}


class CoreTestModel:
    def __init__(self):
        self.calls = []
        self.overrides = {}
        self.domain = "CONSUMER"

    def generate(self, prompt, schema):
        name = schema["stage"].removeprefix("core_").upper()
        self.calls.append(name)
        context = json.loads(prompt.split("CASE DATA:\n", 1)[1])
        text = context["passages"][0]["text"]
        refs = [{"passage": 0, "excerpt": text}]
        facts = list(context.get("facts") or {})
        defaults = {
            "CASE_STAGE": {"stage": "NEW_CONSULTATION", "sources": refs, "review_required": False},
            "FACT_TIMELINE": {"facts": [{"key": "purchase", "proposition": text, "category": "PURCHASE", "sources": refs,
                "date": {"expression": "3 September 2026", "precision": "EXACT_DATE", "normalized": "2026-09-03"}, "exact_values": ["24,500"]}],
                "incidents": [{"key": "purchase", "description": "Purchase", "fact_keys": ["purchase"], "date": {"expression": "3 September 2026", "precision": "EXACT_DATE", "normalized": "2026-09-03"}}]},
            "PARTY_RELATIONSHIP": {"parties": [{"key": "purchaser", "name": "Kavya", "role": "PURCHASER", "fact_ids": facts, "sources": refs}, {"key": "seller", "name": "Sample Store", "role": "SELLER", "fact_ids": facts, "sources": refs}],
                "relationships": [{"left_key": "purchaser", "right_key": "seller", "relationship": "PURCHASE", "fact_ids": facts}]},
            "EVIDENCE_MAPPING": {"links": [], "unresolved": []},
            "CLARIFICATION": {"questions": []},
            "RECONCILIATION": {"conflicts": [], "unresolved": []},
            "DOMAIN_ROUTER": {"primary_domain": self.domain, "primary_subdomain": "DEFECTIVE_GOODS", "secondary_domains": [], "fact_ids": facts,
                "relationship_ids": list(context.get("relationships") or {}), "confidence": "HIGH", "review_required": self.domain == "OTHER_OR_UNCERTAIN", "ambiguity": [], "reasons": ["Supplied purchase and defect facts"]},
        }
        output = {"language": LANGUAGE, **defaults[name]}
        override = self.overrides.get(name)
        if callable(override):
            return override(copy.deepcopy(output), context)
        return copy.deepcopy({**output, **(override or {})})


def core_case(db, case_id="c", story=STORY, **changes):
    case = {"id": case_id, "case_id": case_id, "owner_user_id": "u", "status": "DRAFT", "stage": "NEW_CONSULTATION", "input_version": 1,
            "workflow_version": 2, "engine1_execution": CORE_VERSION, "client_story": story, "evidence": [], **changes}
    case["raw_package"] = build_raw_package(case, SimpleNamespace(mode="mock"), working_language_required=False)
    db.create("cases", case)
    return case
