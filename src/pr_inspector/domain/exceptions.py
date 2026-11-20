"""Domain exceptions for pr-inspector."""


class PRInspectorError(Exception):
    """Base exception for all pr-inspector domain errors."""


class DiffExtractionError(PRInspectorError):
    """Raised when git diff extraction or parsing fails."""


class ReviewExecutionError(PRInspectorError):
    """Raised when review analysis execution fails."""
