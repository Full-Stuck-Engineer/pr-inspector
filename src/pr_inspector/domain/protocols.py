"""Domain ports (Protocols) defining external boundaries."""

from typing import Protocol, runtime_checkable

from pr_inspector.domain.entities import FileDiff, PRReviewResult, TelemetryRecord


@runtime_checkable
class DiffProvider(Protocol):
    """Port for extracting and parsing git diffs."""

    def get_diff(self, target_ref: str | None = None, staged: bool = False) -> list[FileDiff]:
        """Extract and parse git diff, returning structured file diffs."""
        ...


@runtime_checkable
class LLMReviewer(Protocol):
    """Port for performing automated PR review using an LLM."""

    def review(self, diffs: list[FileDiff]) -> tuple[PRReviewResult, TelemetryRecord]:
        """Analyze diffs and produce structured review and telemetry."""
        ...


@runtime_checkable
class TelemetrySink(Protocol):
    """Port for persisting or publishing telemetry records."""

    def record(self, telemetry: TelemetryRecord) -> None:
        """Record telemetry data."""
        ...
