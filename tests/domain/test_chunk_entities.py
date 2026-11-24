"""Unit tests for RAG domain entities and protocols (Issue #17)."""

from pr_inspector.domain.entities import (
    ChunkType,
    CodeChunk,
    FileChangeSet,
    IndexManifest,
    SymbolDefinition,
    SymbolKind,
)
from pr_inspector.domain.protocols import (
    CodeChunker,
    KeywordIndex,
    ManifestStore,
    Reranker,
    VectorStore,
)


def test_code_chunk_attributes_and_serialization():
    chunk = CodeChunk(
        id="src/math.py:1-10:add",
        file_path="src/math.py",
        content="def add(a: int, b: int) -> int:\n    return a + b",
        start_line=1,
        end_line=10,
        chunk_type=ChunkType.FUNCTION,
        symbol_name="add",
        language="python",
    )
    assert chunk.id == "src/math.py:1-10:add"
    assert chunk.start_line == 1
    assert chunk.end_line == 10
    assert chunk.chunk_type == ChunkType.FUNCTION

    data = chunk.model_dump()
    assert data["symbol_name"] == "add"
    assert data["language"] == "python"

    restored = CodeChunk.model_validate(data)
    assert restored == chunk


def test_symbol_definition_attributes():
    symbol = SymbolDefinition(
        name="ReviewDiffUseCase",
        kind=SymbolKind.CLASS,
        file_path="src/application/use_cases/review_diff.py",
        line_number=25,
        signature="class ReviewDiffUseCase:",
        docstring="Orchestrates diff extraction and review.",
    )
    assert symbol.name == "ReviewDiffUseCase"
    assert symbol.kind == SymbolKind.CLASS
    assert symbol.line_number == 25
    assert symbol.docstring is not None


def test_file_change_set_has_changes():
    empty_changeset = FileChangeSet()
    assert not empty_changeset.has_changes

    added_changeset = FileChangeSet(added=["a.py"])
    assert added_changeset.has_changes

    modified_changeset = FileChangeSet(modified=["b.py"])
    assert modified_changeset.has_changes

    deleted_changeset = FileChangeSet(deleted=["c.py"])
    assert deleted_changeset.has_changes

    unchanged_only = FileChangeSet(unchanged=["d.py"])
    assert not unchanged_only.has_changes


def test_index_manifest_serialization_roundtrip():
    manifest = IndexManifest(
        version=1,
        file_hashes={"src/app.py": "abc123sha", "README.md": "def456sha"},
    )
    json_str = manifest.model_dump_json()
    restored = IndexManifest.model_validate_json(json_str)

    assert restored.version == 1
    assert restored.file_hashes["src/app.py"] == "abc123sha"
    assert restored.file_hashes["README.md"] == "def456sha"
    assert restored.updated_at is not None


def test_protocols_runtime_checkable():
    class DummyChunker:
        def chunk_file(self, file_path: str, content: str) -> list[CodeChunk]:
            return []

    class DummyVectorStore:
        def upsert(self, chunks: list[CodeChunk]) -> None:
            pass

        def delete(self, chunk_ids: list[str]) -> None:
            pass

        def search(
            self, query_embedding: list[float], top_k: int = 5
        ) -> list[tuple[CodeChunk, float]]:
            return []

    class DummyKeywordIndex:
        def upsert(self, chunks: list[CodeChunk]) -> None:
            pass

        def delete(self, chunk_ids: list[str]) -> None:
            pass

        def search(self, query: str, top_k: int = 5) -> list[tuple[CodeChunk, float]]:
            return []

    class DummyReranker:
        def rerank(
            self, query: str, candidates: list[CodeChunk], top_k: int = 5
        ) -> list[tuple[CodeChunk, float]]:
            return []

    class DummyManifestStore:
        def load_manifest(self) -> IndexManifest | None:
            return None

        def save_manifest(self, manifest: IndexManifest) -> None:
            pass

    assert isinstance(DummyChunker(), CodeChunker)
    assert isinstance(DummyVectorStore(), VectorStore)
    assert isinstance(DummyKeywordIndex(), KeywordIndex)
    assert isinstance(DummyReranker(), Reranker)
    assert isinstance(DummyManifestStore(), ManifestStore)
