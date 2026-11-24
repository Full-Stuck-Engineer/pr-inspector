"""In-memory BM25 lexical keyword index with code-aware tokenization."""

import math
import re
from collections import Counter

from pr_inspector.domain.entities import CodeChunk
from pr_inspector.domain.protocols import KeywordIndex

# Regex to split words by non-alphanumeric characters, underscores, and camelCase
_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")


def tokenize_code(text: str) -> list[str]:
    """Tokenize source code into lowercase keywords, splitting snake_case and camelCase."""
    tokens: list[str] = []
    for word in _WORD_RE.findall(text):
        lower_word = word.lower()
        tokens.append(lower_word)

        # Split camelCase: ReviewDiffUseCase -> Review, Diff, Use, Case
        split_camel = _CAMEL_RE.sub(r"\1 \2", word).split()
        if len(split_camel) > 1:
            for sub in split_camel:
                tokens.append(sub.lower())

        # Split snake_case: review_diff_use_case -> review, diff, use, case
        if "_" in lower_word:
            for sub in lower_word.split("_"):
                if sub:
                    tokens.append(sub)

    return tokens


class BM25KeywordIndex(KeywordIndex):
    """In-memory BM25 implementation for exact symbol and identifier search."""

    def __init__(self, k1: float = 1.5, b: float = 0.75, symbol_boost: float = 2.0) -> None:
        self.k1 = k1
        self.b = b
        self.symbol_boost = symbol_boost
        self._chunks: dict[str, CodeChunk] = {}
        self._doc_lens: dict[str, int] = {}
        self._term_frequencies: dict[str, Counter[str]] = {}
        self._doc_frequencies: Counter[str] = Counter()

    def _chunk_text(self, chunk: CodeChunk) -> str:
        # Include symbol name, parent symbol, file path and body content
        parts = [chunk.content, chunk.file_path]
        if chunk.symbol_name:
            parts.append(chunk.symbol_name)
        if chunk.parent_symbol:
            parts.append(chunk.parent_symbol)
        return " ".join(parts)

    def upsert(self, chunks: list[CodeChunk]) -> None:
        """Insert or replace chunks in the index."""
        for chunk in chunks:
            if chunk.id in self._chunks:
                self.delete([chunk.id])

            tokens = tokenize_code(self._chunk_text(chunk))
            doc_len = len(tokens)
            tf = Counter(tokens)

            self._chunks[chunk.id] = chunk
            self._doc_lens[chunk.id] = doc_len
            self._term_frequencies[chunk.id] = tf

            for term in tf:
                self._doc_frequencies[term] += 1

    def delete(self, chunk_ids: list[str]) -> None:
        """Remove chunks from the index by ID."""
        for cid in chunk_ids:
            if cid not in self._chunks:
                continue

            tf = self._term_frequencies.pop(cid, Counter())
            self._doc_lens.pop(cid, None)
            self._chunks.pop(cid, None)

            for term in tf:
                self._doc_frequencies[term] -= 1
                if self._doc_frequencies[term] <= 0:
                    del self._doc_frequencies[term]

    def search(self, query: str, top_k: int = 5) -> list[tuple[CodeChunk, float]]:
        """Search chunks by BM25 relevance score."""
        query_tokens = tokenize_code(query)
        if not query_tokens or not self._chunks:
            return []

        num_docs = len(self._chunks)
        avg_doc_len = sum(self._doc_lens.values()) / num_docs if num_docs > 0 else 1.0

        scores: dict[str, float] = {}
        query_counter = Counter(query_tokens)

        for term in query_counter:
            df = self._doc_frequencies.get(term, 0)
            if df == 0:
                continue

            # Standard non-negative Robertson-Spärck Jones IDF
            idf = math.log(1.0 + (num_docs - df + 0.5) / (df + 0.5))

            for cid, chunk in self._chunks.items():
                f = self._term_frequencies[cid].get(term, 0)
                if f == 0:
                    continue

                doc_len = self._doc_lens[cid]
                denom = f + self.k1 * (1.0 - self.b + self.b * (doc_len / avg_doc_len))
                term_score = idf * (f * (self.k1 + 1.0)) / denom

                # Boost exact symbol match if query term matches chunk symbol
                if chunk.symbol_name and term == chunk.symbol_name.lower():
                    term_score *= self.symbol_boost

                scores[cid] = scores.get(cid, 0.0) + term_score

        sorted_results = [
            (self._chunks[cid], round(score, 4))
            for cid, score in sorted(scores.items(), key=lambda entry: entry[1], reverse=True)
        ]

        return sorted_results[:top_k]
