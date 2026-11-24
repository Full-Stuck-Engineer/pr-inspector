"""Unit tests for ReviewDiffUseCase with codebase context retrieval."""

from unittest.mock import MagicMock

from pr_inspector.application.use_cases.review_diff import ReviewDiffUseCase
from pr_inspector.domain.entities import (
    DiffHunk,
    DiffLine,
    FileDiff,
    PRReviewResult,
    ReviewIssue,
    RiskLevel,
    TelemetryRecord,
)
from pr_inspector.domain.protocols import ContextRetriever, DiffProvider, LLMReviewer


def make_diff(file_path: str = "src/api.py") -> FileDiff:
    line = DiffLine(line_type="add", content="def new_func(): pass", new_line_number=10)
    hunk = DiffHunk(
        header="@@ -1,5 +1,5 @@",
        old_start=1,
        old_lines=5,
        new_start=1,
        new_lines=5,
        lines=[line],
    )
    return FileDiff(file_path=file_path, hunks=[hunk])


def test_use_case_passes_retrieved_context_to_reviewer():
    diff = make_diff()
    mock_diff_provider = MagicMock(spec=DiffProvider)
    mock_diff_provider.get_diff.return_value = [diff]

    mock_context_retriever = MagicMock(spec=ContextRetriever)
    mock_context_retriever.retrieve_context_for_diffs.return_value = "### src/auth.py context"

    mock_result = PRReviewResult(
        summary="Context-aware review",
        risk_level=RiskLevel.LOW,
        issues=[
            ReviewIssue(
                file_path="src/api.py",
                line_number=1,
                severity=RiskLevel.LOW,
                title="Notice",
                description="Verified against auth",
                cited_files=["src/auth.py"],
            )
        ],
        cited_files=["src/auth.py"],
    )
    mock_telemetry = TelemetryRecord(
        model="test-model",
        input_tokens=100,
        output_tokens=50,
        latency_ms=200.0,
        timestamp="2026-11-24T00:00:00Z",
    )

    mock_reviewer = MagicMock(spec=LLMReviewer)
    mock_reviewer.review.return_value = (mock_result, mock_telemetry)

    use_case = ReviewDiffUseCase(
        diff_provider=mock_diff_provider,
        reviewer=mock_reviewer,
        context_retriever=mock_context_retriever,
    )

    result, telemetry = use_case.execute()

    assert result == mock_result
    assert result.cited_files == ["src/auth.py"]
    mock_context_retriever.retrieve_context_for_diffs.assert_called_once_with([diff])
    mock_reviewer.review.assert_called_once_with([diff], context="### src/auth.py context")


def test_use_case_without_context_retriever_passes_none():
    diff = make_diff()
    mock_diff_provider = MagicMock(spec=DiffProvider)
    mock_diff_provider.get_diff.return_value = [diff]

    mock_result = PRReviewResult(
        summary="Standard review",
        risk_level=RiskLevel.LOW,
        issues=[],
    )
    mock_telemetry = TelemetryRecord(
        model="test-model",
        input_tokens=100,
        output_tokens=50,
        latency_ms=200.0,
        timestamp="2026-11-24T00:00:00Z",
    )

    mock_reviewer = MagicMock(spec=LLMReviewer)
    mock_reviewer.review.return_value = (mock_result, mock_telemetry)

    use_case = ReviewDiffUseCase(
        diff_provider=mock_diff_provider,
        reviewer=mock_reviewer,
        context_retriever=None,
    )

    result, telemetry = use_case.execute()

    assert result == mock_result
    mock_reviewer.review.assert_called_once_with([diff], context=None)
