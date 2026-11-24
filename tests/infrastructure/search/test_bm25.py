"""Unit tests for BM25KeywordIndex."""

from pr_inspector.domain.entities import ChunkType, CodeChunk
from pr_inspector.domain.protocols import KeywordIndex
from pr_inspector.infrastructure.search.bm25 import BM25KeywordIndex, tokenize_code


def make_chunk(
    cid: str,
    content: str,
    path: str = "src/main.py",
    symbol_name: str | None = None,
    chunk_type: ChunkType = ChunkType.FUNCTION,
) -> CodeChunk:
    return CodeChunk(
        id=cid,
        file_path=path,
        content=content,
        start_line=1,
        end_line=10,
        chunk_type=chunk_type,
        symbol_name=symbol_name,
    )


def test_protocol_conformance():
    index = BM25KeywordIndex()
    assert isinstance(index, KeywordIndex)


def test_tokenize_code_camel_and_snake_case():
    tokens = tokenize_code("ReviewDiffUseCase get_diff_hunks(self, target_ref)")
    assert "reviewdiffusecase" in tokens
    assert "review" in tokens
    assert "diff" in tokens
    assert "use" in tokens
    assert "case" in tokens
    assert "get_diff_hunks" in tokens
    assert "hunks" in tokens
    assert "target_ref" in tokens
    assert "ref" in tokens


def test_bm25_empty_search():
    index = BM25KeywordIndex()
    assert index.search("anything") == []

    c1 = make_chunk("c1", "def foo(): pass")
    index.upsert([c1])
    assert index.search("nonexistent_term") == []


def test_bm25_exact_symbol_match_ranked_highest():
    chunk_def = make_chunk(
        "c_def",
        "class ReviewDiffUseCase:\n    def execute(self): pass",
        symbol_name="ReviewDiffUseCase",
        chunk_type=ChunkType.CLASS,
    )
    chunk_mention = make_chunk(
        "c_mention",
        "# Calls ReviewDiffUseCase here\nrunner.run()",
        symbol_name="run_command",
    )
    chunk_unrelated = make_chunk(
        "c_other",
        "def format_report(): return 'done'",
        symbol_name="format_report",
    )

    index = BM25KeywordIndex()
    index.upsert([chunk_mention, chunk_def, chunk_unrelated])

    results = index.search("ReviewDiffUseCase", top_k=2)

    assert len(results) == 2
    assert results[0][0].id == "c_def"
    assert results[1][0].id == "c_mention"
    assert results[0][1] > results[1][1]


def test_bm25_upsert_replaces_existing_chunk():
    index = BM25KeywordIndex()
    c1_v1 = make_chunk("c1", "def old_alpha(): pass", symbol_name="old_alpha")
    index.upsert([c1_v1])

    assert len(index.search("old_alpha")) == 1

    c1_v2 = make_chunk("c1", "def new_beta(): pass", symbol_name="new_beta")
    index.upsert([c1_v2])

    assert index.search("old_alpha") == []
    assert len(index.search("new_beta")) == 1


def test_bm25_delete():
    index = BM25KeywordIndex()
    c1 = make_chunk("c1", "def foo(): return 42", symbol_name="foo")
    c2 = make_chunk("c2", "def bar(): return 43", symbol_name="bar")
    index.upsert([c1, c2])

    assert len(index.search("foo")) == 1
    assert len(index.search("bar")) == 1

    index.delete(["c1"])
    assert index.search("foo") == []
    assert len(index.search("bar")) == 1
