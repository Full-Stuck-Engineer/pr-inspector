"""Markdown structure-aware document chunker."""

import re

from pr_inspector.domain.entities import ChunkType, CodeChunk

HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.*)$")


class MarkdownHeadingChunker:
    """Chunks Markdown documents by heading sections with hierarchical breadcrumbs."""

    def chunk_file(self, file_path: str, content: str) -> list[CodeChunk]:
        """Split Markdown document into section chunks based on headers."""
        if not content.strip():
            return []

        lines = content.splitlines()
        headings: list[tuple[int, int, str]] = []  # (line_idx_0_based, level, title)

        for idx, line in enumerate(lines):
            match = HEADING_REGEX.match(line)
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()
                headings.append((idx, level, title))

        if not headings:
            return [
                CodeChunk(
                    id=f"{file_path}:1-{len(lines)}:document",
                    file_path=file_path,
                    content=content,
                    start_line=1,
                    end_line=len(lines),
                    chunk_type=ChunkType.MARKDOWN_SECTION,
                    language="markdown",
                )
            ]

        chunks: list[CodeChunk] = []

        # Preamble before first heading if any content exists
        first_heading_idx = headings[0][0]
        if first_heading_idx > 0:
            preamble_text = "\n".join(lines[:first_heading_idx]).strip()
            if preamble_text:
                chunks.append(
                    CodeChunk(
                        id=f"{file_path}:1-{first_heading_idx}:preamble",
                        file_path=file_path,
                        content=preamble_text,
                        start_line=1,
                        end_line=first_heading_idx,
                        chunk_type=ChunkType.MARKDOWN_SECTION,
                        symbol_name="Preamble",
                        language="markdown",
                    )
                )

        # Slice each section from current heading to next heading (or end of file)
        for i, (line_idx, level, title) in enumerate(headings):
            start_line = line_idx + 1
            if i + 1 < len(headings):
                end_line = headings[i + 1][0]  # line before next heading
            else:
                end_line = len(lines)

            section_lines = lines[line_idx:end_line]
            section_text = "\n".join(section_lines).strip()
            if not section_text:
                continue

            # Determine parent heading breadcrumb from preceding higher-level heading
            parent_symbol = None
            for _prev_idx, prev_level, prev_title in reversed(headings[:i]):
                if prev_level < level:
                    parent_symbol = prev_title
                    break

            slug = re.sub(r"[^\w\-]+", "_", title.lower()).strip("_")
            chunk_id = f"{file_path}:{start_line}-{end_line}:{slug}"

            chunks.append(
                CodeChunk(
                    id=chunk_id,
                    file_path=file_path,
                    content=section_text,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type=ChunkType.MARKDOWN_SECTION,
                    symbol_name=title,
                    parent_symbol=parent_symbol,
                    language="markdown",
                )
            )

        return chunks
