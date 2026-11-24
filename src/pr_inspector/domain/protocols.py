"""Domain ports (Protocols) defining external boundaries."""

from typing import Protocol, runtime_checkable

from pr_inspector.domain.entities import (
    CodeChunk,
    FileDiff,
    IndexManifest,
    PRReviewResult,
    TelemetryRecord,
)


@runtime_checkable
class DiffProvider(Protocol):
    """Port for extracting and parsing git diffs."""

    def get_diff(self, target_ref: str | None = None, staged: bool = False) -> list[FileDiff]:
        """Extract and parse git diff, returning structured file diffs."""
        ...


@runtime_checkable
class LLMReviewer(Protocol):
    """Port for performing automated PR review using an LLM."""

    def review(self, diffs: list[FileDiff]) -> tuple[PRReviewResult, TelemetryRecord]:
        """Analyze diffs and produce structured review and telemetry."""
        ...


@runtime_checkable
class TelemetrySink(Protocol):
    """Port for persisting or publishing telemetry records."""

    def record(self, telemetry: TelemetryRecord) -> None:
        """Record telemetry data."""
        ...


@runtime_checkable
class CodeChunker(Protocol):
    """Port for parsing and chunking file contents into structure-aware chunks."""

    def chunk_file(self, file_path: str, content: str) -> list[CodeChunk]:
        """Split a file's content into structured, annotated code chunks."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Port for dense vector indexing and semantic similarity search."""

    def upsert(self, chunks: list[CodeChunk]) -> None:
        """Insert or update chunks in the vector index."""
        ...

    def delete(self, chunk_ids: list[str]) -> None:
        """Remove chunks from the vector index by ID."""
        ...

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[tuple[CodeChunk, float]]:
        """Search chunks by cosine similarity to a query embedding vector."""
        ...


@runtime_checkable
class KeywordIndex(Protocol):
    """Port for lexical / keyword-based search (e.g. BM25 / SQLite FTS)."""

    def upsert(self, chunks: list[CodeChunk]) -> None:
        """Insert or update chunks in the keyword index."""
        ...

    def delete(self, chunk_ids: list[str]) -> None:
        """Remove chunks from the keyword index by ID."""
        ...

    def search(self, query: str, top_k: int = 5) -> list[tuple[CodeChunk, float]]:
        """Search chunks by keyword relevance score."""
        ...


@runtime_checkable
class Reranker(Protocol):
    """Port for precision reranking of candidate chunks against a query."""

    def rerank(
        self, query: str, candidates: list[CodeChunk], top_k: int = 5
    ) -> list[tuple[CodeChunk, float]]:
        """Score and rerank candidate chunks in descending order of relevance."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Port for generating dense vector embeddings from text."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings for a batch of input texts."""
        ...

    def embed_query(self, query: str) -> list[float]:
        """Compute embedding for a single search query."""
        ...


@runtime_checkable
class ManifestStore(Protocol):
    """Port for persisting and loading the indexing manifest."""

    def load_manifest(self) -> IndexManifest | None:
        """Load stored manifest if it exists, or return None."""
        ...

    def save_manifest(self, manifest: IndexManifest) -> None:
        """Save updated manifest to persistent storage."""
        ...
