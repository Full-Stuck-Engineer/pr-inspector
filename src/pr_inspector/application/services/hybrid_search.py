"""Application service orchestrating hybrid search (BM25 + Dense Vectors) and reranking."""

from pr_inspector.domain.entities import CodeChunk
from pr_inspector.domain.fusion import reciprocal_rank_fusion
from pr_inspector.domain.protocols import (
    EmbeddingProvider,
    KeywordIndex,
    Reranker,
    VectorStore,
)


class HybridSearchRetriever:
    """Orchestrates keyword search, dense vector search, RRF fusion, and precision reranking."""

    def __init__(
        self,
        keyword_index: KeywordIndex,
        vector_store: VectorStore,
        embedder: EmbeddingProvider,
        reranker: Reranker | None = None,
        candidate_multiplier: int = 2,
    ) -> None:
        self.keyword_index = keyword_index
        self.vector_store = vector_store
        self.embedder = embedder
        self.reranker = reranker
        self.candidate_multiplier = max(1, candidate_multiplier)

    def retrieve(self, query: str, top_k: int = 5) -> list[tuple[CodeChunk, float]]:
        """Retrieve most relevant chunks using hybrid retrieval and optional reranking."""
        if not query.strip() or top_k < 1:
            return []

        candidate_k = top_k * self.candidate_multiplier

        # 1. Lexical / Keyword Search
        keyword_results = self.keyword_index.search(query, top_k=candidate_k)

        # 2. Dense Vector Semantic Search
        query_embedding = self.embedder.embed_query(query)
        vector_results = self.vector_store.search(query_embedding, top_k=candidate_k)

        # 3. Reciprocal Rank Fusion
        fused = reciprocal_rank_fusion(
            [keyword_results, vector_results],
            top_k=candidate_k,
        )

        if not fused:
            return []

        # 4. Optional Precision Reranking
        if self.reranker is not None:
            candidates = [chunk for chunk, _ in fused]
            return self.reranker.rerank(query, candidates, top_k=top_k)

        return fused[:top_k]

    def retrieve_chunks(self, query: str, top_k: int = 5) -> list[CodeChunk]:
        """Convenience method returning solely the ordered CodeChunk objects."""
        return [chunk for chunk, _ in self.retrieve(query, top_k=top_k)]
