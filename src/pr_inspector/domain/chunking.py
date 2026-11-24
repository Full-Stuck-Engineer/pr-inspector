"""Token-budgeted batching of file diffs for LLM review."""

import math
from dataclasses import replace

from pr_inspector.domain.entities import DiffHunk, FileDiff

# Source code tokenizes to roughly 3-4 characters per token. The low end is used so the
# estimate errs towards overshooting the real count and batches stay under the ceiling.
CHARS_PER_TOKEN = 3


def estimate_tokens(text: str) -> int:
    """Estimate the token count of ``text`` without depending on a model tokenizer."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def _diff_tokens(file_diff: FileDiff) -> int:
    return estimate_tokens(file_diff.annotated_diff_text)


def _split_by_hunks(file_diff: FileDiff, max_tokens: int) -> list[FileDiff]:
    """Split one oversized file into parts made of whole hunks.

    A hunk is never cut: its annotated lines carry exact line numbers, and a hunk header
    that disagrees with its body would mislead the model. A single hunk larger than the
    ceiling therefore becomes a part of its own.
    """
    parts: list[FileDiff] = []
    current: list[DiffHunk] = []
    for hunk in file_diff.hunks:
        candidate = [*current, hunk]
        if current and _diff_tokens(replace(file_diff, hunks=candidate)) > max_tokens:
            parts.append(replace(file_diff, hunks=current))
            current = [hunk]
        else:
            current = candidate
    if current:
        parts.append(replace(file_diff, hunks=current))
    return parts


def split_into_batches(diffs: list[FileDiff], max_tokens: int) -> list[list[FileDiff]]:
    """Pack file diffs, in order, into batches that stay under ``max_tokens``.

    Files without hunks (pure renames, mode changes) carry nothing to review and are
    dropped. A file that does not fit a batch on its own is split at hunk boundaries.
    """
    if max_tokens < 1:
        raise ValueError("max_tokens must be at least 1")

    batches: list[list[FileDiff]] = []
    current: list[FileDiff] = []
    current_tokens = 0

    for file_diff in diffs:
        if not file_diff.hunks:
            continue

        tokens = _diff_tokens(file_diff)
        if tokens <= max_tokens:
            units = [(file_diff, tokens)]
        else:
            units = [(part, _diff_tokens(part)) for part in _split_by_hunks(file_diff, max_tokens)]

        for unit, unit_tokens in units:
            if current and current_tokens + unit_tokens > max_tokens:
                batches.append(current)
                current, current_tokens = [], 0
            current.append(unit)
            current_tokens += unit_tokens

    if current:
        batches.append(current)
    return batches
