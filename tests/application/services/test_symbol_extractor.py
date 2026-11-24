"""Unit tests for DiffSymbolExtractor."""

from pr_inspector.application.services.symbol_extractor import DiffSymbolExtractor
from pr_inspector.domain.entities import DiffHunk, DiffLine, FileDiff


def make_diff(lines_data: list[tuple[str, str]], header: str = "@@ -1,5 +1,6 @@") -> FileDiff:
    lines = [DiffLine(line_type=t, content=c) for t, c in lines_data]
    hunk = DiffHunk(
        header=header,
        old_start=1,
        old_lines=5,
        new_start=1,
        new_lines=len(lines),
        lines=lines,
    )
    return FileDiff(file_path="src/service.py", hunks=[hunk])


def test_symbol_extractor_empty_diffs():
    extractor = DiffSymbolExtractor()
    assert extractor.extract_symbols([]) == []
    assert extractor.build_search_query([]) == ""


def test_symbol_extractor_definitions():
    diff = make_diff(
        [
            ("context", "import os"),
            ("add", "def validate_token(token: str) -> bool:"),
            ("add", "    return len(token) > 10"),
            ("add", "class TokenValidator:"),
            ("add", "    pass"),
        ]
    )

    extractor = DiffSymbolExtractor()
    symbols = extractor.extract_symbols([diff])

    assert "validate_token" in symbols
    assert "TokenValidator" in symbols


def test_symbol_extractor_imports():
    diff = make_diff(
        [
            ("add", "from auth.crypto import hash_password, verify_secret"),
            ("add", "import jwt"),
        ]
    )

    extractor = DiffSymbolExtractor()
    symbols = extractor.extract_symbols([diff])

    assert "crypto" in symbols
    assert "hash_password" in symbols
    assert "verify_secret" in symbols
    assert "jwt" in symbols


def test_symbol_extractor_hunk_header_and_build_query():
    diff = make_diff(
        [
            ("add", "    result = calculate_risk_score(data)"),
        ],
        header="@@ -10,3 +10,4 @@ def process_payload(data):",
    )

    extractor = DiffSymbolExtractor()
    symbols = extractor.extract_symbols([diff])

    assert "process_payload" in symbols
    assert "calculate_risk_score" in symbols

    query = extractor.build_search_query([diff], max_terms=5)
    assert "process_payload" in query
    assert "calculate_risk_score" in query
