"""Unit tests for ReviewContextRetriever."""

from unittest.mock import MagicMock

from pr_inspector.application.services.context_retriever import ReviewContextRetriever
from pr_inspector.application.services.hybrid_search import HybridSearchRetriever
from pr_inspector.domain.entities import ChunkType, CodeChunk, DiffHunk, DiffLine, FileDiff
from pr_inspector.domain.protocols import ContextRetriever


def make_chunk(cid: str, path: str, content: str = "pass", symbol: str | None = None) -> CodeChunk:
    return CodeChunk(
        id=cid,
        file_path=path,
        content=content,
        start_line=10,
        end_line=20,
        chunk_type=ChunkType.FUNCTION,
        symbol_name=symbol or cid,
        language="python",
    )


def make_diff(file_path: str, code: str) -> FileDiff:
    line = DiffLine(line_type="add", content=code)
    hunk = DiffHunk(
        header="@@ -1,5 +1,5 @@",
        old_start=1,
        old_lines=5,
        new_start=1,
        new_lines=5,
        lines=[line],
    )
    return FileDiff(file_path=file_path, hunks=[hunk])


def test_context_retriever_protocol_conformance():
    mock_hybrid = MagicMock(spec=HybridSearchRetriever)
    retriever = ReviewContextRetriever(hybrid_retriever=mock_hybrid)
    assert isinstance(retriever, ContextRetriever)


def test_context_retriever_empty_inputs():
    mock_hybrid = MagicMock(spec=HybridSearchRetriever)
    retriever = ReviewContextRetriever(hybrid_retriever=mock_hybrid)
    assert retriever.retrieve_context_for_diffs([]) == ""
    assert retriever.retrieve_context_for_diffs([make_diff("src/a.py", "")], top_k=0) == ""


def test_context_retriever_filters_out_diff_files():
    mock_hybrid = MagicMock(spec=HybridSearchRetriever)
    diff = make_diff("src/auth.py", "def check_token(token): pass")

    c_same_file = make_chunk("c1", "src/auth.py", "def old_auth(): pass")
    c_caller_file = make_chunk(
        "c2",
        "src/api/routes.py",
        "def login_route(): check_token()",
        symbol="login_route",
    )

    # Hybrid retriever returns both chunks
    mock_hybrid.retrieve.return_value = [(c_same_file, 0.95), (c_caller_file, 0.80)]

    retriever = ReviewContextRetriever(hybrid_retriever=mock_hybrid)
    formatted = retriever.retrieve_context_for_diffs([diff], top_k=5)

    # Must include caller file, but exclude same file
    assert "src/api/routes.py" in formatted
    assert "login_route" in formatted
    assert "src/auth.py" not in formatted


def test_context_retriever_token_budget_limiting():
    mock_hybrid = MagicMock(spec=HybridSearchRetriever)
    diff = make_diff("src/service.py", "def process(): pass")

    # Large chunks
    c1 = make_chunk("c1", "src/dep1.py", "x = 1\n" * 50)
    c2 = make_chunk("c2", "src/dep2.py", "y = 2\n" * 50)

    mock_hybrid.retrieve.return_value = [(c1, 0.9), (c2, 0.8)]

    # Budget that fits only 1 chunk (~70 tokens)
    retriever = ReviewContextRetriever(hybrid_retriever=mock_hybrid, max_context_tokens=100)
    formatted = retriever.retrieve_context_for_diffs([diff], top_k=5)

    assert "src/dep1.py" in formatted
    assert "src/dep2.py" not in formatted
