"""Application service for retrieving and formatting codebase context for diff reviews."""

from pr_inspector.application.services.hybrid_search import HybridSearchRetriever
from pr_inspector.application.services.symbol_extractor import DiffSymbolExtractor
from pr_inspector.domain.chunking import estimate_tokens
from pr_inspector.domain.entities import CodeChunk, FileDiff
from pr_inspector.domain.protocols import ContextRetriever

DEFAULT_MAX_CONTEXT_TOKENS = 4000


class ReviewContextRetriever(ContextRetriever):
    """Retrieves relevant codebase context for diffs and formats it into markdown blocks."""

    def __init__(
        self,
        hybrid_retriever: HybridSearchRetriever,
        symbol_extractor: DiffSymbolExtractor | None = None,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    ) -> None:
        self.hybrid_retriever = hybrid_retriever
        self.symbol_extractor = symbol_extractor or DiffSymbolExtractor()
        self.max_context_tokens = max_context_tokens

    def retrieve_context_for_diffs(self, diffs: list[FileDiff], top_k: int = 5) -> str:
        """Retrieve relevant codebase chunks for the diffs and format as Markdown."""
        if not diffs or top_k < 1:
            return ""

        query = self.symbol_extractor.build_search_query(diffs)
        if not query.strip():
            return ""

        # Fetch candidates with headroom to allow filtering out files in the diff
        raw_candidates = self.hybrid_retriever.retrieve(query, top_k=top_k * 3)
        if not raw_candidates:
            return ""

        diff_files = {d.file_path for d in diffs if d.file_path}
        diff_files.update(d.old_path for d in diffs if d.old_path)

        # Filter out chunks that belong to the files being modified in the diff
        selected_chunks: list[CodeChunk] = []
        for chunk, _score in raw_candidates:
            if chunk.file_path not in diff_files:
                selected_chunks.append(chunk)
            if len(selected_chunks) >= top_k:
                break

        if not selected_chunks:
            return ""

        return self.format_context_chunks(selected_chunks)

    def format_context_chunks(self, chunks: list[CodeChunk]) -> str:
        """Format chunks into Markdown code blocks respecting the token budget."""
        formatted_blocks: list[str] = []
        accumulated_tokens = 0

        for chunk in chunks:
            type_val = chunk.chunk_type.value
            symbol_desc = f", {type_val} `{chunk.symbol_name}`" if chunk.symbol_name else ""
            line_range = f"lines {chunk.start_line}-{chunk.end_line}{symbol_desc}"
            header = f"### `{chunk.file_path}` ({line_range})"
            block = f"{header}\n```{chunk.language}\n{chunk.content}\n```"

            block_tokens = estimate_tokens(block)
            if formatted_blocks and (accumulated_tokens + block_tokens > self.max_context_tokens):
                break

            formatted_blocks.append(block)
            accumulated_tokens += block_tokens

        return "\n\n".join(formatted_blocks)
