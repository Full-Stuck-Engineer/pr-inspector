"""Tests for pr-inspector CLI commands and formatting."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from pr_inspector import __version__
from pr_inspector.cli import app
from pr_inspector.domain.entities import (
    PRReviewResult,
    ReviewIssue,
    RiskLevel,
    TelemetryRecord,
)
from pr_inspector.domain.exceptions import DiffExtractionError

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "AI-powered PR review CLI tool" in result.stdout


def test_cli_hello():
    result = runner.invoke(app, ["hello"])
    assert result.exit_code == 0
    assert "pr-inspector is ready" in result.stdout


def test_cli_review_help():
    result = runner.invoke(app, ["review", "--help"])
    assert result.exit_code == 0
    assert "--target-ref" in result.stdout
    assert "--model" in result.stdout
    assert "--json" in result.stdout
    assert "--output" in result.stdout
    assert "--fail-on" in result.stdout


def test_cli_review_json_output():
    mock_result = PRReviewResult(
        summary="No issues found",
        risk_level=RiskLevel.LOW,
        issues=[],
    )
    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = (mock_result, None)

    with patch("pr_inspector.cli.create_review_use_case", return_value=mock_use_case):
        result = runner.invoke(app, ["review", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["risk_level"] == "LOW"
        assert data["summary"] == "No issues found"


def test_cli_review_rich_dashboard_output():
    mock_result = PRReviewResult(
        summary="Found 1 critical SQL injection",
        risk_level=RiskLevel.HIGH,
        issues=[
            ReviewIssue(
                file_path="src/db.py",
                line_number=45,
                severity=RiskLevel.HIGH,
                title="SQL Injection",
                description="Unsanitized query concatenation",
                suggested_fix="cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
            )
        ],
    )
    mock_telemetry = TelemetryRecord(
        model="gpt-4o-mini",
        input_tokens=200,
        output_tokens=80,
        latency_ms=350.2,
        timestamp="2026-11-22T00:00:00Z",
    )
    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = (mock_result, mock_telemetry)

    with patch("pr_inspector.cli.create_review_use_case", return_value=mock_use_case):
        # Default fail-on is HIGH, so this exits with code 1
        result = runner.invoke(app, ["review"])
        assert result.exit_code == 1
        assert "pr-inspector Assessment" in result.stdout
        assert "SQL Injection" in result.stdout
        assert "src/db.py" in result.stdout
        assert "Telemetry & Performance Metrics" in result.stdout


def test_cli_review_fail_on_thresholds():
    mock_result = PRReviewResult(
        summary="Medium risk items",
        risk_level=RiskLevel.MEDIUM,
        issues=[],
    )
    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = (mock_result, None)

    with patch("pr_inspector.cli.create_review_use_case", return_value=mock_use_case):
        # MEDIUM < HIGH: should exit 0
        res_pass = runner.invoke(app, ["review", "--fail-on", "HIGH"])
        assert res_pass.exit_code == 0

        # MEDIUM >= MEDIUM: should exit 1
        res_fail = runner.invoke(app, ["review", "--fail-on", "MEDIUM"])
        assert res_fail.exit_code == 1


def test_cli_review_output_file_export(tmp_path: Path):
    mock_result = PRReviewResult(
        summary="Export test",
        risk_level=RiskLevel.LOW,
        issues=[],
    )
    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = (mock_result, None)

    json_file = tmp_path / "report.json"
    md_file = tmp_path / "report.md"

    with patch("pr_inspector.cli.create_review_use_case", return_value=mock_use_case):
        runner.invoke(app, ["review", "--output", str(json_file)])
        assert json_file.exists()
        json_data = json.loads(json_file.read_text(encoding="utf-8"))
        assert json_data["risk_level"] == "LOW"

        runner.invoke(app, ["review", "--output", str(md_file)])
        assert md_file.exists()
        md_text = md_file.read_text(encoding="utf-8")
        assert "# Automated PR Review Report" in md_text


def test_cli_review_error_exit_code():
    mock_use_case = MagicMock()
    mock_use_case.execute.side_effect = DiffExtractionError("fatal: not a git repo")

    with patch("pr_inspector.cli.create_review_use_case", return_value=mock_use_case):
        result = runner.invoke(app, ["review"])
        assert result.exit_code == 2
        assert "Review Error" in result.stdout


def test_cli_review_json_output_is_lossless_for_long_and_markup_like_text():
    # Longer than a terminal line, and containing tokens that look like Rich markup.
    summary = (
        "Reads config[0] and arr[i], then prints [red]colors[/red]. "
        + "This sentence makes the summary longer than a terminal line. " * 6
    ).strip()
    suggested_fix = "Use [bold]parameterized queries[/bold] instead of string formatting. " * 3
    mock_result = PRReviewResult(
        summary=summary,
        risk_level=RiskLevel.HIGH,
        issues=[
            ReviewIssue(
                file_path="src/db.py",
                line_number=45,
                severity=RiskLevel.HIGH,
                title="SQL Injection",
                description="Unsanitized query concatenation. " * 5,
                suggested_fix=suggested_fix,
            )
        ],
    )
    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = (mock_result, None)

    with patch("pr_inspector.cli.create_review_use_case", return_value=mock_use_case):
        result = runner.invoke(app, ["review", "--json", "--fail-on", "CRITICAL"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["summary"] == summary
    assert data["issues"][0]["suggested_fix"] == suggested_fix
    assert PRReviewResult.model_validate(data) == mock_result
