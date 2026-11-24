"""Combining the per-batch outcomes of a chunked review into a single outcome."""

from collections.abc import Sequence

from pr_inspector.domain.entities import RISK_ORDER, PRReviewResult, TelemetryRecord


def merge_review_results(results: Sequence[PRReviewResult]) -> PRReviewResult:
    """Merge batch results: highest risk level, every issue, summaries joined in order."""
    if not results:
        raise ValueError("at least one review result is required")
    if len(results) == 1:
        return results[0]

    summary = " ".join(text for result in results if (text := result.summary.strip()))
    risk_level = max((result.risk_level for result in results), key=RISK_ORDER.__getitem__)
    issues = [issue for result in results for issue in result.issues]
    return PRReviewResult(summary=summary, risk_level=risk_level, issues=issues)


def merge_telemetry(records: Sequence[TelemetryRecord]) -> TelemetryRecord:
    """Merge batch telemetry into one record for the run.

    Batches run one after another, so token counts and latencies add up. The timestamp is
    the moment the last batch finished.
    """
    if not records:
        raise ValueError("at least one telemetry record is required")
    if len(records) == 1:
        return records[0]

    return TelemetryRecord(
        model=records[0].model,
        input_tokens=sum(record.input_tokens for record in records),
        output_tokens=sum(record.output_tokens for record in records),
        latency_ms=round(sum(record.latency_ms for record in records), 2),
        timestamp=records[-1].timestamp,
    )
