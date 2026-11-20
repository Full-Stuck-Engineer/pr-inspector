# Architecture & SOLID Coding Rules

All code authored, refactored, or reviewed in this repository must strictly adhere to Clean Architecture boundaries and Pythonic SOLID design principles.

---

## 1. The Clean Architecture Dependency Rule

> **Core Axiom:** Dependencies must point strictly inward. Inner layers know nothing about outer layers.

```
┌────────────────────────────────────────────────────────┐
│  Presentation / Interface (CLI, Web, API)             │
│   ┌──────────────────────────────────────────────────┐ │
│   │  Infrastructure (Adapters, SDKs, Git, HTTP, DB) │ │
│   │   ┌────────────────────────────────────────────┐ │ │
│   │   │  Application (Use Cases, Interactors)      │ │ │
│   │   │   ┌──────────────────────────────────────┐ │ │ │
│   │   │   │  Domain (Entities, Protocols, Logic) │ │ │ │
│   │   │   └──────────────────────────────────────┘ │ │ │
│   │   └────────────────────────────────────────────┘ │ │
│   └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
                    ───► Dependencies Inward
```

### Layer Constraints & Import Matrix

| Layer | Permitted Imports | Strictly Forbidden Imports |
| :--- | :--- | :--- |
| **Domain** (`domain/`) | Python Standard Library, typing, domain models | Application, Infrastructure, Presentation, third-party frameworks/SDKs |
| **Application** (`application/`) | Domain, Python Standard Library | Infrastructure, Presentation, CLI tools, external SDKs |
| **Infrastructure** (`infrastructure/`) | Domain, Application (for DTOs/Protocols), external libraries/SDKs | Presentation |
| **Presentation** (`interface/` or `cli.py`) | Domain, Application, Infrastructure (for Composition Root wiring only) | None |

---

## 2. SOLID Design Guardrails

1. **Single Responsibility Principle (SRP):**
   * A class or module should have one, and only one, reason to change.
   * Separate business orchestration (use cases) from data access (gateways/adapters) and output presentation (formatters/renderers).
   * Avoid "god objects" or omnibus services.

2. **Open/Closed Principle (OCP):**
   * Core use cases must be open for extension, closed for modification.
   * Introduce new behavior by implementing new adapters against existing `Protocol`s, not by adding branching `if/else` ladders inside use cases.

3. **Liskov Substitution Principle (LSP):**
   * Any implementation of a `Protocol` must be fully substitutable for any other without breaking caller assumptions.
   * Never raise `NotImplementedError` for methods declared in a protocol contract.
   * Do not alter return types or violate promised invariants in subclasses or adapters.

4. **Interface Segregation Principle (ISP):**
   * Prefer multiple focused, single-purpose `Protocol`s over large, omnibus interfaces.
   * Clients should not be forced to depend on methods they do not use.

5. **Dependency Inversion Principle (DIP):**
   * High-level modules (Application) must not depend on low-level modules (Infrastructure). Both must depend on abstractions (Protocols in Domain).
   * Use `typing.Protocol` for structural typing and runtime-decoupled contracts.

---

## 3. Implementation Rules

1. **No Direct Instantiation in Use Cases:**
   * Never instantiate external clients (e.g. HTTP clients, subprocess wrappers, SDKs) inside a use case.
   * Pass all dependencies explicitly via the constructor (`__init__`).

2. **Composition Root:**
   * Instantiate and wire dependencies at the entry point of the application (e.g. `cli.py` or a dedicated container/factory).

3. **Pure Domain Models:**
   * Domain models and value objects must be clean data structures (e.g. Pydantic models or dataclasses) without embedded database or network logic.

4. **Testing Isolation:**
   * Domain and Application unit tests must run fully in-memory without network calls, subprocesses, or filesystem writes. Use in-memory fake adapters satisfying the domain `Protocol`s.
