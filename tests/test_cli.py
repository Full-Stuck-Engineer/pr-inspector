from typer.testing import CliRunner

from pr_inspector import __version__
from pr_inspector.cli import app

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
