# Git & GitHub Development Workflow Rules

All development work, branch management, commit practices, and pull requests in this repository must strictly adhere to the following rules.

---

## 1. Issue-Driven Development (Issue First)

> **No code is written without an issue.**

* **Before any implementation begins:** A GitHub issue must exist describing the objective, context, and clear acceptance criteria.
* If a task originates from a roadmap (e.g. Trello card), the GitHub issue must reference that milestone or task description.
* Every commit message should reference the issue (`refs #<issue_number>`).
* Every Pull Request must link and close the issue (`Closes #<issue_number>`).

---

## 2. Permanent Phase Branching

> **Every phase has a dedicated, permanent branch for educational and reference purposes.**

* The project evolves across 4 phases: `phase-1`, `phase-2`, `phase-3`, and `phase-4`.
* **Branch Lifecycles:**
  * When starting work on a phase, create a permanent branch from `main`:
    ```bash
    git checkout -b phase-1 main
    git push -u origin phase-1
    ```
  * Individual feature/issue branches branch off the active phase branch:
    ```bash
    git checkout -b issue-1-diff-extractor phase-1
    ```
  * Pull Requests for individual issues target the phase branch:
    ```bash
    gh pr create --base phase-1
    ```
  * When an entire phase is complete, a milestone PR merges `phase-N` into `main`.
  * **Critical:** The `phase-N` branch is **never deleted**. It remains permanently on the remote so anyone can checkout that specific phase snapshot (`git checkout phase-1`).

---

## 3. Strict Commit Budget: Maximum 400 Lines

> **Keep diffs small, focused, and reviewable.**

* **The Rule:** Each commit must not exceed **400 lines of code changed** (sum of added and modified lines).
* **Why:** Studies show review accuracy degrades rapidly beyond 400 lines. Furthermore, small diffs allow `pr-inspector` to dogfood and review its own commits effectively.
* **Exclusions:**
  * Auto-generated dependency lockfiles (e.g., `uv.lock`, `package-lock.json`).
  * Raw benchmark datasets or synthetic golden test fixtures.
* **Enforcement:** If a feature requires more than 400 lines, decompose it into atomic commits:
  1. Commit 1: Domain models & interfaces (Protocols)
  2. Commit 2: Core application use cases / business logic
  3. Commit 3: Infrastructure adapter implementations
  4. Commit 4: Tests and CLI wiring

---

## 4. Conventional Commits Standard

All commit messages must follow the Conventional Commits specification:

```text
<type>(<scope>): <subject> (refs #<issue_number>)

[optional body]
```

### Allowed Types
* `feat`: A new feature or capability.
* `fix`: A bug fix.
* `docs`: Documentation updates only.
* `test`: Adding or modifying tests without application code changes.
* `refactor`: Code restructuring without functional behavior changes.
* `chore`: Dependency updates, tooling, or build configuration.

### Examples
* `feat(domain): define review result entity and diff protocols (refs #1)`
* `feat(git): implement git diff extractor adapter (refs #1)`
* `test(git): add unit tests for git diff line annotation (refs #1)`

---

## 5. Explicit User Approval for Commits (Non-Negotiable)

> **NEVER execute `git commit` unless the user explicitly requests it.**

* The assistant must **never** make automatic, speculative, or unprompted git commits.
* Staging (`git add`) and committing (`git commit`) are strictly performed only when the user explicitly says: *"make commit"*, *"commit this"*, or provides an explicit commit instruction.
