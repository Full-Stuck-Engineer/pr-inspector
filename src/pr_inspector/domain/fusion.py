"""Domain logic for combining ranked search results via Reciprocal Rank Fusion."""

from collections.abc import Sequence

from pr_inspector.domain.entities import CodeChunk

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[CodeChunk | tuple[CodeChunk, float]]],
    k: int = DEFAULT_RRF_K,
    top_k: int | None = None,
) -> list[tuple[CodeChunk, float]]:
    """Combine multiple ranked search results into a single fused ranking.

    Reciprocal Rank Fusion (RRF) scores each document d across m rankings as:
        RRF(d) = sum_{m} 1 / (k + rank_m(d))

    Args:
        rankings: A list of rankings, where each ranking is an ordered sequence of
            CodeChunks or (CodeChunk, score) tuples (best rank first).
        k: Smoothing constant to control the weight of high ranks (default 60).
        top_k: Optional limit on the number of returned chunks.

    Returns:
        List of (CodeChunk, fused_score) tuples sorted in descending order of fused score.
    """
    if k < 1:
        raise ValueError("k must be at least 1")

    scores: dict[str, float] = {}
    chunk_map: dict[str, CodeChunk] = {}

    for ranking in rankings:
        for rank_0, item in enumerate(ranking):
            chunk = item[0] if isinstance(item, tuple) else item
            rank_1 = rank_0 + 1  # 1-based rank
            chunk_id = chunk.id

            scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank_1))
            if chunk_id not in chunk_map:
                chunk_map[chunk_id] = chunk

    sorted_results = [
        (chunk_map[cid], round(score, 6))
        for cid, score in sorted(scores.items(), key=lambda entry: entry[1], reverse=True)
    ]

    if top_k is not None:
        return sorted_results[:top_k]
    return sorted_results
