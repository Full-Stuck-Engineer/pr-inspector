"""Unit tests for Reciprocal Rank Fusion (RRF)."""

import pytest

from pr_inspector.domain.entities import ChunkType, CodeChunk
from pr_inspector.domain.fusion import DEFAULT_RRF_K, reciprocal_rank_fusion


def make_chunk(cid: str, path: str = "src/main.py", content: str = "pass") -> CodeChunk:
    return CodeChunk(
        id=cid,
        file_path=path,
        content=content,
        start_line=1,
        end_line=5,
        chunk_type=ChunkType.FUNCTION,
        symbol_name=cid,
    )


def test_rrf_empty_rankings():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_rrf_single_ranking():
    c1 = make_chunk("c1")
    c2 = make_chunk("c2")

    fused = reciprocal_rank_fusion([[c1, c2]], k=60)
    assert len(fused) == 2
    assert fused[0][0].id == "c1"
    assert fused[0][1] == pytest.approx(1.0 / 61, abs=1e-5)
    assert fused[1][0].id == "c2"
    assert fused[1][1] == pytest.approx(1.0 / 62, abs=1e-5)


def test_rrf_multiple_rankings_fusion_and_deduplication():
    c1 = make_chunk("c1")
    c2 = make_chunk("c2")
    c3 = make_chunk("c3")

    # Ranking 1 (lexical): c1 (rank 1), c2 (rank 2)
    # Ranking 2 (vector):  c2 (rank 1), c3 (rank 2)
    r1 = [c1, c2]
    r2 = [c2, c3]

    fused = reciprocal_rank_fusion([r1, r2], k=60)

    # c2 score: 1/(60+2) + 1/(60+1) = 1/62 + 1/61 =~ 0.016129 + 0.016393 = 0.032522
    # c1 score: 1/(60+1) =~ 0.016393
    # c3 score: 1/(60+2) =~ 0.016129
    # Expected order: c2, c1, c3
    assert [f[0].id for f in fused] == ["c2", "c1", "c3"]
    assert fused[0][1] > fused[1][1] > fused[2][1]


def test_rrf_accepts_tuples_with_scores():
    c1 = make_chunk("c1")
    c2 = make_chunk("c2")

    r1 = [(c1, 10.5), (c2, 8.2)]
    r2 = [(c2, 0.95), (c1, 0.80)]

    fused = reciprocal_rank_fusion([r1, r2], k=DEFAULT_RRF_K)
    # Both appeared at rank 1 and rank 2 across the two rankings, so tied
    assert len(fused) == 2
    assert fused[0][1] == fused[1][1]


def test_rrf_top_k_limiting():
    chunks = [make_chunk(f"c{i}") for i in range(10)]
    fused = reciprocal_rank_fusion([chunks], top_k=3)
    assert len(fused) == 3
    assert [f[0].id for f in fused] == ["c0", "c1", "c2"]


def test_rrf_invalid_k_rejected():
    with pytest.raises(ValueError, match="at least 1"):
        reciprocal_rank_fusion([[make_chunk("c1")]], k=0)
