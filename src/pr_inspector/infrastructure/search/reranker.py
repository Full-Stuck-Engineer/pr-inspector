"""Cross-encoder precision reranker scoring candidates against a code query."""

from collections.abc import Callable

from pr_inspector.domain.entities import ChunkType, CodeChunk
from pr_inspector.domain.protocols import Reranker
from pr_inspector.infrastructure.search.bm25 import tokenize_code


def default_cross_score(query: str, chunk: CodeChunk) -> float:
    """Compute precision cross-scoring between a query and a candidate CodeChunk."""
    query_tokens = set(tokenize_code(query))
    if not query_tokens:
        return 0.0

    chunk_tokens = set(tokenize_code(f"{chunk.symbol_name or ''} {chunk.content}"))
    overlap = query_tokens.intersection(chunk_tokens)
    if not overlap:
        return 0.0

    # Base overlap ratio: how much of the query is satisfied by this chunk
    coverage = len(overlap) / len(query_tokens)
    score = coverage * 10.0

    # Strong bonus for exact symbol match
    if chunk.symbol_name:
        symbol_lower = chunk.symbol_name.lower()
        if symbol_lower in query_tokens or any(t == symbol_lower for t in tokenize_code(query)):
            score += 5.0

    # Bonus for definitions over comments or generic text
    if chunk.chunk_type in (ChunkType.FUNCTION, ChunkType.CLASS):
        score += 2.0

    return round(score, 4)


class CrossEncoderReranker(Reranker):
    """Reranker adapter scoring top candidate chunks against the target code query."""

    def __init__(
        self,
        scorer: Callable[[str, CodeChunk], float] | None = None,
    ) -> None:
        self._scorer = scorer or default_cross_score

    def rerank(
        self, query: str, candidates: list[CodeChunk], top_k: int = 5
    ) -> list[tuple[CodeChunk, float]]:
        """Score candidates and return them sorted in descending order of relevance."""
        if not candidates or not query.strip():
            return []

        scored = [(c, self._scorer(query, c)) for c in candidates]
        scored.sort(key=lambda entry: entry[1], reverse=True)
        return scored[:top_k]
