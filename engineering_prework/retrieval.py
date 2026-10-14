"""ENGINEERING PREWORK — NOT PRODUCTION LEGAL RETRIEVAL.

Pure offline contracts; no application routes, persistence, network or model loads.
Metadata is trusted only inside synthetic experiments. Production integration must
resolve eligibility from authenticated immutable review records, never caller flags.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from math import log
import re
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Issue:
    issue_id: str
    statement: str
    domain: str
    language: str
    jurisdiction: str
    on_date: date
    fact_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    candidate_queries: tuple[str, ...] = ()


@dataclass(frozen=True)
class Query:
    issue_id: str
    text: str
    language: str


@dataclass(frozen=True)
class DomainPack:
    domain: str
    query_templates: tuple[str, ...] = ("{statement}",)


def plan(issue: Issue, pack: DomainPack) -> tuple[Query, ...]:
    if not re.fullmatch(r"L\d{3,}", issue.issue_id) or pack.domain != issue.domain:
        raise ValueError("Issue identity/domain mismatch")
    texts = [issue.statement, *issue.candidate_queries]
    texts.extend(t.format(statement=issue.statement) for t in pack.query_templates)
    return tuple(Query(issue.issue_id, t, issue.language)
                 for t in dict.fromkeys(s.strip() for s in texts) if t)


@dataclass(frozen=True)
class Passage:
    passage_id: str
    source_id: str
    revision: str
    domain: str
    jurisdiction: str
    language: str
    official: bool
    document: str
    document_hash: str
    start: int
    end: int
    quote: str
    citation: str
    review_state: str = "REVIEW_PENDING"
    receipt_id: str | None = None
    verification: str = "PENDING"
    temporal_reviewed: bool = False
    effective_from: date | None = None
    effective_until: date | None = None
    coverage_through: date | None = None
    version_verified: bool = False
    citation_covered: bool = False
    hierarchy_verified: bool = False


def exact_passage(p: Passage) -> bool:
    return bool(p.quote and 0 <= p.start < p.end <= len(p.document)
                and p.document[p.start:p.end] == p.quote
                and sha256(p.document.encode("utf-8")).hexdigest() == p.document_hash)


class AuthorityGate(Protocol):
    def reasons(self, passage: Passage, issue: Issue) -> tuple[str, ...]: ...


class ConservativeGate:
    """Synthetic policy, not an alternative to Phase 4 authority approval."""
    def reasons(self, p: Passage, issue: Issue) -> tuple[str, ...]:
        failures = []
        if p.review_state != "REVIEWED_PRIMARY" or not p.receipt_id or p.verification != "VERIFIED":
            failures.append("review_ineligible")
        if not p.official:
            failures.append("official_source_required")
        if p.domain != issue.domain:
            failures.append("domain")
        if p.jurisdiction != issue.jurisdiction:
            failures.append("jurisdiction")
        if (not p.temporal_reviewed or p.effective_from is None
                or p.coverage_through is None
                or issue.on_date < p.effective_from
                or issue.on_date > p.coverage_through
                or (p.effective_until is not None and issue.on_date >= p.effective_until)):
            failures.append("temporal")
        if not p.version_verified:
            failures.append("amendment_version")
        if not p.hierarchy_verified:
            failures.append("precedent_hierarchy")
        if not p.citation_covered or not p.citation or not p.revision:
            failures.append("citation_coverage")
        if not exact_passage(p):
            failures.append("exact_passage")
        return tuple(failures)


class DenseRetriever(Protocol):
    """Provider owns multilingual encoding; returns candidate IDs, never new law."""
    def rank(self, query: Query, candidates: Sequence[Passage]) -> Sequence[str]: ...


class LegalReranker(Protocol):
    """Legal-BERT or other model may order IDs, not change passages/eligibility."""
    def rank(self, queries: Sequence[Query], candidates: Sequence[Passage]) -> Sequence[str]: ...


class Tokenizer(Protocol):
    def __call__(self, text: str) -> Sequence[str]: ...


def unicode_tokens(text: str) -> list[str]:
    # Baseline only. Language-specific segmentation belongs in a provider.
    return re.findall(r"\w+", text.casefold(), re.UNICODE)


def bm25(query: str, candidates: Sequence[Passage], tokenize: Tokenizer = unicode_tokens) -> list[str]:
    if not candidates:
        return []
    documents = [Counter(tokenize(p.quote)) for p in candidates]
    lengths = [sum(d.values()) for d in documents]
    average = sum(lengths) / len(lengths) or 1
    terms = set(tokenize(query))
    scores = []
    for p, counts, length in zip(candidates, documents, lengths):
        score = 0.0
        for term in terms:
            frequency = counts[term]
            df = sum(term in d for d in documents)
            idf = log(1 + (len(documents) - df + .5) / (df + .5))
            score += idf * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * length / average))
        if score > 0:
            scores.append((p.passage_id, score))
    return [pid for pid, _ in sorted(scores, key=lambda v: (-v[1], v[0]))]


@dataclass(frozen=True)
class Result:
    issue_id: str
    passages: tuple[Passage, ...]
    excluded: tuple[tuple[str, tuple[str, ...]], ...]
    abstained: bool


class OfflineRetrieval:
    def __init__(self, *, enabled: bool = False, dense: DenseRetriever | None = None,
                 reranker: LegalReranker | None = None, tokenizer: Tokenizer = unicode_tokens):
        self.enabled, self.dense, self.reranker, self.tokenizer = enabled, dense, reranker, tokenizer

    def search(self, issue: Issue, pack: DomainPack, corpus: Sequence[Passage], k: int = 5) -> Result:
        if not self.enabled:
            raise RuntimeError("Offline engineering prework is disabled")
        if k < 1:
            raise ValueError("k must be positive")
        if len({p.passage_id for p in corpus}) != len(corpus):
            raise ValueError("Duplicate passage identity")
        queries = plan(issue, pack)
        gate = ConservativeGate()
        excluded = tuple((p.passage_id, reasons) for p in corpus if (reasons := gate.reasons(p, issue)))
        rejected = {pid for pid, _ in excluded}
        eligible = {p.passage_id: p for p in corpus if p.passage_id not in rejected}
        scores: Counter = Counter()
        for query in queries:
            rankings = [bm25(query.text, list(eligible.values()), self.tokenizer)]
            if self.dense and eligible:
                rankings.append(self.dense.rank(query, tuple(eligible.values())))
            for ranking in rankings:
                # Deduplicate and discard invented or ineligible provider IDs.
                safe = dict.fromkeys(pid for pid in ranking if pid in eligible)
                for rank, pid in enumerate(safe, 1):
                    scores[pid] += 1 / (60 + rank)
        ids = sorted(scores, key=lambda pid: (-scores[pid], pid))
        if self.reranker and ids:
            proposed = self.reranker.rank(queries, tuple(eligible[pid] for pid in ids))
            ordered = list(dict.fromkeys(pid for pid in proposed if pid in scores))
            ids = ordered + [pid for pid in ids if pid not in ordered]
        passages = tuple(eligible[pid] for pid in ids[:k])
        return Result(issue.issue_id, passages, excluded, not passages)


@dataclass(frozen=True)
class CitationTrace:
    statement_id: str
    fact_id: str
    evidence_id: str
    issue_id: str
    source_id: str
    revision: str
    passage_id: str
    citation: str
    finding_id: str


def verify_trace(trace: CitationTrace, issue: Issue, result: Result,
                 statement_fact_links: set[tuple[str, str]],
                 fact_evidence_links: set[tuple[str, str]]) -> bool:
    """Structural provenance only; cannot establish legal entailment/truth."""
    return bool(trace.finding_id and trace.issue_id == issue.issue_id == result.issue_id
                and trace.fact_id in issue.fact_ids and trace.evidence_id in issue.evidence_ids
                and (trace.statement_id, trace.fact_id) in statement_fact_links
                and (trace.fact_id, trace.evidence_id) in fact_evidence_links
                and any((p.source_id, p.revision, p.passage_id, p.citation) ==
                        (trace.source_id, trace.revision, trace.passage_id, trace.citation)
                        and not ConservativeGate().reasons(p, issue) for p in result.passages))
