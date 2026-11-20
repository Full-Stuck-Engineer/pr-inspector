---
name: solid-principles
description: Practical, Pythonic guide to SOLID principles. Use when designing classes, modules, and interfaces, refactoring coupled code, or reviewing code against Pythonic SOLID best practices.
---

# Practical & Pythonic SOLID Guide

This skill provides an actionable, modern Python implementation guide for the SOLID design principles. Rather than relying on heavyweight classical OOP hierarchies and bloated Abstract Base Classes (ABCs), this guide leverages modern Python idioms: `typing.Protocol` (structural subtyping), dataclasses/Pydantic, composition over inheritance, and clean dependency injection.

---

## The 5 Principles at a Glance

| Principle | Core Idea in Modern Python | Key Mechanism / Idiom |
| :--- | :--- | :--- |
| **S**RP | A class or module should have one reason to change | Separate data models, orchestration, and I/O |
| **O**CP | Open for extension, closed for modification | Pluggable strategies via `Protocol` contracts |
| **L**SP | Implementations must be swappable without breaking callers | Consistent signatures, exceptions, and return types |
| **I**SP | Clients should not depend on methods they don't use | Fine-grained, single-purpose `Protocol`s |
| **D**IP | High-level logic depends on abstractions, not concretions | Constructor injection using `typing.Protocol` |

---

## 1. Single Responsibility Principle (SRP)

> **"Gather together the things that change for the same reasons. Separate those that change for different reasons."**

### Python Anti-Pattern: The Omnibus "God Object"
```python
# BAD: Mixes parsing, business rules, external network calls, and terminal formatting
class PRReviewer:
    def execute(self, repo_path: str):
        # 1. Runs git subprocess
        diff = subprocess.check_output(["git", "diff"], cwd=repo_path)
        # 2. Formats prompt and calls OpenAI SDK directly
        client = openai.OpenAI()
        resp = client.chat.completions.create(...)
        # 3. Formats console output with color codes
        print(f"\033[92mReview: {resp.choices[0].message.content}\033[0m")
```

### Pythonic Solution: Separation of Concerns
Split into single-purpose components:
1. `GitDiffExtractor`: Responsible solely for extracting and parsing diff text.
2. `LLMAnalyzer`: Responsible solely for communicating with the language model.
3. `PRReviewUseCase`: Orchestrates the flow between extractor and analyzer.
4. `CLIFormatter`: Formats the resulting domain model into terminal/rich output.

---

## 2. Open/Closed Principle (OCP)

> **"Software entities should be open for extension, but closed for modification."**

### Python Anti-Pattern: The `isinstance` / `type` Branching Ladder
```python
# BAD: Modifying this function every time a new provider is added
class ModelRunner:
    def run_prompt(self, provider: str, prompt: str):
        if provider == "openai":
            return self._call_openai(prompt)
        elif provider == "ollama":
            return self._call_ollama(prompt)
        elif provider == "gemini":
            return self._call_gemini(prompt)
        raise ValueError(f"Unknown provider: {provider}")
```

### Pythonic Solution: Strategy Pattern via `Protocol`
Define the contract once; extend by creating new adapter classes without altering existing runner code:
```python
from typing import Protocol

class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str:
        ...

# Open for extension: add new classes without touching existing use cases
class OpenAIProvider:
    def complete(self, prompt: str) -> str:
        # implementation
        ...

class OllamaProvider:
    def complete(self, prompt: str) -> str:
        # implementation
        ...

class ModelRunner:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def run_prompt(self, prompt: str) -> str:
        return self._provider.complete(prompt)
```

---

## 3. Liskov Substitution Principle (LSP)

> **"Subtypes must be substitutable for their base types without altering program correctness."**

### Python Anti-Patterns:
1. **Raising `NotImplementedError`:** An adapter implements an interface but raises an error on a method it cannot support.
2. **Changing return types or shapes:** Returning `None` instead of the expected entity, or returning a completely different dictionary structure.
3. **Leaking provider-specific exceptions:** Raising `openai.RateLimitError` directly into a use case that expects a generic `ProviderUnavailableError`.

### Pythonic Solution:
* Ensure all adapters normalize external exceptions into domain-level exceptions.
* Adhere strictly to the method signatures and return types defined in the `Protocol`.

```python
from domain.exceptions import ProviderConnectionError

class ThirdPartyAdapter:
    def fetch(self, resource_id: str) -> Resource:
        try:
            raw = self._client.get(resource_id)
            return Resource(id=raw["id"], data=raw["payload"])
        except ExternalVendorTimeout as exc:
            # Normalize to domain exception to preserve LSP
            raise ProviderConnectionError(f"Failed to fetch {resource_id}") from exc
```

---

## 4. Interface Segregation Principle (ISP)

> **"Clients should not be forced to depend upon interfaces that they do not use."**

### Python Anti-Pattern: Fat Abstract Base Classes
```python
# BAD: A single giant interface forcing all adapters to implement everything
from abc import ABC, abstractmethod

class Repository(ABC):
    @abstractmethod
    def read(self, id: str): ...
    @abstractmethod
    def write(self, item): ...
    @abstractmethod
    def delete(self, id: str): ...
    @abstractmethod
    def export_csv(self): ...
    @abstractmethod
    def purge_cache(self): ...
```

### Pythonic Solution: Small, Composable Protocols
In Python, prefer small, 1-2 method `Protocol`s (following the Unix philosophy). Compose them when a caller requires multiple capabilities:

```python
from typing import Protocol

class ItemReader(Protocol):
    def get_by_id(self, item_id: str) -> Item | None:
        ...

class ItemWriter(Protocol):
    def save(self, item: Item) -> None:
        ...

# A use case that only reads only needs ItemReader
class GetItemUseCase:
    def __init__(self, reader: ItemReader) -> None:
        self._reader = reader

# A use case that needs both can combine them
class SyncItemUseCase:
    def __init__(self, reader: ItemReader, writer: ItemWriter) -> None:
        self._reader = reader
        self._writer = writer
```

---

## 5. Dependency Inversion Principle (DIP)

> **"High-level modules should not depend on low-level modules. Both should depend on abstractions."**

### Python Anti-Pattern: Hardcoded Concretions
```python
# BAD: High-level business logic is directly coupled to a concrete SDK
import requests

class ProcessPaymentUseCase:
    def execute(self, amount: float):
        # Hardcoded low-level dependency
        resp = requests.post("https://stripe.com/api", json={"amount": amount})
        return resp.json()
```

### Pythonic Solution: Inversion via `typing.Protocol` + Constructor Injection
1. Define the abstraction (the Port) inside the domain or application layer.
2. High-level use cases accept the abstraction via `__init__`.
3. Low-level adapters implement the abstraction.

```python
# 1. Abstraction in Domain / Application
from typing import Protocol

class PaymentGateway(Protocol):
    def charge(self, amount_cents: int) -> str:
        ...

# 2. High-level Use Case depends on the abstraction
class ProcessPaymentUseCase:
    def __init__(self, gateway: PaymentGateway) -> None:
        self._gateway = gateway

    def execute(self, amount_cents: int) -> str:
        return self._gateway.charge(amount_cents)

# 3. Low-level Infrastructure Adapter implements the abstraction
class StripePaymentAdapter:
    def charge(self, amount_cents: int) -> str:
        # Concrete stripe SDK calls here
        return "charge_id_123"
```

---

## 6. Code Review Checklist for SOLID Compliance

When writing or reviewing code, check:

- [ ] **SRP:** Does this class or function have more than one reason to change? If you change the database schema, the CLI output, or the business algorithm, does this same file change?
- [ ] **OCP:** Can I add a new provider/engine without modifying existing use case files?
- [ ] **LSP:** Can any adapter satisfying a `Protocol` be swapped in without causing `AttributeError`, unhandled vendor exceptions, or unexpected `None` returns?
- [ ] **ISP:** Are interfaces kept to 1–3 focused methods? Does the client use every method in the `Protocol` it requires?
- [ ] **DIP:** Are dependencies passed into `__init__`, or are concrete classes instantiated inside the function body? Are types annotated with `Protocol`s rather than concrete adapter classes?
