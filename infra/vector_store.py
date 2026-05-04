"""ChromaDB-backed vector store for RAG retrieval.

Provides a thin wrapper around ChromaDB for storing and querying document
embeddings.  The store persists to a local directory (default: .vectordb/)
so it survives container restarts when mounted on a volume.

Usage:
    from infra.vector_store import VectorStore
    from infra.embeddings import get_embedder

    store = VectorStore(persist_dir=Path(".vectordb"))
    store.upsert_documents(
        collection="research_artifacts",
        ids=["art-001"],
        texts=["some content"],
        metadatas=[{"agent_id": "beta-agent-1", "action": "ANALYZE"}],
        embedder=get_embedder(),
    )
    results = store.query(
        collection="research_artifacts",
        query_text="protein folding mechanisms",
        embedder=get_embedder(),
        n_results=5,
    )
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infra.embeddings import Embedder


BATCH_SIZE = 128


@dataclass
class QueryResult:
    ids: list[str]
    documents: list[str]
    metadatas: list[dict[str, Any]]
    distances: list[float]


class VectorStore:
    def __init__(self, persist_dir: Path | str = ".vectordb"):
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError(
                "chromadb is required for the vector store. "
                "Install with: pip install '.[rag]'"
            ) from exc

        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))

    def _get_or_create_collection(self, name: str) -> Any:
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_documents(
        self,
        collection: str,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, Any]],
        embedder: Embedder,
    ) -> int:
        """Upsert documents with their embeddings. Returns count upserted."""
        if not ids:
            return 0

        coll = self._get_or_create_collection(collection)
        upserted = 0

        for start in range(0, len(ids), BATCH_SIZE):
            batch_ids = ids[start : start + BATCH_SIZE]
            batch_texts = texts[start : start + BATCH_SIZE]
            batch_metas = metadatas[start : start + BATCH_SIZE]
            batch_embeddings = embedder.embed(batch_texts)

            coll.upsert(
                ids=batch_ids,
                embeddings=batch_embeddings,
                documents=batch_texts,
                metadatas=batch_metas,
            )
            upserted += len(batch_ids)

        return upserted

    def query(
        self,
        collection: str,
        query_text: str,
        embedder: Embedder,
        *,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
        min_relevance: float = 0.0,
    ) -> QueryResult:
        """Query the collection by semantic similarity. Returns ranked results."""
        coll = self._get_or_create_collection(collection)

        if coll.count() == 0:
            return QueryResult(ids=[], documents=[], metadatas=[], distances=[])

        query_embedding = embedder.embed_query(query_text)

        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(n_results, coll.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = coll.query(**kwargs)

        ids = results["ids"][0] if results["ids"] else []
        documents = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []

        if min_relevance > 0.0:
            filtered = [
                (i, d, m, dist)
                for i, d, m, dist in zip(ids, documents, metadatas, distances)
                if (1.0 - dist) >= min_relevance
            ]
            if filtered:
                ids, documents, metadatas, distances = zip(*filtered)
                ids, documents, metadatas, distances = (
                    list(ids), list(documents), list(metadatas), list(distances),
                )
            else:
                ids, documents, metadatas, distances = [], [], [], []

        return QueryResult(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            distances=distances,
        )

    def delete_collection(self, collection: str) -> None:
        """Delete an entire collection."""
        try:
            self._client.delete_collection(collection)
        except Exception:
            pass

    def collection_count(self, collection: str) -> int:
        """Return the number of documents in a collection."""
        try:
            coll = self._client.get_collection(collection)
            return coll.count()
        except Exception:
            return 0
