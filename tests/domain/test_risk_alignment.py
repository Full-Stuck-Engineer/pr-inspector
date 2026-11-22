"""Tests for risk_level consistency with the issues it aggregates (issue #10).

``risk_level`` drives the ``--fail-on`` CI exit-code contract. The LLM sets it
independently of the issues it reports, so a model that under-reports its own
severity could let a critical finding pass CI. The validator must correct the
risk level upward to match the highest issue severity.
"""

import pytest
from pydantic import ValidationError

from pr_inspector.domain.entities import PRReviewResult, ReviewIssue, RiskLevel


def _issue(severity: RiskLevel, path: str = "src/db.py") -> ReviewIssue:
    return ReviewIssue(
        file_path=path,
        line_number=42,
        severity=severity,
        title="f-string interpolated into cursor.execute()",
        description="User input reaches the query string unparameterised.",
    )


class TestRiskLevelAlignment:
    def test_critical_issue_under_low_risk_is_corrected(self):
        """The reported bug: a CRITICAL issue must not stay under LOW."""
        result = PRReviewResult(
            summary="looks fine",
            risk_level=RiskLevel.LOW,
            issues=[_issue(RiskLevel.CRITICAL)],
        )
        assert result.risk_level is RiskLevel.CRITICAL

    def test_risk_level_matching_issues_is_unchanged(self):
        result = PRReviewResult(
            summary="one high issue",
            risk_level=RiskLevel.HIGH,
            issues=[_issue(RiskLevel.HIGH)],
        )
        assert result.risk_level is RiskLevel.HIGH

    def test_no_issues_leaves_risk_level_alone(self):
        result = PRReviewResult(summary="clean diff", risk_level=RiskLevel.LOW, issues=[])
        assert result.risk_level is RiskLevel.LOW

    def test_higher_risk_than_issues_is_not_downgraded(self):
        """Over-reporting is the fail-safe direction and must be preserved."""
        result = PRReviewResult(
            summary="cautious",
            risk_level=RiskLevel.CRITICAL,
            issues=[_issue(RiskLevel.MEDIUM)],
        )
        assert result.risk_level is RiskLevel.CRITICAL

    def test_highest_of_several_issues_wins(self):
        result = PRReviewResult(
            summary="mixed severities",
            risk_level=RiskLevel.LOW,
            issues=[
                _issue(RiskLevel.LOW, "a.py"),
                _issue(RiskLevel.HIGH, "b.py"),
                _issue(RiskLevel.MEDIUM, "c.py"),
            ],
        )
        assert result.risk_level is RiskLevel.HIGH

    @pytest.mark.parametrize(
        "reported,expected",
        [
            (RiskLevel.LOW, RiskLevel.CRITICAL),
            (RiskLevel.MEDIUM, RiskLevel.CRITICAL),
            (RiskLevel.HIGH, RiskLevel.CRITICAL),
            (RiskLevel.CRITICAL, RiskLevel.CRITICAL),
        ],
    )
    def test_correction_is_monotonic(self, reported, expected):
        result = PRReviewResult(
            summary="s",
            risk_level=reported,
            issues=[_issue(RiskLevel.CRITICAL)],
        )
        assert result.risk_level is expected

    def test_serialized_output_reflects_correction(self):
        """The corrected value must survive model_dump, so CI sees it."""
        result = PRReviewResult(
            summary="s",
            risk_level=RiskLevel.LOW,
            issues=[_issue(RiskLevel.CRITICAL)],
        )
        assert result.model_dump()["risk_level"] == "CRITICAL"

    def test_invalid_risk_level_still_rejected(self):
        with pytest.raises(ValidationError):
            PRReviewResult(summary="s", risk_level="BANANA", issues=[])
