"""Embedding adapters for generating dense vector embeddings."""

import hashlib
import math
import os

from openai import OpenAI

from pr_inspector.domain.protocols import EmbeddingProvider
from pr_inspector.infrastructure.search.bm25 import tokenize_code


class DeterministicTestEmbedder(EmbeddingProvider):
    """Zero-dependency deterministic embedder for unit testing and offline evaluation.

    Generates normalized dense vectors by hashing token n-grams into fixed dimensions.
    """

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def _embed_single(self, text: str) -> list[float]:
        if not text.strip():
            return [0.0] * self.dim

        vec = [0.0] * self.dim
        tokens = tokenize_code(text)
        for token in tokens:
            # Hash word into bucket
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            vec[idx] += 1.0

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [round(v / norm, 6) for v in vec]
        return vec

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_single(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._embed_single(query)


class OpenAICompatibleEmbedder(EmbeddingProvider):
    """Generates embeddings using an OpenAI or Ollama compatible /v1/embeddings endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        timeout: float = 30.0,
    ) -> None:
        resolved_key = (
            api_key or os.getenv("PR_INSPECTOR_API_KEY") or os.getenv("OPENAI_API_KEY") or "ollama"
        )
        resolved_base_url = (
            base_url or os.getenv("PR_INSPECTOR_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        )

        if not resolved_base_url and resolved_key == "ollama":
            resolved_base_url = "http://localhost:11434/v1"

        self.model = model
        self.client = OpenAI(
            base_url=resolved_base_url,
            api_key=resolved_key,
            timeout=timeout,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(input=texts, model=self.model)
        return [data.embedding for data in response.data]

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]
