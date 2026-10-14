"""Generic VectorStore abstraction and provider-swappable interface for CaseSeva.

ENGINEERING PREWORK ONLY — NOT PRODUCTION VECTOR RAG.
Keeps hybrid retrieval engineering prework swappable across MongoDB Vector Search,
ChromaDB, Qdrant, or in-memory vector indexers. Production vector RAG is not claimed.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import math
from typing import Any, Sequence


@dataclass
class VectorDocument:
    doc_id: str
    text: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


def cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


class VectorStore(ABC):
    @abstractmethod
    def add_documents(self, documents: Sequence[VectorDocument]) -> None:
        raise NotImplementedError

    @abstractmethod
    def similarity_search(
        self,
        query_embedding: Sequence[float],
        limit: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[VectorDocument]:
        raise NotImplementedError

    @abstractmethod
    def delete_documents(self, doc_ids: Sequence[str]) -> None:
        raise NotImplementedError


class InMemoryVectorStore(VectorStore):
    """Local baseline vector store for unit tests and local experimentation."""

    def __init__(self):
        self._docs: dict[str, VectorDocument] = {}

    def add_documents(self, documents: Sequence[VectorDocument]) -> None:
        for doc in documents:
            self._docs[doc.doc_id] = doc

    def similarity_search(
        self,
        query_embedding: Sequence[float],
        limit: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[VectorDocument]:
        candidates = list(self._docs.values())
        if filter_metadata:
            candidates = [
                d for d in candidates
                if all(d.metadata.get(k) == v for k, v in filter_metadata.items())
            ]
        scored = []
        for doc in candidates:
            score = cosine_similarity(query_embedding, doc.embedding)
            res = VectorDocument(
                doc_id=doc.doc_id,
                text=doc.text,
                embedding=doc.embedding,
                metadata=doc.metadata,
                score=score,
            )
            scored.append(res)
        scored.sort(key=lambda d: d.score, reverse=True)
        return scored[:limit]

    def delete_documents(self, doc_ids: Sequence[str]) -> None:
        for did in doc_ids:
            self._docs.pop(did, None)


class MongoVectorStore(VectorStore):
    """MongoDB Vector Search provider adapter stub.

    Compatible with MongoDB vector search collections. Provider is swappable
    with ChromaDB, Qdrant, or FAISS.
    """

    def __init__(self, collection_name: str = "legal_vectors", db_name: str = "caseseva"):
        from ..database.mongo_client import get_mongo_db
        self.db = get_mongo_db(db_name)
        self.collection = self.db[collection_name]

    def add_documents(self, documents: Sequence[VectorDocument]) -> None:
        operations = []
        for doc in documents:
            d = {
                "_id": doc.doc_id,
                "doc_id": doc.doc_id,
                "text": doc.text,
                "embedding": doc.embedding,
                "metadata": doc.metadata,
            }
            self.collection.replace_one({"_id": doc.doc_id}, d, upsert=True)

    def similarity_search(
        self,
        query_embedding: Sequence[float],
        limit: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[VectorDocument]:
        # Fallback in-memory scoring if MongoDB Vector Index is not configured locally
        cursor = self.collection.find({})
        candidates = []
        for d in cursor:
            meta = d.get("metadata", {})
            if filter_metadata and not all(meta.get(k) == v for k, v in filter_metadata.items()):
                continue
            emb = d.get("embedding", [])
            score = cosine_similarity(query_embedding, emb)
            candidates.append(VectorDocument(
                doc_id=d["doc_id"],
                text=d.get("text", ""),
                embedding=emb,
                metadata=meta,
                score=score,
            ))
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates[:limit]

    def delete_documents(self, doc_ids: Sequence[str]) -> None:
        self.collection.delete_many({"_id": {"$in": list(doc_ids)}})
