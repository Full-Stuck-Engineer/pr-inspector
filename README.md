# pr-inspector

Automated, lightweight, and observable AI-powered PR review CLI tool.

## Setup & Installation

This project uses [uv](https://github.com/astral-sh/uv) for fast, reproducible dependency and environment management.

### Prerequisites
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`)

### Install Dependencies
```bash
uv sync
```

### Running the CLI
```bash
# Via uv
uv run pr-inspector --help
uv run pr-inspector --version
uv run pr-inspector hello
```

### Development
```bash
# Run tests
uv run pytest

# Lint and format checks
uv run ruff check .
uv run ruff format --check .
```
