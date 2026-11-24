"""Unit tests for JsonFileChunkStore."""

from pr_inspector.domain.entities import ChunkType, CodeChunk
from pr_inspector.infrastructure.indexer.chunk_store import JsonFileChunkStore


def test_chunk_store_empty_when_file_not_found(tmp_path):
    store = JsonFileChunkStore(tmp_path / "missing.json")
    assert store.load_chunks() == []


def test_chunk_store_save_and_load_roundtrip(tmp_path):
    store_file = tmp_path / "sub" / "chunks.json"
    store = JsonFileChunkStore(store_file)

    chunks = [
        CodeChunk(
            id="src/math.py:1-5:add",
            file_path="src/math.py",
            content="def add(a, b):\n    return a + b",
            start_line=1,
            end_line=5,
            chunk_type=ChunkType.FUNCTION,
            symbol_name="add",
            language="python",
        ),
        CodeChunk(
            id="README.md:1-10:sec",
            file_path="README.md",
            content="# Title\nHello world",
            start_line=1,
            end_line=10,
            chunk_type=ChunkType.MARKDOWN_SECTION,
            language="markdown",
        ),
    ]

    store.save_chunks(chunks)
    assert store_file.is_file()

    loaded = store.load_chunks()
    assert len(loaded) == 2
    assert loaded[0] == chunks[0]
    assert loaded[1] == chunks[1]


def test_chunk_store_graceful_recovery_on_corrupt_file(tmp_path):
    store_file = tmp_path / "corrupt.json"
    store_file.write_text("invalid json content {{{", encoding="utf-8")

    store = JsonFileChunkStore(store_file)
    assert store.load_chunks() == []


def test_chunk_store_graceful_recovery_on_non_list_json(tmp_path):
    store_file = tmp_path / "non_list.json"
    store_file.write_text('{"key": "value"}', encoding="utf-8")

    store = JsonFileChunkStore(store_file)
    assert store.load_chunks() == []
