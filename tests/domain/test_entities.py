"""Unit tests for domain entities and protocols."""

import pytest
from pydantic import ValidationError

from pr_inspector.domain.entities import (
    DiffHunk,
    DiffLine,
    FileDiff,
    PRReviewResult,
    ReviewIssue,
    RiskLevel,
)
from pr_inspector.domain.protocols import DiffProvider


def test_review_issue_validation():
    issue = ReviewIssue(
        file_path="src/main.py",
        line_number=42,
        severity=RiskLevel.HIGH,
        title="SQL Injection vulnerability",
        description="User input is concatenated directly into query.",
        suggested_fix="Use parameterized queries.",
    )
    assert issue.line_number == 42
    assert issue.severity == RiskLevel.HIGH


def test_review_issue_invalid_line_number():
    with pytest.raises(ValidationError):
        ReviewIssue(
            file_path="src/main.py",
            line_number=0,  # line number must be >= 1
            severity=RiskLevel.LOW,
            title="Invalid line",
            description="Testing validator",
        )


def test_pr_review_result_serialization():
    result = PRReviewResult(
        summary="Changes look safe with minor improvements suggested.",
        risk_level=RiskLevel.LOW,
        issues=[
            ReviewIssue(
                file_path="src/utils.py",
                line_number=10,
                severity=RiskLevel.LOW,
                title="Unused variable",
                description="Variable 'tmp' is assigned but never used.",
            )
        ],
    )
    data = result.model_dump()
    assert data["risk_level"] == "LOW"
    assert len(data["issues"]) == 1
    assert data["issues"][0]["line_number"] == 10


def test_file_diff_annotated_text_generation():
    hunk = DiffHunk(
        header="@@ -10,3 +10,4 @@ def calculate():",
        old_start=10,
        old_lines=3,
        new_start=10,
        new_lines=4,
        lines=[
            DiffLine(
                line_type="context",
                content="def calculate():",
                old_line_number=10,
                new_line_number=10,
            ),
            DiffLine(line_type="del", content="    old_logic()", old_line_number=11),
            DiffLine(line_type="add", content="    new_logic()", new_line_number=11),
            DiffLine(line_type="add", content="    validate()", new_line_number=12),
        ],
    )
    diff = FileDiff(file_path="src/calc.py", hunks=[hunk])
    annotated = diff.annotated_diff_text

    assert "--- a/src/calc.py" in annotated
    assert "+++ b/src/calc.py" in annotated
    assert "  10 | def calculate():" in annotated
    assert "     -     old_logic()" in annotated
    assert "  11 +     new_logic()" in annotated
    assert "  12 +     validate()" in annotated


def test_protocols_runtime_checkable():
    class DummyDiffProvider:
        def get_diff(self, target_ref: str | None = None, staged: bool = False) -> list[FileDiff]:
            return []

    assert isinstance(DummyDiffProvider(), DiffProvider)
