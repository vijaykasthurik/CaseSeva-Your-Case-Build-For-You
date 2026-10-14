"""ENGINEERING PREWORK — NOT PRODUCTION LEGAL RETRIEVAL. Synthetic offline metrics."""
from dataclasses import dataclass
from .retrieval import DomainPack, Issue, OfflineRetrieval, Passage


def metrics(ranked: list[str], relevant: set[str], k: int) -> dict[str, float]:
    if k < 1:
        raise ValueError("k must be positive")
    top = list(dict.fromkeys(ranked))[:k]
    hits = len(set(top) & relevant)
    return {"recall_at_k": hits / len(relevant) if relevant else 0.0,
            "precision_at_k": hits / k,
            "mrr_at_k": next((1 / n for n, p in enumerate(top, 1) if p in relevant), 0.0)}


@dataclass(frozen=True)
class BenchmarkCase:
    issue: Issue
    pack: DomainPack
    corpus: tuple[Passage, ...]
    relevant: frozenset[str]
    exact_citations: frozenset[tuple[str, str, str, str]]
    expected_abstention: bool
    forbidden_ids: frozenset[str] = frozenset()


def evaluate(engine: OfflineRetrieval, case: BenchmarkCase, k: int = 5) -> dict:
    result = engine.search(case.issue, case.pack, case.corpus, k)
    ids = [p.passage_id for p in result.passages]
    citations = {(p.source_id, p.revision, p.passage_id, p.citation) for p in result.passages}
    return {**metrics(ids, set(case.relevant), k),
            "exact_citation_recovery": len(citations & case.exact_citations) / len(case.exact_citations)
            if case.exact_citations else None,
            "abstention_correct": result.abstained == case.expected_abstention,
            "filters_correct": not bool(set(ids) & case.forbidden_ids)}
