"""Unit tests for cited_files tracking and aggregation in domain entities."""

from pr_inspector.domain.entities import PRReviewResult, ReviewIssue, RiskLevel
from pr_inspector.domain.review_merging import merge_review_results


def test_cited_files_defaults_to_empty():
    issue = ReviewIssue(
        file_path="src/main.py",
        line_number=10,
        severity=RiskLevel.LOW,
        title="Note",
        description="test",
    )
    assert issue.cited_files == []

    result = PRReviewResult(
        summary="ok",
        risk_level=RiskLevel.LOW,
        issues=[issue],
    )
    assert result.cited_files == []


def test_merge_review_results_aggregates_and_deduplicates_citations():
    r1 = PRReviewResult(
        summary="Batch 1",
        risk_level=RiskLevel.LOW,
        issues=[
            ReviewIssue(
                file_path="src/a.py",
                line_number=1,
                severity=RiskLevel.LOW,
                title="t1",
                description="d1",
                cited_files=["src/utils.py", "src/auth.py"],
            )
        ],
        cited_files=["src/auth.py"],
    )

    r2 = PRReviewResult(
        summary="Batch 2",
        risk_level=RiskLevel.MEDIUM,
        issues=[
            ReviewIssue(
                file_path="src/b.py",
                line_number=5,
                severity=RiskLevel.MEDIUM,
                title="t2",
                description="d2",
                cited_files=["src/models.py"],
            )
        ],
        cited_files=["src/config.py", "src/utils.py"],
    )

    merged = merge_review_results([r1, r2])

    assert merged.cited_files == [
        "src/auth.py",
        "src/config.py",
        "src/models.py",
        "src/utils.py",
    ]
