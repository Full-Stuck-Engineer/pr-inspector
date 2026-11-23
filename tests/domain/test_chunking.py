"""Unit tests for token-budgeted diff batching."""

import pytest

from pr_inspector.domain.chunking import (
    CHARS_PER_TOKEN,
    estimate_tokens,
    split_into_batches,
)
from pr_inspector.domain.entities import DiffHunk, DiffLine, FileDiff


def make_hunk(start: int, lines: int = 5, width: int = 40) -> DiffHunk:
    return DiffHunk(
        header=f"@@ -{start},{lines} +{start},{lines} @@",
        old_start=start,
        old_lines=lines,
        new_start=start,
        new_lines=lines,
        lines=[
            DiffLine(line_type="add", content="x" * width, new_line_number=start + offset)
            for offset in range(lines)
        ],
    )


def make_file(path: str, hunks: int = 1, lines: int = 5, **kwargs) -> FileDiff:
    return FileDiff(
        file_path=path,
        hunks=[make_hunk(start=1 + index * 100, lines=lines) for index in range(hunks)],
        **kwargs,
    )


def tokens_of(file_diff: FileDiff) -> int:
    return estimate_tokens(file_diff.annotated_diff_text)


def test_estimate_tokens_rounds_up():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("a" * CHARS_PER_TOKEN) == 1
    assert estimate_tokens("a" * (CHARS_PER_TOKEN + 1)) == 2


def test_small_diff_is_a_single_batch():
    files = [make_file("a.py"), make_file("b.py")]

    batches = split_into_batches(files, max_tokens=10_000)

    assert batches == [files]


def test_files_are_packed_in_order_without_splitting_a_file():
    files = [make_file("a.py"), make_file("b.py"), make_file("c.py")]
    ceiling = tokens_of(files[0]) * 2  # room for two files, not three

    batches = split_into_batches(files, max_tokens=ceiling)

    assert [[f.file_path for f in batch] for batch in batches] == [["a.py", "b.py"], ["c.py"]]


def test_every_batch_respects_the_ceiling():
    # Zero-padded so every file renders to the same size.
    files = [make_file(f"f{index:02d}.py") for index in range(12)]
    ceiling = tokens_of(files[0]) * 3

    batches = split_into_batches(files, max_tokens=ceiling)

    assert len(batches) == 4
    for batch in batches:
        assert sum(tokens_of(f) for f in batch) <= ceiling


def test_oversized_file_is_split_at_hunk_boundaries():
    big = make_file("big.py", hunks=6, is_new=False, old_path="old_big.py")
    one_hunk = tokens_of(make_file("big.py", hunks=1))
    ceiling = one_hunk * 2  # roughly two hunks per part

    batches = split_into_batches([big], max_tokens=ceiling)

    parts = [part for batch in batches for part in batch]
    assert len(parts) > 1
    assert all(part.file_path == "big.py" for part in parts)
    assert all(part.old_path == "old_big.py" for part in parts)
    # Whole hunks, original order, none lost or duplicated: line numbers stay exact.
    assert [h for part in parts for h in part.hunks] == big.hunks
    assert all(tokens_of(part) <= ceiling for part in parts)


def test_single_oversized_hunk_gets_its_own_batch():
    huge = make_file("huge.py", hunks=1, lines=200)
    small = make_file("small.py")
    ceiling = tokens_of(small) * 2
    assert tokens_of(huge) > ceiling

    batches = split_into_batches([small, huge, small], max_tokens=ceiling)

    assert [[f.file_path for f in batch] for batch in batches] == [
        ["small.py"],
        ["huge.py"],
        ["small.py"],
    ]


def test_split_preserves_new_and_deleted_flags():
    added = make_file("new.py", hunks=4, is_new=True)
    ceiling = tokens_of(make_file("new.py", hunks=1)) * 2

    parts = [part for batch in split_into_batches([added], ceiling) for part in batch]

    assert all(part.is_new for part in parts)
    assert all(not part.is_deleted for part in parts)


def test_files_without_hunks_are_dropped():
    renamed = FileDiff(file_path="renamed.py", old_path="old.py")
    real = make_file("real.py")

    assert split_into_batches([renamed, real], max_tokens=10_000) == [[real]]
    assert split_into_batches([renamed], max_tokens=10_000) == []


def test_empty_input_yields_no_batches():
    assert split_into_batches([], max_tokens=100) == []


@pytest.mark.parametrize("bad_ceiling", [0, -5])
def test_non_positive_ceiling_is_rejected(bad_ceiling: int):
    with pytest.raises(ValueError, match="at least 1"):
        split_into_batches([make_file("a.py")], max_tokens=bad_ceiling)
