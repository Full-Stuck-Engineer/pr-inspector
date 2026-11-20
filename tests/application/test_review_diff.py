"""Unit tests for ReviewDiffUseCase using in-memory fakes."""

from pr_inspector.application.use_cases.review_diff import ReviewDiffUseCase
from pr_inspector.domain.entities import (
    FileDiff,
    PRReviewResult,
    ReviewIssue,
    RiskLevel,
    TelemetryRecord,
)


class FakeDiffProvider:
    def __init__(self, diffs: list[FileDiff]) -> None:
        self.diffs = diffs
        self.last_target_ref: str | None = None
        self.last_staged: bool = False

    def get_diff(self, target_ref: str | None = None, staged: bool = False) -> list[FileDiff]:
        self.last_target_ref = target_ref
        self.last_staged = staged
        return self.diffs


class FakeLLMReviewer:
    def __init__(self, result: PRReviewResult, telemetry: TelemetryRecord) -> None:
        self.result = result
        self.telemetry = telemetry
        self.called_with_diffs: list[FileDiff] | None = None

    def review(self, diffs: list[FileDiff]) -> tuple[PRReviewResult, TelemetryRecord]:
        self.called_with_diffs = diffs
        return self.result, self.telemetry


class FakeTelemetrySink:
    def __init__(self) -> None:
        self.records: list[TelemetryRecord] = []

    def record(self, telemetry: TelemetryRecord) -> None:
        self.records.append(telemetry)


def test_review_diff_use_case_success():
    expected_result = PRReviewResult(
        summary="Found 1 high severity vulnerability",
        risk_level=RiskLevel.HIGH,
        issues=[
            ReviewIssue(
                file_path="src/auth.py",
                line_number=25,
                severity=RiskLevel.HIGH,
                title="Hardcoded API secret",
                description="Raw secret found in source code",
            )
        ],
    )
    expected_telemetry = TelemetryRecord(
        model="qwen2.5-coder:7b",
        input_tokens=150,
        output_tokens=60,
        latency_ms=450.0,
        timestamp="2026-11-20T23:00:00Z",
    )
    diff_provider = FakeDiffProvider([FileDiff(file_path="src/auth.py")])
    reviewer = FakeLLMReviewer(expected_result, expected_telemetry)
    telemetry_sink = FakeTelemetrySink()

    use_case = ReviewDiffUseCase(
        diff_provider=diff_provider,
        reviewer=reviewer,
        telemetry_sink=telemetry_sink,
    )

    result, telemetry = use_case.execute(target_ref="main", staged=False)

    assert result == expected_result
    assert telemetry == expected_telemetry
    assert diff_provider.last_target_ref == "main"
    assert len(telemetry_sink.records) == 1
    assert reviewer.called_with_diffs is not None


def test_review_diff_use_case_empty_diff_bypass():
    diff_provider = FakeDiffProvider([])
    reviewer = FakeLLMReviewer(
        PRReviewResult(summary="Should not be called", risk_level=RiskLevel.LOW),
        TelemetryRecord(
            model="dummy",
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            timestamp="",
        ),
    )
    telemetry_sink = FakeTelemetrySink()

    use_case = ReviewDiffUseCase(
        diff_provider=diff_provider,
        reviewer=reviewer,
        telemetry_sink=telemetry_sink,
    )

    result, telemetry = use_case.execute()

    # Bypassed LLM
    assert result.risk_level == RiskLevel.LOW
    assert len(result.issues) == 0
    assert "No reviewable code changes" in result.summary
    assert telemetry is None
    assert reviewer.called_with_diffs is None
    assert len(telemetry_sink.records) == 0
