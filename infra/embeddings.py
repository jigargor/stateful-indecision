"""Embedding API abstraction for RAG retrieval.

Supports multiple providers behind a single interface.  Provider is selected
by the EMBEDDING_PROVIDER env var (default: "voyage").

Usage:
    from infra.embeddings import get_embedder
    embedder = get_embedder()
    vectors = embedder.embed(["some text", "another text"])
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod


class Embedder(ABC):
    model: str
    dimensions: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for each text."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Return a single embedding vector optimized for query."""


class VoyageEmbedder(Embedder):
    def __init__(self, model: str = "voyage-3-large", dimensions: int = 1024):
        try:
            import voyageai
        except ImportError as exc:
            raise ImportError(
                "voyageai is required for Voyage embeddings. "
                "Install with: pip install '.[rag]'"
            ) from exc
        self.model = model
        self.dimensions = dimensions
        api_key = os.environ.get("VOYAGE_API_KEY", "")
        self._client = voyageai.Client(api_key=api_key) if api_key else voyageai.Client()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = self._client.embed(
            texts,
            model=self.model,
            input_type="document",
            output_dimension=self.dimensions,
        )
        return result.embeddings

    def embed_query(self, text: str) -> list[float]:
        result = self._client.embed(
            [text],
            model=self.model,
            input_type="query",
            output_dimension=self.dimensions,
        )
        return result.embeddings[0]


class OpenAIEmbedder(Embedder):
    def __init__(self, model: str = "text-embedding-3-small", dimensions: int = 1536):
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "openai is required for OpenAI embeddings. "
                "Install with: pip install openai"
            ) from exc
        self.model = model
        self.dimensions = dimensions
        self._client = openai.OpenAI()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            input=texts,
            model=self.model,
            dimensions=self.dimensions,
        )
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


_PROVIDERS: dict[str, type[Embedder]] = {
    "voyage": VoyageEmbedder,
    "openai": OpenAIEmbedder,
}


def get_embedder(
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
) -> Embedder:
    """Factory that returns the configured embedder.

    Provider is resolved from the argument, then EMBEDDING_PROVIDER env var,
    then defaults to "voyage".
    """
    provider = provider or os.environ.get("EMBEDDING_PROVIDER", "voyage")
    cls = _PROVIDERS.get(provider)
    if cls is None:
        raise ValueError(
            f"Unknown embedding provider '{provider}'. "
            f"Available: {list(_PROVIDERS.keys())}"
        )
    kwargs: dict = {}
    if model is not None:
        kwargs["model"] = model
    if dimensions is not None:
        kwargs["dimensions"] = dimensions
    return cls(**kwargs)
