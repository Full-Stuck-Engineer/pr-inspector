"""Command line interface for pr-inspector."""

import typer
from rich.console import Console

from pr_inspector import __version__

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


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Automated PR review CLI tool."""
    pass


@app.command()
def hello() -> None:
    """Smoke test command to verify CLI environment."""
    console.print("[bold green]pr-inspector[/bold green] is ready! :rocket:")


if __name__ == "__main__":
    app()
