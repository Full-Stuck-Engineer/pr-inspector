"""Unit tests for CrossEncoderReranker."""

from pr_inspector.domain.entities import ChunkType, CodeChunk
from pr_inspector.domain.protocols import Reranker
from pr_inspector.infrastructure.search.reranker import CrossEncoderReranker


def make_chunk(
    cid: str,
    content: str,
    symbol_name: str | None = None,
    chunk_type: ChunkType = ChunkType.FUNCTION,
) -> CodeChunk:
    return CodeChunk(
        id=cid,
        file_path="src/main.py",
        content=content,
        start_line=1,
        end_line=10,
        chunk_type=chunk_type,
        symbol_name=symbol_name,
    )


def test_reranker_protocol_conformance():
    reranker = CrossEncoderReranker()
    assert isinstance(reranker, Reranker)


def test_reranker_empty_inputs():
    reranker = CrossEncoderReranker()
    assert reranker.rerank("", [make_chunk("c1", "content")]) == []
    assert reranker.rerank("query", []) == []


def test_reranker_scores_and_orders_candidates():
    c_irrelevant = make_chunk("c_irr", "def unrelated(): pass")
    c_partial = make_chunk("c_part", "def calculate_diff(): pass")
    c_exact = make_chunk(
        "c_exact",
        "class ReviewDiffUseCase:\n    def execute(self): pass",
        symbol_name="ReviewDiffUseCase",
        chunk_type=ChunkType.CLASS,
    )

    reranker = CrossEncoderReranker()
    results = reranker.rerank("ReviewDiffUseCase", [c_irrelevant, c_partial, c_exact], top_k=3)

    assert len(results) == 3
    assert results[0][0].id == "c_exact"
    assert results[1][0].id == "c_part"
    assert results[2][0].id == "c_irr"
    assert results[0][1] > results[1][1] > results[2][1]


def test_reranker_custom_scorer_injection():
    # Inject an inverted mock scorer: shorter id gets higher score
    custom_reranker = CrossEncoderReranker(scorer=lambda q, c: float(len(c.content)))
    c1 = make_chunk("c1", "a")
    c2 = make_chunk("c2", "aaa")

    results = custom_reranker.rerank("query", [c1, c2])
    assert results[0][0].id == "c2"
    assert results[0][1] == 3.0
