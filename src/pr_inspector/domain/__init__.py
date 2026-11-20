"""Domain layer containing pure business entities, exceptions, and protocols."""

from pr_inspector.domain.entities import (
    DiffHunk,
    DiffLine,
    FileDiff,
    PRReviewResult,
    ReviewIssue,
    RiskLevel,
    TelemetryRecord,
)
from pr_inspector.domain.exceptions import (
    DiffExtractionError,
    PRInspectorError,
    ReviewExecutionError,
)
from pr_inspector.domain.protocols import DiffProvider, LLMReviewer, TelemetrySink

__all__ = [
    "DiffExtractionError",
    "DiffHunk",
    "DiffLine",
    "DiffProvider",
    "FileDiff",
    "LLMReviewer",
    "PRInspectorError",
    "PRReviewResult",
    "ReviewExecutionError",
    "ReviewIssue",
    "RiskLevel",
    "TelemetryRecord",
    "TelemetrySink",
]
