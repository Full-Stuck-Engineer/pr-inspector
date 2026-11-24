"""Unit tests for merging per-batch review outcomes."""

import pytest

from pr_inspector.domain.entities import PRReviewResult, ReviewIssue, RiskLevel, TelemetryRecord
from pr_inspector.domain.review_merging import merge_review_results, merge_telemetry


def make_issue(path: str, line: int, severity: RiskLevel = RiskLevel.MEDIUM) -> ReviewIssue:
    return ReviewIssue(
        file_path=path,
        line_number=line,
        severity=severity,
        title=f"Problem in {path}",
        description="details",
    )


def make_record(input_tokens: int, output_tokens: int, latency_ms: float, stamp: str):
    return TelemetryRecord(
        model="qwen2.5-coder:7b",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        timestamp=stamp,
    )


def test_single_result_is_returned_unchanged():
    result = PRReviewResult(summary="Only one", risk_level=RiskLevel.LOW)

    assert merge_review_results([result]) is result


def test_merge_takes_highest_risk_and_keeps_every_issue_in_order():
    first = PRReviewResult(
        summary="Batch one.",
        risk_level=RiskLevel.MEDIUM,
        issues=[make_issue("a.py", 3)],
    )
    second = PRReviewResult(
        summary="Batch two.",
        risk_level=RiskLevel.CRITICAL,
        issues=[make_issue("b.py", 9, RiskLevel.CRITICAL), make_issue("b.py", 12)],
    )
    third = PRReviewResult(summary="Batch three.", risk_level=RiskLevel.LOW)

    merged = merge_review_results([first, second, third])

    assert merged.risk_level == RiskLevel.CRITICAL
    assert [(i.file_path, i.line_number) for i in merged.issues] == [
        ("a.py", 3),
        ("b.py", 9),
        ("b.py", 12),
    ]
    assert merged.summary == "Batch one. Batch two. Batch three."


def test_merged_risk_is_never_below_the_highest_issue_severity():
    # Batch one under-reports its own risk; the merged result must still reflect the issue.
    under_reported = PRReviewResult(
        summary="Looks fine.",
        risk_level=RiskLevel.LOW,
        issues=[make_issue("a.py", 1, RiskLevel.HIGH)],
    )
    clean = PRReviewResult(summary="Clean.", risk_level=RiskLevel.LOW)

    merged = merge_review_results([clean, under_reported])

    assert merged.risk_level == RiskLevel.HIGH


def test_blank_summaries_are_skipped():
    blank = PRReviewResult(summary="   ", risk_level=RiskLevel.LOW)
    real = PRReviewResult(summary="Real.", risk_level=RiskLevel.LOW)

    assert merge_review_results([blank, real]).summary == "Real."


def test_merge_review_results_requires_input():
    with pytest.raises(ValueError, match="at least one"):
        merge_review_results([])


def test_single_telemetry_record_is_returned_unchanged():
    record = make_record(10, 5, 100.0, "t1")

    assert merge_telemetry([record]) is record


def test_telemetry_is_summed_and_stamped_with_the_last_batch():
    merged = merge_telemetry(
        [
            make_record(100, 20, 1500.5, "t1"),
            make_record(250, 40, 2200.25, "t2"),
            make_record(50, 10, 300.0, "t3"),
        ]
    )

    assert merged.model == "qwen2.5-coder:7b"
    assert merged.input_tokens == 400
    assert merged.output_tokens == 70
    assert merged.latency_ms == 4000.75
    assert merged.timestamp == "t3"


def test_merge_telemetry_sums_rag_metrics():
    r1 = TelemetryRecord(
        model="test-m",
        input_tokens=100,
        output_tokens=20,
        latency_ms=500.0,
        timestamp="t1",
        retrieved_chunks=3,
        rerank_latency_ms=45.5,
        context_tokens=1200,
    )
    r2 = TelemetryRecord(
        model="test-m",
        input_tokens=150,
        output_tokens=30,
        latency_ms=600.0,
        timestamp="t2",
        retrieved_chunks=2,
        rerank_latency_ms=30.2,
        context_tokens=800,
    )
    merged = merge_telemetry([r1, r2])

    assert merged.retrieved_chunks == 5
    assert merged.rerank_latency_ms == 75.7
    assert merged.context_tokens == 2000
    assert merged.timestamp == "t2"


def test_merge_telemetry_requires_input():
    with pytest.raises(ValueError, match="at least one"):
        merge_telemetry([])
