---
name: clean-architecture
description: Generic Python Clean Architecture guide. Use when designing, organizing, or refactoring Python applications into Domain, Application, Infrastructure, and Presentation layers with strict dependency rules and composition roots.
---

# Generic Python Clean Architecture Guide

This skill provides a practical, generic reference for structuring Python applications using Clean Architecture principles. It applies equally to CLI tools, background workers, microservices, and web APIs.

---

## 1. Core Architecture Topology

Clean Architecture organizes code into concentric layers where dependencies strictly point inward:

```
┌────────────────────────────────────────────────────────┐
│  Presentation / Interface                              │
│  (CLI commands, HTTP endpoints, Webhooks, CLI flags)   │
│   ┌──────────────────────────────────────────────────┐ │
│   │  Infrastructure                                  │ │
│   │  (External APIs, DBs, Git/OS subprocesses, SDKs) │ │
│   │   ┌────────────────────────────────────────────┐ │ │
│   │   │  Application                               │ │ │
│   │   │  (Use cases, orchestrators, workflow DTOs) │ │ │
│   │   │   ┌──────────────────────────────────────┐ │ │ │
│   │   │   │  Domain                              │ │ │ │
│   │   │   │  (Entities, Value Objects, Protocols)│ │ │ │
│   │   │   └──────────────────────────────────────┘ │ │ │
│   │   └────────────────────────────────────────────┘ │ │
│   └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

### Standard Directory Structure

```text
src/<package_name>/
├── domain/                  # Enterprise business rules & abstractions
│   ├── __init__.py
│   ├── entities.py          # Pure data models / value objects
│   ├── exceptions.py        # Domain-specific errors
│   └── protocols.py         # Port interfaces (typing.Protocol)
├── application/             # Application business rules
│   ├── __init__.py
│   ├── dtos.py              # Request / Response data transfer objects
│   └── use_cases/           # Individual use case interactors
│       ├── __init__.py
│       └── process_item.py
├── infrastructure/          # Adapters to external systems
│   ├── __init__.py
│   ├── git/                 # Git/OS subprocess adapters
│   ├── clients/             # HTTP / SDK adapters
│   └── storage/             # File system / database adapters
└── interface/               # Entry points & user interfaces
    ├── __init__.py
    └── cli/                 # Typer / Click commands & formatters
```

---

## 2. Layer Definitions & Implementation Patterns

### Layer 1: Domain (`domain/`)
The heart of the application. Contains business data models and the abstract contracts ("ports") required by business workflows.

* **Rules:**
  * Zero dependencies on outer layers or external frameworks (no Typer, requests, httpx, database drivers, or vendor SDKs).
  * Standard library and typing only (Pydantic is acceptable for immutable schema validation).
* **Key Components:**
  * **Entities / Value Objects:** Pure state with domain-level validation.
  * **Protocols:** Structural contracts (`typing.Protocol`) describing needed capabilities.
  * **Domain Exceptions:** High-level errors representing business rule failures.

```python
# domain/protocols.py
from typing import Protocol, runtime_checkable
from domain.entities import Item, ProcessingResult

@runtime_checkable
class ItemProvider(Protocol):
    """Port for fetching items from a data source."""
    def fetch_item(self, item_id: str) -> Item:
        ...

@runtime_checkable
class ResultPublisher(Protocol):
    """Port for publishing processing results."""
    def publish(self, result: ProcessingResult) -> None:
        ...
```

---

### Layer 2: Application (`application/`)
Orchestrates the flow of data to and from domain entities and directs domain protocols to achieve workflow objectives.

* **Rules:**
  * Depends **only** on the Domain layer.
  * Never imports from Infrastructure or Interface.
  * Contains **Use Cases** (also known as Interactors). Each use case should typically have a single public execution method (e.g., `execute()` or `run()`).
  * Accepts dependencies via constructor injection using domain protocols.

```python
# application/use_cases/process_item.py
from dataclasses import dataclass
from domain.entities import Item, ProcessingResult
from domain.protocols import ItemProvider, ResultPublisher
from domain.exceptions import ItemNotFoundError

@dataclass(frozen=True)
class ProcessItemCommand:
    item_id: str
    dry_run: bool = False

class ProcessItemUseCase:
    def __init__(self, provider: ItemProvider, publisher: ResultPublisher) -> None:
        self._provider = provider
        self._publisher = publisher

    def execute(self, command: ProcessItemCommand) -> ProcessingResult:
        item = self._provider.fetch_item(command.item_id)
        if not item:
            raise ItemNotFoundError(f"Item {command.item_id} does not exist.")

        result = item.process()
        if not command.dry_run:
            self._publisher.publish(result)
        return result
```

---

### Layer 3: Infrastructure (`infrastructure/`)
Contains concrete implementations ("adapters") of domain protocols that interface with external tools, APIs, databases, files, or subprocesses.

* **Rules:**
  * Implements domain `Protocol`s.
  * Translates external errors (e.g. `HTTPStatusError`, `CalledProcessError`) into domain/application exceptions.
  * Does not contain business validation rules.

```python
# infrastructure/clients/http_provider.py
import httpx
from domain.entities import Item
from domain.exceptions import ItemNotFoundError

class HttpItemProvider:
    """Concrete adapter satisfying domain.protocols.ItemProvider."""
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url
        self._timeout = timeout

    def fetch_item(self, item_id: str) -> Item:
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(f"{self._base_url}/items/{item_id}")
                resp.raise_for_status()
                data = resp.json()
                return Item(id=data["id"], title=data["title"])
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ItemNotFoundError(f"Item {item_id} not found upstream.") from exc
            raise
```

---

### Layer 4: Presentation / Interface (`interface/` or `cli.py`)
Entry points that accept external inputs, parse CLI arguments, handle terminal output formatting, or serve HTTP endpoints.

* **Rules:**
  * Translates raw user input into application Commands/DTOs.
  * Calls application use cases.
  * Formats application results for human or API consumption (e.g. Rich terminal markup, JSON output).
  * Houses the **Composition Root**.

---

## 3. The Composition Root Pattern

The Composition Root is the single location where concrete infrastructure adapters are instantiated and injected into application use cases.

```python
# interface/cli.py or composition.py
import typer
from rich.console import Console
from infrastructure.clients.http_provider import HttpItemProvider
from infrastructure.storage.console_publisher import ConsoleResultPublisher
from application.use_cases.process_item import ProcessItemUseCase, ProcessItemCommand

console = Console()
app = typer.Typer()

def build_process_item_use_case() -> ProcessItemUseCase:
    """Factory wiring dependencies together at startup."""
    provider = HttpItemProvider(base_url="https://api.example.com")
    publisher = ConsoleResultPublisher()
    return ProcessItemUseCase(provider=provider, publisher=publisher)

@app.command()
def process(item_id: str, dry_run: bool = False) -> None:
    use_case = build_process_item_use_case()
    command = ProcessItemCommand(item_id=item_id, dry_run=dry_run)
    result = use_case.execute(command)
    console.print(f"[bold green]Success:[/bold green] {result}")
```

---

## 4. Testing Strategy by Layer

| Layer | Test Type | Speed | Dependencies / Mocks |
| :--- | :--- | :--- | :--- |
| **Domain** | Pure Unit Tests | Instant (<1ms) | No mocks; test pure functions and entity invariants |
| **Application** | Use Case Unit Tests | Fast (~5ms) | In-memory fakes satisfying Domain Protocols (no mock libraries needed) |
| **Infrastructure** | Integration Tests | Slower | Real local filesystem, testcontainers, or wiremock/pytest-recording |
| **Interface / CLI** | End-to-End / CLI Tests | Medium | CliRunner invoking commands with fake or real composition |

### Example: Testing a Use Case with an In-Memory Fake

```python
# tests/unit/test_process_item.py
class FakeItemProvider:
    def __init__(self, items: dict[str, Item]) -> None:
        self.items = items

    def fetch_item(self, item_id: str) -> Item:
        return self.items.get(item_id)

class FakeResultPublisher:
    def __init__(self) -> None:
        self.published = []

    def publish(self, result: ProcessingResult) -> None:
        self.published.append(result)

def test_process_item_success():
    provider = FakeItemProvider({"123": Item(id="123", title="Test")})
    publisher = FakeResultPublisher()
    use_case = ProcessItemUseCase(provider=provider, publisher=publisher)

    result = use_case.execute(ProcessItemCommand(item_id="123"))

    assert result.is_successful
    assert len(publisher.published) == 1
```

---

## 5. Step-by-Step Recipe: Adding a New Feature

When adding a feature to a Clean Architecture codebase, work from the inside out:

1. **Domain:** Define the core entity or value object, domain exceptions, and required port `Protocol`s in `domain/`.
2. **Application:** Write the use case interactor in `application/use_cases/`, accepting the `Protocol` in `__init__`.
3. **Unit Test:** Test the use case in `tests/unit/` using an in-memory fake implementing the `Protocol`.
4. **Infrastructure:** Implement the real external adapter in `infrastructure/` satisfying the `Protocol`.
5. **Presentation:** Wire the adapter into the use case within the composition root and expose the command/endpoint in `interface/`.
