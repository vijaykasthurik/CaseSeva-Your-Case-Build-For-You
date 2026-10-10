import json
from pathlib import Path
from typing import Any

from ..llm import LLMAdapter


class MockLLMAdapter(LLMAdapter):
    def __init__(self, fixture_root: str | Path = "fixtures/llm"):
        self.fixture_root = Path(fixture_root)

    def generate(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if schema.get("workflow_version") == 2:
            context = schema.get("development_context", {})
            raw = context.get("raw_case_package", {})
            case = context.get("case_file", {})
            stage = schema["stage"]
            if stage == "intake_cleaning":
                return {"narrative": raw.get("original_text", ""), "uncertainties": ["Development mode: no live AI analysis was performed."]}
            if stage == "evidence_indexing":
                return {"items": [{"evidence_id": item["evidence_id"], "description": item["extraction"]["original_text"][:200], "quality": item["extraction"]["status"]} for item in raw.get("evidence", [])]}
            if stage == "fact_extraction":
                return {"facts": [{"fact_id": "F001", "text": raw.get("original_story") or raw.get("original_text", ""), "confidence": 0, "evidence_ids": []}]}
            if stage == "timeline_construction":
                return {"timeline": []}
            if stage == "party_identification":
                return {"parties": {"client_role": "unknown", "opposite_party": "unknown", "relationship": "unknown"}}
            if stage == "missing_information":
                return {"questions": []}
            if stage == "reconciliation":
                return {"facts": case.get("facts", []), "timeline": case.get("timeline", []), "parties": case.get("parties", {}), "changes": ["Development only: answers recorded without live reconciliation."]}
            if stage == "engine1_domain_router":
                return {"domains": [], "reasoning": "Mock mode does not establish legal domain readiness.", "requires_review": True}
            if stage == "legal_issue_identification":
                return {"issues": []}
            if stage == "evidence_issue_mapping":
                return {"mappings": []}
            if stage == "engine2_claimant_counsel":
                return {"points": []}
            if stage == "engine2_opponent_counsel":
                return {"objections": []}
            if stage == "engine2_evidence_challenger":
                return {"attacks": [], "document_requests": []}
            if stage == "engine2_rebuttal":
                return {"rebuttals": []}
            if stage == "engine2_neutral_evaluation":
                return {"issue_readiness": [{"issue_id": item["issue_id"], "level": "Unresolved", "reasons": ["No live argument analysis was performed."], "improvements": ["Live processing and advocate review required."]} for item in case.get("legal_issues", [])], "unresolved_risks": ["Development mode: argument analysis is not a live assessment."], "advocate_review_points": [], "foundation_flags": []}
            raise ValueError(f"No explicit development implementation for stage {stage}; live output was not substituted.")
        if schema.get("fixture") == "uninformative":
            raise ValueError("Semantic sanity check failed: 'parties' returned all unknown roles.")
        if schema.get("fixture") == "malformed":
            return json.loads((self.fixture_root / "malformed.json").read_text(encoding="utf-8"))
        if schema.get("fixture") == "no_document":
            return json.loads((self.fixture_root / "evidence_challenger_resolved.json").read_text(encoding="utf-8"))
        if schema.get("fixture") == "document_request":
            return json.loads((self.fixture_root / "evidence_challenger_request.json").read_text(encoding="utf-8"))
        if schema.get("fixture") == "hallucinated_statute":
            return json.loads((self.fixture_root / "statute_retrieval_hallucinated.json").read_text(encoding="utf-8"))
        if schema.get("fixture") == "other_domain":
            return json.loads((self.fixture_root / "domain_router_other.json").read_text(encoding="utf-8"))
        if schema.get("fixture") == "labor_domain":
            return json.loads((self.fixture_root / "domain_router_labor.json").read_text(encoding="utf-8"))
        if schema.get("fixture") == "statute_retrieval_labor":
            return json.loads((self.fixture_root / "statute_retrieval_labor.json").read_text(encoding="utf-8"))

        stage = str(schema.get("stage", "default")).lower().replace(" ", "_")
        fixture = self.fixture_root / f"{stage}.json"
        if not fixture.exists():
            fixture = self.fixture_root / "placeholder.json"
        return json.loads(fixture.read_text(encoding="utf-8"))
