"""Composite chunker routing by file type with fallback sliding line window."""

from pathlib import Path

from pr_inspector.domain.entities import ChunkType, CodeChunk
from pr_inspector.infrastructure.indexer.ast_chunker import PythonAstChunker
from pr_inspector.infrastructure.indexer.markdown_chunker import MarkdownHeadingChunker


class LineWindowChunker:
    """Sliding line window chunker for configuration and generic text files."""

    def __init__(self, window_size: int = 60, overlap: int = 10) -> None:
        self.window_size = window_size
        self.overlap = overlap

    def chunk_file(self, file_path: str, content: str) -> list[CodeChunk]:
        """Split content into fixed line windows with overlap."""
        if not content.strip():
            return []

        lines = content.splitlines()
        chunks: list[CodeChunk] = []
        step = max(1, self.window_size - self.overlap)

        for start_idx in range(0, len(lines), step):
            end_idx = min(start_idx + self.window_size, len(lines))
            chunk_lines = lines[start_idx:end_idx]
            chunk_text = "\n".join(chunk_lines).strip()
            if not chunk_text:
                continue

            start_line = start_idx + 1
            end_line = end_idx

            chunks.append(
                CodeChunk(
                    id=f"{file_path}:{start_line}-{end_line}:window_{start_line}",
                    file_path=file_path,
                    content=chunk_text,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type=ChunkType.TEXT_BLOCK,
                    language=Path(file_path).suffix.lstrip(".").lower() or "text",
                )
            )

            if end_idx == len(lines):
                break

        return chunks


class CompositeChunker:
    """Routes files to appropriate structure-aware chunkers based on extension."""

    def __init__(
        self,
        ast_chunker: PythonAstChunker | None = None,
        markdown_chunker: MarkdownHeadingChunker | None = None,
        fallback_chunker: LineWindowChunker | None = None,
    ) -> None:
        self.ast_chunker = ast_chunker or PythonAstChunker()
        self.markdown_chunker = markdown_chunker or MarkdownHeadingChunker()
        self.fallback_chunker = fallback_chunker or LineWindowChunker()

    def chunk_file(self, file_path: str, content: str) -> list[CodeChunk]:
        """Route to specialized chunker based on file path extension."""
        suffix = Path(file_path).suffix.lower()

        if suffix == ".py":
            return self.ast_chunker.chunk_file(file_path, content)
        if suffix in (".md", ".markdown"):
            return self.markdown_chunker.chunk_file(file_path, content)

        return self.fallback_chunker.chunk_file(file_path, content)
