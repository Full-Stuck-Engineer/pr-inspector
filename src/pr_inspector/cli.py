"""Command line interface for pr-inspector."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from pr_inspector import __version__
from pr_inspector.application.use_cases.review_diff import ReviewDiffUseCase
from pr_inspector.domain.entities import RISK_ORDER, RiskLevel
from pr_inspector.domain.exceptions import PRInspectorError
from pr_inspector.infrastructure.git.diff_extractor import GitCliDiffProvider
from pr_inspector.infrastructure.llm.openai_client import OpenAICompatibleLLMReviewer
from pr_inspector.infrastructure.telemetry.file_sink import FileTelemetrySink
from pr_inspector.interface.formatters import export_report, render_review_dashboard

app = typer.Typer(
    name="pr-inspector",
    help="AI-powered PR review CLI tool.",
    add_completion=False,
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold cyan]pr-inspector[/bold cyan] version [green]{__version__}[/green]")
        raise typer.Exit()


def create_review_use_case(
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> ReviewDiffUseCase:
    """Composition root: wire infrastructure adapters to application use case."""
    diff_provider = GitCliDiffProvider()
    reviewer = OpenAICompatibleLLMReviewer(
        base_url=base_url,
        api_key=api_key,
        model=model,
    )
    telemetry_sink = FileTelemetrySink()
    return ReviewDiffUseCase(
        diff_provider=diff_provider,
        reviewer=reviewer,
        telemetry_sink=telemetry_sink,
    )


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Automated PR review CLI tool."""
    pass


@app.command()
def hello() -> None:
    """Smoke test command to verify CLI environment."""
    console.print("[bold green]pr-inspector[/bold green] is ready! :rocket:")


@app.command(name="review")
def review(
    target_ref: Annotated[
        str | None,
        typer.Option(
            "--target-ref",
            "-r",
            help="Git reference/branch/commit to diff against (e.g. main, HEAD~1).",
        ),
    ] = None,
    staged: Annotated[
        bool,
        typer.Option(
            "--staged",
            "-s",
            help="Review only staged git changes.",
        ),
    ] = False,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help="LLM model name (defaults to qwen2.5-coder:7b or gpt-4o-mini).",
        ),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            "-u",
            help="Custom OpenAI-compatible API base URL (defaults to http://localhost:11434/v1).",
        ),
    ] = None,
    api_key: Annotated[
        str | None,
        typer.Option(
            "--api-key",
            "-k",
            help="API key for cloud providers (or set OPENAI_API_KEY).",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output raw structured JSON to stdout instead of terminal dashboard.",
        ),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Optional path to write review report (.json or .md).",
        ),
    ] = None,
    fail_on: Annotated[
        RiskLevel,
        typer.Option(
            "--fail-on",
            help="Failure threshold for exit code 1 (LOW, MEDIUM, HIGH, CRITICAL).",
        ),
    ] = RiskLevel.HIGH,
) -> None:
    """Review git diff and report potential bugs, security issues, and risk."""
    try:
        use_case = create_review_use_case(base_url=base_url, api_key=api_key, model=model)
        result, telemetry = use_case.execute(target_ref=target_ref, staged=staged)

        if json_output:
            # Raw text, not console.print: Rich would wrap long lines inside JSON strings
            # and strip markup-like tokens, so the output would no longer parse.
            typer.echo(result.model_dump_json(indent=2))
        else:
            render_review_dashboard(console, result, telemetry)

        if output:
            export_report(output, result, telemetry, as_json=json_output)
            if not json_output:
                console.print(f"[dim]Report saved to [bold]{output}[/bold][/dim]\n")

        # Configurable failure threshold
        if RISK_ORDER[result.risk_level] >= RISK_ORDER[fail_on]:
            raise typer.Exit(code=1)

    except PRInspectorError as exc:
        console.print(f"[bold red]Review Error:[/bold red] {exc}", style="red")
        raise typer.Exit(code=2) from exc


if __name__ == "__main__":
    app()
