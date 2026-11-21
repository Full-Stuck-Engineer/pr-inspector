"""Review diff use case orchestrating extraction, analysis, and telemetry."""

from pr_inspector.domain.entities import PRReviewResult, RiskLevel, TelemetryRecord
from pr_inspector.domain.protocols import DiffProvider, LLMReviewer, TelemetrySink


class ReviewDiffUseCase:
    """Orchestrates pulling diffs, triggering LLM review, and recording telemetry."""

    def __init__(
        self,
        diff_provider: DiffProvider,
        reviewer: LLMReviewer,
        telemetry_sink: TelemetrySink | None = None,
    ) -> None:
        self._diff_provider = diff_provider
        self._reviewer = reviewer
        self._telemetry_sink = telemetry_sink

    def execute(
        self,
        target_ref: str | None = None,
        staged: bool = False,
    ) -> tuple[PRReviewResult, TelemetryRecord | None]:
        """Execute diff review workflow."""
        diffs = self._diff_provider.get_diff(target_ref=target_ref, staged=staged)

        # Empty diff optimization: bypass LLM call, save tokens and latency
        if not diffs:
            clean_result = PRReviewResult(
                summary="No reviewable code changes detected.",
                risk_level=RiskLevel.LOW,
                issues=[],
            )
            return clean_result, None

        review_result, telemetry = self._reviewer.review(diffs)

        if self._telemetry_sink is not None:
            self._telemetry_sink.record(telemetry)

        return review_result, telemetry
