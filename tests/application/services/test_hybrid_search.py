"""Unit tests for HybridSearchRetriever application service."""

from unittest.mock import MagicMock

from pr_inspector.application.services.hybrid_search import HybridSearchRetriever
from pr_inspector.domain.entities import ChunkType, CodeChunk
from pr_inspector.domain.protocols import (
    EmbeddingProvider,
    KeywordIndex,
    Reranker,
    VectorStore,
)
from pr_inspector.infrastructure.search.bm25 import BM25KeywordIndex
from pr_inspector.infrastructure.search.embedder import DeterministicTestEmbedder
from pr_inspector.infrastructure.search.reranker import CrossEncoderReranker
from pr_inspector.infrastructure.search.vector_store import InMemoryVectorStore


def make_chunk(cid: str, content: str, symbol_name: str | None = None) -> CodeChunk:
    return CodeChunk(
        id=cid,
        file_path="src/main.py",
        content=content,
        start_line=1,
        end_line=10,
        chunk_type=ChunkType.FUNCTION,
        symbol_name=symbol_name,
    )


def test_hybrid_search_end_to_end_with_real_adapters():
    embedder = DeterministicTestEmbedder(dim=32)
    keyword_index = BM25KeywordIndex()
    vector_store = InMemoryVectorStore(embedder=embedder)
    reranker = CrossEncoderReranker()

    c1 = make_chunk("c1", "def review_diff(): pass", symbol_name="review_diff")
    c2 = make_chunk("c2", "def parse_markdown(): pass", symbol_name="parse_markdown")
    c3 = make_chunk("c3", "def unrelated(): pass", symbol_name="unrelated")

    # Index chunks in both stores
    keyword_index.upsert([c1, c2, c3])
    vector_store.upsert([c1, c2, c3])

    retriever = HybridSearchRetriever(
        keyword_index=keyword_index,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
    )

    results = retriever.retrieve("review diff", top_k=2)

    assert len(results) == 2
    assert results[0][0].id == "c1"

    chunks = retriever.retrieve_chunks("review diff", top_k=1)
    assert len(chunks) == 1
    assert chunks[0].id == "c1"


def test_hybrid_search_empty_query():
    retriever = HybridSearchRetriever(
        keyword_index=MagicMock(spec=KeywordIndex),
        vector_store=MagicMock(spec=VectorStore),
        embedder=MagicMock(spec=EmbeddingProvider),
    )
    assert retriever.retrieve("") == []
    assert retriever.retrieve("   ") == []
    assert retriever.retrieve("query", top_k=0) == []


def test_hybrid_search_without_reranker():
    c1 = make_chunk("c1", "content 1")
    c2 = make_chunk("c2", "content 2")

    mock_keyword = MagicMock(spec=KeywordIndex)
    mock_keyword.search.return_value = [(c1, 1.0)]

    mock_vector = MagicMock(spec=VectorStore)
    mock_vector.search.return_value = [(c2, 0.9)]

    mock_embedder = MagicMock(spec=EmbeddingProvider)
    mock_embedder.embed_query.return_value = [0.1, 0.2]

    retriever = HybridSearchRetriever(
        keyword_index=mock_keyword,
        vector_store=mock_vector,
        embedder=mock_embedder,
        reranker=None,
    )

    results = retriever.retrieve("query", top_k=2)
    assert len(results) == 2
    # Both chunks returned in fused score order
    ids = {r[0].id for r in results}
    assert ids == {"c1", "c2"}


def test_hybrid_search_with_reranker_called():
    c1 = make_chunk("c1", "content 1")

    mock_keyword = MagicMock(spec=KeywordIndex)
    mock_keyword.search.return_value = [(c1, 1.0)]

    mock_vector = MagicMock(spec=VectorStore)
    mock_vector.search.return_value = []

    mock_embedder = MagicMock(spec=EmbeddingProvider)
    mock_embedder.embed_query.return_value = [0.1]

    mock_reranker = MagicMock(spec=Reranker)
    mock_reranker.rerank.return_value = [(c1, 99.0)]

    retriever = HybridSearchRetriever(
        keyword_index=mock_keyword,
        vector_store=mock_vector,
        embedder=mock_embedder,
        reranker=mock_reranker,
    )

    results = retriever.retrieve("query", top_k=1)
    assert len(results) == 1
    assert results[0][0].id == "c1"
    assert results[0][1] == 99.0
    mock_reranker.rerank.assert_called_once_with("query", [c1], top_k=1)
