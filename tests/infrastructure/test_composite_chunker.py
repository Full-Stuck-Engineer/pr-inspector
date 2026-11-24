"""Unit tests for CompositeChunker and LineWindowChunker (Issue #17)."""

from pr_inspector.domain.entities import ChunkType
from pr_inspector.infrastructure.indexer.composite_chunker import (
    CompositeChunker,
    LineWindowChunker,
)


def test_line_window_chunker():
    chunker = LineWindowChunker(window_size=5, overlap=2)
    lines = [f"line {i}" for i in range(1, 13)]
    content = "\n".join(lines)

    chunks = chunker.chunk_file("pyproject.toml", content)
    assert len(chunks) >= 3

    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 5
    assert chunks[0].chunk_type == ChunkType.TEXT_BLOCK
    assert chunks[0].language == "toml"


def test_composite_chunker_routing():
    chunker = CompositeChunker()

    # Routes .py to AST
    py_chunks = chunker.chunk_file("app.py", "def foo():\n    return 42\n")
    assert any(c.chunk_type == ChunkType.FUNCTION for c in py_chunks)

    # Routes .md to Markdown
    md_chunks = chunker.chunk_file("README.md", "# Heading\nContent\n")
    assert any(c.chunk_type == ChunkType.MARKDOWN_SECTION for c in md_chunks)

    # Routes .toml to LineWindow
    toml_chunks = chunker.chunk_file("pyproject.toml", "[tool.ruff]\nline-length = 100\n")
    assert any(c.chunk_type == ChunkType.TEXT_BLOCK for c in toml_chunks)
