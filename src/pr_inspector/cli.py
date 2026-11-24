"""Command line interface for pr-inspector."""

import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from pr_inspector import __version__
from pr_inspector.application.services.context_retriever import ReviewContextRetriever
from pr_inspector.application.services.hybrid_search import HybridSearchRetriever
from pr_inspector.application.use_cases.index_repository import IndexRepositoryUseCase
from pr_inspector.application.use_cases.review_diff import (
    DEFAULT_MAX_INPUT_TOKENS,
    ReviewDiffUseCase,
)
from pr_inspector.domain.entities import RISK_ORDER, RiskLevel
from pr_inspector.domain.exceptions import PRInspectorError
from pr_inspector.infrastructure.git.diff_extractor import GitCliDiffProvider
from pr_inspector.infrastructure.indexer.chunk_store import JsonFileChunkStore
from pr_inspector.infrastructure.indexer.composite_chunker import CompositeChunker
from pr_inspector.infrastructure.indexer.file_scanner import IncrementalFileScanner
from pr_inspector.infrastructure.llm.openai_client import OpenAICompatibleLLMReviewer
from pr_inspector.infrastructure.search.bm25 import BM25KeywordIndex
from pr_inspector.infrastructure.search.embedder import (
    DeterministicTestEmbedder,
    OpenAICompatibleEmbedder,
)
from pr_inspector.infrastructure.search.reranker import CrossEncoderReranker
from pr_inspector.infrastructure.search.vector_store import InMemoryVectorStore
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


def create_index_use_case(repo_root: Path | str = ".") -> IndexRepositoryUseCase:
    """Composition root for repository indexing use case."""
    root = Path(repo_root).resolve()
    scanner = IncrementalFileScanner(root)
    chunker = CompositeChunker()
    chunk_store = JsonFileChunkStore(root / ".pr-inspector" / "chunks.json")
    return IndexRepositoryUseCase(
        repo_root=root,
        scanner=scanner,
        chunker=chunker,
        chunk_store=chunk_store,
    )


def create_review_use_case(
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
    enable_rag: bool = True,
    repo_root: Path | str = ".",
) -> ReviewDiffUseCase:
    """Composition root: wire infrastructure adapters to application use case."""
    diff_provider = GitCliDiffProvider()
    reviewer = OpenAICompatibleLLMReviewer(
        base_url=base_url,
        api_key=api_key,
        model=model,
    )
    telemetry_sink = FileTelemetrySink()

    context_retriever = None
    if enable_rag:
        root = Path(repo_root).resolve()
        chunk_store = JsonFileChunkStore(root / ".pr-inspector" / "chunks.json")
        chunks = chunk_store.load_chunks()

        # If index does not exist, build index on the fly
        if not chunks and not (root / ".pr-inspector" / "chunks.json").is_file():
            index_use_case = create_index_use_case(repo_root=root)
            index_use_case.execute()
            chunks = chunk_store.load_chunks()

        if chunks:
            keyword_index = BM25KeywordIndex()
            keyword_index.upsert(chunks)

            embedder = (
                DeterministicTestEmbedder()
                if os.getenv("PR_INSPECTOR_OFFLINE_TEST")
                else OpenAICompatibleEmbedder(base_url=base_url, api_key=api_key)
            )
            vector_store = InMemoryVectorStore(embedder=embedder)
            vector_store.upsert(chunks)

            reranker = CrossEncoderReranker()
            hybrid_retriever = HybridSearchRetriever(
                keyword_index=keyword_index,
                vector_store=vector_store,
                embedder=embedder,
                reranker=reranker,
            )
            context_retriever = ReviewContextRetriever(hybrid_retriever=hybrid_retriever)

    return ReviewDiffUseCase(
        diff_provider=diff_provider,
        reviewer=reviewer,
        telemetry_sink=telemetry_sink,
        context_retriever=context_retriever,
        max_input_tokens=max_input_tokens,
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


@app.command(name="index")
def index_command(
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force full reindexing of all files, ignoring existing manifest.",
        ),
    ] = False,
    clean: Annotated[
        bool,
        typer.Option(
            "--clean",
            "-c",
            help="Purge existing index cache before re-indexing.",
        ),
    ] = False,
    repo_path: Annotated[
        Path,
        typer.Option(
            "--repo-path",
            "-p",
            help="Repository root directory to scan and index.",
        ),
    ] = Path("."),
) -> None:
    """Build or incrementally update the repository code chunk index."""
    try:
        use_case = create_index_use_case(repo_root=repo_path)
        target_dir = repo_path.resolve()
        console.print(
            f"[bold blue]Indexing repository[/bold blue] at [bold cyan]{target_dir}[/bold cyan]..."
        )
        result = use_case.execute(force=force, clean=clean)

        table = Table(title="Codebase Indexing Summary", box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Files Scanned", str(result.total_files_scanned))
        table.add_row("Added Files", str(result.added_files))
        table.add_row("Modified Files", str(result.modified_files))
        table.add_row("Deleted Files", str(result.deleted_files))
        table.add_row("Unchanged Files", str(result.unchanged_files))
        table.add_row("Total Chunks Generated", str(result.total_chunks))
        table.add_row("Elapsed Time", f"{result.duration_ms:.2f} ms")

        console.print(table)
        console.print("[bold green]✔ Codebase index updated successfully![/bold green]\n")
    except PRInspectorError as exc:
        console.print(f"[bold red]Indexing Error:[/bold red] {exc}", style="red")
        raise typer.Exit(code=2) from exc


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
    rag: Annotated[
        bool,
        typer.Option(
            "--rag/--no-rag",
            help="Enable or disable codebase RAG context enrichment for the review.",
        ),
    ] = True,
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
    max_input_tokens: Annotated[
        int,
        typer.Option(
            "--max-input-tokens",
            envvar="PR_INSPECTOR_MAX_INPUT_TOKENS",
            min=1,
            help="Token ceiling per LLM request; larger diffs are split into batches.",
        ),
    ] = DEFAULT_MAX_INPUT_TOKENS,
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
        use_case = create_review_use_case(
            base_url=base_url,
            api_key=api_key,
            model=model,
            max_input_tokens=max_input_tokens,
            enable_rag=rag,
        )
        result, telemetry = use_case.execute(target_ref=target_ref, staged=staged)

        if json_output:
            # Raw text, not console.print: Rich would wrap long lines inside JSON strings
            # and strip markup-like tokens, so the output would no longer parse.
            typer.echo(result.model_dump_json(indent=2))
        else:
            retrieved_chunks = None
            if hasattr(use_case, "_context_retriever") and use_case._context_retriever is not None:
                chunks = getattr(use_case._context_retriever, "last_retrieved_chunks", None)
                if isinstance(chunks, list) and chunks:
                    retrieved_chunks = chunks
            render_review_dashboard(console, result, telemetry, retrieved_chunks=retrieved_chunks)

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
