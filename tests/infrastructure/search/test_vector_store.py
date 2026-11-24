"""Unit tests for InMemoryVectorStore and EmbeddingProviders."""

import pytest

from pr_inspector.domain.entities import ChunkType, CodeChunk
from pr_inspector.domain.protocols import EmbeddingProvider, VectorStore
from pr_inspector.infrastructure.search.embedder import DeterministicTestEmbedder
from pr_inspector.infrastructure.search.vector_store import (
    InMemoryVectorStore,
    cosine_similarity,
)


def make_chunk(cid: str, content: str = "pass") -> CodeChunk:
    return CodeChunk(
        id=cid,
        file_path="src/main.py",
        content=content,
        start_line=1,
        end_line=5,
        chunk_type=ChunkType.FUNCTION,
        symbol_name=cid,
    )


def test_cosine_similarity_math():
    # Identical vectors -> 1.0
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    # Orthogonal vectors -> 0.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    # Opposite vectors -> -1.0
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0
    # Zero vector -> 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    with pytest.raises(ValueError, match="mismatch"):
        cosine_similarity([1.0], [1.0, 2.0])


def test_deterministic_embedder():
    embedder = DeterministicTestEmbedder(dim=32)
    assert isinstance(embedder, EmbeddingProvider)

    v1 = embedder.embed_query("review diff use case")
    v2 = embedder.embed_query("review diff use case")
    v3 = embedder.embed_query("completely different words")

    assert len(v1) == 32
    assert v1 == v2  # deterministic
    assert v1 != v3
    assert cosine_similarity(v1, v2) == 1.0


def test_vector_store_protocol_conformance():
    store = InMemoryVectorStore()
    assert isinstance(store, VectorStore)


def test_vector_store_with_injected_embedder():
    embedder = DeterministicTestEmbedder(dim=16)
    store = InMemoryVectorStore(embedder=embedder)

    c1 = make_chunk("c1", "def review_diff(): pass")
    c2 = make_chunk("c2", "def parse_markdown(): pass")
    store.upsert([c1, c2])

    query_vec = embedder.embed_query("review diff")
    results = store.search(query_vec, top_k=2)

    assert len(results) == 2
    assert results[0][0].id == "c1"
    assert results[0][1] > results[1][1]


def test_vector_store_manual_embeddings_and_delete():
    store = InMemoryVectorStore()

    c1 = make_chunk("c1")
    c2 = make_chunk("c2")

    store.upsert([c1, c2], embeddings=[[1.0, 0.0], [0.0, 1.0]])

    results = store.search([1.0, 0.0], top_k=1)
    assert len(results) == 1
    assert results[0][0].id == "c1"
    assert results[0][1] == 1.0

    store.delete(["c1"])
    results_after_delete = store.search([1.0, 0.0], top_k=2)
    assert len(results_after_delete) == 1
    assert results_after_delete[0][0].id == "c2"


def test_vector_store_upsert_validation_errors():
    store = InMemoryVectorStore()
    with pytest.raises(ValueError, match="No embedder configured"):
        store.upsert([make_chunk("c1")])

    with pytest.raises(ValueError, match="does not match"):
        store.upsert([make_chunk("c1")], embeddings=[[1.0], [2.0]])
