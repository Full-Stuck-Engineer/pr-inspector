"""In-memory dense vector store supporting exact cosine similarity search."""

import math

from pr_inspector.domain.entities import CodeChunk
from pr_inspector.domain.protocols import EmbeddingProvider, VectorStore


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two numeric vectors."""
    if len(v1) != len(v2):
        raise ValueError(f"Vector dimension mismatch: {len(v1)} vs {len(v2)}")

    dot_product = sum(a * b for a, b in zip(v1, v2, strict=True))
    norm_v1 = math.sqrt(sum(a * a for a in v1))
    norm_v2 = math.sqrt(sum(b * b for b in v2))

    if norm_v1 == 0.0 or norm_v2 == 0.0:
        return 0.0

    return round(dot_product / (norm_v1 * norm_v2), 4)


class InMemoryVectorStore(VectorStore):
    """In-memory vector store implementing cosine similarity search over CodeChunks."""

    def __init__(self, embedder: EmbeddingProvider | None = None) -> None:
        self.embedder = embedder
        self._chunks: dict[str, CodeChunk] = {}
        self._embeddings: dict[str, list[float]] = {}

    def upsert(
        self,
        chunks: list[CodeChunk],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """Insert or update chunks and their embeddings."""
        if not chunks:
            return

        if embeddings is None:
            if self.embedder is None:
                raise ValueError(
                    "No embedder configured in InMemoryVectorStore and no embeddings provided"
                )
            texts = [f"{c.file_path} {c.symbol_name or ''}\n{c.content}" for c in chunks]
            embeddings = self.embedder.embed_texts(texts)

        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Number of chunks ({len(chunks)}) does not match embeddings ({len(embeddings)})"
            )

        for chunk, embedding in zip(chunks, embeddings, strict=True):
            self._chunks[chunk.id] = chunk
            self._embeddings[chunk.id] = embedding

    def delete(self, chunk_ids: list[str]) -> None:
        """Remove chunks and their embeddings by chunk ID."""
        for cid in chunk_ids:
            self._chunks.pop(cid, None)
            self._embeddings.pop(cid, None)

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[tuple[CodeChunk, float]]:
        """Search chunks by cosine similarity to a query embedding vector."""
        if not self._embeddings or not query_embedding:
            return []

        scored: list[tuple[CodeChunk, float]] = []
        for cid, emb in self._embeddings.items():
            sim = cosine_similarity(query_embedding, emb)
            scored.append((self._chunks[cid], sim))

        scored.sort(key=lambda entry: entry[1], reverse=True)
        return scored[:top_k]
