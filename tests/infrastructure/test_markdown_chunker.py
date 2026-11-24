"""Unit tests for MarkdownHeadingChunker (Issue #17)."""

from pr_inspector.domain.entities import ChunkType
from pr_inspector.infrastructure.indexer.markdown_chunker import MarkdownHeadingChunker

SAMPLE_MARKDOWN = """# Project Documentation

Welcome to the project.

## Architecture

Our architecture follows Clean Architecture.

### Domain Layer

Contains entities and business protocols.

### Infrastructure Layer

Contains external clients and databases.

## Contributing

Please follow PR rules.
"""


def test_chunk_markdown_heading_hierarchy():
    chunker = MarkdownHeadingChunker()
    chunks = chunker.chunk_file("docs/guide.md", SAMPLE_MARKDOWN)

    assert len(chunks) == 5

    # Top-level title section
    title_chunk = chunks[0]
    assert title_chunk.symbol_name == "Project Documentation"
    assert title_chunk.parent_symbol is None
    assert "Welcome to the project" in title_chunk.content

    # Architecture section
    arch_chunk = chunks[1]
    assert arch_chunk.symbol_name == "Architecture"
    assert arch_chunk.parent_symbol == "Project Documentation"

    # Domain Layer subsection
    domain_chunk = chunks[2]
    assert domain_chunk.symbol_name == "Domain Layer"
    assert domain_chunk.parent_symbol == "Architecture"
    assert "Contains entities" in domain_chunk.content

    # Infrastructure Layer subsection
    infra_chunk = chunks[3]
    assert infra_chunk.symbol_name == "Infrastructure Layer"
    assert infra_chunk.parent_symbol == "Architecture"

    # Contributing section
    contrib_chunk = chunks[4]
    assert contrib_chunk.symbol_name == "Contributing"
    assert contrib_chunk.parent_symbol == "Project Documentation"


def test_chunk_markdown_no_headings():
    chunker = MarkdownHeadingChunker()
    text = "Just a plain document without any markdown headers.\nLine 2.\nLine 3."
    chunks = chunker.chunk_file("notes.txt", text)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == ChunkType.MARKDOWN_SECTION
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3
    assert chunks[0].content == text


def test_chunk_empty_markdown():
    chunker = MarkdownHeadingChunker()
    assert chunker.chunk_file("empty.md", "") == []
    assert chunker.chunk_file("empty.md", "   \n\t  ") == []
