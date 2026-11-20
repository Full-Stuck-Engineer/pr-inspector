---
name: git-workflow
description: Step-by-step GitHub CLI and Git development playbook. Use when creating issues, setting up phase branches, managing the 400-line commit budget, opening pull requests, and performing merges.
---

# Git & GitHub Development Workflow Playbook

This skill provides actionable command-line procedures for executing the project's Issue-Driven Development, permanent phase branching, and atomic commit practices using the GitHub CLI (`gh`) and `git`.

---

## 1. Issue-Driven Development: Creating Issues

Always start by creating an issue before writing any code.

### Command
```bash
gh issue create \
  --title "[<Phase>] <Short Description>" \
  --body "## Objective
<1-2 sentences on what this issue accomplishes>

## Scope & Tasks
- [ ] Task 1
- [ ] Task 2
- [ ] Unit & integration tests

## Acceptance Criteria
- [ ] Passes ruff lint and format check
- [ ] Tests pass via pytest
- [ ] Less than 400 lines of code changed per commit"
```

### Example
```bash
gh issue create \
  --title "[Phase 1] Implement Core Domain Entities & Git Diff Protocols" \
  --body "## Objective
Define the pure domain models and port protocols for PR review results and git diff extraction.

## Scope & Tasks
- [ ] Create domain entities (PRReviewResult, ReviewIssue, RiskLevel)
- [ ] Define DiffProvider and LLMReviewer protocols
- [ ] Add unit tests for entity validation

## Acceptance Criteria
- [ ] Clean Architecture: Domain has 0 external dependencies
- [ ] uv run pytest passes
- [ ] uv run ruff check passes"
```

Record the generated issue number (e.g. `#1`).

---

## 2. Permanent Phase & Feature Branch Management

The 4 milestone branches are:
1. `phase/01-diff-cli`
2. `phase/02-codebase-rag`
3. `phase/03-agent-evals`
4. `phase/04-production`

### Step 2.1: Initialize Permanent Phase Branch (Once per phase)
When starting a new phase, branch off `main` and push to remote:
```bash
# Check out main and ensure up-to-date
git checkout main
git pull origin main

# Create and push permanent phase branch
git checkout -b phase/01-diff-cli main
git push -u origin phase/01-diff-cli
```

### Step 2.2: Create Feature / Issue Branch
Every issue gets its own feature branch created off the active phase branch:
```bash
# Branch name format: issue-<number>-<short-description>
git checkout -b issue-1-domain-diff-protocols phase/01-diff-cli
```

---

## 3. Auditing the 400-Line Commit Budget

Before committing, verify that the total lines of code changed are **under 400 lines**.

### Audit Command
```bash
# Check summary of changes
git diff --stat

# Exclude uv.lock or fixtures from the count:
git diff --stat -- . ':(exclude)uv.lock' ':(exclude)*.json'
```

If the lines added/modified exceed 400 lines, **split the changes into atomic commits** using targeted `git add <path>`:
1. First commit: Domain models & Protocols.
2. Second commit: Implementation / Adapters.
3. Third commit: Tests.

---

## 4. Conventional Commits (When Explicitly Requested)

> **Reminder:** Never run `git commit` unless the user explicitly asks to commit.

### Format
```bash
git add <selected_files>
git commit -m "<type>(<scope>): <subject> (refs #<issue_number>)"
```

### Examples
```bash
# Domain entities
git add src/pr_inspector/domain/
git commit -m "feat(domain): define review result entities and diff protocols (refs #1)"

# Unit tests
git add tests/domain/
git commit -m "test(domain): add validation tests for review models (refs #1)"
```

---

## 5. Opening Pull Requests

Once the feature branch is ready and tested, open a Pull Request targeting the active phase branch.

### Command
```bash
# Push branch to remote
git push -u origin HEAD

# Create Pull Request targeting the active phase branch
gh pr create \
  --base phase/01-diff-cli \
  --title "[Phase 1] Implement Core Domain Entities & Git Diff Protocols" \
  --body "## Summary
Brief description of the changes made.

## Closes
Closes #1

## Verification
- [x] uv run pytest
- [x] uv run ruff check .
- [x] Commit diff <= 400 lines"
```

---

## 6. Reviewing and Merging Pull Requests

### Inspect PR Diff
```bash
gh pr diff <pr_number>
```

### Dogfooding `pr-inspector` (Phase 1+)
Once `pr-inspector` is built, run it against the feature branch:
```bash
uv run pr-inspector review --target-ref phase/01-diff-cli
```

### Merging Feature PR into Phase Branch
```bash
gh pr merge <pr_number> --squash --delete-branch
```

*Note: The feature branch is deleted upon merge, but the **`phase/01-diff-cli` branch remains permanently active on remote**.*

---

## 7. Milestone Merge: Phase Completion

When all issues for a phase are merged into the phase branch:
1. Open a Milestone PR from `phase/0X-...` into `main`:
   ```bash
   gh pr create --base main --head phase/01-diff-cli --title "Milestone: Complete Phase 1 - Automated PR Review CLI"
   ```
2. Merge the Milestone PR into `main`.
3. **DO NOT delete `phase/0X-...`**. Ensure the branch remains permanently on GitHub as an educational snapshot.
