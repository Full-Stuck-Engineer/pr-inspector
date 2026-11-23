# pr-inspector

Automated, lightweight, and observable AI-powered PR review CLI tool.

## Features

- **Pydantic Structured Outputs:** Schema guarantees (`summary`, `risk_level`, `issues[]`) with zero framework bloat.
- **Rich Visual Dashboard:** Terminal dashboard displaying risk badges, line-by-line findings, and actionable recommendations.
- **CI/CD Quality Gate:** Strict exit-code contracts via `--fail-on` thresholding (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- **Production Resilience:** Automatic exponential backoff retries with jitter for rate limits (429) and server errors (5xx), plus token ceiling truncation detection.
- **Observable Telemetry:** Every review records model name, token usage, and latency.

## Setup & Installation

This project uses [uv](https://github.com/astral-sh/uv) for fast, reproducible dependency and environment management.

### Prerequisites
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`)

### Install Dependencies
```bash
uv sync
```

## Configuration

`pr-inspector` uses an OpenAI-compatible interface and works with cloud LLM providers or local offline models.

### Cloud Providers (OpenAI, Gemini)
```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"
```

### Local Models (Ollama / vLLM)
Run private, offline reviews with zero API costs:
```bash
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_API_KEY="ollama"
export OPENAI_MODEL="qwen2.5-coder:7b"
```

## Usage

### Reviewing Diffs

```bash
# Review unstaged & staged changes in the current working directory
uv run pr-inspector review

# Review changes against a base branch
uv run pr-inspector review --base main

# Review a specific commit
uv run pr-inspector review --commit HEAD~1
```

### Exporting Reports
Export structured reviews to JSON or formatted Markdown:
```bash
uv run pr-inspector review --output review-report.json
uv run pr-inspector review --output review-report.md
```

### Large Diffs (`--max-input-tokens`)
A large diff is split into batches, each batch is reviewed in its own request, and the results are merged into one report. Whole files are kept together where possible; a file bigger than the ceiling is split between hunks, never inside one, so reported line numbers stay exact.
```bash
# Default ceiling is 8000 tokens of diff per request
uv run pr-inspector review --max-input-tokens 6000

# Or set it once for the shell
export PR_INSPECTOR_MAX_INPUT_TOKENS=6000
```
A single hunk larger than the ceiling, typically a very large new file, is still sent whole. If any batch fails, the whole review fails: a partially reviewed diff must never pass the `--fail-on` gate.

Ollama defaults to a 4k-token context window on machines with 16 GB of memory or less. Either start the server with a larger window (`OLLAMA_CONTEXT_LENGTH=16384 ollama serve`) or lower `--max-input-tokens` to fit the window you have.

### CI/CD Gating (`--fail-on`)
Block broken pull requests in CI pipelines by exiting with non-zero code on risk thresholds:
```bash
# Fails the CI pipeline if review identifies HIGH or CRITICAL risk
uv run pr-inspector review --base origin/main --fail-on HIGH
```

## Development

```bash
# Run tests
uv run pytest

# Lint and format checks
uv run ruff check .
uv run ruff format --check .
```

## Authors

- **Anthony Febrian** - [@anthonyfebrian](https://github.com/anthonyfebrian)
- **Nadiv** - [@nadiv](https://github.com/nadiv)
