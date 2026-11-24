"""Application service for retrieving and formatting codebase context for diff reviews."""

import time
from typing import Any

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
        self.last_retrieved_chunks: list[CodeChunk] = []
        self.last_retrieval_stats: dict[str, Any] = {
            "retrieved_chunks": 0,
            "context_tokens": 0,
            "rerank_latency_ms": 0.0,
        }

    def _reset_stats(self, rerank_ms: float = 0.0) -> None:
        self.last_retrieved_chunks = []
        self.last_retrieval_stats = {
            "retrieved_chunks": 0,
            "context_tokens": 0,
            "rerank_latency_ms": round(rerank_ms, 2),
        }

    def retrieve_context_for_diffs(self, diffs: list[FileDiff], top_k: int = 5) -> str:
        """Retrieve relevant codebase chunks for the diffs and format as Markdown."""
        start_time = time.perf_counter()
        if not diffs or top_k < 1:
            self._reset_stats()
            return ""

        query = self.symbol_extractor.build_search_query(diffs)
        if not query.strip():
            self._reset_stats()
            return ""

        # Fetch candidates with headroom to allow filtering out files in the diff
        raw_candidates = self.hybrid_retriever.retrieve(query, top_k=top_k * 3)
        retrieval_ms = (time.perf_counter() - start_time) * 1000
        if not raw_candidates:
            self._reset_stats(rerank_ms=retrieval_ms)
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
            self._reset_stats(rerank_ms=retrieval_ms)
            return ""

        formatted_context = self.format_context_chunks(selected_chunks)
        self.last_retrieved_chunks = selected_chunks
        self.last_retrieval_stats = {
            "retrieved_chunks": len(selected_chunks),
            "context_tokens": estimate_tokens(formatted_context),
            "rerank_latency_ms": round(retrieval_ms, 2),
        }
        return formatted_context

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
