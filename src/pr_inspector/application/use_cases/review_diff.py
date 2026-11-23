"""Review diff use case orchestrating extraction, analysis, and telemetry."""

from pr_inspector.domain.chunking import split_into_batches
from pr_inspector.domain.entities import FileDiff, PRReviewResult, RiskLevel, TelemetryRecord
from pr_inspector.domain.exceptions import ReviewExecutionError
from pr_inspector.domain.protocols import DiffProvider, LLMReviewer, TelemetrySink
from pr_inspector.domain.review_merging import merge_review_results, merge_telemetry

# Ceiling for the diff text of one LLM request. It excludes the system prompt and the model's
# output, leaving headroom inside a 16k-token context window, a common size for local models.
DEFAULT_MAX_INPUT_TOKENS = 8000


class ReviewDiffUseCase:
    """Orchestrates pulling diffs, triggering LLM review, and recording telemetry.

    A diff that fits the token ceiling costs exactly one reviewer call. A larger one is
    reviewed in several calls, split by file and, inside an oversized file, by hunk. The
    batch outcomes are merged into one result and one telemetry record for the run.

    If any batch fails, the whole review fails. Returning a result for only part of the
    diff would let unreviewed code pass a ``--fail-on`` gate.
    """

    def __init__(
        self,
        diff_provider: DiffProvider,
        reviewer: LLMReviewer,
        telemetry_sink: TelemetrySink | None = None,
        max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
    ) -> None:
        if max_input_tokens < 1:
            raise ValueError("max_input_tokens must be at least 1")
        self._diff_provider = diff_provider
        self._reviewer = reviewer
        self._telemetry_sink = telemetry_sink
        self._max_input_tokens = max_input_tokens

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

        review_result, telemetry = self._review_in_batches(diffs)

        if self._telemetry_sink is not None:
            self._telemetry_sink.record(telemetry)

        return review_result, telemetry

    def _review_in_batches(self, diffs: list[FileDiff]) -> tuple[PRReviewResult, TelemetryRecord]:
        # Files without hunks cannot be split; hand the diff to the reviewer untouched.
        batches = split_into_batches(diffs, self._max_input_tokens) or [diffs]

        results: list[PRReviewResult] = []
        records: list[TelemetryRecord] = []
        for position, batch in enumerate(batches, start=1):
            try:
                result, telemetry = self._reviewer.review(batch)
            except ReviewExecutionError as exc:
                if len(batches) == 1:
                    raise
                raise ReviewExecutionError(
                    f"Review failed on batch {position} of {len(batches)}: {exc}"
                ) from exc
            results.append(result)
            records.append(telemetry)

        return merge_review_results(results), merge_telemetry(records)
