"""Terminal rendering and report export formatters."""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pr_inspector.domain.entities import CodeChunk, PRReviewResult, RiskLevel, TelemetryRecord

RISK_STYLE_MAP: dict[RiskLevel, str] = {
    RiskLevel.LOW: "bold green",
    RiskLevel.MEDIUM: "bold yellow",
    RiskLevel.HIGH: "bold red",
    RiskLevel.CRITICAL: "bold white on red",
}


def render_review_dashboard(
    console: Console,
    result: PRReviewResult,
    telemetry: TelemetryRecord | None = None,
    retrieved_chunks: list[CodeChunk] | None = None,
) -> None:
    """Render a full Rich visual dashboard in the terminal."""
    risk_style = RISK_STYLE_MAP.get(result.risk_level, "bold cyan")
    banner_text = f"Overall Risk Level: [{risk_style}]{result.risk_level}[/{risk_style}]"
    console.print(Panel(banner_text, title="pr-inspector Assessment", expand=False))

    console.print(Panel(result.summary, title="Summary", border_style="blue"))

    if result.cited_files:
        cited_list = ", ".join(f"[bold cyan]{f}[/bold cyan]" for f in result.cited_files)
        console.print(
            Panel(
                cited_list,
                title=f"Referenced Codebase Files ({len(result.cited_files)})",
                border_style="cyan",
            )
        )

    if retrieved_chunks:
        chunk_table = Table(
            title=f"Retrieved Codebase Context ({len(retrieved_chunks)} chunks)", box=None
        )
        chunk_table.add_column("File", style="cyan")
        chunk_table.add_column("Lines", style="yellow")
        chunk_table.add_column("Type / Symbol", style="magenta")
        for chunk in retrieved_chunks:
            symbol_part = f"`{chunk.symbol_name}`" if chunk.symbol_name else chunk.chunk_type.value
            chunk_table.add_row(
                chunk.file_path, f"{chunk.start_line}-{chunk.end_line}", symbol_part
            )
        console.print(chunk_table)

    if not result.issues:
        console.print("[bold green]✔ No issues or vulnerabilities detected![/bold green]\n")
    else:
        issue_count = len(result.issues)
        console.print(f"\n[bold underline]Identified Issues ({issue_count}):[/bold underline]\n")
        for i, issue in enumerate(result.issues, start=1):
            sev_style = RISK_STYLE_MAP.get(issue.severity, "bold")
            header = (
                f"[bold cyan]{issue.file_path}[/bold cyan]:"
                f"[bold yellow]{issue.line_number}[/bold yellow] "
                f"[{sev_style}][{issue.severity}][/{sev_style}] {issue.title}"
            )
            content = [issue.description]
            if issue.suggested_fix:
                content.append("\n[bold]Suggested Remediation:[/bold]")
                content.append(issue.suggested_fix)
            if issue.cited_files:
                content.append(
                    f"\n[bold dim]Cited References:[/bold dim] {', '.join(issue.cited_files)}"
                )

            panel = Panel("\n".join(content), title=f"Issue #{i} - {header}", border_style="yellow")
            console.print(panel)

    if telemetry is not None:
        table = Table(title="Telemetry & Performance Metrics", box=None)
        table.add_column("Model", style="cyan")
        table.add_column("Input Tokens", style="magenta")
        table.add_column("Output Tokens", style="magenta")
        table.add_column("Latency (ms)", style="green")
        if telemetry.retrieved_chunks > 0:
            table.add_column("RAG Chunks", style="blue")
            table.add_column("Context Tokens", style="blue")
            table.add_column("Rerank (ms)", style="green")
        table.add_column("Timestamp", style="dim")

        row = [
            telemetry.model,
            str(telemetry.input_tokens),
            str(telemetry.output_tokens),
            f"{telemetry.latency_ms:.2f} ms",
        ]
        if telemetry.retrieved_chunks > 0:
            row.extend(
                [
                    str(telemetry.retrieved_chunks),
                    str(telemetry.context_tokens),
                    f"{telemetry.rerank_latency_ms:.2f} ms",
                ]
            )
        row.append(telemetry.timestamp)
        table.add_row(*row)
        console.print(table)


def format_markdown_report(result: PRReviewResult, telemetry: TelemetryRecord | None) -> str:
    """Format review and telemetry into clean GitHub-flavored Markdown."""
    lines: list[str] = [
        "# Automated PR Review Report",
        "",
        f"**Risk Level:** `{result.risk_level}`",
        "",
        "## Summary",
        result.summary,
        "",
    ]

    if result.cited_files:
        lines.extend(
            [
                "## Referenced Codebase Files",
                *[f"- `{f}`" for f in result.cited_files],
                "",
            ]
        )

    lines.append("## Issues")

    if not result.issues:
        lines.append("*No issues or vulnerabilities detected.*")
    else:
        for i, issue in enumerate(result.issues, start=1):
            issue_lines = [
                f"### #{i} [{issue.severity}] {issue.title}",
                f"- **File:** `{issue.file_path}`",
                f"- **Line:** `{issue.line_number}`",
            ]
            if issue.cited_files:
                cited_str = ", ".join(f"`{f}`" for f in issue.cited_files)
                issue_lines.append(f"- **Cited Files:** {cited_str}")
            issue_lines.extend(["", issue.description])

            if issue.suggested_fix:
                issue_lines.extend(
                    [
                        "",
                        "**Suggested Fix:**",
                        "```",
                        issue.suggested_fix,
                        "```",
                    ]
                )
            issue_lines.append("")
            lines.extend(issue_lines)

    if telemetry:
        telemetry_rows = [
            "",
            "## Telemetry",
            "| Metric | Value |",
            "| :--- | :--- |",
            f"| **Model** | `{telemetry.model}` |",
            f"| **Input Tokens** | `{telemetry.input_tokens}` |",
            f"| **Output Tokens** | `{telemetry.output_tokens}` |",
            f"| **Latency** | `{telemetry.latency_ms} ms` |",
        ]
        if telemetry.retrieved_chunks > 0:
            telemetry_rows.extend(
                [
                    f"| **Retrieved Chunks** | `{telemetry.retrieved_chunks}` |",
                    f"| **Context Tokens** | `{telemetry.context_tokens}` |",
                    f"| **Rerank Latency** | `{telemetry.rerank_latency_ms} ms` |",
                ]
            )
        telemetry_rows.append(f"| **Timestamp** | `{telemetry.timestamp}` |")
        lines.extend(telemetry_rows)

    return "\n".join(lines)


def export_report(
    path: Path,
    result: PRReviewResult,
    telemetry: TelemetryRecord | None,
    as_json: bool = False,
) -> None:
    """Save review report to file with extension-aware formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".json" or as_json:
        content = result.model_dump_json(indent=2)
    elif path.suffix == ".md":
        content = format_markdown_report(result, telemetry)
    else:
        content = (
            f"Risk Level: {result.risk_level}\n"
            f"Summary: {result.summary}\n"
            f"Issues: {len(result.issues)}\n"
        )
    path.write_text(content, encoding="utf-8")
